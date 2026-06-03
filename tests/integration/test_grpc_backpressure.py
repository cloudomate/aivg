"""Feature 021 — US1 reliability: a slow downstream consumer must not make
the gateway buffer without bound (FR-021).

Exercised at the adapter level (the unit of backpressure) so the assertion is
deterministic: inbound and merged-outbound queues are bounded, so a stalled
peer causes frame drops, never unbounded memory growth or a crash.
"""

from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("grpc")

from aivg_core.transports.grpc.codec import CODEC_PCM_S16LE_16K  # noqa: E402
from aivg_core.transports.grpc.media_adapter import GrpcMediaAdapter  # noqa: E402

import _audio_fixtures as fx  # noqa: E402

_WIRE_FRAME = b"\x10\x20" * 320


def test_inbound_bounded_under_stalled_consumer():
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    # Consumer (Session) never drains _in.
    for _ in range(1000):
        a.push_inbound(_WIRE_FRAME)
    assert a._in.qsize() <= a._in.maxsize == 100


def test_ui_event_sink_never_raises_when_serverqueue_full():
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    # Flood the merged outbound ServerFrame queue past its bound; the UI sink
    # must swallow QueueFull rather than propagate (voice path protected).
    for _ in range(a._server.maxsize + 50):
        a.ui_event_sink({"type": "partial_transcript", "text": "x"})
    assert a._server.qsize() <= a._server.maxsize


@pytest.mark.asyncio
async def test_outbound_out_queue_bounded_and_paces(monkeypatch):
    """Feature 023: send_audio decodes a long clip into many 48 kHz frames, but a
    stalled consumer must NOT grow `_out` without bound — the bounded queue makes
    send_audio block (pace) instead (FR-021 / FR-011)."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    # ~2.5 s @ 48 kHz / 20 ms ≈ 125 frames, more than _out.maxsize (100).
    task = asyncio.create_task(a.send_audio(fx.sine_wav(rate=24000, hz=300.0, ms=2500)))
    await asyncio.sleep(0.2)  # let it decode + fill the queue
    assert a._out.qsize() <= a._out.maxsize == 100, "outbound queue exceeded its bound"
    assert not task.done(), "send_audio must block on a full _out (backpressure), not grow it"
    # Unblock: drain with the pump so the task completes and nothing leaks.
    pump = asyncio.create_task(a.run_outbound_pump())
    await asyncio.wait_for(task, timeout=5.0)
    await a.close()
    while await asyncio.wait_for(a.next_server_frame(), timeout=2.0) is not None:
        pass
    await asyncio.wait_for(pump, timeout=2.0)
