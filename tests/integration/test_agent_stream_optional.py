"""Feature 015 US3 (SC-003 / FR-006): the voice loop's preference for
``agent_stream`` over ``agent_step + synthesize`` is shape-detected at
Session construction and cached.

A platform that exposes ONLY the required ``agent_step`` MUST drive
one turn to completion via the synthesize fallback. A platform that
ALSO exposes ``agent_stream`` MUST use it (verifiable by spy: the
``synthesize`` count stays at zero for the streamed turn)."""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

import pytest

from aivg_core.logsink import LogSink
from aivg_core.models import VoiceSession
from aivg_core.platforms.base import EndpointResult
from aivg_core.webrtc.session import Session


_EOU = b"<EOU>"


class _PlatformBase:
    """Tiny in-test platform double — implements the required surface
    plus a deterministic endpoint marker (FR-005 server-side authority
    stays inside the platform, not the test transport)."""

    name = "stream-test"

    def __init__(self) -> None:
        self.synth_calls = 0

    async def startup(self, *, gateway_config: dict) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        return audio.replace(_EOU, b"").decode("utf-8", "ignore")

    async def synthesize(self, text: str) -> bytes:
        self.synth_calls += 1
        return f"clip:{text}".encode("utf-8")

    async def endpoint(self, frame: bytes) -> EndpointResult:
        return EndpointResult(end_of_utterance=(frame == _EOU))


class _StepOnlyPlatform(_PlatformBase):
    """Exposes only ``agent_step`` — voice loop MUST use synthesize."""

    async def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        for piece in ("hello ", "world."):
            yield piece


class _StreamPlatform(_PlatformBase):
    """Exposes BOTH ``agent_step`` and the optional ``agent_stream``
    extension — voice loop MUST prefer ``agent_stream``."""

    async def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        yield "step-fallback"  # MUST NOT be reached

    async def agent_stream(
        self,
        text: str,
        session_id: str,
        *,
        history=None,
        turn=None,
    ) -> AsyncIterator[bytes]:
        yield b"stream-audio-1"
        yield b"stream-audio-2"


@pytest.mark.asyncio
async def test_step_only_platform_uses_synthesize_fallback(tmp_path):
    from fakes import FakeTransport

    plat = _StepOnlyPlatform()
    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id="s", device_id="d"), tr, plat, sink
    )
    runner = asyncio.create_task(sess.run())
    tr.push(b"hi", _EOU)
    deadline = asyncio.get_event_loop().time() + 2.0
    while not tr.sent and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)
    # Step-only path: accumulated reply "hello world.", one synthesize call.
    assert plat.synth_calls == 1
    assert tr.sent[0] == b"clip:hello world."


@pytest.mark.asyncio
async def test_stream_platform_prefers_agent_stream(tmp_path):
    from fakes import FakeTransport

    plat = _StreamPlatform()
    sink = LogSink(gateway_log=tmp_path / "g.log")
    tr = FakeTransport()
    sess = Session(
        VoiceSession(session_id="s", device_id="d"), tr, plat, sink
    )
    runner = asyncio.create_task(sess.run())
    tr.push(b"hi", _EOU)
    # Wait for both stream chunks.
    deadline = asyncio.get_event_loop().time() + 2.0
    while len(tr.sent) < 2 and asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(0.005)
    tr.end_stream()
    await asyncio.wait_for(runner, timeout=2)
    # Streaming path: synthesize NEVER called.
    assert plat.synth_calls == 0
    assert tr.sent == [b"stream-audio-1", b"stream-audio-2"]
