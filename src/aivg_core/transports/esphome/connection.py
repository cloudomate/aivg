"""One-task-per-device connection driver for the ESPHome transport.

Each accepted TCP connection runs an :class:`EsphomeConnection`
co-routine inside its own :class:`asyncio.Task` (R-2). The task
progresses through ``HANDSHAKING → AUTHING → READY → VOICE_ACTIVE``
states and tears down cleanly on disconnect.

Reuses the existing :class:`aivg_core.webrtc.session.Session` via the
:class:`EsphomeMediaTransport` adapter (R-3) so the per-turn state
machine is shared across transports.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from enum import Enum
from typing import TYPE_CHECKING, Optional

import aioesphomeapi.api_pb2 as pb

from ...logsink import LogSink
from ...models import (
    AdoptionState,
    ClientStatus,
    LogLevel,
    LogSource,
    VoiceSession,
)
from ...webrtc.session import Session
from .auth import KeystoreResolver, verify
from .framing import encode_message, FramingError, read_next_message
from .media_adapter import EsphomeMediaTransport
from .voice_protocol import (
    Event,
    make_device_info_response,
    make_hello_response,
    make_voice_assistant_audio,
    make_voice_assistant_configuration_response,
    make_voice_assistant_event_response,
    make_voice_assistant_response,
)

if TYPE_CHECKING:
    from ...platforms.base import AgentPlatform
    from ...registry import Registry

_LOG = logging.getLogger(__name__)

# Per-frame outbound chunk size: write one VoiceAssistantAudio
# message per 20 ms of audio. Matches what HA's voice satellite
# implementations use.
_OUTBOUND_CHUNK_MS = 20


class ConnState(Enum):
    HANDSHAKING = "handshaking"
    AUTHING = "authing"
    READY = "ready"
    VOICE_ACTIVE = "voice_active"
    CLOSING = "closing"
    CLOSED = "closed"


class EsphomeConnection:
    """One connected ESPHome device. Owns the socket, the framing
    state, the auth state, and at most one in-flight
    :class:`Session`."""

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        *,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: LogSink,
        keystore: KeystoreResolver,
        bootstrap_key: Optional[str],
        ui_broadcast=None,
        # Feature 017 client-mode: when ``direction="client"``, this
        # connection is the dialer side. AIVG sent the HelloRequest
        # outbound; the *device* listens on port 6053. The opposite
        # direction (``direction="server"``) accepts incoming peers
        # (e.g., OHF-Voice's linux-voice-assistant or a future
        # Linux-side satellite). The wire protocol is symmetric
        # post-auth; only the handshake direction differs.
        direction: str = "server",
        # Client mode requires the device's identity + key up-front
        # (we KNOW which device we're dialing). Ignored in server mode.
        device_id_override: Optional[str] = None,
        api_key_override: Optional[str] = None,
    ) -> None:
        self._reader = reader
        self._writer = writer
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._keystore = keystore
        self._bootstrap_key = bootstrap_key
        self._ui_broadcast = ui_broadcast
        self._direction = direction
        self._device_id_override = device_id_override
        self._api_key_override = api_key_override

        self.state = ConnState.HANDSHAKING
        self.device_id: Optional[str] = None
        self.device_info: dict = {}

        self._media_adapter: Optional[EsphomeMediaTransport] = None
        self._session: Optional[Session] = None
        self._session_task: Optional[asyncio.Task] = None
        self._outbound_writer_task: Optional[asyncio.Task] = None

    # --- entry point --------------------------------------------------

    async def run(self) -> None:
        """Main per-task co-routine. Handles the connection's full
        lifecycle. Idempotent re: errors — every path lands in
        :meth:`_close`."""
        peer = self._writer.get_extra_info("peername") or "?"
        try:
            await self._handshake()
            await self._authenticate()
            await self._serve_voice()
        except (asyncio.IncompleteReadError, ConnectionError):
            _LOG.debug("esphome: peer %s disconnected", peer)
        except FramingError as exc:
            _LOG.info("esphome: framing error from %s: %s", peer, exc)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - never crash the listener
            _LOG.exception("esphome: unhandled connection error from %s", peer)
        finally:
            await self._close()

    # --- internal phases ---------------------------------------------

    async def _send(self, msg) -> None:
        """Serialize + write one protobuf message to the socket."""
        self._writer.write(encode_message(msg))
        await self._writer.drain()

    async def _recv(self):
        """Read one protobuf message. Returns ``(opcode, message)``."""
        return await read_next_message(self._reader)

    async def _handshake(self) -> None:
        """Initial Hello exchange. Direction-aware: in server mode we
        receive HelloRequest then send HelloResponse; in client mode
        we send HelloRequest first then read the device's
        HelloResponse."""
        if self._direction == "client":
            # We are dialing a device. Send HelloRequest first.
            self.device_id = self._device_id_override or f"aivg-{uuid.uuid4().hex[:8]}"
            await self._send(pb.HelloRequest(
                client_info="aivg-gateway",
                api_version_major=1,
                api_version_minor=10,
            ))
            opcode, msg = await self._recv()
            if not isinstance(msg, pb.HelloResponse):
                raise FramingError(
                    f"client-mode expected HelloResponse from device, got opcode {opcode}"
                )
            self.device_info["server_info"] = msg.server_info
            self.device_info["api_version_major"] = msg.api_version_major
            self.device_info["api_version_minor"] = msg.api_version_minor
        else:
            # Server mode: receive HelloRequest, reply HelloResponse.
            opcode, msg = await self._recv()
            if not isinstance(msg, pb.HelloRequest):
                raise FramingError(f"expected HelloRequest, got opcode {opcode}")
            # The client_info field carries the device's identity
            # (typically the ESPHome device's `name` config field).
            self.device_id = (msg.client_info or "").strip() or f"unknown-{uuid.uuid4().hex[:8]}"
            self.device_info["client_info"] = msg.client_info
            self.device_info["api_version_major"] = msg.api_version_major
            self.device_info["api_version_minor"] = msg.api_version_minor
            await self._send(make_hello_response())
        self.state = ConnState.AUTHING

    async def _authenticate(self) -> None:
        """Auth phase. In server mode we receive a ConnectRequest /
        AuthenticationRequest with the device's password and verify
        it against our keystore. In client mode we send ConnectRequest
        carrying the per-device api_key (which we already know — we
        looked it up before dialing) and verify the device's
        ConnectResponse.invalid_password is False.

        After successful auth (either direction), the device appears
        in the registry tagged as ``transport='esphome_api'``."""
        if self._direction == "client":
            # We dialed the device. We KNOW the api_key for the device
            # we picked from the dialer's config.
            api_key = self._api_key_override or ""
            await self._send(pb.ConnectRequest(password=api_key))
            opcode, msg = await self._recv()
            if not isinstance(msg, pb.ConnectResponse):
                raise FramingError(
                    f"client-mode expected ConnectResponse, got opcode {opcode}"
                )
            if msg.invalid_password:
                self._log(
                    LogLevel.WARN,
                    f"esphome client-mode: auth rejected by device "
                    f"{self.device_id!r}",
                )
                raise FramingError("device rejected our api_key")
        else:
            opcode, msg = await self._recv()
            presented = ""
            if isinstance(msg, pb.ConnectRequest):
                presented = msg.password
            elif isinstance(msg, pb.AuthenticationRequest):
                presented = msg.password
            else:
                raise FramingError(
                    f"expected ConnectRequest/AuthenticationRequest, got opcode {opcode}"
                )

            expected = await self._keystore.resolve(self.device_id or "")
            if not verify(presented, expected, bootstrap_key=self._bootstrap_key):
                if isinstance(msg, pb.ConnectRequest):
                    await self._send(pb.ConnectResponse(invalid_password=True))
                else:
                    await self._send(pb.AuthenticationResponse(invalid_password=True))
                self._log(
                    LogLevel.INFO,
                    f"esphome: auth_failed device_id={self.device_id!r}",
                )
                raise FramingError("auth failed")
            if isinstance(msg, pb.ConnectRequest):
                await self._send(pb.ConnectResponse(invalid_password=False))
            else:
                await self._send(pb.AuthenticationResponse(invalid_password=False))

        # Register the device with the existing AIVG registry, tagging
        # the transport. Same step for both directions — auth succeeded.
        client = self._registry.register(
            device_id=self.device_id,  # type: ignore[arg-type]
            device_type="esphome",
            firmware_version=str(self.device_info.get("api_version_major", "")),
        )
        client.transport = "esphome_api"
        client.status = ClientStatus.ONLINE
        client.adoption_state = AdoptionState.ADOPTED
        client.touch()
        self._log(LogLevel.INFO, f"esphome: device_adopted device_id={self.device_id!r}")

        # Client mode: we MUST subscribe to voice-assistant pipelines
        # or the device won't push wake-word events to us. In server
        # mode, the device does this for us.
        if self._direction == "client":
            await self._send(pb.SubscribeVoiceAssistantRequest(subscribe=True))

        self.state = ConnState.READY

    async def _serve_voice(self) -> None:
        """Main message dispatch loop. Handles ping/keepalive, voice-
        pipeline lifecycle, audio frames. Runs until the peer
        disconnects."""
        while self.state in (ConnState.READY, ConnState.VOICE_ACTIVE):
            opcode, msg = await self._recv()

            if msg is None:
                # Unknown opcode — silently drop per spec edge-case.
                _LOG.debug("esphome: unknown opcode %d dropped", opcode)
                continue

            if isinstance(msg, pb.PingRequest):
                await self._send(pb.PingResponse())
                continue
            if isinstance(msg, pb.DeviceInfoRequest):
                await self._send(make_device_info_response())
                continue
            if isinstance(msg, pb.ListEntitiesRequest):
                await self._send(pb.ListEntitiesDoneResponse())
                continue
            if isinstance(msg, pb.SubscribeStatesRequest):
                # We expose no entities; ignore the subscribe.
                continue
            if isinstance(msg, pb.DisconnectRequest):
                await self._send(pb.DisconnectResponse())
                return  # graceful close
            if isinstance(msg, pb.SubscribeVoiceAssistantRequest):
                # Device asks to subscribe to voice-assistant pipelines.
                # No response is sent here — the contract is "ack by
                # accepting the next VoiceAssistantRequest(start=True)".
                continue
            if isinstance(msg, pb.VoiceAssistantConfigurationRequest):
                await self._send(make_voice_assistant_configuration_response())
                continue
            if isinstance(msg, pb.VoiceAssistantRequest):
                if msg.start:
                    await self._start_voice_pipeline(msg)
                else:
                    await self._stop_voice_pipeline()
                continue
            if isinstance(msg, pb.VoiceAssistantAudio):
                await self._on_voice_audio(msg)
                continue
            if isinstance(msg, pb.VoiceAssistantEventResponse):
                # Device-side lifecycle event (WAKE_WORD_START etc.).
                # Logged but not used to drive state — server-side
                # endpointing is authoritative (R-4 / Principle I).
                _LOG.debug("esphome: device event_type=%d", msg.event_type)
                continue

            # Anything else — silently drop.
            _LOG.debug("esphome: ignoring message %s", type(msg).__name__)

    # --- voice-pipeline lifecycle ------------------------------------

    async def _start_voice_pipeline(self, req: pb.VoiceAssistantRequest) -> None:
        """Device asked us to begin a voice pipeline. Construct a
        :class:`Session` against an :class:`EsphomeMediaTransport`
        adapter and run it on a background task."""
        if self._session is not None:
            # Single-turn-per-device invariant: a new pipeline-start
            # mid-pipeline cancels the prior one (matches HA's behaviour).
            await self._stop_voice_pipeline()

        await self._send(make_voice_assistant_response(port=0, error=False))
        await self._send(
            make_voice_assistant_event_response(Event.RUN_START)
        )

        # Build a fresh Session for this turn.
        session_id = uuid.uuid4().hex
        model = VoiceSession(
            session_id=session_id, device_id=self.device_id or "?",
        )
        model.transport = "esphome_api"

        media = EsphomeMediaTransport(self)
        self._media_adapter = media
        # Construct the Session with the EsphomeMediaTransport in the
        # MediaTransport slot. Session sees an AgentPlatform identically
        # to the WebRTC path.
        sess = Session(model, media, self._platform, self._sink, ui_sink=self._ui_sink)
        self._session = sess
        # Tell the device we're now listening.
        await self._send(
            make_voice_assistant_event_response(Event.STT_START)
        )

        # Spawn Session.run() and the outbound-audio writer.
        self._session_task = asyncio.create_task(sess.run())
        self._outbound_writer_task = asyncio.create_task(self._pump_outbound())

        # Watch the session for completion so we can emit RUN_END.
        asyncio.create_task(self._on_session_done(sess))

        self.state = ConnState.VOICE_ACTIVE

    def _ui_sink(self, evt: dict) -> None:
        """Forward call-scoped UI events to the management plane
        broadcaster (if wired)."""
        if self._ui_broadcast is None:
            return
        try:
            self._ui_broadcast({**evt, "device_id": self.device_id})
        except Exception:  # noqa: BLE001 - UI fan-out must never break voice
            pass

    async def _pump_outbound(self) -> None:
        """Pull resampled 16 kHz chunks from the media adapter and
        wrap each in a ``VoiceAssistantAudio`` message. Runs until
        the adapter returns ``None`` (close signal)."""
        media = self._media_adapter
        if media is None:
            return
        try:
            while True:
                chunk = await media.drain_outbound()
                if chunk is None:
                    return
                if chunk:
                    await self._send(make_voice_assistant_audio(chunk))
        except (ConnectionError, asyncio.CancelledError):
            raise
        except Exception:  # noqa: BLE001
            _LOG.exception("esphome: outbound writer crashed")

    async def _on_voice_audio(self, msg: pb.VoiceAssistantAudio) -> None:
        """Device → us: inbound audio frame. Push into the media
        adapter (which resamples + reframes to 48 kHz / 20 ms)."""
        if self._media_adapter is None:
            return  # not in a pipeline
        if msg.data:
            self._media_adapter.push_inbound(msg.data)
        if msg.end:
            # Device signalled end-of-audio — flush the reframer
            # (server-side endpoint detector is still authoritative;
            # this is just a graceful EOF hint).
            self._media_adapter.push_eof()

    async def _on_session_done(self, sess: Session) -> None:
        """Wait for Session.run() to complete, then emit RUN_END and
        clean up. Called once per pipeline start."""
        try:
            await self._session_task  # type: ignore[arg-type]
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        try:
            await self._send(
                make_voice_assistant_event_response(Event.TTS_END)
            )
            await self._send(
                make_voice_assistant_event_response(Event.RUN_END)
            )
        except (ConnectionError, OSError):
            pass
        # Tear down adapter / writer.
        if self._media_adapter is not None:
            await self._media_adapter.close()
        if self._outbound_writer_task is not None:
            self._outbound_writer_task.cancel()
            try:
                await self._outbound_writer_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._session = None
        self._media_adapter = None
        self._session_task = None
        self._outbound_writer_task = None
        if self.state == ConnState.VOICE_ACTIVE:
            self.state = ConnState.READY

    async def _stop_voice_pipeline(self) -> None:
        """Cancel an in-flight pipeline (caller-initiated)."""
        if self._session_task is not None and not self._session_task.done():
            self._session_task.cancel()
            try:
                await self._session_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    # --- close --------------------------------------------------------

    async def _close(self) -> None:
        """Idempotent cleanup. Cancels in-flight session, removes the
        device from the registry's online set, closes the socket."""
        if self.state == ConnState.CLOSED:
            return
        self.state = ConnState.CLOSING
        await self._stop_voice_pipeline()
        if self._media_adapter is not None:
            await self._media_adapter.close()
        if self._outbound_writer_task is not None:
            self._outbound_writer_task.cancel()
        # Mark the device offline in the registry. We do NOT remove
        # the registry entry — the device's adoption persists across
        # reconnects (matches WebRTC behaviour).
        if self.device_id:
            client = self._registry.get_client(self.device_id)
            if client is not None:
                client.status = ClientStatus.OFFLINE
                client.touch()
        try:
            self._writer.close()
            await self._writer.wait_closed()
        except (ConnectionError, OSError):
            pass
        self.state = ConnState.CLOSED

    # --- logging helper ----------------------------------------------

    def _log(self, level: LogLevel, message: str, **meta) -> None:
        try:
            self._sink.emit(
                self.device_id or "?",
                level,
                LogSource.SYSTEM,  # NOTE: existing LogSource enum has no "esphome" yet
                message,
                {**meta, "transport": "esphome_api"} if meta else {"transport": "esphome_api"},
            )
        except Exception:  # noqa: BLE001 - logging must never break voice
            pass
