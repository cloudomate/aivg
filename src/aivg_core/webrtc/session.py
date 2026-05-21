"""Per-call voice session: the conversation state machine.

Transport-agnostic by design — it talks to a ``MediaTransport`` (aiortc in
production, an in-memory fake in tests), so the full loop, barge-in, and
reconnect behaviour are validated with no network or hardware.

State machine (data-model.md):
    idle → listening → thinking → speaking → listening
    speaking → listening   (barge-in, in-flight turn cancelled ≤300 ms)
    any → error → (teardown / re-offer) → idle

Constitution I: STT / endpointing / agent / TTS are reached ONLY via the
:class:`~aivg_core.platforms.base.AgentPlatform` Protocol — never by
naming a specific plugin. At most one turn in flight per session
(FR-012). Feature 015 closed the runtime side of this seam.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Optional, Protocol

from ..platforms.base import AgentPlatform, AllProvidersUnavailable, EndpointResult
from ..logsink import LogSink
from ..turnlatency import build_breakdown
from ..models import (
    ConversationTurn,
    LogLevel,
    LogSource,
    SessionState,
    TurnOutcome,
    VoiceSession,
)

# Barge-in budget (SC-003): playback must stop within this window.
BARGE_IN_DEADLINE_S = 0.3


# Feature 010 — instrumentation verbosity is a CONFIG knob (constitution
# IV / FR-011/FR-012): the existing `satellite:` block's
# `default_config.latency_log` ∈ {full, summary, off}, default "summary"
# (always-on lightweight). Read once via the EXISTING loader — no new
# config file/loader, no hardcoded mode. Unreadable config (e.g. the
# fake-transport test env) → safe default, never raises.
_LAT_MODE_CACHE: "Optional[str]" = None


def _latency_log_mode() -> str:
    global _LAT_MODE_CACHE
    if _LAT_MODE_CACHE is None:
        mode = "summary"
        try:
            from ..config import load_adapter_config

            dc = load_adapter_config().default_config or {}
            m = str(dc.get("latency_log", "summary")).strip().lower()
            if m in ("full", "summary", "off"):
                mode = m
        except Exception:  # noqa: BLE001 - never let config break the turn
            mode = "summary"
        _LAT_MODE_CACHE = mode
    return _LAT_MODE_CACHE


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


async def _reply_audio(platform: "AgentPlatform", text: str):
    """Yield reply audio in order. Feature 015: the platform contract
    surfaces just ``synthesize(text) -> bytes`` (single clip) — older
    Hermes-bridge-flavoured ``tts_stream`` is still useful for
    per-sentence pipelining, so we shape-detect it as a plugin-internal
    optimisation (Hermes exposes it via the bridge that
    ``HermesAgentPlatform`` wraps). Plugins that lack it just produce
    one clip per call."""
    stream = getattr(platform, "tts_stream", None)
    if stream is not None:
        async for audio in stream(text):
            yield audio
    else:
        yield await platform.synthesize(text)


class Session:
    def __init__(
        self,
        model: VoiceSession,
        transport: MediaTransport,
        platform: AgentPlatform,
        sink: LogSink,
        ui_sink: "Optional[callable]" = None,
    ) -> None:
        self.model = model
        self._transport = transport
        # Feature 015 / FR-002: Session consumes the canonical
        # AgentPlatform Protocol; no platform-specific symbol crosses
        # this constructor.
        self._platform = platform
        # Cache the optional feature-008 ``agent_stream`` extension at
        # session construction (FR-006). The per-turn responder checks
        # this attribute instead of calling ``getattr`` on every turn.
        self._agent_stream = getattr(platform, "agent_stream", None)
        self._sink = sink
        # Call-scoped UI events ONLY (partial transcript, listening/speaking,
        # barge-in). Production wires this to a single SCTP datachannel on the
        # voice PC. Durable control NEVER flows here (constitution III).
        self._ui_sink = ui_sink
        self._stopped = asyncio.Event()
        self._pending_frame: Optional[bytes] = None
        # Sticky EOF flag: set when an inbound ``None`` (transport
        # closed) was already consumed by the barge-in watcher and
        # must still be reported to the main loop's next receive.
        # Without this, the watcher silently swallowed the EOF and the
        # main loop would block forever in :meth:`_next_frame`.
        self._eof_seen: bool = False

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

    @staticmethod
    def _stamp(turn: "ConversationTurn", name: str) -> None:
        """Record a stage instant once (first write wins — idempotent so a
        retried/duplicated seam never skews the breakdown). FR-007: pure
        timestamp capture, no behaviour/content change."""
        turn.lat_instants.setdefault(name, time.monotonic())

    def _emit_latency(self, turn: "ConversationTurn") -> None:
        """Feature 010: emit ONE consolidated per-turn latency breakdown via
        the existing LogSink (FR-001/FR-002). Always called on turn end
        (success/error/barge-in/empty); tolerant of missing instants
        (FR-008). Verbosity from the config knob; never raises."""
        mode = _latency_log_mode()
        if mode == "off":
            return
        try:
            b = build_breakdown(turn.lat_instants)
            if not b.stages:
                return  # nothing measured (e.g. failed before endpoint)
            fields = b.as_log_fields()
            if mode == "summary":
                fields = {
                    k: fields[k]
                    for k in ("total_ms", "dominant", "complete")
                    if k in fields
                }
            self._log(LogLevel.INFO, LogSource.SYSTEM, "turn latency", **fields)
        except Exception:  # noqa: BLE001 - instrumentation must never break a turn
            pass

    def _set_state(self, state: SessionState) -> None:
        self.model.state = state
        self.model.touch()
        self.model.webrtc_state = self._transport.connection_state
        self._ui("state", state=state.value)

    async def _next_frame(self) -> Optional[bytes]:
        if self._pending_frame is not None:
            f, self._pending_frame = self._pending_frame, None
            return f
        if self._eof_seen:
            return None  # consume the sticky EOF once, then resume normal recv
        return await self._transport.receive()

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
            sig: EndpointResult = await self._platform.endpoint(frame)
            if sig.end_of_utterance:
                return buf
        return None

    async def _handle_turn(self, utterance: list[bytes]) -> None:
        turn = ConversationTurn(
            turn_id=uuid.uuid4().hex, session_id=self.model.session_id
        )
        self.model.current_turn = turn
        # Feature 010: the endpoint was detected the instant
        # _collect_utterance returned this utterance. end_of_speech is
        # silence_duration earlier — that value is INHERITED from Hermes
        # config via the bridge's silence rule (FR-011: not hardcoded
        # here); if the bridge does not expose it (fake), omit it and the
        # breakdown simply starts at endpoint_detected (FR-008).
        _ep = time.monotonic()
        turn.lat_instants["endpoint_detected"] = _ep
        # Feature 010 stamping: the silence_secs reach is plugin-internal
        # (Hermes config → bridge → platform). Read via the agreed
        # private attribute name the Hermes plugin exposes; absent on
        # other platforms → omit the field, breakdown starts at
        # endpoint_detected (FR-008).
        _sil = getattr(self._platform, "_silence_secs", None)
        if isinstance(_sil, (int, float)) and _sil >= 0:
            turn.lat_instants["end_of_speech"] = _ep - float(_sil)
        try:
            self._set_state(SessionState.THINKING)
            # Inbound PCM was decoded to s16 mono @ 48000 Hz by the
            # transport (see signaling._SR); pass that rate explicitly.
            turn.user_text = await self._platform.transcribe(
                b"".join(utterance), sample_rate=48000
            )
            self._stamp(turn, "stt_done")
            self._log(LogLevel.INFO, LogSource.ASR, "transcribed", text=turn.user_text)
            self._ui("partial_transcript", text=turn.user_text)

            pipeline = asyncio.create_task(self._respond(turn))
            watcher = asyncio.create_task(self._watch_for_bargein())
            done, pending = await asyncio.wait(
                {pipeline, watcher}, return_when=asyncio.FIRST_COMPLETED
            )

            if watcher in done and not pipeline.done():
                w_frame = watcher.result()
                if w_frame is None:
                    # Transport closed mid-turn. Cancel the pipeline,
                    # mark the turn FAILED, and let the main loop pick
                    # up the EOF on its next receive (no _pending_frame
                    # stash — we don't fabricate a frame).
                    pipeline.cancel()
                    try:
                        await asyncio.wait_for(pipeline, timeout=BARGE_IN_DEADLINE_S)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    turn.outcome = TurnOutcome.FAILED
                else:
                    # Barge-in: cancel the in-flight reply within the deadline.
                    t0 = time.monotonic()
                    await self._transport.stop_playback()
                    pipeline.cancel()
                    try:
                        await asyncio.wait_for(pipeline, timeout=BARGE_IN_DEADLINE_S)
                    except (asyncio.CancelledError, asyncio.TimeoutError):
                        pass
                    self._pending_frame = w_frame
                    turn.outcome = TurnOutcome.INTERRUPTED
                    self._ui("barge_in")
                    self._log(
                        LogLevel.INFO,
                        LogSource.SYSTEM,
                        "barge-in",
                        stop_ms=(time.monotonic() - t0) * 1000.0,
                    )
            else:
                # Pipeline won the race. Cancel the watcher and reap
                # whatever frame it may have already consumed from the
                # transport — otherwise an inbound EOF / speech-start
                # would be silently swallowed and the next
                # ``_collect_utterance`` could block forever (observed
                # under concurrent test load).
                watcher.cancel()
                eaten: Optional[bytes] = None
                eof_eaten = False
                try:
                    if watcher.done():
                        # Watcher had already finished before cancel —
                        # reap its result.
                        eaten = watcher.result()
                    else:
                        eaten = await watcher  # may raise CancelledError
                except asyncio.CancelledError:
                    eaten = None
                except Exception:  # noqa: BLE001
                    eaten = None
                else:
                    if eaten is None:
                        eof_eaten = True
                if eaten is not None:
                    # The watcher consumed a real frame just before
                    # cancellation landed (speech-start while pipeline
                    # was wrapping up). Re-stash for the next turn.
                    self._pending_frame = eaten
                if eof_eaten:
                    self._eof_seen = True
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
            self._emit_latency(turn)  # feature 010 — one breakdown per turn
            self.model.current_turn = None
            self._set_state(SessionState.LISTENING)

    async def _respond(self, turn: ConversationTurn) -> None:
        # Feature 015 / FR-006: if the platform exposes the OPTIONAL
        # ``agent_stream`` extension (feature 008 delta-+ per-sentence
        # synth path — the Hermes plugin forwards to the bridge here),
        # speak each sentence the moment it is final while the agent is
        # still generating the rest. Caching is in ``__init__`` so this
        # per-turn site never pays a hasattr cost. Plugins without the
        # extension fall through to the ``agent_step + synthesize`` path
        # below — byte-identical to the feature-006 baseline for the
        # fake-transport suite (FR-005 / FR-009 / SC-007).
        streamer = self._agent_stream
        if streamer is not None:
            spoke = False
            # Each send_audio blocks until that unit has drained
            # (feature 005), so the barge-in watcher stays live for the
            # whole reply; cancelling this task tears down agent_stream,
            # which abandons not-yet-played/synthesised units AND
            # interrupts the still-running agent (FR-004).
            async for audio in streamer(
                turn.user_text, session_id=self.model.session_id, turn=turn
            ):
                if not spoke:
                    self._set_state(SessionState.SPEAKING)
                    spoke = True
                    self._stamp(turn, "first_audio_delivered")  # feature 010
                await self._transport.send_audio(audio)
            return  # empty / tool-only → never entered SPEAKING; to listening

        # Baseline path: accumulate text deltas, then synthesise.
        # R-2 empty-reply convention: accumulated ``.strip() == ""``
        # means tool-only / empty turn → skip synthesis cleanly
        # (constitution I — no Piper fallback for empty replies).
        acc: list[str] = []
        async for delta in self._platform.agent_step(
            turn.user_text, self.model.session_id
        ):
            acc.append(delta)
        reply_text = "".join(acc)
        turn.agent_text = reply_text
        if not reply_text.strip():
            return  # empty / tool-only turn → clean return to listening
        self._set_state(SessionState.SPEAKING)
        # Per-sentence pipelining if the platform exposes ``tts_stream``;
        # otherwise one synthesis call. Each ``send_audio`` blocks until
        # that unit drains (feature 005) so barge-in stays live.
        _spoke = False
        async for audio in _reply_audio(self._platform, reply_text):
            if not _spoke:
                _spoke = True
                self._stamp(turn, "first_audio_delivered")  # feature 010
            await self._transport.send_audio(audio)

    async def _watch_for_bargein(self) -> Optional[bytes]:
        """Return the first inbound frame the platform's server-side
        endpoint detector flags as speech start, or ``None`` if the
        transport closed (EOF) while we were watching (constitution
        I — device-side VAD never substitutes).

        The pre-feature-015 implementation stalled on ``await
        sleep(3600)`` after consuming an EOF frame, which lost the
        EOF signal — under concurrency the next ``_collect_utterance``
        then blocked forever instead of returning. Returning the EOF
        signals teardown so :meth:`_handle_turn` can re-stash it on
        :attr:`_pending_frame` for the main loop to observe (FR-014
        edge: transport drops while watching)."""
        while True:
            frame = await self._transport.receive()
            if frame is None:
                return None  # transport gone — propagate EOF
            sig: EndpointResult = await self._platform.endpoint(frame)
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
