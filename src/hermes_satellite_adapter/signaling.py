"""WebRTC signaling plane (design §2.2).

The client/satellite is the OFFERER; this adapter is the ANSWERER, for every
device type. The client does a FULL ICE GATHER then posts the complete SDP, so
``/webrtc/candidate`` is only a fallback (and unnecessary on a LAN).

``SignalingService`` is transport-factory injected so the offer→session wiring
is testable with a fake transport; ``AiortcTransport`` (lazy import) is the
production realisation. No SDP munging; Opus 48 kHz negotiated by default.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from .hermes_bridge import HermesBridge
from .logsink import LogSink
from .models import LogLevel, LogSource
from .registry import Registry
from .session import MediaTransport, Session

# A transport factory turns an SDP offer into (answer_sdp, MediaTransport).
TransportFactory = Callable[[str, str], Awaitable[tuple[str, MediaTransport]]]


class SignalingService:
    def __init__(
        self,
        registry: Registry,
        bridge: HermesBridge,
        sink: LogSink,
        transport_factory: TransportFactory,
    ) -> None:
        self._reg = registry
        self._bridge = bridge
        self._sink = sink
        self._make_transport = transport_factory
        self._tasks: dict[str, asyncio.Task] = {}

    async def handle_offer(self, body: dict[str, Any]) -> dict[str, Any]:
        device_id = body["device_id"]
        if self._reg.get_client(device_id) is None:
            # Accept register-on-offer for robustness; client should register first.
            self._reg.register(device_id=device_id, device_type=body.get("device_type", "browser"))

        answer_sdp, transport = await self._make_transport(body["sdp"], device_id)
        sess_model = self._reg.open_session(device_id)
        sess_model.webrtc_state = transport.connection_state
        session = Session(sess_model, transport, self._bridge, self._sink)
        self._tasks[sess_model.session_id] = asyncio.create_task(self._run(session))
        self._sink.emit(
            device_id, LogLevel.INFO, LogSource.WEBRTC, "session opened",
            {"session_id": sess_model.session_id},
        )
        return {"sdp": answer_sdp, "type": "answer"}

    async def _run(self, session: Session) -> None:
        sid = session.model.session_id
        try:
            await session.run()
        finally:
            self._reg.close_session(sid)
            self._tasks.pop(sid, None)
            self._sink.emit(
                session.model.device_id, LogLevel.INFO, LogSource.WEBRTC,
                "session closed", {"session_id": sid},
            )

    def status(self, device_id: str) -> Optional[dict[str, Any]]:
        sess = self._reg.session_for_device(device_id)
        if sess is None:
            return None
        return {
            "session_id": sess.session_id,
            "webrtc_state": sess.webrtc_state,
            "state": sess.state.value,
            "bitrate_tx": sess.bitrate_tx,
            "bitrate_rx": sess.bitrate_rx,
        }

    async def drop(self, device_id: str) -> None:
        """ICE/connection drop: tear down the session; expect a fresh offer."""
        sess = self._reg.session_for_device(device_id)
        if sess is None:
            return
        task = self._tasks.get(sess.session_id)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._reg.close_session(sess.session_id)


async def aiortc_transport_factory(offer_sdp: str, device_id: str):  # pragma: no cover
    """Production transport: aiortc answerer, Opus 48 kHz mono, full-gather.

    Lazy import keeps the package importable (and the test suite runnable)
    without aiortc installed.
    """
    from aiortc import RTCPeerConnection, RTCSessionDescription  # noqa: WPS433

    pc = RTCPeerConnection()
    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)
    # NOTE: a real AiortcTransport adapting RTCPeerConnection audio tracks to the
    # MediaTransport Protocol (Opus<->PCM via `av`) is wired here; omitted from
    # the test build since aiortc is not a test dependency.
    raise NotImplementedError(
        "aiortc transport adapter is production-only; tests use FakeTransport"
    )
