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

from ..platforms.base import AgentPlatform
from ..logsink import LogSink
from ..models import LogLevel, LogSource
from ..registry import Registry
from .session import MediaTransport, Session

# A transport factory turns an SDP offer into (answer_sdp, MediaTransport).
TransportFactory = Callable[[str, str], Awaitable[tuple[str, MediaTransport]]]


class SignalingService:
    def __init__(
        self,
        registry: Registry,
        platform: AgentPlatform,
        sink: LogSink,
        transport_factory: TransportFactory,
        ui_broadcast=None,
    ) -> None:
        self._reg = registry
        # Feature 015 / FR-003: the signaling service holds the active
        # AgentPlatform and threads it through to each per-call Session.
        # No platform-specific symbol crosses this boundary.
        self._platform = platform
        self._sink = sink
        self._make_transport = transport_factory
        # Optional fan-out for call-scoped UI events (state / partial
        # transcript / barge-in) onto the control-plane WS (constitution III:
        # these are non-durable; durable control stays on the WS proper).
        self._ui_broadcast = ui_broadcast
        self._tasks: dict[str, asyncio.Task] = {}

    async def handle_offer(self, body: dict[str, Any]) -> dict[str, Any]:
        device_id = body["device_id"]
        if self._reg.get_client(device_id) is None:
            # Accept register-on-offer for robustness; client should register first.
            self._reg.register(device_id=device_id, device_type=body.get("device_type", "browser"))

        answer_sdp, transport = await self._make_transport(body["sdp"], device_id)
        sess_model = self._reg.open_session(device_id)
        sess_model.webrtc_state = transport.connection_state
        # Make the outbound media path observable in gateway.log via the
        # visible JSON LogSink (constitution V — verify before relying).
        if hasattr(transport, "attach_sink"):
            transport.attach_sink(self._sink, device_id)
        ui_sink = None
        if self._ui_broadcast is not None:
            def ui_sink(evt, _dev=device_id):  # noqa: WPS430
                try:
                    self._ui_broadcast({**evt, "device_id": _dev})
                except Exception:  # noqa: BLE001 - UI fan-out must never break voice
                    pass
        session = Session(
            sess_model, transport, self._platform, self._sink, ui_sink=ui_sink
        )
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


# Wire/internal audio constants (feature 001 design contract +
# HermesV013Bridge defaults): Opus 48 kHz mono on the wire; internal PCM is
# signed-16 mono 48 kHz framed at 20 ms (960 samples = 1920 bytes) so the
# decoded audio matches exactly what Hermes STT / the server-side endpoint
# algorithm already account for (SC-001 / FR-001 / FR-004).
_SR = 48000
_FRAME_MS = 20
_SAMPLES_PER_FRAME = _SR * _FRAME_MS // 1000  # 960
_FRAME_BYTES = _SAMPLES_PER_FRAME * 2  # mono s16 → 1920

# A live RTCPeerConnection in one of these states yields no more audio; the
# session loop treats receive()==None as the clean end signal (FR-006).
_DEAD_STATES = {"failed", "closed"}


class AiortcTransport:  # pragma: no cover - host-only (needs aiortc/av)
    """Real backer for ``session.MediaTransport`` (FR-003).

    Pure audio plumbing only — decode/encode/resample/buffer. NO STT/TTS/
    agent/endpointing/VAD (constitution I / FR-008/FR-011); endpointing stays
    behind ``HermesBridge``. Substitutable for ``FakeTransport`` with zero
    change to ``session.py`` (contract C1–C8).
    """

    def __init__(self, pc, in_track, out_track, out_queue) -> None:
        from .media import PcmFramer  # noqa: WPS433

        self._pc = pc
        self._in = in_track
        self._out = out_track
        self._out_q = out_queue
        self._framer = PcmFramer(_FRAME_BYTES)
        self._in_buf: list[bytes] = []
        self._resampler = None  # built lazily on first inbound frame
        self._closed = False
        self._sink = None
        self._dev = "?"
        self._in_seen = False

    def attach_sink(self, sink, device_id: str) -> None:
        """Wire the visible JSON LogSink so the outbound media path is
        observable in gateway.log (constitution V)."""
        self._sink = sink
        self._dev = device_id

    def _emit(self, msg: str, **meta) -> None:
        try:
            if self._sink is not None:
                self._sink.emit(
                    self._dev, LogLevel.INFO, LogSource.WEBRTC, msg, meta or None
                )
        except Exception:  # noqa: BLE001 - logging must never affect audio
            pass

    # --- inbound: caller Opus → s16 mono 48 kHz, uniform 20 ms frames ----
    async def receive(self):
        from aiortc.mediastreams import MediaStreamError  # noqa: WPS433

        while not self._in_buf:
            if self._closed or self._pc.connectionState in _DEAD_STATES:
                return None
            try:
                frame = await self._in.recv()
            except MediaStreamError:
                return None  # inbound track ended → clean session end (C2)
            for pcm in self._decode_inbound(frame):
                self._in_buf.extend(self._framer.push(pcm))
        return self._in_buf.pop(0)

    def _decode_inbound(self, frame) -> list[bytes]:
        import av  # noqa: WPS433

        if self._resampler is None:
            self._resampler = av.AudioResampler(
                format="s16", layout="mono", rate=_SR
            )
        out = self._resampler.resample(frame)
        frames = out if isinstance(out, (list, tuple)) else [out]
        chunks: list[bytes] = []
        for f in frames:
            if f is None:
                continue
            want = f.samples * 2  # mono s16
            try:
                buf = f.planes[0].to_bytes()
            except AttributeError:
                buf = bytes(f.planes[0])
            chunks.append(buf[:want])
        return chunks

    # --- outbound: any TTS container/rate → 48 kHz mono → Opus track -----
    async def send_audio(self, pcm: bytes) -> None:
        import io

        import av  # noqa: WPS433

        if not pcm or len(pcm) < 16:
            self._emit("send_audio: empty/sentinel, nothing emitted", n=len(pcm or b""))
            return  # empty / tool-only / sentinel → emit nothing (C4)
        head = pcm[:4]
        self._emit("send_audio: received TTS bytes", n=len(pcm), head=repr(head))
        try:
            container = av.open(io.BytesIO(pcm))
        except Exception as exc:  # noqa: BLE001 - undecodable/sentinel: drop
            self._emit("send_audio: av.open FAILED (dropped)", err=str(exc))
            return
        import array as _array

        resampler = av.AudioResampler(format="s16", layout="mono", rate=_SR)
        enq = 0
        peak = 0          # max |sample| across all decoded PCM (0 ⇒ silence)
        raw_total = 0
        first_meta = None
        try:
            for frame in container.decode(audio=0):
                out = resampler.resample(frame)
                for f in out if isinstance(out, (list, tuple)) else [out]:
                    if f is None:
                        continue
                    try:
                        b = f.planes[0].to_bytes()
                    except AttributeError:
                        b = bytes(f.planes[0])
                    seg = b[: f.samples * 2]
                    raw_total += len(seg)
                    if first_meta is None:
                        first_meta = {
                            "fmt": getattr(f.format, "name", "?"),
                            "lay": getattr(f.layout, "name", "?"),
                            "rate": getattr(f, "sample_rate", "?"),
                            "samples": f.samples,
                            "plane_len": len(b),
                            "seg_len": len(seg),
                        }
                    if seg:
                        a = _array.array("h")
                        a.frombytes(seg[: len(seg) - (len(seg) % 2)])
                        for s in a:
                            v = -s if s < 0 else s
                            if v > peak:
                                peak = v
                    for chunk in self._framer.push(seg):
                        await self._out_q.put(chunk)
                        enq += 1
            tail = self._framer.flush()
            if tail:
                await self._out_q.put(tail)
                enq += 1
        except Exception as exc:  # noqa: BLE001 - never kill the session (C4)
            self._emit("send_audio: decode aborted (partial)", err=str(exc), enqueued=enq)
        finally:
            container.close()
        self._emit("send_audio: enqueued frames for playback", frames=enq,
                   approx_seconds=round(enq * _FRAME_MS / 1000.0, 2),
                   pcm_peak=peak, raw_bytes=raw_total, first=first_meta)
        # Block until the clip has actually been sent (queue drained by the
        # outbound track at real-time pace). This keeps session.py in SPEAKING
        # for the REAL playback duration so the barge-in watcher stays live and
        # can interrupt mid-playback (SC-004). stop_playback() drains the queue
        # on barge-in → this returns promptly; close()/cancellation also unwind
        # here. session.py and the MediaTransport contract are unchanged
        # (FakeTransport.send_audio still returns instantly).
        import asyncio as _aio

        while not self._closed and not self._out_q.empty():
            await _aio.sleep(0.05)
        self._emit("send_audio: playback drained", frames=enq)

    async def stop_playback(self) -> None:
        # Barge-in: drop everything queued; the outbound track falls back to
        # silence and stays usable for the next turn (C5 / ≤300 ms / no wedge).
        try:
            while True:
                self._out_q.get_nowait()
        except Exception:  # noqa: BLE001 - QueueEmpty
            pass

    @property
    def connection_state(self) -> str:
        return self._pc.connectionState

    async def close(self) -> None:
        if self._closed:
            return  # idempotent (C7)
        self._closed = True
        for t in (self._in, self._out):
            try:
                t.stop()
            except Exception:  # noqa: BLE001
                pass
        try:
            await self._pc.close()
        except Exception:  # noqa: BLE001
            pass


async def aiortc_transport_factory(offer_sdp: str, device_id: str):  # pragma: no cover - host-only
    """Production transport: aiortc answerer, Opus 48 kHz mono, full-gather.

    Lazy import keeps the package importable (and the fake-transport suite
    runnable) without aiortc/av installed (constitution V / FR-012). Builds a
    real ``AiortcTransport`` over the negotiated peer. If the offer carries no
    receivable inbound audio track, fail loudly rather than return a transport
    that would hang in ``receive()`` (FR-007 / edge: no inbound track).
    """
    import asyncio
    import time
    from fractions import Fraction

    import av  # noqa: WPS433
    from aiortc import RTCPeerConnection, RTCSessionDescription  # noqa: WPS433
    from aiortc.mediastreams import MediaStreamError, MediaStreamTrack  # noqa: WPS433

    out_q: "asyncio.Queue[bytes]" = asyncio.Queue()

    class _OutboundAudioTrack(MediaStreamTrack):
        """Paces 20 ms Opus frames to the peer; emits silence when idle so the
        sender never starves (no desync — SC-006) and barge-in leaves it
        immediately reusable (C5)."""

        kind = "audio"

        def __init__(self) -> None:
            super().__init__()
            self._pts = 0
            self._start = None
            self._silence = b"\x00" * _FRAME_BYTES
            self._n = 0          # total recv() pulls by aiortc's sender
            self._real = 0       # frames that carried real (queued) audio
            self._tx = None      # AiortcTransport, bound post-construction

        async def recv(self):
            if self.readyState != "live":
                raise MediaStreamError
            self._n += 1
            now = time.time()
            if self._start is None:
                self._start = now
            else:
                target = self._start + (self._pts + _SAMPLES_PER_FRAME) / _SR
                delay = target - now
                if delay > 0:
                    await asyncio.sleep(delay)
            try:
                data = out_q.get_nowait()
                self._real += 1
            except Exception:  # noqa: BLE001 - QueueEmpty → silence
                data = self._silence
            if self._tx is not None and (self._n == 1 or self._n % 100 == 0):
                self._tx._emit(
                    "outbound track: aiortc pulling",
                    pulls=self._n, real_frames=self._real, qsize=out_q.qsize(),
                )
            # Exactly _FRAME_BYTES (1920 = 960 s16 mono samples). aiortc's
            # plane.update requires len == plane.buffer_size; for s16/mono/960
            # that IS 1920, so feed the exact buffer and never index len(plane)
            # (the previous len(plane) path could mis-size and raise, which
            # killed the sender after a single pull — the observed bug).
            if len(data) != _FRAME_BYTES:
                data = (bytes(data) + self._silence)[:_FRAME_BYTES]
            try:
                frame = av.AudioFrame(
                    format="s16", layout="mono", samples=_SAMPLES_PER_FRAME
                )
                frame.planes[0].update(data)
                frame.sample_rate = _SR
                frame.pts = self._pts
                frame.time_base = Fraction(1, _SR)
            except Exception as exc:  # noqa: BLE001 - report once, stay alive
                if self._tx is not None and not getattr(self, "_frame_err", False):
                    self._frame_err = True
                    self._tx._emit(
                        "outbound track: FRAME BUILD FAILED",
                        err=f"{type(exc).__name__}: {exc}",
                    )
                # Keep the sender alive with a guaranteed-valid silent frame
                # so we don't lose the whole call to one bad frame.
                frame = av.AudioFrame(
                    format="s16", layout="mono", samples=_SAMPLES_PER_FRAME
                )
                frame.sample_rate = _SR
                frame.pts = self._pts
                frame.time_base = Fraction(1, _SR)
            self._pts += _SAMPLES_PER_FRAME
            return frame

    pc = RTCPeerConnection()
    audio_in: "asyncio.Future" = asyncio.get_event_loop().create_future()

    @pc.on("track")
    def _on_track(track):  # noqa: WPS430
        if track.kind == "audio" and not audio_in.done():
            audio_in.set_result(track)

    await pc.setRemoteDescription(RTCSessionDescription(sdp=offer_sdp, type="offer"))
    # Canonical aiortc answerer order: setRemoteDescription FIRST, then attach
    # the send track so it binds to the transceiver the offer negotiated
    # sendrecv. Adding before setRemoteDescription can park it on a separate
    # non-sending transceiver → the browser sees a track but no RTP ever
    # arrives (silent playback — the exact symptom observed).
    out_track = _OutboundAudioTrack()
    audio_tr = next(
        (t for t in pc.getTransceivers() if t.kind == "audio"), None
    )
    if audio_tr is not None:
        audio_tr.sender.replaceTrack(out_track)
        audio_tr.direction = "sendrecv"
    else:
        pc.addTrack(out_track)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)  # aiortc full-gathers before resolving

    try:
        in_track = await asyncio.wait_for(audio_in, timeout=5.0)
    except asyncio.TimeoutError as exc:
        await pc.close()
        raise RuntimeError(
            f"voice offer for {device_id} carried no inbound audio track; "
            f"failing the offer (no media path possible)."
        ) from exc

    transport = AiortcTransport(pc, in_track, out_track, out_q)
    out_track._tx = transport  # enable outbound-egress breadcrumbs
    return pc.localDescription.sdp, transport


def build_signaling_app(service: "SignalingService"):  # pragma: no cover
    """Thin aiohttp wiring for the WebRTC voice plane (lazy import; production
    only). Mirrors management.build_management_app (constitution IV — reuse the
    proven pattern). Routes delegate to the already-tested SignalingService.

    Kept on its OWN aiohttp site / port, never merged with the control plane
    (constitution III / spec FR-003).
    """
    from aiohttp import web  # noqa: WPS433

    app = web.Application()

    async def _offer(req):
        return web.json_response(await service.handle_offer(await req.json()))

    async def _candidate(req):
        # Full-gather is the norm on LAN; candidate is the documented fallback.
        return web.Response(status=204)

    async def _status(req):
        st = service.status(req.match_info["device_id"])
        return web.json_response(st) if st else web.Response(status=404)

    app.add_routes(
        [
            web.post("/webrtc/offer", _offer),
            web.post("/webrtc/candidate", _candidate),
            web.get("/webrtc/status/{device_id}", _status),
        ]
    )
    return app
