"""Feature 021 — unit tests for downstream codec selection/encoding (T016)."""

from __future__ import annotations

import pytest

pytest.importorskip("grpc")

from aivg_core.transports.grpc import codec  # noqa: E402


def test_pref_pcm_selected():
    assert codec.select_downstream_codec([codec.CODEC_PCM_S16LE_16K], "pcm") == codec.CODEC_PCM_S16LE_16K


def test_opus_is_producible_via_pyav():
    # Feature 024: Opus downstream is encoded via PyAV's bundled libopus (PyAV is
    # already a hard dependency), so Opus is now producible without opuslib.
    assert codec._opus_available()


def test_pref_opus_selected():
    # A client preferring Opus now gets Opus (full-band 48 kHz), not the old
    # PCM fallback.
    assert codec.select_downstream_codec([codec.CODEC_OPUS], "pcm") == codec.CODEC_OPUS


def test_empty_prefs_use_configured_default():
    assert codec.select_downstream_codec([], "pcm") == codec.CODEC_PCM_S16LE_16K


def test_default_opus_selected():
    assert codec.select_downstream_codec([], "opus") == codec.CODEC_OPUS


def test_pcm_encode_is_passthrough():
    payload = b"\x01\x02\x03\x04"
    assert codec.encode(codec.CODEC_PCM_S16LE_16K, payload) == payload


def test_opus_encoder_48k_roundtrips_full_band():
    """OpusEncoder48k encodes at 48 kHz, so a 12 kHz tone survives — the band the
    16 kHz path (Nyquist 8 kHz) cannot carry."""
    import math
    import struct

    import _audio_fixtures as fx

    enc = codec.OpusEncoder48k()
    packets = []
    for i in range(20):  # 20 × 20 ms frames of a 12 kHz tone @ 48 kHz
        frame = struct.pack(
            "<960h",
            *[int(8000 * math.sin(2 * math.pi * 12000 * ((i * 960 + n) / 48000))) for n in range(960)],
        )
        packets += enc.encode(frame)
    packets += enc.flush()
    assert packets, "Opus encoder produced no packets"
    pcm = fx.opus_decode_48k(packets)
    assert fx.peak(pcm) > 2000
    assert 12000 * 0.9 <= fx.zero_crossing_hz(pcm, 48000) <= 12000 * 1.1
