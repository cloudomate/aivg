"""Feature 005 / US1: the locally-provable slice of FR-004 (contract C1/C3).

aiortc/av are not local test deps, so the real WebRTC path is host-proven
(constitution V). What *is* deterministically testable without the media
stack — splitting an arbitrary PCM byte stream into uniform 20 ms frames,
remainder carry-over, and silence-padded flush — lives in
``hermes_satellite_adapter.media`` and is fully exercised here.
"""

import pytest

from aivg_core.webrtc.media import PcmFramer, frame_bytes

FRAME = 1920  # 20 ms, 48 kHz, mono, s16 (= 960 samples * 2 bytes)


def test_frame_bytes_default_matches_bridge_accounting():
    # HermesV013Bridge: 48 kHz, 0.02 s, s16 mono → 1920 B (SC-001 parity).
    assert frame_bytes(48000, 20) == FRAME
    assert frame_bytes(16000, 20) == 640
    assert frame_bytes(48000, 10) == 960


@pytest.mark.parametrize("bad", [0, -2, -1])
def test_frame_bytes_rejects_nonpositive_args(bad):
    with pytest.raises(ValueError):
        frame_bytes(bad, 20)
    with pytest.raises(ValueError):
        frame_bytes(48000, 0)
    with pytest.raises(ValueError):
        frame_bytes(48000, 20, channels=0)


@pytest.mark.parametrize("bad", [0, -2, 1, 1919, 3])
def test_framer_rejects_invalid_frame_size(bad):
    # Must be > 0 AND even (s16 sample aligned) — odd would split a sample.
    with pytest.raises(ValueError):
        PcmFramer(bad)


def test_exact_multiple_yields_whole_frames_no_remainder():
    f = PcmFramer(FRAME)
    out = f.push(b"\x01\x02" * (FRAME))  # exactly 2 frames
    assert len(out) == 2
    assert all(len(x) == FRAME for x in out)
    assert f.flush() is None  # nothing buffered


def test_partial_is_buffered_never_returned_then_carried_over():
    f = PcmFramer(FRAME)
    assert f.push(b"\x00" * (FRAME - 4)) == []  # sub-frame → nothing yet
    out = f.push(b"\x00" * 4 + b"\x11" * FRAME)  # completes #1, fills #2
    assert len(out) == 2
    assert all(len(x) == FRAME for x in out)
    assert f.flush() is None


def test_remainder_accumulates_across_many_small_pushes():
    f = PcmFramer(FRAME)
    produced = []
    for _ in range(FRAME // 2):  # 960 pushes of 2 bytes = exactly 1 frame
        produced += f.push(b"\xab\xcd")
    assert len(produced) == 1 and len(produced[0]) == FRAME
    assert f.flush() is None


def test_flush_zero_pads_partial_tail_to_full_frame():
    f = PcmFramer(FRAME)
    f.push(b"\x07" * 100)  # sub-frame remainder
    tail = f.flush()
    assert tail is not None
    assert len(tail) == FRAME
    assert tail[:100] == b"\x07" * 100
    assert tail[100:] == b"\x00" * (FRAME - 100)  # silence pad, never a tone
    assert f.flush() is None  # buffer cleared after flush


def test_flush_empty_returns_none():
    assert PcmFramer(FRAME).flush() is None


def test_no_push_ever_returns_a_partial_frame():
    f = PcmFramer(8)
    # Feed an irregular stream; every emitted frame MUST be exactly 8 bytes.
    stream = [b"abc", b"defghi", b"j", b"klmnopqrstuv", b"", b"wxyz"]
    for chunk in stream:
        for fr in f.push(chunk):
            assert len(fr) == 8
    tail = f.flush()
    assert tail is None or len(tail) == 8
