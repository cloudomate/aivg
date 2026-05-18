"""Pure PCM (re)framing — stdlib only, deterministically unit-testable.

Constitution I (NON-NEGOTIABLE): this module performs NO voice activity
detection, NO endpointing, NO STT/TTS. It only reshapes a byte stream into
fixed-size frames and pads a trailing remainder with digital silence.
Endpointing stays behind ``HermesBridge`` (server-side, Hermes-owned).

It exists so the one slice of feature 005 that *can* be proven without the
real media stack (FR-004 format/framing reconciliation) gets real local
coverage, while the aiortc/av glue is honestly host-proven (constitution V).
"""

from __future__ import annotations

from typing import List, Optional


def frame_bytes(
    sample_rate: int, ms: float, *, channels: int = 1, width: int = 2
) -> int:
    """Bytes in one ``ms``-millisecond PCM frame.

    Default (48 000 Hz, 20 ms, mono, 16-bit) = 1920 bytes — the frame size
    ``HermesV013Bridge`` accounts endpoint timing in (``frame_seconds`` 0.02,
    ``pcm_sample_rate`` 48 000, s16 mono).
    """
    if sample_rate <= 0 or ms <= 0 or channels <= 0 or width <= 0:
        raise ValueError("sample_rate, ms, channels, width must all be > 0")
    n = int(round(sample_rate * (ms / 1000.0))) * channels * width
    if n <= 0:
        raise ValueError("computed frame size must be > 0")
    return n


class PcmFramer:
    """Split an arbitrary PCM byte stream into uniform ``frame_size`` frames.

    ``push`` returns only *complete* frames; any partial remainder is buffered
    and prepended to the next ``push``. ``flush`` zero-pads a leftover
    remainder up to one full frame (digital silence only — never a synthesized
    tone, constitution I).
    """

    __slots__ = ("frame_size", "_buf")

    def __init__(self, frame_size: int) -> None:
        if frame_size <= 0:
            raise ValueError("frame_size must be > 0")
        if frame_size % 2 != 0:
            # s16 samples are 2 bytes; an odd frame size would split a sample.
            raise ValueError("frame_size must be even (16-bit sample aligned)")
        self.frame_size = frame_size
        self._buf = bytearray()

    def push(self, data: bytes) -> List[bytes]:
        """Append ``data``; return every newly-complete frame in order.

        Never returns a partial frame; the sub-frame remainder persists in the
        internal buffer for the next call.
        """
        if data:
            self._buf.extend(data)
        frames: List[bytes] = []
        fs = self.frame_size
        while len(self._buf) >= fs:
            frames.append(bytes(self._buf[:fs]))
            del self._buf[:fs]
        return frames

    def flush(self) -> Optional[bytes]:
        """Return the buffered remainder right-padded with silence to one full
        frame, or ``None`` if nothing is buffered. Clears the buffer."""
        if not self._buf:
            return None
        rem = bytes(self._buf)
        self._buf.clear()
        if len(rem) < self.frame_size:
            rem = rem + b"\x00" * (self.frame_size - len(rem))
        return rem
