"""Deterministic test doubles — no live Hermes build, no aiortc, no hardware.

``FakeHermesBridge`` also proves the constitution-I boundary: the rest of the
package only ever sees this Protocol implementation.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from aivg_core.platforms.base import EndpointResult
from aivg_core.platforms.hermes.bridge import (
    AgentReply,
    AllProvidersUnavailable,
    EndpointSignal,
    SessionCtx,
)
from aivg_core.webrtc.session import MediaTransport

EOU = b"<EOU>"
SPEECH = b"<SPEECH>"
_MARKERS = (EOU, SPEECH)


class FakeHermesBridge:
    """Endpoint authority stays with the bridge (constitution I): markers in
    the audio frames decide turn boundaries, not any device-side VAD.

    Feature 015: dual-implements the
    :class:`aivg_core.platforms.base.AgentPlatform` Protocol so the
    session loop can accept this test double directly as its
    ``platform=`` argument (no bridge-→-platform adapter needed).
    The original bridge-shaped methods (``detect_endpoint``,
    ``stt_transcribe``, ``agent_turn``, ``tts_synthesize``) remain for
    tests that exercise the bridge surface directly.
    """

    # AgentPlatform Protocol: stable lowercase identifier.
    name: str = "fake-hermes"

    def __init__(
        self,
        *,
        agent_latency: float = 0.0,
        tts_latency: float = 0.0,
        empty_reply: bool = False,
        providers_down: bool = False,
        reply_prefix: str = "echo: ",
    ) -> None:
        self.agent_latency = agent_latency
        self.tts_latency = tts_latency
        self.empty_reply = empty_reply
        self.providers_down = providers_down
        self.reply_prefix = reply_prefix
        self.calls: list[str] = []

    # ----- bridge-shaped surface (preserved for tests that target it) -----

    async def detect_endpoint(
        self, pcm_stream: AsyncIterator[bytes], *, ctx: SessionCtx
    ) -> EndpointSignal:
        eou = started = False
        async for frame in pcm_stream:
            if frame == EOU:
                eou = True
            elif frame == SPEECH:
                started = True
        return EndpointSignal(end_of_utterance=eou, speech_started=started)

    async def stt_transcribe(self, pcm: bytes, *, ctx: SessionCtx) -> str:
        self.calls.append("stt")
        if self.providers_down:
            raise AllProvidersUnavailable("stt down")
        for m in _MARKERS:
            pcm = pcm.replace(m, b"")
        return pcm.decode("utf-8", "ignore")

    async def agent_turn(self, user_text: str, *, ctx: SessionCtx) -> AgentReply:
        self.calls.append("agent")
        await asyncio.sleep(self.agent_latency)
        if self.empty_reply:
            return AgentReply(text="", is_empty=True)
        return AgentReply(text=f"{self.reply_prefix}{user_text}")

    async def tts_synthesize(self, text: str, *, ctx: SessionCtx) -> bytes:
        self.calls.append("tts")
        await asyncio.sleep(self.tts_latency)
        if self.providers_down:
            raise AllProvidersUnavailable("tts down")
        return b"AUDIO:" + text.encode()

    # ----- AgentPlatform Protocol surface (feature 015) -------------------

    async def startup(self, *, gateway_config: dict) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        ctx = SessionCtx(device_id="-", session_id="-")
        return await self.stt_transcribe(audio, ctx=ctx)

    async def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        ctx = SessionCtx(device_id="-", session_id=session_id)
        reply = await self.agent_turn(text, ctx=ctx)
        if reply.is_empty or not (reply.text or "").strip():
            return
        yield reply.text

    async def synthesize(self, text: str) -> bytes:
        ctx = SessionCtx(device_id="-", session_id="-")
        return await self.tts_synthesize(text, ctx=ctx)

    async def endpoint(self, frame: bytes) -> EndpointResult:
        async def _one():
            yield frame
        sig = await self.detect_endpoint(
            _one(), ctx=SessionCtx(device_id="-", session_id="-")
        )
        return EndpointResult(
            end_of_utterance=sig.end_of_utterance,
            speech_started=sig.speech_started,
        )


class FakeTransport(MediaTransport):
    def __init__(self) -> None:
        self._in: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self.sent: list[bytes] = []
        self.stop_calls = 0
        self._state = "connected"
        self.closed = False

    # producer-side test helpers
    def push(self, *frames: bytes) -> None:
        for f in frames:
            self._in.put_nowait(f)

    def push_utterance(self, text: str) -> None:
        self._in.put_nowait(text.encode())
        self._in.put_nowait(EOU)

    def end_stream(self) -> None:
        self._in.put_nowait(None)

    # MediaTransport protocol
    async def receive(self) -> Optional[bytes]:
        return await self._in.get()

    async def send_audio(self, pcm: bytes) -> None:
        self.sent.append(pcm)

    async def stop_playback(self) -> None:
        self.stop_calls += 1

    @property
    def connection_state(self) -> str:
        return self._state

    def drop(self) -> None:
        self._state = "failed"
        self._in.put_nowait(None)

    async def close(self) -> None:
        self.closed = True
        self._state = "closed"
