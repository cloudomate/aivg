"""Feature 021 — US1 binding integration test.

Drives one full voice turn through the gRPC transport end-to-end against the
echo platform fixture, over a real ``grpc.aio`` channel on an ephemeral port.
No Hermes import (asserted by AST walk), mirroring the esphome transport's
binding test.
"""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import socket
import sys
from pathlib import Path

import pytest

pytest.importorskip("grpc")
import grpc  # noqa: E402

from aivg_core.logsink import LogSink  # noqa: E402
from aivg_core.platforms.base import PluginRegistry  # noqa: E402
from aivg_core.registry import Registry  # noqa: E402
from aivg_core.transports.grpc import GrpcAudioTransport  # noqa: E402
from aivg_core.transports.grpc._generated import audio_pb2, audio_pb2_grpc  # noqa: E402

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "platforms"


@pytest.fixture
def echo_platform(monkeypatch):
    monkeypatch.syspath_prepend(str(_FIXTURE_DIR.parent))
    spec = importlib.util.spec_from_file_location(
        "aivg_core.platforms.echo", _FIXTURE_DIR / "echo" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(sys.modules, "aivg_core.platforms.echo", mod)
    plat = PluginRegistry.load("echo")
    yield plat, mod
    sys.modules.pop("aivg_core.platforms.echo", None)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _client_frames(session_id: str, n_pcm: int):
    """Async generator of ClientFrames: header, PCM frames, end-of-utterance."""
    yield audio_pb2.ClientFrame(
        session=audio_pb2.SessionHeader(
            session_id=session_id,
            downstream_codec_pref=[audio_pb2.Codec.Value("CODEC_PCM_S16LE_16K")],
        )
    )
    pcm = b"\x12\x34" * 320  # 320 samples = 640 bytes @ 16 kHz (20 ms)
    for _ in range(n_pcm):
        yield audio_pb2.ClientFrame(pcm=audio_pb2.PcmChunk(samples=pcm))
        await asyncio.sleep(0)  # let the server-side reader drain
    yield audio_pb2.ClientFrame(
        event=audio_pb2.ClientEvent(kind=audio_pb2.ClientEvent.END_OF_UTTERANCE)
    )


@pytest.mark.asyncio
async def test_one_turn_over_grpc(echo_platform):
    import _audio_fixtures as fx

    plat, mod = echo_platform
    mod.PLATFORM.reply_deltas = ["echo says hi"]
    mod.PLATFORM.eou_after_frames = 5
    mod.PLATFORM._frame_count = 0
    # Feature 023: a real provider returns an ENCODED container at its native
    # rate (here a 24 kHz WAV); the transport decodes/resamples to 48 kHz before
    # queuing. (The echo default returns a non-audio string the decoder correctly
    # drops — that string encoded the pre-023 "treat bytes as PCM" bug.)
    _tone = fx.sine_wav(rate=24000, hz=440.0, ms=200)

    async def _synth(_text: str) -> bytes:
        return _tone

    mod.PLATFORM.synthesize = _synth

    registry = Registry()
    sink = LogSink()
    port = _free_port()
    transport = GrpcAudioTransport(
        registry=registry, platform=plat, sink=sink, host="127.0.0.1", port=port
    )
    await transport.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = audio_pb2_grpc.AudioStub(channel)
            audio_frames = []
            events = []
            transcripts = []
            call = stub.Stream(_client_frames("sess-1", n_pcm=10))
            async for sf in call:
                body = sf.WhichOneof("body")
                if body == "audio":
                    audio_frames.append(sf.audio)
                elif body == "event":
                    events.append(sf.event.kind)
                elif body == "transcript":
                    transcripts.append(sf.transcript.text)

        # Reply audio must have come back over the same stream.
        assert audio_frames, "no AudioChunk received over the gRPC stream"
        assert any(a.payload for a in audio_frames), "reply audio payload empty"
        assert all(
            a.codec == audio_pb2.Codec.Value("CODEC_PCM_S16LE_16K") for a in audio_frames
        ), "downstream codec not the explicit PCM default"
        # Feature 023: the ~200 ms decoded reply yields substantial 16 kHz PCM
        # (≈ 0.2 s · 16 kHz · 2 B ≈ 6400 B) — proof the clip was decoded+resampled,
        # not the handful of bytes the pre-023 raw-passthrough produced.
        total = sum(len(a.payload) for a in audio_frames)
        assert total > 2000, f"downstream audio implausibly small ({total} B) — not decoded"
        # Turn-timing events ride the same stream (FR-010).
        assert audio_pb2.ServerEvent.SPEAKING_STARTED in events
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_missing_session_header_is_rejected(echo_platform):
    """First frame not a SessionHeader -> FAILED_PRECONDITION (FR-006)."""
    plat, _ = echo_platform
    registry = Registry()
    sink = LogSink()
    port = _free_port()
    transport = GrpcAudioTransport(
        registry=registry, platform=plat, sink=sink, host="127.0.0.1", port=port
    )
    await transport.start()
    try:
        async def _bad_frames():
            # First frame is PCM, not a SessionHeader.
            yield audio_pb2.ClientFrame(pcm=audio_pb2.PcmChunk(samples=b"\x00\x00"))

        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = audio_pb2_grpc.AudioStub(channel)
            with pytest.raises(grpc.aio.AioRpcError) as ei:
                async for _ in stub.Stream(_bad_frames()):
                    pass
            assert ei.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    finally:
        await transport.stop()


def test_no_hermes_imports_in_this_test():
    """Constitutional binding: a platform-agnostic transport test MUST NOT
    import the Hermes plugin."""
    tree = ast.parse(Path(__file__).read_text())
    refs = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and "platforms.hermes" in node.module:
            refs.append(node.module)
        elif isinstance(node, ast.Import):
            refs += [a.name for a in node.names if "platforms.hermes" in a.name]
    assert refs == [], f"Hermes referenced: {refs}"
