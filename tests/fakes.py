"""Deterministic test doubles — no live Hermes build, no aiortc, no hardware.

``FakeHermesBridge`` also proves the constitution-I boundary: the rest of the
package only ever sees this Protocol implementation.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator, Optional

from hermes_satellite_adapter.hermes_bridge import (
    AgentReply,
    AllProvidersUnavailable,
    EndpointSignal,
    SessionCtx,
)
from hermes_satellite_adapter.session import MediaTransport

EOU = b"<EOU>"
SPEECH = b"<SPEECH>"
_MARKERS = (EOU, SPEECH)


class FakeHermesBridge:
    """Endpoint authority stays with the bridge (constitution I): markers in
    the audio frames decide turn boundaries, not any device-side VAD."""

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
