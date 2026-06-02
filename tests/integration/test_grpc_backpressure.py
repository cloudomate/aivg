"""Feature 021 — US1 reliability: a slow downstream consumer must not make
the gateway buffer without bound (FR-021).

Exercised at the adapter level (the unit of backpressure) so the assertion is
deterministic: inbound and merged-outbound queues are bounded, so a stalled
peer causes frame drops, never unbounded memory growth or a crash.
"""

from __future__ import annotations

import pytest

pytest.importorskip("grpc")

from aivg_core.transports.grpc.codec import CODEC_PCM_S16LE_16K  # noqa: E402
from aivg_core.transports.grpc.media_adapter import GrpcMediaAdapter  # noqa: E402

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
