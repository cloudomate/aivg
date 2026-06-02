#!/usr/bin/env python3
"""Standalone gRPC voice-plane gateway for native-client smoke testing.

Runs feature 021's `GrpcAudioTransport` (aivg.satellite.v1.Audio/Stream) backed
by the in-repo **echo** agent platform — the same backend the gateway's pytest
integration tests use. It exercises the full audio path (mic PCM -> transcribe
-> agent -> synthesize -> reply audio) without needing a real Hermes/STT/TTS
stack, so a native client (the C++ libaivg-sat gRPC transport, feature 022) can
be smoke-tested against a real gateway-side server.

Usage:
    .venv/bin/python scripts/run_grpc_echo_gateway.py [--host 0.0.0.0] [--port 8645]

Echo behaviour: after `--eou-frames` upstream frames the turn fires; the reply
is `--reply` synthesized to bytes and streamed back as PCM AudioChunks.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))


def _load_echo_platform(reply: str, eou_frames: int):
    """Load the echo fixture as `aivg_core.platforms.echo` (same trick the
    pytest fixtures use) and configure its turn behaviour."""
    fixture = ROOT / "tests" / "fixtures" / "platforms" / "echo" / "__init__.py"
    spec = importlib.util.spec_from_file_location("aivg_core.platforms.echo", fixture)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules["aivg_core.platforms.echo"] = mod
    from aivg_core.platforms.base import PluginRegistry

    plat = PluginRegistry.load("echo")
    mod.PLATFORM.reply_deltas = [reply]
    mod.PLATFORM.eou_after_frames = eou_frames
    mod.PLATFORM._frame_count = 0

    # The echo fixture's synthesize() returns ASCII bytes (`echo:synth(...)`),
    # not valid PCM — the gateway's 48k->16k resampler (audioop.ratecv, width 2)
    # rejects odd-length non-PCM data, so no AudioChunks reach the client. A
    # real TTS returns valid PCM; substitute ~300 ms of 48 kHz mono s16 silence
    # so the gateway streams AudioChunks a native client can actually receive.
    async def _pcm_synth(_text: str) -> bytes:
        return b"\x00\x00" * (48000 * 300 // 1000)  # 300 ms @ 48 kHz s16 mono

    mod.PLATFORM.synthesize = _pcm_synth
    return plat


async def _main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8645)
    ap.add_argument("--reply", default="hello from the echo gateway")
    ap.add_argument("--eou-frames", type=int, default=5)
    args = ap.parse_args()

    from aivg_core.logsink import LogSink
    from aivg_core.registry import Registry
    from aivg_core.transports.grpc import GrpcAudioTransport

    plat = _load_echo_platform(args.reply, args.eou_frames)
    transport = GrpcAudioTransport(
        registry=Registry(), platform=plat, sink=LogSink(),
        host=args.host, port=args.port,
    )
    await transport.start()
    print(f"grpc echo gateway: Audio.Stream on {args.host}:{args.port} "
          f"(eou_after={args.eou_frames}, reply={args.reply!r})", flush=True)
    try:
        await asyncio.Event().wait()  # run until killed
    finally:
        await transport.stop()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
