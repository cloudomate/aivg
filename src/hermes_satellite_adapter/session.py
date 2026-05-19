"""Per-call voice session: the conversation state machine.

Transport-agnostic by design — it talks to a ``MediaTransport`` (aiortc in
production, an in-memory fake in tests), so the full loop, barge-in, and
reconnect behaviour are validated with no network or hardware.

State machine (data-model.md):
    idle → listening → thinking → speaking → listening
    speaking → listening   (barge-in, in-flight turn cancelled ≤300 ms)
    any → error → (teardown / re-offer) → idle

Constitution I: STT / endpointing / agent / TTS are reached ONLY via the
``HermesBridge`` seam. At most one turn in flight per session (FR-012).
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional, Protocol

from .hermes_bridge import (
    AgentReply,
    AllProvidersUnavailable,
    HermesBridge,
    SessionCtx,
)
from .logsink import LogSink
from .models import (
    ConversationTurn,
    LogLevel,
    LogSource,
    SessionState,
    TurnOutcome,
    VoiceSession,
)

# Barge-in budget (SC-003): playback must stop within this window.
BARGE_IN_DEADLINE_S = 0.3


class MediaTransport(Protocol):
    async def receive(self) -> Optional[bytes]:
        """Next inbound PCM frame, or None when the transport has closed."""

    async def send_audio(self, pcm: bytes) -> None:
        """Send one outbound PCM chunk to the peer."""

    async def stop_playback(self) -> None:
        """Promptly drop any queued/playing outbound audio (barge-in)."""

    @property
    def connection_state(self) -> str: ...

    async def close(self) -> None: ...


async def _reply_audio(bridge, text: str, ctx):
    """Yield reply audio in order. If the bridge can stream
    (``tts_stream`` — the real Hermes bridge), speak it sentence-by-sentence
    (feature 006); otherwise fall back to a single synthesized clip so the
    fake-transport conversation suite behaves byte-identically to before
    (FR-008 / SC-006 — no test changes)."""
    stream = getattr(bridge, "tts_stream", None)
    if stream is not None:
        async for audio in stream(text, ctx=ctx):
            yield audio
    else:
        yield await bridge.tts_synthesize(text, ctx=ctx)


class Session:
    def __init__(
        self,
        model: VoiceSession,
        transport: MediaTransport,
        bridge: HermesBridge,
        sink: LogSink,
        ui_sink: "Optional[callable]" = None,
    ) -> None:
        self.model = model
        self._transport = transport
        self._bridge = bridge
        self._sink = sink
        # Call-scoped UI events ONLY (partial transcript, listening/speaking,
        # barge-in). Production wires this to a single SCTP datachannel on the
        # voice PC. Durable control NEVER flows here (constitution III).
        self._ui_sink = ui_sink
        self._ctx = SessionCtx(device_id=model.device_id, session_id=model.session_id)
        self._stopped = asyncio.Event()
        self._pending_frame: Optional[bytes] = None

    def _ui(self, kind: str, **data) -> None:
        if self._ui_sink is None:
            return
        try:
            self._ui_sink({"type": kind, "session_id": self.model.session_id, **data})
        except Exception:
            pass  # a UI sink failure must never affect the voice path

    # --- helpers ---------------------------------------------------------
    def _log(self, level: LogLevel, source: LogSource, msg: str, **meta) -> None:
        self._sink.emit(self.model.device_id, level, source, msg, meta or None)

    def _set_state(self, state: SessionState) -> None:
        self.model.state = state
        self.model.touch()
        self.model.webrtc_state = self._transport.connection_state
        self._ui("state", state=state.value)

    async def _next_frame(self) -> Optional[bytes]:
        if self._pending_frame is not None:
            f, self._pending_frame = self._pending_frame, None
            return f
        return await self._transport.receive()

    async def _one(self, frame: bytes):
        async def gen():
            yield frame

        return gen()

    # --- main loop -------------------------------------------------------
    async def run(self) -> None:
        self._set_state(SessionState.LISTENING)
        try:
            while not self._stopped.is_set():
                utterance = await self._collect_utterance()
                if utterance is None:  # transport closed
                    break
                await self._handle_turn(utterance)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            self.model.last_error = str(exc)
            self._set_state(SessionState.ERROR)
            self._log(LogLevel.ERROR, LogSource.SYSTEM, f"session crashed: {exc}")
        finally:
            await self._transport.close()

    async def _collect_utterance(self) -> Optional[list[bytes]]:
        self._set_state(SessionState.LISTENING)
        buf: list[bytes] = []
        while not self._stopped.is_set():
            frame = await self._next_frame()
            if frame is None:
                return None
            buf.append(frame)
            sig = await self._bridge.detect_endpoint(await self._one(frame), ctx=self._ctx)
            if sig.end_of_utterance:
                return buf
        return None

    async def _handle_turn(self, utterance: list[bytes]) -> None:
        turn = ConversationTurn(
            turn_id=uuid.uuid4().hex, session_id=self.model.session_id
        )
        self.model.current_turn = turn
        try:
            self._set_state(SessionState.THINKING)
            turn.user_text = await self._bridge.stt_transcribe(
                b"".join(utterance), ctx=self._ctx
            )
            self._log(LogLevel.INFO, LogSource.ASR, "transcribed", text=turn.user_text)
            self._ui("partial_transcript", text=turn.user_text)

            pipeline = asyncio.create_task(self._respond(turn))
            watcher = asyncio.create_task(self._watch_for_bargein())
            done, pending = await asyncio.wait(
                {pipeline, watcher}, return_when=asyncio.FIRST_COMPLETED
            )

            if watcher in done and not pipeline.done():
                # Barge-in: cancel the in-flight reply within the deadline.
                t0 = time.monotonic()
                await self._transport.stop_playback()
                pipeline.cancel()
                try:
                    await asyncio.wait_for(pipeline, timeout=BARGE_IN_DEADLINE_S)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._pending_frame = watcher.result()
                turn.outcome = TurnOutcome.INTERRUPTED
                self._ui("barge_in")
                self._log(
                    LogLevel.INFO,
                    LogSource.SYSTEM,
                    "barge-in",
                    stop_ms=(time.monotonic() - t0) * 1000.0,
                )
            else:
                watcher.cancel()
                with_exc = pipeline.exception() if pipeline.done() else None
                if with_exc:
                    raise with_exc
                if turn.outcome is None:
                    turn.outcome = TurnOutcome.COMPLETED
        except AllProvidersUnavailable:
            turn.outcome = TurnOutcome.FAILED
            self.model.last_error = "all speech providers unavailable"
            self._log(
                LogLevel.ERROR, LogSource.SYSTEM, "all providers unavailable; notifying user"
            )
            await self._notify_failure()
        finally:
            turn.ended_at = time.time()
            self._log(
                LogLevel.INFO,
                LogSource.SYSTEM,
                "turn complete",
                outcome=turn.outcome.value if turn.outcome else None,
                latency_ms=turn.latency_ms,
            )
            self.model.current_turn = None
            self._set_state(SessionState.LISTENING)

    async def _respond(self, turn: ConversationTurn) -> None:
        # Feature 007: if the bridge can stream the answer AS the agent
        # composes it (``agent_stream`` — the real Hermes bridge consuming
        # Hermes's own draft-streaming hook), speak each sentence the moment
        # it is final, while the agent is still generating the rest
        # (FR-001/FR-002). SPEAKING is entered on the FIRST unit, not after
        # the whole reply. The fake bridge has no ``agent_stream`` → the
        # feature-006 path below runs verbatim, so the fake-transport suite
        # is byte-identical (FR-005 / FR-009 / SC-007).
        streamer = getattr(self._bridge, "agent_stream", None)
        if streamer is not None:
            spoke = False
            # Each send_audio blocks until that unit has drained (feature
            # 005), so the barge-in watcher stays live for the whole reply;
            # cancelling this task tears down agent_stream, which abandons
            # not-yet-played/synthesised units AND interrupts the still-
            # running agent (FR-004).
            async for audio in streamer(turn.user_text, ctx=self._ctx, turn=turn):
                if not spoke:
                    self._set_state(SessionState.SPEAKING)
                    spoke = True
                await self._transport.send_audio(audio)
            return  # empty / tool-only → never entered SPEAKING; to listening

        reply: AgentReply = await self._bridge.agent_turn(turn.user_text, ctx=self._ctx)
        turn.agent_text = reply.text
        if reply.is_empty or not reply.text:
            return  # empty / tool-only turn → clean return to listening
        self._set_state(SessionState.SPEAKING)
        # Feature 006: speak the reply in order, one speakable unit at a time.
        # Each send_audio blocks until that unit has drained (feature 005),
        # so the barge-in watcher stays live across the whole streamed reply
        # and cancelling this task abandons not-yet-played/synthesized units.
        async for audio in _reply_audio(self._bridge, reply.text, self._ctx):
            await self._transport.send_audio(audio)

    async def _watch_for_bargein(self) -> bytes:
        """Return the first inbound frame that Hermes flags as speech start."""
        while True:
            frame = await self._transport.receive()
            if frame is None:
                await asyncio.sleep(3600)  # transport gone; let pipeline win
            sig = await self._bridge.detect_endpoint(await self._one(frame), ctx=self._ctx)
            if sig.speech_started:
                return frame

    async def _notify_failure(self) -> None:
        try:
            await self._transport.send_audio(b"__PROVIDERS_UNAVAILABLE__")
        except Exception:
            pass

    # --- lifecycle -------------------------------------------------------
    async def stop(self) -> None:
        """Tear down on ICE/connection drop or shutdown; a fresh offer creates
        a new Session (FR-014 / design Appendix E)."""
        self._stopped.set()
        if self.model.current_turn and self.model.current_turn.outcome is None:
            self.model.current_turn.outcome = TurnOutcome.FAILED
        await self._transport.close()
