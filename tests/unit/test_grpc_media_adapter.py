"""Feature 021 — unit tests for ``GrpcMediaAdapter`` (T015).

Covers resample/reframe (16 kHz↔48 kHz), the outbound PCM→ServerFrame pump,
EOF signalling, UI-event → ServerFrame mapping, and bounded-queue
backpressure (no unbounded growth).
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("grpc")

from aivg_core.transports.grpc._generated import audio_pb2  # noqa: E402
from aivg_core.transports.grpc.codec import CODEC_PCM_S16LE_16K  # noqa: E402
from aivg_core.transports.grpc.media_adapter import GrpcMediaAdapter  # noqa: E402

_WIRE_FRAME = b"\x10\x20" * 320  # 640 bytes = 20 ms @ 16 kHz


@pytest.mark.asyncio
async def test_push_inbound_resamples_and_reframes():
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    # Push a few 16 kHz/20 ms frames (resampler warmup means a single frame
    # can underfill one internal 48 kHz frame); each emitted frame must be a
    # full 48 kHz/20 ms internal frame (1920 bytes).
    for _ in range(3):
        a.push_inbound(_WIRE_FRAME)
    frame = await asyncio.wait_for(a.receive(), timeout=1.0)
    assert frame is not None and len(frame) == 1920


@pytest.mark.asyncio
async def test_push_eof_yields_none():
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    a.push_eof()
    out = await asyncio.wait_for(a.receive(), timeout=1.0)
    assert out is None


@pytest.mark.asyncio
async def test_outbound_pump_emits_audio_serverframe():
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    pump = asyncio.create_task(a.run_outbound_pump())
    # Session pushes a 48 kHz/20 ms PCM chunk (1920 bytes).
    await a.send_audio(b"\x00\x01" * 960)
    frame = await asyncio.wait_for(a.next_server_frame(), timeout=1.0)
    assert frame.WhichOneof("body") == "audio"
    assert frame.audio.codec == CODEC_PCM_S16LE_16K
    assert frame.audio.payload, "downsampled payload must be non-empty"
    assert frame.audio.seq == 1
    await a.close()
    # After close, the pump terminates the stream with a None sentinel.
    tail = await asyncio.wait_for(a.next_server_frame(), timeout=1.0)
    assert tail is None
    await asyncio.wait_for(pump, timeout=1.0)


@pytest.mark.asyncio
async def test_ui_event_sink_maps_state_and_transcript():
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    a.ui_event_sink({"type": "state", "state": "speaking"})
    f1 = await asyncio.wait_for(a.next_server_frame(), timeout=1.0)
    assert f1.event.kind == audio_pb2.ServerEvent.SPEAKING_STARTED
    a.ui_event_sink({"type": "state", "state": "listening"})
    f2 = await asyncio.wait_for(a.next_server_frame(), timeout=1.0)
    assert f2.event.kind == audio_pb2.ServerEvent.SPEAKING_ENDED
    a.ui_event_sink({"type": "partial_transcript", "text": "hello"})
    f3 = await asyncio.wait_for(a.next_server_frame(), timeout=1.0)
    assert f3.WhichOneof("body") == "transcript" and f3.transcript.text == "hello"


@pytest.mark.asyncio
async def test_inbound_queue_is_bounded_drops_not_grows():
    """A stalled Session (never draining _in) must NOT make push_inbound grow
    memory without bound (FR-021)."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    for _ in range(500):  # far more than the queue maxsize (100)
        a.push_inbound(_WIRE_FRAME)
    assert a._in.qsize() <= 100, "inbound queue exceeded its bound"
