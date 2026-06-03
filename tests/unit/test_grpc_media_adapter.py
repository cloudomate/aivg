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
from aivg_core.transports.grpc.codec import (  # noqa: E402
    CODEC_OPUS,
    CODEC_PCM_S16LE_16K,
)
from aivg_core.transports.grpc.media_adapter import GrpcMediaAdapter  # noqa: E402

import _audio_fixtures as fx  # noqa: E402

_WIRE_FRAME = b"\x10\x20" * 320  # 640 bytes = 20 ms @ 16 kHz
_WIRE_SR = 16000  # downstream AudioChunk PCM rate


async def _drain_audio(a: GrpcMediaAdapter) -> "list[audio_pb2.ServerFrame]":
    """Close the adapter and collect every queued ServerFrame up to the None
    sentinel."""
    await a.close()
    frames = []
    while True:
        f = await asyncio.wait_for(a.next_server_frame(), timeout=1.0)
        if f is None:
            break
        frames.append(f)
    return frames


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
    # Session hands send_audio a provider-encoded *container* (here a 24 kHz WAV),
    # NOT raw PCM — send_audio decodes + resamples to 48 kHz before queuing (023).
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    pump = asyncio.create_task(a.run_outbound_pump())
    await a.send_audio(fx.sine_wav(rate=24000, hz=440.0, ms=200))
    frames = await _drain_audio(a)
    audio = [f for f in frames if f.WhichOneof("body") == "audio"]
    assert audio, "at least one AudioChunk ServerFrame must be emitted"
    assert all(f.audio.codec == CODEC_PCM_S16LE_16K for f in audio)
    assert all(f.audio.payload for f in audio), "every downsampled payload non-empty"
    assert [f.audio.seq for f in audio] == list(range(1, len(audio) + 1)), "monotonic seq"
    await asyncio.wait_for(pump, timeout=1.0)


@pytest.mark.asyncio
async def test_outbound_audio_reconstructs_the_tone_not_noise():
    """Regression guard for the feature-023 bug: a non-48 kHz tone container must
    come out as the SAME tone on the 16 kHz downstream wire — not noise."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    pump = asyncio.create_task(a.run_outbound_pump())
    await a.send_audio(fx.sine_wav(rate=24000, hz=440.0, ms=400, amplitude=8000))
    frames = await _drain_audio(a)
    payload = b"".join(f.audio.payload for f in frames if f.WhichOneof("body") == "audio")
    assert fx.peak(payload) > 2000, "downstream audio is silence/garbage, not the tone"
    est = fx.zero_crossing_hz(payload, _WIRE_SR)
    assert 440.0 * 0.85 <= est <= 440.0 * 1.15, f"pitch not preserved (~{est:.0f} Hz)"
    await asyncio.wait_for(pump, timeout=1.0)


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", [b"", b"short", b"__PROVIDERS_UNAVAILABLE__"])
async def test_empty_sentinel_emits_no_audio_and_stays_usable(bad):
    """US2: empty / sub-minimal / sentinel input emits no AudioChunk, and the
    adapter still works for a subsequent valid clip."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    pump = asyncio.create_task(a.run_outbound_pump())
    await a.send_audio(bad)
    assert a._out.qsize() == 0, "no frames should be queued for empty/sentinel input"
    # Still usable: a real clip afterwards produces audio.
    await a.send_audio(fx.sine_wav(rate=24000, hz=440.0, ms=60))
    frames = await _drain_audio(a)
    assert any(f.WhichOneof("body") == "audio" for f in frames)
    await asyncio.wait_for(pump, timeout=1.0)


@pytest.mark.asyncio
async def test_undecodable_clip_dropped_without_raising():
    """US2: undecodable bytes emit no audio and never raise."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    pump = asyncio.create_task(a.run_outbound_pump())
    await a.send_audio(fx.corrupt_blob())  # must not raise
    assert a._out.qsize() == 0
    frames = await _drain_audio(a)
    assert not any(f.WhichOneof("body") == "audio" for f in frames)
    await asyncio.wait_for(pump, timeout=1.0)


@pytest.mark.asyncio
async def test_stop_playback_drains_queued_frames_for_bargein():
    """US3: barge-in drops queued/unplayed audio frames promptly."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    # No pump running: frames accumulate in _out, then barge-in drains them.
    await a.send_audio(fx.sine_wav(rate=24000, hz=440.0, ms=500))
    assert a._out.qsize() > 0, "clip should have queued multiple 20 ms frames"
    await a.stop_playback()
    assert a._out.qsize() == 0, "stop_playback must drain queued audio"


@pytest.mark.asyncio
async def test_streaming_two_clips_no_seam_discontinuity():
    """US3: two consecutive clips in one turn stream cleanly (carried downsample
    state keeps the seam seamless — no click)."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    pump = asyncio.create_task(a.run_outbound_pump())
    await a.send_audio(fx.sine_wav(rate=24000, hz=440.0, ms=200))
    await a.send_audio(fx.sine_wav(rate=24000, hz=440.0, ms=200))
    frames = await _drain_audio(a)
    payload = b"".join(f.audio.payload for f in frames if f.WhichOneof("body") == "audio")
    # Both clips present (≈ 400 ms @ 16 kHz s16 ≈ 12800 B) and still the same tone.
    assert len(payload) > int(0.30 * _WIRE_SR) * 2
    est = fx.zero_crossing_hz(payload, _WIRE_SR)
    assert 440.0 * 0.85 <= est <= 440.0 * 1.15
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


# --- feature 024: Opus downstream encoded at native 48 kHz (full band) -----


@pytest.mark.asyncio
async def test_opus_downstream_is_48k_full_band():
    """With Opus negotiated, downstream is Opus encoded at 48 kHz (NO 48->16
    downsample), so a 12 kHz tone survives — the band the 16 kHz PCM path
    (Nyquist 8 kHz) cannot carry — and the payload is compressed."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_OPUS)
    pump = asyncio.create_task(a.run_outbound_pump())
    await a.send_audio(fx.sine_wav(rate=48000, hz=12000.0, ms=300, amplitude=8000))
    frames = await _drain_audio(a)
    audio = [f.audio for f in frames if f.WhichOneof("body") == "audio"]
    assert audio and all(ac.codec == CODEC_OPUS for ac in audio)
    # Opus is compressed: each packet is far smaller than a raw 1920 B PCM frame.
    assert all(0 < len(ac.payload) < 1920 for ac in audio)
    pcm = fx.opus_decode_48k([ac.payload for ac in audio])
    assert fx.peak(pcm) > 2000, "decoded Opus is silence/garbage"
    assert 12000 * 0.9 <= fx.zero_crossing_hz(pcm, 48000) <= 12000 * 1.1, "full band not preserved"
    await asyncio.wait_for(pump, timeout=2.0)
