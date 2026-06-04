"""Per-``Audio.Stream`` lifecycle (feature 021, FR-006/010/012/020/023).

Mirrors ``transports.esphome.connection._start_voice_pipeline``: validate the
opening ``SessionHeader``, bind the ``session_id`` to a :class:`VoiceSession`,
construct a :class:`GrpcMediaAdapter` + the canonical :class:`Session`, and
bridge inbound ``ClientFrame``s (PCM + events) while the servicer yields the
merged outbound ``ServerFrame`` stream.
"""

from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Callable, Optional, TYPE_CHECKING

import grpc

from ...logsink import LogSink
from ...models import LogLevel, LogSource, VoiceSession
from ...webrtc.session import Session
from ._generated import audio_pb2
from .codec import select_downstream_codec
from .media_adapter import GrpcMediaAdapter

if TYPE_CHECKING:
    from ...platforms.base import AgentPlatform

_LOG = logging.getLogger(__name__)

_ClientEvent = audio_pb2.ClientEvent


async def serve_stream(
    request_iterator: "AsyncIterator[audio_pb2.ClientFrame]",
    context: "grpc.aio.ServicerContext",
    *,
    platform: "AgentPlatform",
    sink: LogSink,
    downstream_codec_name: str = "pcm",
    ui_broadcast: Optional[Callable[[dict], None]] = None,
) -> "AsyncIterator[audio_pb2.ServerFrame]":
    """Drive one voice session over a bidi ``Audio.Stream`` call.

    Yields ``ServerFrame``s (audio + events + transcripts). The first inbound
    frame MUST be a ``SessionHeader``; otherwise the call is aborted with
    ``FAILED_PRECONDITION`` (FR-006).
    """
    # 1) First frame must be a SessionHeader (FR-006).
    try:
        first = await request_iterator.__anext__()
    except StopAsyncIteration:
        return
    if first.WhichOneof("body") != "session" or not first.session.session_id:
        await context.abort(
            grpc.StatusCode.FAILED_PRECONDITION,
            "first ClientFrame must be a SessionHeader with a session_id",
        )
        return  # pragma: no cover - abort raises

    session_id = first.session.session_id
    codec = select_downstream_codec(
        list(first.session.downstream_codec_pref), downstream_codec_name
    )

    # 2) Bind the session. (Phase 1: device_id defaults to session_id; the
    #    management plane mints the id and owns device binding — Phase 2.)
    model = VoiceSession(session_id=session_id, device_id=session_id)
    model.transport = "grpc"
    adapter = GrpcMediaAdapter(downstream_codec=codec)

    def _ui_sink(evt: dict) -> None:
        adapter.ui_event_sink(evt)
        if ui_broadcast is not None:
            try:
                ui_broadcast({**evt, "device_id": model.device_id})
            except Exception:  # noqa: BLE001 - fan-out must never break voice
                pass

    session = Session(model, adapter, platform, sink, ui_sink=_ui_sink)
    sink.emit(
        model.device_id, LogLevel.INFO, LogSource.SYSTEM,
        "grpc: stream open", {"session_id": session_id, "codec": int(codec)},
    )

    reader = asyncio.create_task(_read_inbound(request_iterator, adapter))
    runner = asyncio.create_task(session.run())
    pump = asyncio.create_task(adapter.run_outbound_pump())

    drop_reason = "complete"
    try:
        while True:
            frame = await adapter.next_server_frame()
            if frame is None:
                break
            yield frame
    except asyncio.CancelledError:
        drop_reason = "cancelled"
        raise
    finally:
        reader.cancel()
        await adapter.close()
        for t in (runner, pump):
            try:
                await asyncio.wait_for(asyncio.shield(t), timeout=2.0)
            except Exception:  # noqa: BLE001
                t.cancel()
        sink.emit(
            model.device_id, LogLevel.INFO, LogSource.SYSTEM,
            "grpc: stream closed", {"session_id": session_id, "reason": drop_reason},
        )


async def _read_inbound(
    request_iterator: "AsyncIterator[audio_pb2.ClientFrame]",
    adapter: GrpcMediaAdapter,
) -> None:
    """Pump inbound ``ClientFrame``s into the media adapter until the client
    stream ends or drops. A dropped/closed stream signals EOF so the session
    unwinds cleanly and the next wake can re-establish (FR-019/FR-020)."""
    try:
        async for frame in request_iterator:
            body = frame.WhichOneof("body")
            if body == "pcm":
                adapter.push_inbound(frame.pcm.samples)
            elif body == "opus":
                adapter.push_inbound_opus(frame.opus.payload)  # feature 025
            elif body == "event":
                kind = frame.event.kind
                if kind == _ClientEvent.END_OF_UTTERANCE:
                    adapter.push_eof()
                elif kind == _ClientEvent.BARGE_IN_START:
                    await adapter.stop_playback()
                # WAKE_FIRED: explicit session start; the session is already
                # running (FR-012) — nothing further to do here.
            # A stray extra SessionHeader is ignored.
    except (asyncio.CancelledError, grpc.aio.AioRpcError):
        pass
    except Exception:  # noqa: BLE001 - reader must not crash the call
        _LOG.exception("grpc: inbound reader error")
    finally:
        # Stream ended/closed -> end-of-utterance so Session.run() unwinds.
        adapter.push_eof()
