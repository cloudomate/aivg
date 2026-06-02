"""Downstream-codec selection + encoding for the gRPC audio plane
(feature 021, FR-009 / research R-4).

The gateway chooses the downstream codec explicitly and stamps it on every
``AudioChunk`` — the client never has to assume. Phase 1 ships **PCM
s16le 16 kHz** as the safe default (passthrough); Opus is an opt-in
optimisation that degrades gracefully to PCM when no encoder is available,
so the MVP never blocks on libopus.
"""

from __future__ import annotations

from ._generated import audio_pb2

# Convenience aliases for the generated enum values.
CODEC_UNSPECIFIED = audio_pb2.Codec.Value("CODEC_UNSPECIFIED")
CODEC_OPUS = audio_pb2.Codec.Value("CODEC_OPUS")
CODEC_PCM_S16LE_16K = audio_pb2.Codec.Value("CODEC_PCM_S16LE_16K")

_NAME_TO_CODEC = {
    "pcm": CODEC_PCM_S16LE_16K,
    "opus": CODEC_OPUS,
}


def _opus_available() -> bool:
    """Whether an Opus encoder is importable. Phase-1 MVP ships without
    one, so this is False and selection falls back to PCM."""
    import importlib.util

    return importlib.util.find_spec("opuslib") is not None


def select_downstream_codec(
    prefs: "list[int]",
    configured_default: str = "pcm",
) -> int:
    """Pick the downstream codec.

    Order of preference (FR-009):
      1. the client's ``SessionHeader.downstream_codec_pref`` (best-first),
         honoured only for codecs the gateway can actually produce;
      2. the gateway's configured default (``transports.grpc.downstream_codec``);
      3. PCM s16le 16 kHz (always supported).

    Opus is only selectable when an encoder is present; otherwise it is
    skipped so a client preferring Opus on a gateway without libopus still
    gets working PCM audio rather than silence.
    """
    def _producible(codec: int) -> bool:
        if codec == CODEC_PCM_S16LE_16K:
            return True
        if codec == CODEC_OPUS:
            return _opus_available()
        return False

    for c in prefs or []:
        if _producible(c):
            return c
    default = _NAME_TO_CODEC.get((configured_default or "pcm").lower(), CODEC_PCM_S16LE_16K)
    if _producible(default):
        return default
    return CODEC_PCM_S16LE_16K


def encode(codec: int, pcm_s16le_16k: bytes) -> bytes:
    """Encode one 16 kHz s16le mono PCM chunk to the chosen codec's wire
    payload. PCM is a passthrough; Opus encodes when available, else falls
    back to returning PCM (the caller has already selected a producible
    codec via :func:`select_downstream_codec`, so this fallback is only a
    defensive belt)."""
    if codec == CODEC_PCM_S16LE_16K:
        return pcm_s16le_16k
    if codec == CODEC_OPUS and _opus_available():  # pragma: no cover - no encoder in MVP env
        import opuslib  # noqa: WPS433

        enc = opuslib.Encoder(16000, 1, opuslib.APPLICATION_VOIP)
        # 20 ms @ 16 kHz = 320 samples/frame; caller frames upstream.
        return enc.encode(pcm_s16le_16k, 320)
    return pcm_s16le_16k
