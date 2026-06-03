"""Feature 023 — unit tests for the shared TTS decoder ``decode_tts_to_pcm48k``.

Proves the canonical decode/resample (PyAV / in-process ffmpeg) that both the
gRPC and WebRTC transports rely on: non-48 kHz container → s16 mono 48 kHz with
duration + pitch preserved; stereo → mono; empty/undecodable → b"" (never raises).
"""

from __future__ import annotations

import pytest

pytest.importorskip("av")

from aivg_core.audio.tts_decode import decode_tts_to_pcm48k  # noqa: E402

import _audio_fixtures as fx  # noqa: E402

_SR = 48000


def test_resamples_non_48k_to_48k_mono_preserving_duration():
    wav = fx.sine_wav(rate=24000, hz=440.0, ms=200)
    out = decode_tts_to_pcm48k(wav)
    # 200 ms @ 48 kHz mono s16 = 0.2 * 48000 * 2 = 19200 bytes (± resampler warmup).
    expected = int(0.200 * _SR) * 2
    assert abs(len(out) - expected) <= _SR * 2 * 0.02  # within ~20 ms
    assert out != wav  # decoded PCM, not the raw container bytes


def test_decoded_tone_preserves_pitch_and_is_not_noise():
    wav = fx.sine_wav(rate=24000, hz=440.0, ms=300, amplitude=8000)
    out = decode_tts_to_pcm48k(wav)
    assert fx.peak(out) > 2000, "decoded audio must carry the tone (not silence/garbage)"
    est = fx.zero_crossing_hz(out, _SR)
    assert 440.0 * 0.85 <= est <= 440.0 * 1.15, f"pitch not preserved (got ~{est:.0f} Hz)"


def test_stereo_is_downmixed_to_mono():
    stereo = fx.stereo_wav(rate=24000, hz=440.0, ms=200)
    out = decode_tts_to_pcm48k(stereo)
    # Output is mono: ~ same sample count as the mono case, not double.
    expected = int(0.200 * _SR) * 2
    assert abs(len(out) - expected) <= _SR * 2 * 0.02


def test_empty_returns_empty():
    assert decode_tts_to_pcm48k(b"") == b""


def test_undecodable_returns_empty_without_raising():
    assert decode_tts_to_pcm48k(fx.corrupt_blob()) == b""


def test_short_sentinel_returns_empty():
    assert decode_tts_to_pcm48k(b"__PROVIDERS_UNAVAILABLE__") == b""
