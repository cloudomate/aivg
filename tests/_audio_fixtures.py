"""Reusable in-memory audio fixtures for feature 023 tests.

Synthesizes *encoded containers* (WAV) so tests exercise the real decode path —
the bug was that the gRPC transport treated encoded bytes as if they were raw
48 kHz PCM. Also provides a deliberately-undecodable blob.

Stdlib only (``wave`` + ``struct`` + ``math``); no PyAV needed to *produce* the
input, which keeps the fixtures independent of the code under test.
"""

from __future__ import annotations

import io
import math
import struct
import wave


def sine_wav(*, rate: int = 24000, hz: float = 440.0, ms: int = 200, channels: int = 1,
             amplitude: int = 8000) -> bytes:
    """A mono/stereo s16 WAV sine at ``rate`` Hz (default 24 kHz — NOT 48 kHz, so
    decoding must resample). Returns the full WAV container bytes."""
    n = int(rate * ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frames = bytearray()
        for i in range(n):
            s = int(amplitude * math.sin(2 * math.pi * hz * (i / rate)))
            frames += struct.pack("<h", s) * channels
        w.writeframes(bytes(frames))
    return buf.getvalue()


def stereo_wav(*, rate: int = 24000, hz: float = 440.0, ms: int = 200) -> bytes:
    """A 2-channel WAV; decoding must downmix to mono."""
    return sine_wav(rate=rate, hz=hz, ms=ms, channels=2)


def corrupt_blob() -> bytes:
    """Non-container bytes (>= 16 B) that ``av.open`` cannot decode."""
    return b"\x00\x01\x02\x03not-a-media-container\xff\xfe" * 4


def zero_crossing_hz(pcm_s16le: bytes, rate: int) -> float:
    """Estimate the dominant frequency of a clean s16 mono tone via zero-crossing
    rate (crossings/sec ≈ 2·f). Good enough to assert pitch was preserved."""
    a = struct.unpack("<%dh" % (len(pcm_s16le) // 2), pcm_s16le[: len(pcm_s16le) // 2 * 2])
    if len(a) < 2:
        return 0.0
    crossings = sum(1 for i in range(1, len(a)) if (a[i - 1] < 0) != (a[i] < 0))
    duration = len(a) / rate
    return (crossings / 2.0) / duration if duration else 0.0


def peak(pcm_s16le: bytes) -> int:
    """Max |sample| of s16 mono PCM (0 ⇒ silence)."""
    a = struct.unpack("<%dh" % (len(pcm_s16le) // 2), pcm_s16le[: len(pcm_s16le) // 2 * 2])
    return max((abs(s) for s in a), default=0)
