"""Feature 021 — US1 reliability: a gateway restart / stream drop does NOT
require renegotiation or a manual restart; the next turn opens a fresh
stream and completes (FR-019/FR-020, acceptance scenarios 4/5).
"""

from __future__ import annotations

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


async def _full_turn_frames(session_id: str):
    yield audio_pb2.ClientFrame(session=audio_pb2.SessionHeader(session_id=session_id))
    pcm = b"\x12\x34" * 320
    for _ in range(10):
        yield audio_pb2.ClientFrame(pcm=audio_pb2.PcmChunk(samples=pcm))
        await asyncio.sleep(0)
    yield audio_pb2.ClientFrame(
        event=audio_pb2.ClientEvent(kind=audio_pb2.ClientEvent.END_OF_UTTERANCE)
    )


async def _complete_turn(port: int) -> int:
    audio = 0
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
        stub = audio_pb2_grpc.AudioStub(ch)
        async for sf in stub.Stream(_full_turn_frames("s")):
            if sf.WhichOneof("body") == "audio":
                audio += 1
    return audio


@pytest.mark.asyncio
async def test_gateway_restart_recovers_on_next_turn(echo_platform):
    import _audio_fixtures as fx

    plat, mod = echo_platform
    mod.PLATFORM.reply_deltas = ["hi"]
    mod.PLATFORM.eou_after_frames = 5
    mod.PLATFORM._frame_count = 0
    # Feature 023: provider TTS is a decodable container (a 24 kHz WAV), so the
    # post-restart turn produces real decoded downstream audio.
    _tone = fx.sine_wav(rate=24000, hz=440.0, ms=120)

    async def _synth(_text: str) -> bytes:
        return _tone

    mod.PLATFORM.synthesize = _synth

    registry = Registry()
    sink = LogSink()
    port = _free_port()

    # First gateway instance: open a stream, start streaming, then "restart"
    # the gateway (stop the server) mid-session.
    t1 = GrpcAudioTransport(registry=registry, platform=plat, sink=sink, host="127.0.0.1", port=port)
    await t1.start()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
        stub = audio_pb2_grpc.AudioStub(ch)

        async def _partial():
            # Keep the request stream OPEN (don't end it) so the session is
            # genuinely mid-flight when the gateway is killed underneath it.
            yield audio_pb2.ClientFrame(session=audio_pb2.SessionHeader(session_id="s0"))
            yield audio_pb2.ClientFrame(pcm=audio_pb2.PcmChunk(samples=b"\x00\x00" * 320))
            await asyncio.sleep(5.0)

        call = stub.Stream(_partial())
        await asyncio.sleep(0.05)  # ensure the call is live
        await t1.stop()  # gateway "restart" — kill the server mid-session
        # The in-flight call terminates promptly (the client never hangs);
        # whether it surfaces as an RPC error or a clean close is incidental —
        # the contract that matters is recovery on the next turn, below.
        try:
            async for _ in call:
                pass
        except grpc.aio.AioRpcError:
            pass

    # New gateway instance on the SAME port (a real restart). The next turn
    # must complete with no renegotiation and no manual intervention.
    mod.PLATFORM._frame_count = 0
    t2 = GrpcAudioTransport(registry=registry, platform=plat, sink=sink, host="127.0.0.1", port=port)
    await t2.start()
    try:
        audio_frames = await _complete_turn(port)
        assert audio_frames > 0, "post-restart turn produced no audio"
    finally:
        await t2.stop()
