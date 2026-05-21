"""Refactored client-mode dialer using ``aioesphomeapi.APIClient``
directly (feature 017 / post-MVP).

The original :mod:`.dialer` + :mod:`.connection` + :mod:`.noise_handshake`
client-mode path hand-rolled the entire ESPHome native API — TCP
options, noise handshake, framing, reconnect, voice-pipeline events.
A subtle noise-cipher-state drift in the home-rolled implementation
caused modern ESPHome firmware (verified against 2026.5.0) to RST our
post-handshake messages even though both the handshake itself and the
encryption math were byte-identical to upstream.

Rather than chase that bug, this module **delegates the entire
client-side wire surface to** :mod:`aioesphomeapi` (the same library
Home Assistant uses, ~30+ versions of battle-testing). AIVG keeps
ownership of: the AgentPlatform plumbing, the per-device task
lifecycle, the registry / management-plane discriminator, the
MediaTransport adapter. The ESPHome wire details (Noise, framing,
reconnect, version-skew) become an external dep concern.

This is the **strict** v1.1 client-mode path. Server mode
(:class:`EsphomeTransport` accepting inbound connections) keeps the
home-rolled plaintext framing in :mod:`.framing` + :mod:`.connection`
because that path is verified end-to-end (T024 integration test) and
plaintext server-side doesn't have the noise complications.
"""

from __future__ import annotations

import asyncio
import logging
import random
import uuid
from typing import TYPE_CHECKING, Any, Callable, Optional

from aioesphomeapi import (
    APIClient,
    InvalidAuthAPIError,
    InvalidEncryptionKeyAPIError,
    ReconnectLogic,
    ResolveAPIError,
    VoiceAssistantEventType,
)

from ...logsink import LogSink
from ...models import (
    AdoptionState,
    ClientStatus,
    LogLevel,
    LogSource,
    VoiceSession,
)
from ...webrtc.session import Session
from .media_adapter import EsphomeMediaTransport

if TYPE_CHECKING:
    from ...platforms.base import AgentPlatform
    from ...registry import Registry

_LOG = logging.getLogger(__name__)


class EsphomeApiClientDialer:
    """Per-device dialer driven by :class:`aioesphomeapi.APIClient`.

    For each configured device the dialer:

    1. Constructs an ``APIClient`` (handles TCP + Noise/plaintext +
       framing + protocol-version negotiation entirely upstream).
    2. Connects via :class:`ReconnectLogic` — the lib's
       battle-tested reconnect-with-backoff is BETTER than ours and
       handles ESPHome firmware quirks we'd otherwise re-discover.
    3. Subscribes to voice-assistant pipelines.
    4. Routes audio + lifecycle events into a per-device
       :class:`EsphomeMediaTransport` adapter that drives the
       existing :class:`aivg_core.webrtc.session.Session`.
    5. Registers the device in the AIVG registry with
       ``transport="esphome_api"`` so it shows up in ``aivg list``.

    The constitution-IV invariants (no ``platforms/`` modifications,
    no ``webrtc/session.py`` modifications) remain in force — the
    dialer talks to the AgentPlatform only through Session, never
    directly.
    """

    def __init__(
        self,
        *,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: LogSink,
        devices: list[dict],  # [{host, port, device_id, noise_psk, password?}]
        ui_broadcast: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._devices = devices
        self._ui_broadcast = ui_broadcast
        # One ReconnectLogic instance per device — owns its own
        # connection + reconnect cadence.
        self._reconnects: dict[str, ReconnectLogic] = {}
        self._device_runners: dict[str, "_PerDeviceRunner"] = {}
        self._zeroconf = None
        self._stopped = False

    async def start(self) -> None:
        # ReconnectLogic needs an AsyncZeroconf instance. We construct
        # one in-process (it'll be torn down in stop).
        from zeroconf.asyncio import AsyncZeroconf

        self._zeroconf = AsyncZeroconf()
        for dev in self._devices:
            runner = _PerDeviceRunner(
                dev=dev,
                registry=self._registry,
                platform=self._platform,
                sink=self._sink,
                ui_broadcast=self._ui_broadcast,
                zeroconf=self._zeroconf,
            )
            self._device_runners[runner.device_id] = runner
            await runner.start()
        _LOG.info(
            "esphome: APIClient-based dialer started for %d device(s): %s",
            len(self._devices),
            ", ".join(r.device_id for r in self._device_runners.values()),
        )

    async def stop(self) -> None:
        self._stopped = True
        for runner in list(self._device_runners.values()):
            await runner.stop()
        self._device_runners.clear()
        if self._zeroconf is not None:
            await self._zeroconf.async_close()
            self._zeroconf = None

    @property
    def device_count(self) -> int:
        return sum(1 for r in self._device_runners.values() if r.is_connected)


class _PerDeviceRunner:
    """One device's lifecycle: connect → subscribe → relay voice
    pipeline → disconnect. Per-device task owned by ReconnectLogic."""

    def __init__(
        self,
        *,
        dev: dict,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: LogSink,
        ui_broadcast: Optional[Callable[[dict], None]],
        zeroconf: Any,
    ) -> None:
        self.device_id: str = str(dev["device_id"])
        self._host: str = str(dev["host"])
        self._port: int = int(dev.get("port", 6053))
        self._noise_psk: Optional[str] = dev.get("noise_psk") or None
        self._password: Optional[str] = dev.get("password") or None
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._ui_broadcast = ui_broadcast
        self._zeroconf = zeroconf

        self._client: Optional[APIClient] = None
        self._reconnect: Optional[ReconnectLogic] = None
        self._unsub_va: Optional[Callable[[], None]] = None
        self._media: Optional[EsphomeMediaTransport] = None
        self._session: Optional[Session] = None
        self._session_task: Optional[asyncio.Task] = None
        self._outbound_writer_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client._connection is not None

    async def start(self) -> None:
        """Construct the APIClient + ReconnectLogic and start
        connecting. Reconnect is handled by the lib."""
        self._client = APIClient(
            address=self._host,
            port=self._port,
            password=self._password,
            noise_psk=self._noise_psk,
            client_info="aivg-gateway",
            zeroconf_instance=self._zeroconf.zeroconf,
        )
        self._reconnect = ReconnectLogic(
            client=self._client,
            on_connect=self._on_connect,
            on_disconnect=self._on_disconnect,
            zeroconf_instance=self._zeroconf,
            name=self.device_id,
            on_connect_error=self._on_connect_error,
        )
        await self._reconnect.start()

    async def stop(self) -> None:
        if self._reconnect is not None:
            await self._reconnect.stop()
            self._reconnect = None
        await self._teardown_session()
        if self._client is not None:
            try:
                await self._client.disconnect(force=True)
            except Exception:  # noqa: BLE001
                pass
            self._client = None

    async def _on_connect(self) -> None:
        """Called by ReconnectLogic each time the connection is
        established. Registers the device and subscribes to the
        voice-assistant pipeline."""
        if self._client is None:
            return
        try:
            info = await self._client.device_info()
            _LOG.info(
                "esphome: connected to %s (esphome=%s, mac=%s)",
                info.name, info.esphome_version, info.mac_address,
            )
            # Register in AIVG registry tagged as esphome_api transport.
            client = self._registry.register(
                device_id=self.device_id,
                device_type="esphome",
                firmware_version=info.esphome_version or "",
                ip_address=self._host,
            )
            client.transport = "esphome_api"
            client.status = ClientStatus.ONLINE
            client.adoption_state = AdoptionState.ADOPTED
            client.touch()
            self._sink.emit(
                self.device_id, LogLevel.INFO, LogSource.SYSTEM,
                f"esphome: device_adopted device_id={self.device_id!r}",
                {"transport": "esphome_api"},
            )
            # Subscribe to voice-pipeline events.
            self._unsub_va = self._client.subscribe_voice_assistant(
                handle_start=self._handle_va_start,
                handle_stop=self._handle_va_stop,
                handle_audio=self._handle_va_audio,
            )
        except Exception:  # noqa: BLE001
            _LOG.exception("esphome: on_connect failed for %s", self.device_id)

    async def _on_disconnect(self, expected_disconnect: bool) -> None:
        """Called by ReconnectLogic when the connection drops."""
        _LOG.info(
            "esphome: device %s disconnected (expected=%s)",
            self.device_id, expected_disconnect,
        )
        if self._unsub_va is not None:
            try:
                self._unsub_va()
            except Exception:  # noqa: BLE001
                pass
            self._unsub_va = None
        await self._teardown_session()
        # Mark offline in registry; device record stays.
        c = self._registry.get_client(self.device_id)
        if c is not None:
            c.status = ClientStatus.OFFLINE
            c.touch()

    async def _on_connect_error(self, exc: Exception) -> None:
        """Called on a single connect attempt failure."""
        if isinstance(exc, (InvalidAuthAPIError, InvalidEncryptionKeyAPIError)):
            self._sink.emit(
                self.device_id, LogLevel.ERROR, LogSource.SYSTEM,
                f"esphome: auth/encryption rejected by device "
                f"{self.device_id!r}: {exc}",
                {"transport": "esphome_api"},
            )
        elif isinstance(exc, ResolveAPIError):
            _LOG.debug("esphome: %s unreachable: %s", self.device_id, exc)
        else:
            _LOG.debug("esphome: %s connect error: %s", self.device_id, exc)

    # --- voice-pipeline handlers (called by aioesphomeapi) -----------

    async def _handle_va_start(
        self,
        conversation_id: str,
        flags: int,
        audio_settings,
        wake_word_phrase: Optional[str],
    ) -> Optional[int]:
        """Device requests a pipeline start. Returns port=0 to mean
        'send audio over the same API connection, not UDP'."""
        async with self._lock:
            await self._teardown_session()
            # Build a fresh Session for this turn.
            session_id = uuid.uuid4().hex
            model = VoiceSession(session_id=session_id, device_id=self.device_id)
            model.transport = "esphome_api"
            self._media = EsphomeMediaTransport(connection=None)  # type: ignore[arg-type]
            self._session = Session(
                model, self._media, self._platform, self._sink,
                ui_sink=self._ui_sink,
            )
            self._session_task = asyncio.create_task(self._session.run())
            self._outbound_writer_task = asyncio.create_task(
                self._pump_outbound()
            )
            # Tell the device we're listening.
            self._send_event(VoiceAssistantEventType.VOICE_ASSISTANT_STT_START)
        return 0  # use the same API connection for audio (not UDP)

    async def _handle_va_stop(self, abort: bool) -> None:
        """Device says the pipeline is done (or barge-in / aborted)."""
        async with self._lock:
            await self._teardown_session()
            self._send_event(VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END)

    async def _handle_va_audio(
        self, data: bytes, extra: Optional[bytes] = None
    ) -> None:
        """Device → us: a chunk of microphone audio (PCM16 mono 16 kHz).
        Push into the media adapter, which resamples to 48 kHz and
        feeds Session."""
        if self._media is None or not data:
            return
        self._media.push_inbound(data)

    async def _pump_outbound(self) -> None:
        """Pull resampled 16 kHz chunks from the media adapter and
        send them to the device as ``VoiceAssistantAudio`` frames."""
        media = self._media
        client = self._client
        if media is None or client is None:
            return
        try:
            while True:
                chunk = await media.drain_outbound()
                if chunk is None:
                    return
                if chunk:
                    client.send_voice_assistant_audio(chunk)
        except (ConnectionError, asyncio.CancelledError):
            raise
        except Exception:  # noqa: BLE001
            _LOG.exception("esphome: outbound writer crashed for %s", self.device_id)

    def _send_event(self, event_type: int) -> None:
        """Fire a VoiceAssistantEventResponse if the client is alive."""
        if self._client is None:
            return
        try:
            self._client.send_voice_assistant_event(event_type, None)
        except Exception:  # noqa: BLE001
            _LOG.debug("esphome: send_event failed", exc_info=True)

    def _ui_sink(self, evt: dict) -> None:
        if self._ui_broadcast is None:
            return
        try:
            self._ui_broadcast({**evt, "device_id": self.device_id})
        except Exception:  # noqa: BLE001
            pass

    async def _teardown_session(self) -> None:
        """Cancel the in-flight Session + outbound writer + media
        adapter for this device. Idempotent."""
        if self._session_task is not None and not self._session_task.done():
            self._session_task.cancel()
            try:
                await self._session_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._outbound_writer_task is not None:
            self._outbound_writer_task.cancel()
            try:
                await self._outbound_writer_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        if self._media is not None:
            await self._media.close()
        self._session = None
        self._session_task = None
        self._outbound_writer_task = None
        self._media = None
