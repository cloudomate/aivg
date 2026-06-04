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
    """Whether a 48 kHz Opus encoder is available. Uses PyAV's bundled libopus
    (PyAV is already a hard dependency), so Opus downstream needs no extra
    package — it is effectively always producible (feature 024)."""
    try:
        import av  # noqa: WPS433

        av.codec.Codec("libopus", "w")
        return True
    except Exception:  # noqa: BLE001 - any import/codec failure => not producible
        return False


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


def encode(codec: int, pcm: bytes) -> bytes:
    """Wire payload for a raw-PCM downstream codec — a passthrough. Opus
    downstream is encoded by the stateful :class:`OpusEncoder48k` in the media
    adapter (feature 024), not here, so this only handles PCM."""
    return pcm


class OpusEncoder48k:
    """Stateful 48 kHz mono Opus encoder (libopus via PyAV — already a project
    dependency, so no extra package is needed).

    The gateway pipeline is native 48 kHz; encoding Opus directly at 48 kHz —
    rather than downsampling to 16 kHz first — preserves the full audio band for
    a device that decodes Opus at 48 kHz (feature 024). Opus is internally always
    48 kHz, so this is wire-compatible: a 16 kHz-decoder device still decodes the
    same packets (to 16 kHz); it simply now receives full-band audio.

    Feed exactly one 20 ms / 960-sample s16 mono frame per :meth:`encode` call;
    encoder priming may delay the first packet, so each call returns
    zero-or-more Opus packets. :meth:`flush` drains the tail at session end.
    """

    SR = 48000

    def __init__(self) -> None:
        import av  # noqa: WPS433

        self._av = av
        ctx = av.codec.CodecContext.create("libopus", "w")
        ctx.sample_rate = self.SR
        ctx.format = "s16"
        ctx.layout = "mono"
        ctx.open()
        self._ctx = ctx
        self._pts = 0

    def encode(self, pcm48: bytes) -> "list[bytes]":
        import fractions  # noqa: WPS433

        samples = len(pcm48) // 2
        frame = self._av.AudioFrame(format="s16", layout="mono", samples=samples)
        frame.planes[0].update(pcm48)
        frame.sample_rate = self.SR
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, self.SR)
        self._pts += samples
        return [bytes(p) for p in self._ctx.encode(frame)]

    def flush(self) -> "list[bytes]":
        """Drain any buffered packets (call once when the session closes)."""
        return [bytes(p) for p in self._ctx.encode(None)]


class OpusDecoder48k:
    """Stateful 48 kHz mono Opus decoder (libopus via PyAV). Decodes one upstream
    Opus mic packet to 48 kHz s16 mono PCM (feature 025). Returns ``b""`` (never
    raises) on a malformed/undecodable packet so a bad frame is a localized audio
    gap, not a session failure (FR-007)."""

    SR = 48000

    def __init__(self) -> None:
        import av  # noqa: WPS433

        self._av = av
        ctx = av.codec.CodecContext.create("libopus", "r")
        ctx.sample_rate = self.SR
        ctx.format = "s16"
        ctx.layout = "mono"
        ctx.open()
        self._ctx = ctx

    def decode(self, payload: bytes) -> bytes:
        if not payload:
            return b""
        try:
            out = bytearray()
            for frame in self._ctx.decode(self._av.Packet(payload)):
                b = bytes(frame.planes[0])
                out += b[: frame.samples * 2]  # s16 mono -> 2 bytes/sample
            return bytes(out)
        except Exception:  # noqa: BLE001 - drop a bad packet (FR-007), never raise
            return b""
