"""Feature 021 — unit tests for downstream codec selection/encoding (T016)."""

from __future__ import annotations

import pytest

pytest.importorskip("grpc")

from aivg_core.transports.grpc import codec  # noqa: E402


def test_pref_pcm_selected():
    assert codec.select_downstream_codec([codec.CODEC_PCM_S16LE_16K], "pcm") == codec.CODEC_PCM_S16LE_16K


def test_pref_opus_without_encoder_falls_back_to_pcm():
    # MVP env has no opuslib -> Opus is not producible -> fall through to the
    # configured default (pcm), never silence.
    assert codec.select_downstream_codec([codec.CODEC_OPUS], "pcm") == codec.CODEC_PCM_S16LE_16K


def test_empty_prefs_use_configured_default():
    assert codec.select_downstream_codec([], "pcm") == codec.CODEC_PCM_S16LE_16K


def test_default_opus_without_encoder_falls_back_to_pcm():
    assert codec.select_downstream_codec([], "opus") == codec.CODEC_PCM_S16LE_16K


def test_pcm_encode_is_passthrough():
    payload = b"\x01\x02\x03\x04"
    assert codec.encode(codec.CODEC_PCM_S16LE_16K, payload) == payload
