"""Feature 025 — gateway-side upstream Opus mic arm.

The gateway decodes an Opus `ClientFrame.opus` mic packet to 48 kHz and feeds the
same `_in` queue the raw-PCM path feeds (so STT, which runs at 48 kHz, sees
equivalent audio). Covers: decode → equivalent 48 kHz audio (US1), bandwidth
win (SC-002), and malformed-packet robustness (US3/FR-007).
"""

from __future__ import annotations

import math
import struct

import pytest

pytest.importorskip("grpc")
pytest.importorskip("av")

from aivg_core.transports.grpc.codec import CODEC_PCM_S16LE_16K  # noqa: E402
from aivg_core.transports.grpc.media_adapter import GrpcMediaAdapter  # noqa: E402

import _audio_fixtures as fx  # noqa: E402

_SR = 48000


def _tone_pcm48(hz: float, ms: int, amp: int = 8000) -> bytes:
    n = int(_SR * ms / 1000)
    return struct.pack("<%dh" % n, *[int(amp * math.sin(2 * math.pi * hz * (i / _SR))) for i in range(n)])


def _opus_packets(pcm48: bytes) -> "list[bytes]":
    """Encode 48 kHz PCM into 20 ms Opus packets the way a *device mic* would —
    VOIP at a low voice bitrate (not the downstream music-quality encoder)."""
    import av
    import fractions

    enc = av.codec.CodecContext.create("libopus", "w")
    enc.sample_rate = 48000
    enc.format = "s16"
    enc.layout = "mono"
    enc.bit_rate = 24000  # voice — ~10x smaller than 16 kHz PCM
    try:
        enc.options = {"application": "voip"}
    except Exception:  # noqa: BLE001 - option name varies by ffmpeg build
        pass
    enc.open()
    packets: list[bytes] = []
    frame = 1920  # 960 samples * 2 bytes = 20 ms @ 48 kHz
    pts = 0
    for off in range(0, len(pcm48) - frame + 1, frame):
        seg = pcm48[off:off + frame]
        af = av.AudioFrame(format="s16", layout="mono", samples=960)
        af.planes[0].update(seg)
        af.sample_rate = 48000
        af.pts = pts
        af.time_base = fractions.Fraction(1, 48000)
        pts += 960
        packets += [bytes(p) for p in enc.encode(af)]
    packets += [bytes(p) for p in enc.encode(None)]
    return packets


async def _drain_in(a: GrpcMediaAdapter) -> bytes:
    out = bytearray()
    while not a._in.empty():
        f = a._in.get_nowait()
        if f:
            out += f
    return bytes(out)


@pytest.mark.asyncio
async def test_opus_mic_arm_decodes_to_48k_for_stt():
    """US1: an Opus mic packet stream decodes to 48 kHz audio on `_in` that
    reconstructs the spoken tone — what STT consumes (equivalent to PCM)."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    src = _tone_pcm48(440.0, 300)
    for pkt in _opus_packets(src):
        a.push_inbound_opus(pkt)
    pcm = await _drain_in(a)
    assert pcm, "no decoded audio reached the Session queue"
    assert len(pcm) % 1920 == 0, "decoded audio must be 20 ms / 48 kHz frames"
    assert fx.peak(pcm) > 2000, "decoded mic audio is silence/garbage"
    assert 440.0 * 0.85 <= fx.zero_crossing_hz(pcm, _SR) <= 440.0 * 1.15, "tone not preserved"


def test_opus_mic_uplink_is_smaller_than_pcm():
    """SC-002: the Opus mic uplink for an utterance is >= ~5x fewer bytes than
    the equivalent raw 16 kHz PCM."""
    src48 = _tone_pcm48(300.0, 1000)  # 1 s of speech-band tone
    opus_bytes = sum(len(p) for p in _opus_packets(src48))
    pcm16_bytes = int(16000 * 1.0) * 2  # 1 s of 16 kHz s16 mono
    assert opus_bytes * 5 <= pcm16_bytes, f"opus {opus_bytes} B vs pcm16 {pcm16_bytes} B (<5x)"


@pytest.mark.asyncio
async def test_malformed_opus_packet_dropped_without_raising():
    """US3/FR-007: a corrupt Opus packet is a localized gap, not a crash."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    a.push_inbound_opus(b"\x00\x01not-an-opus-packet\xff")  # must not raise
    assert a._in.empty(), "a malformed packet must not enqueue audio"
    # The adapter still works for a subsequent valid packet stream.
    for pkt in _opus_packets(_tone_pcm48(440.0, 60)):
        a.push_inbound_opus(pkt)
    assert not a._in.empty(), "adapter must recover after a bad packet"


def test_pcm_push_inbound_unchanged():
    """US2: the raw-PCM path is untouched — a 16 kHz frame still upsamples to a
    48 kHz/1920 B Session frame."""
    a = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
    for _ in range(3):
        a.push_inbound(b"\x10\x20" * 320)  # 640 B = 20 ms @ 16 kHz
    assert not a._in.empty()
    f = a._in.get_nowait()
    assert len(f) == 1920, "PCM path must still produce 48 kHz/20 ms frames"
