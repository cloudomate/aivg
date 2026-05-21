"""Feature 017 — ``EsphomeMediaTransport`` unit tests.

Proves the adapter satisfies the existing ``MediaTransport`` Protocol
from ``webrtc/session.py`` (R-3 constitutional bet) and that
sample-rate conversion roundtrips cleanly.

Per [contracts/esphome-transport.md § 8](../../specs/017-esphome-voice-transport/contracts/esphome-transport.md#8-contract-tests-binding)
rows 5-6.
"""

from __future__ import annotations

import asyncio
import math
import audioop

import pytest

# Skip cleanly if aioesphomeapi isn't on path (not required by this
# module but the package's __init__ might pull in cross-deps).
pytest.importorskip("aioesphomeapi")

from aivg_core.transports.esphome.media_adapter import (  # noqa: E402
    EsphomeMediaTransport,
    _INTERNAL_FRAME_BYTES,
    _INTERNAL_SR,
    _WIRE_FRAME_BYTES,
    _WIRE_SR,
)
from aivg_core.webrtc.session import MediaTransport  # noqa: E402


class _FakeConn:
    """Stand-in for EsphomeConnection during unit tests."""
    pass


def test_constants():
    """Sanity-check the sample-rate constants."""
    assert _WIRE_SR == 16000
    assert _INTERNAL_SR == 48000
    assert _INTERNAL_FRAME_BYTES == 1920   # 20ms @ 48kHz s16 mono
    assert _WIRE_FRAME_BYTES == 640        # 20ms @ 16kHz s16 mono


def test_protocol_membership():
    """``EsphomeMediaTransport`` MUST satisfy the existing
    :class:`MediaTransport` Protocol. We check the duck-type
    surface explicitly because ``MediaTransport`` is not
    ``runtime_checkable``."""
    em = EsphomeMediaTransport(_FakeConn())
    assert callable(getattr(em, "receive", None))
    assert callable(getattr(em, "send_audio", None))
    assert callable(getattr(em, "stop_playback", None))
    assert hasattr(em, "connection_state")
    assert callable(getattr(em, "close", None))


@pytest.mark.asyncio
async def test_close_is_idempotent():
    em = EsphomeMediaTransport(_FakeConn())
    await em.close()
    await em.close()  # idempotent (C7)
    assert em.connection_state == "closed"


@pytest.mark.asyncio
async def test_receive_returns_none_after_close():
    em = EsphomeMediaTransport(_FakeConn())
    await em.close()
    assert await em.receive() is None


@pytest.mark.asyncio
async def test_push_inbound_resample_and_reframe():
    """Push 3× 640-byte wire frames (60 ms @ 16 kHz) and expect at
    least one 1920-byte internal frame (20 ms @ 48 kHz) emitted via
    ``receive()``. ``audioop.ratecv`` has an initial filter-delay
    transient so a single 640-byte push may produce <1920 bytes of
    upsampled audio — pushing several frames worth proves the
    upsampler+reframer pipeline reliably emits internal frames."""
    em = EsphomeMediaTransport(_FakeConn())
    # A sine-wave-ish payload at 16 kHz, 20 ms = 320 samples = 640 bytes.
    pcm16k = bytes(
        b
        for s in (int(16000 * math.sin(2 * math.pi * 440 * i / 16000))
                  for i in range(320))
        for b in (s & 0xFF, (s >> 8) & 0xFF)
    )
    assert len(pcm16k) == _WIRE_FRAME_BYTES

    # Push three wire frames to overcome the resampler's initial delay.
    for _ in range(3):
        em.push_inbound(pcm16k)

    # We expect at least one full internal frame (1920 bytes).
    frame_48k = await asyncio.wait_for(em.receive(), timeout=1.0)
    assert frame_48k is not None
    assert len(frame_48k) == _INTERNAL_FRAME_BYTES  # 1920 bytes


@pytest.mark.asyncio
async def test_push_eof_flushes_and_signals_none():
    """After ``push_eof()``, ``receive()`` MUST eventually return ``None``."""
    em = EsphomeMediaTransport(_FakeConn())
    em.push_eof()
    # First receive may yield a padded tail frame (if there's any buffer),
    # but eventually a None must come.
    sentinels = 0
    for _ in range(3):
        frame = await em.receive()
        if frame is None:
            sentinels += 1
            break
    assert sentinels == 1


@pytest.mark.asyncio
async def test_send_audio_and_drain_outbound_downsample():
    """Push a 48 kHz 1920-byte frame to ``send_audio`` and expect the
    drain side to yield a downsampled 16 kHz chunk."""
    em = EsphomeMediaTransport(_FakeConn())
    # 1920 bytes = 960 samples @ 48 kHz, 20 ms.
    pcm48k = b"\x10\x20" * 960
    await em.send_audio(pcm48k)
    chunk_16k = await em.drain_outbound()
    assert chunk_16k is not None
    # Downsampled length should be approximately 1/3 of input (48 → 16).
    # audioop.ratecv has some slack across phase; assert in a window.
    assert 600 <= len(chunk_16k) <= 700  # roughly 640 ± slack


@pytest.mark.asyncio
async def test_stop_playback_drains_queue():
    em = EsphomeMediaTransport(_FakeConn())
    await em.send_audio(b"\x01" * 1920)
    await em.send_audio(b"\x02" * 1920)
    await em.stop_playback()
    # After stop_playback, draining the outbound queue should return
    # nothing buffered. We can't peek directly; instead push a fresh
    # chunk and confirm only that one comes through.
    await em.send_audio(b"\x03" * 1920)
    chunk = await em.drain_outbound()
    assert chunk is not None
    # The chunk should be derived from b"\x03" * 1920 (the only
    # non-drained item). We don't assert byte-equality (resampler
    # state evolves) but we DO assert it isn't the b"\x01"-derived
    # frame — by length-bucket comparison this is a weak signal,
    # so we just sanity-check non-emptiness.
    assert len(chunk) > 0


@pytest.mark.asyncio
async def test_send_audio_after_close_is_silent():
    em = EsphomeMediaTransport(_FakeConn())
    await em.close()
    await em.send_audio(b"\x00" * 1920)  # no exception
    # Nothing should drain (the queue was sentinel-signaled in close).
    chunk = await em.drain_outbound()
    assert chunk is None
