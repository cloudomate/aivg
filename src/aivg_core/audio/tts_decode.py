"""Canonical TTS decode → 48 kHz s16 mono PCM (feature 023).

The gateway hands every voice transport the *raw, provider-encoded* TTS clip
(WAV/MP3/Opus/… at the provider's native rate). Each transport must normalize it
to the canonical internal representation — **signed-16-bit little-endian, mono,
48 kHz PCM** — before its wire-specific encoding. This is transport audio
*plumbing* (decode/resample), NOT STT/TTS (Constitution I).

All real work is done by **PyAV**, which is an in-process binding to ffmpeg's
libavformat/libavcodec/libswresample — container demux, codec decode, channel
downmix, and sample-rate conversion are ffmpeg's, not hand-rolled. This is the
single shared decode both the gRPC transport and ``webrtc/signaling.py`` use, so
they cannot diverge in codec/rate support (that divergence was the feature-023
bug). Mirrors ``webrtc/signaling.py:send_audio``.
"""

from __future__ import annotations

_SR = 48000  # canonical internal sample rate (matches OpusBridge / the pipeline)


def decode_tts_to_pcm48k(pcm: bytes) -> bytes:
    """Decode an encoded TTS clip to s16le mono 48 kHz PCM.

    Returns the concatenated PCM bytes. Returns ``b""`` (never raises) when the
    input is empty, too short to be audio, or not openable as a media container.
    On a mid-clip decode error, returns whatever was decoded before the error.
    """
    import io

    import av  # noqa: WPS433 - imported lazily, same as the WebRTC path

    if not pcm or len(pcm) < 16:
        return b""  # empty / sentinel (e.g. b"__PROVIDERS_UNAVAILABLE__") / tool-only
    try:
        container = av.open(io.BytesIO(pcm))
    except Exception:  # noqa: BLE001 - undecodable/sentinel: drop, never raise
        return b""

    resampler = av.AudioResampler(format="s16", layout="mono", rate=_SR)
    out = bytearray()
    try:
        for frame in container.decode(audio=0):
            resampled = resampler.resample(frame)
            for f in resampled if isinstance(resampled, (list, tuple)) else [resampled]:
                if f is None:
                    continue
                try:
                    b = f.planes[0].to_bytes()
                except AttributeError:
                    b = bytes(f.planes[0])
                out += b[: f.samples * 2]  # s16 mono → 2 bytes/sample
    except Exception:  # noqa: BLE001 - partial decode: keep what we have (FR-007)
        pass
    finally:
        container.close()
    return bytes(out)
