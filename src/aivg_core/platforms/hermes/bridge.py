"""The ONLY module permitted to touch Hermes intelligence.

Constitution Principle I (NON-NEGOTIABLE): no Whisper, no Piper, no STT/TTS
engine, no agent loop, no silence algorithm is implemented anywhere in this
package. STT, end-of-utterance detection, the agent, and TTS are reached only
through this Protocol, which delegates to Hermes's existing provider
interfaces. Provider selection + fallback are INHERITED from Hermes config
(constitution IV / FR-006) — this adapter exposes no provider config.

The concrete Hermes-backed implementation is gated behind research.md
VG-1..VG-4 (running-build verification). Until those gates are closed the real
bridge raises a clear error; all behaviour is validated against the
``FakeHermesBridge`` test double.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Protocol, runtime_checkable


class AllProvidersUnavailable(RuntimeError):
    """Raised when every configured provider (and its fallbacks) failed.

    The session turns this into a perceptible failure rather than silence or a
    hung session (FR-015).
    """


class _EmptyAfterStrip(Exception):
    """Feature 009: a speakable unit became empty after Hermes's
    ``_strip_markdown_for_tts`` (e.g. a code-only / URL-only unit). NOT an
    ``AllProvidersUnavailable`` (that is turn-level): callers' existing
    per-unit ``except Exception: continue`` skips it → no synthesis, no
    zero-length audio, no new handler (FR-007 / contract H5)."""


class _UnitSynthFailed(Exception):
    """One unit produced no audio (Hermes ``text_to_speech_tool`` returned
    ``success:false`` for THIS text — e.g. Piper rendered 0 frames →
    ``wave.Error: # channels not specified``). This is a per-unit render
    failure, NOT a provider outage: it MUST skip just this unit and let the
    rest of the answer keep speaking (FR-007). Only a genuine
    provider/dependency outage stays ``AllProvidersUnavailable`` (fatal,
    perceptible — FR-008). Mis-classifying the former as the latter made a
    single unspeakable line kill the whole spoken answer (the "100-line
    story stopped after the intro" defect)."""


@dataclass
class SessionCtx:
    """Per-session context handed across the bridge. Provider selection lives
    in Hermes config and is never re-specified here."""

    device_id: str
    session_id: str
    conversation: dict[str, Any] = field(default_factory=dict)


@dataclass
class EndpointSignal:
    """Result of Hermes's authoritative end-of-utterance detection."""

    end_of_utterance: bool
    speech_started: bool = False


@dataclass
class AgentReply:
    text: str
    is_empty: bool = False  # empty / tool-only turn → return to listening cleanly


@runtime_checkable
class HermesBridge(Protocol):
    async def stt_transcribe(self, pcm: bytes, *, ctx: SessionCtx) -> str:
        """Delegate to Hermes's configured STT provider (+ fallback order)."""

    async def detect_endpoint(
        self, pcm_stream: AsyncIterator[bytes], *, ctx: SessionCtx
    ) -> EndpointSignal:
        """Delegate to Hermes's authoritative server-side silence / end-of-
        utterance algorithm. Device VAD never substitutes for this (FR-005)."""

    async def agent_turn(self, user_text: str, *, ctx: SessionCtx) -> AgentReply:
        """Invoke the Hermes agent as an entity via the SAME path the
        telegram/discord adapters use (FR-004)."""

    async def tts_synthesize(self, text: str, *, ctx: SessionCtx) -> bytes:
        """Delegate to Hermes's configured TTS provider (+ fallback order)."""


class UnboundHermesBridge:
    """Real bridge placeholder. Wiring is research.md tasks T038/T039.

    Importing this module performs ZERO engine construction; instantiating the
    real bridge without closing the verification gates fails loudly so the
    constitution-I boundary cannot be silently bypassed.
    """

    _GATE_MSG = (
        "Real HermesBridge not wired: close verification gates VG-1..VG-4 "
        "(see specs/001-realtime-voice-adapter/research.md). Use FakeHermesBridge "
        "for tests / `--dev-fake-bridge` for local runs."
    )

    async def stt_transcribe(self, pcm: bytes, *, ctx: SessionCtx) -> str:
        raise NotImplementedError(self._GATE_MSG)

    async def detect_endpoint(self, pcm_stream, *, ctx: SessionCtx) -> EndpointSignal:
        raise NotImplementedError(self._GATE_MSG)

    async def agent_turn(self, user_text: str, *, ctx: SessionCtx) -> AgentReply:
        raise NotImplementedError(self._GATE_MSG)

    async def tts_synthesize(self, text: str, *, ctx: SessionCtx) -> bytes:
        raise NotImplementedError(self._GATE_MSG)


# ---------------------------------------------------------------------------
# HermesV013Bridge — concrete delegation to the verified hermes-agent v0.13.0
# entrypoints (research.md D13–D17 / VG-1..VG-4). Every Hermes import is LAZY
# so this package still imports and the fake-driven suite still runs without
# the hermes package present. Still delegation-only: no engine is constructed
# here (constitution I) — STT/TTS/agent live in Hermes; this maps to them.
# ---------------------------------------------------------------------------

# Fallback constants if tools.voice_mode is unavailable at import (host-only).
_SILENCE_RMS_DEFAULT = 200
_SILENCE_SECONDS_DEFAULT = 3.0
_SPEECH_CONFIRM_SECONDS = 0.3  # design §8.1 speech-confirm window


def _pcm16_rms(pcm: bytes) -> float:
    """RMS of signed 16-bit little-endian mono PCM (stdlib only)."""
    import array
    import math

    if len(pcm) < 2:
        return 0.0
    a = array.array("h")
    a.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not a:
        return 0.0
    return math.sqrt(sum(s * s for s in a) / len(a))


class _EndpointState:
    __slots__ = ("silence_secs", "speech_secs", "had_speech")

    def __init__(self) -> None:
        self.silence_secs: float = 0.0
        self.speech_secs: float = 0.0
        self.had_speech: bool = False


class HermesV013Bridge:
    """Delegates to hermes-agent v0.13.0. Construct on the Hermes host.

    - STT  → ``tools.transcription_tools.transcribe_audio`` (D13/VG-1)
    - TTS  → ``tools.tts_tool.text_to_speech_tool``          (D14/VG-1)
    - VAD  → ``tools.voice_mode`` RMS/duration rule           (D15/VG-2)
    - agent→ gateway ``BasePlatformAdapter.handle_message``    (D16/VG-3)

    ``agent_runner`` is an async callable injected by the registration shim
    (``adapter.py``): it takes user text + ctx, drives the gateway agent loop,
    and returns the final reply text. This keeps the agent gateway-owned
    (constitution IV); the bridge never imports the agent itself.
    """

    def __init__(
        self,
        agent_runner: "Callable[[str, SessionCtx], Awaitable[str]] | None" = None,
        *,
        frame_seconds: float = 0.02,
        pcm_sample_rate: int = 48000,
    ) -> None:
        # Retained only for the FR-005 feature-006 fallback (agent_turn via
        # the gateway handle_message→send-future path). Feature 008's
        # streaming path runs Hermes's AIAgent directly and aborts it via
        # the agent's OWN .interrupt() — no adapter-side interrupt callback.
        self._agent_runner = agent_runner
        self._frame_seconds = frame_seconds
        self._sr = pcm_sample_rate
        self._ep: dict[str, _EndpointState] = {}
        # Feature 008: one persistent Hermes AIAgent per voice session
        # (cached by ctx.session_id) + a shared SessionDB → multi-turn
        # conversation continuity at cli.py parity (FR-012). The active
        # agent per session is tracked so barge-in can .interrupt() it.
        self._session_agents: dict = {}
        self._session_db = None
        self._rms_threshold, self._silence_secs = self._load_silence_rule()

    @staticmethod
    def _load_silence_rule() -> tuple[float, float]:
        try:  # reuse the AUTHORITATIVE Hermes rule when on the host
            from tools import voice_mode  # type: ignore

            return (
                float(getattr(voice_mode, "SILENCE_RMS_THRESHOLD", _SILENCE_RMS_DEFAULT)),
                float(getattr(voice_mode, "SILENCE_DURATION_SECONDS", _SILENCE_SECONDS_DEFAULT)),
            )
        except Exception:
            return float(_SILENCE_RMS_DEFAULT), float(_SILENCE_SECONDS_DEFAULT)

    async def stt_transcribe(self, pcm: bytes, *, ctx: SessionCtx) -> str:
        import asyncio
        import tempfile
        import wave

        def _work() -> str:
            try:
                from tools.transcription_tools import (  # type: ignore
                    _extract_transcript_text,
                    transcribe_audio,
                )
            except Exception as exc:  # pragma: no cover - host-only path
                raise AllProvidersUnavailable(f"Hermes STT unavailable: {exc}")
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as fh:
                with wave.open(fh.name, "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(self._sr)
                    w.writeframes(pcm)
                result = transcribe_audio(fh.name)  # provider/fallback from config
            # transcribe_audio (v0.13.0) returns {"success","transcript",
            # "provider"}; Hermes's _extract_transcript_text only knows the
            # "text" key, so it would str(dict) the whole payload. Pull the
            # transcript directly; fall back to the helper for str/other shapes.
            if isinstance(result, dict):
                if not result.get("success", True):
                    raise AllProvidersUnavailable(
                        result.get("error", "STT failed")
                    )
                return (result.get("transcript") or result.get("text") or "").strip()
            return _extract_transcript_text(result)

        return await asyncio.to_thread(_work)

    async def detect_endpoint(self, pcm_stream, *, ctx: SessionCtx) -> EndpointSignal:
        """Apply Hermes's RMS<threshold / silence-duration rule to decoded
        WebRTC PCM frames. Stateful per session; duration is accumulated by
        frame count for deterministic, transport-independent behaviour."""
        st = self._ep.setdefault(ctx.session_id, _EndpointState())
        speech_started = False
        end = False
        async for frame in pcm_stream:
            if _pcm16_rms(frame) >= self._rms_threshold:
                st.speech_secs += self._frame_seconds
                st.silence_secs = 0.0
                if st.speech_secs >= _SPEECH_CONFIRM_SECONDS and not st.had_speech:
                    st.had_speech = True
                    speech_started = True
            else:
                st.speech_secs = 0.0
                if st.had_speech:
                    st.silence_secs += self._frame_seconds
                    if st.silence_secs >= self._silence_secs:
                        end = True
        if end:
            self._ep.pop(ctx.session_id, None)  # reset for the next utterance
        return EndpointSignal(end_of_utterance=end, speech_started=speech_started)

    async def agent_turn(self, user_text: str, *, ctx: SessionCtx) -> AgentReply:
        if self._agent_runner is None:  # pragma: no cover - host-only
            raise NotImplementedError(
                "agent_runner not injected: adapter.register must wire the "
                "gateway BasePlatformAdapter.handle_message path (VG-3/D16)."
            )
        if not user_text.strip():
            return AgentReply(text="", is_empty=True)
        reply = await self._agent_runner(user_text, ctx)
        return AgentReply(text=reply or "", is_empty=not bool(reply))

    async def tts_synthesize(self, text: str, *, ctx: SessionCtx) -> bytes:
        import asyncio
        import json

        def _work() -> bytes:
            try:
                from tools.tts_tool import text_to_speech_tool  # type: ignore
            except Exception as exc:  # pragma: no cover - host-only path
                raise AllProvidersUnavailable(f"Hermes TTS unavailable: {exc}")
            # Feature 009: speak clean prose. Apply Hermes's OWN
            # tools.tts_tool._strip_markdown_for_tts BEFORE synthesis —
            # exactly as Hermes's gateway `_send_voice_reply` and CLI voice
            # do (markdown-stripping is a *caller* responsibility in Hermes;
            # text_to_speech_tool does NOT self-strip). Pure reuse: no
            # bespoke normalizer, no emoji/length/config added (constitution
            # I/IV; specs/009). One site → covers feature-008 `agent_stream`
            # AND feature-006 `tts_stream` (both synthesize via this method).
            # If the helper is missing or raises, fall back to the raw text —
            # never worse than today (FR-008 / contract H6).
            try:
                from tools.tts_tool import _strip_markdown_for_tts  # type: ignore  # noqa: WPS433
                spoken = _strip_markdown_for_tts(text)
            except Exception:  # noqa: BLE001 - FR-008 raw fallback
                spoken = text
            if not spoken or not spoken.strip():
                raise _EmptyAfterStrip()  # FR-007 / H5 — skip this unit
            raw = text_to_speech_tool(spoken)  # provider/voice from config
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                raise AllProvidersUnavailable(f"unexpected TTS result: {raw!r}")
            if not payload.get("success", True):
                err = str(payload.get("error", "TTS failed"))
                low = err.lower()
                # Genuine provider/dependency OUTAGE → fatal & perceptible
                # (FR-008): every unit would fail, so surface it.
                if (
                    "not installed" in low
                    or "no tts provider" in low
                    or "dependency missing" in low
                    or "not available" in low
                ):
                    raise AllProvidersUnavailable(err)
                # Otherwise THIS text just produced no audio (Piper 0-frame
                # / "produced no output" / "generation failed"). Skip only
                # this unit so the rest of the answer keeps speaking
                # (FR-007) — do NOT kill the whole turn.
                raise _UnitSynthFailed(err)
            path = payload.get("file_path") or (
                payload.get("media", "").removeprefix("MEDIA:") or None
            )
            if not path:
                raise AllProvidersUnavailable("TTS returned no audio path")
            with open(path, "rb") as fh:
                return fh.read()

        return await asyncio.to_thread(_work)

    async def tts_stream(self, text: str, *, ctx: SessionCtx):
        """Feature 006: speak the reply sentence-by-sentence.

        Segments the COMPLETED reply (textseg — pure text orchestration, no
        engine; constitution I) and pipelines per-unit synthesis through the
        EXISTING ``tts_synthesize`` (same Hermes provider/voice; FR-005) into
        a bounded look-ahead queue, yielding audio in order. The consumer
        (``session._respond``) plays one unit at a time, so later units are
        synthesized while earlier ones play (FR-003 / SC-001/002).

        - a unit whose synthesis raises a generic error is skipped, the rest
          continues (FR-007)
        - ``AllProvidersUnavailable`` propagates so the turn-level handling
          fires unchanged (FR-006)
        - on consumer close/cancel (barge-in) the producer is cancelled and
          the queue drained — no further unit is synthesized or spoken
          (FR-004 / SC-003)
        """
        import asyncio

        # Same fix as streamasm above: textseg lives under aivg_core.webrtc.
        from ...webrtc.textseg import iter_sentences  # noqa: WPS433

        units = iter_sentences(text)
        if not units:
            return  # empty / tool-only → nothing spoken (FR-006)

        q: "asyncio.Queue" = asyncio.Queue(maxsize=2)  # look-ahead depth (D3)
        _DONE = object()

        async def _producer() -> None:
            try:
                for unit in units:
                    try:
                        audio = await self.tts_synthesize(unit, ctx=ctx)
                    except AllProvidersUnavailable as exc:
                        await q.put(exc)  # turn-level handling (FR-006)
                        return
                    except Exception:  # noqa: BLE001 - skip a bad unit (FR-007)
                        continue
                    await q.put(audio)
                await q.put(_DONE)
            except asyncio.CancelledError:
                raise

        prod = asyncio.create_task(_producer())
        try:
            while True:
                item = await q.get()
                if item is _DONE:
                    return
                if isinstance(item, BaseException):
                    raise item
                yield item
        finally:
            prod.cancel()
            try:
                await prod
            except BaseException:  # noqa: BLE001 - teardown must not leak
                pass

    # -----------------------------------------------------------------
    # Feature 008 — agent text-delta streaming seam (supersedes feature
    # 007's draft-hook, proven unreachable for the LOCAL/voice path on
    # hermes-agent v0.14.0 — research.md D1/D2). We run Hermes's OWN
    # ``AIAgent`` the way its CLI/Discord voice modes do: construct it
    # exactly as ``cli.py`` does (model/runtime inherited from Hermes
    # config — constitution IV) with a per-call ``stream_callback`` that
    # receives text deltas AS the agent generates, feed those deltas
    # through feature 007's reused ``IncrementalUnitAssembler`` → existing
    # Hermes ``tts_synthesize`` (Piper) → WebRTC, so the first sentence is
    # spoken while the agent is still composing the rest. Host-only
    # (constitution V host-proven); the fake bridge exposes no
    # ``agent_stream`` so the fake suite takes the unchanged feature-006
    # path verbatim (FR-005 / SC-007). Barge-in aborts generation via the
    # agent's OWN ``.interrupt()`` (no orphan generation — FR-004).
    # -----------------------------------------------------------------

    def _get_session_agent(self, ctx: SessionCtx):  # pragma: no cover - host-only
        """Get/construct the persistent Hermes ``AIAgent`` for this voice
        session, cached by ``ctx.session_id`` over a SHARED ``SessionDB`` +
        a stable per-session ``session_id`` — so a follow-up turn sees the
        prior turns' context exactly as the gateway ``handle_message`` path
        did (multi-turn continuity at feature-006 parity — FR-012).

        Constructed exactly the way ``cli.py`` constructs it (model +
        runtime credentials INHERITED from Hermes config via
        ``resolve_runtime_provider``/``_get_model_config`` — constitution
        IV; no provider/model hardcoded here). Raises on any host
        import/construction failure so the caller takes the FR-005
        feature-006 fallback.
        """
        sid = ctx.session_id
        agent = self._session_agents.get(sid)
        if agent is not None:
            return agent
        from run_agent import AIAgent  # noqa: WPS433 - host-only, lazy
        from hermes_cli.runtime_provider import (  # noqa: WPS433
            _get_model_config,
            resolve_runtime_provider,
        )
        from hermes_state import SessionDB  # noqa: WPS433

        if self._session_db is None:
            self._session_db = SessionDB()  # one shared DB for the bridge
        model = (_get_model_config().get("default") or "").strip()
        runtime = resolve_runtime_provider()
        agent = AIAgent(
            model=model,
            api_key=runtime.get("api_key"),
            base_url=runtime.get("base_url"),
            provider=runtime.get("provider"),
            api_mode=runtime.get("api_mode"),
            session_id="satellite_%s" % sid,
            platform="satellite",
            session_db=self._session_db,
            quiet_mode=True,
        )
        self._session_agents[sid] = agent
        return agent

    async def _agent_stream_006_fallback(  # pragma: no cover - host-only
        self, user_text: str, *, ctx: SessionCtx, turn=None
    ):
        """FR-005: the Hermes delta seam is unavailable for this turn (host
        import/construct failure). Resolve the reply EXACTLY as feature 006
        — full reply via the gateway ``agent_turn``, then the existing
        per-sentence ``tts_stream`` — so it is never worse than 006."""
        reply = await self.agent_turn(user_text, ctx=ctx)
        if turn is not None:
            turn.agent_text = reply.text or ""
        if reply.is_empty or not (reply.text or "").strip():
            return  # empty / tool-only → back to listening
        async for audio in self.tts_stream(reply.text, ctx=ctx):
            yield audio

    async def agent_stream(self, user_text: str, *, ctx: SessionCtx, turn=None):  # pragma: no cover
        """Yield reply audio AS Hermes's agent generates it.

        Runs Hermes's own ``AIAgent.run_conversation`` in a worker thread
        with a ``stream_callback`` that receives text deltas; each delta is
        folded into feature 007's reused ``IncrementalUnitAssembler`` and
        every newly-complete sentence is synthesised via the EXISTING Hermes
        ``tts_synthesize`` and yielded in order. The consumer
        (``session._respond``) plays one unit at a time, so later sentences
        synthesise while earlier ones play and the first is spoken while the
        agent is still composing the rest (FR-001/FR-002, SC-001/SC-002).

        - empty input / tool-only reply → yields nothing (return to listening)
        - a unit whose synth raises a generic error is skipped (FR-007)
        - ``AllProvidersUnavailable`` / an agent failure propagates so the
          existing turn-level handling fires — perceptible failure, not a
          hang (FR-008 / contract H6)
        - on consumer close/cancel (barge-in) Hermes's agent is interrupted
          via its OWN ``.interrupt()`` and the worker abandoned — no orphan
          sentence AND no orphan generation (FR-004 / SC-004)
        - if the delta seam cannot be reached for this turn, falls back to
          feature 006 verbatim (FR-005)
        """
        import asyncio

        # streamasm lives under aivg_core.webrtc, not next to bridge.py.
        # Was `.streamasm` which silently failed every turn → ModuleNotFoundError
        # got swallowed by session._respond's task-level error handling,
        # making the whole STT→agent→TTS chain go dark right after STT.
        from ...webrtc.streamasm import IncrementalUnitAssembler  # noqa: WPS433

        if not user_text.strip():
            return  # empty input → empty / tool-only turn

        try:
            agent = self._get_session_agent(ctx)
        except Exception:  # noqa: BLE001 - FR-005 mandatory fallback to 006
            async for audio in self._agent_stream_006_fallback(
                user_text, ctx=ctx, turn=turn
            ):
                yield audio
            return

        # FR-012 multi-turn continuity at cli.py parity: restore this
        # session's prior turns from the SHARED SessionDB and feed them in
        # as conversation_history (conversation_loop logs `history=N` from
        # exactly this arg and DOES NOT auto-restore — the caller must, as
        # cli.py does via get_messages_as_conversation). conversation_loop's
        # `_persist_session` writes each turn back keyed by
        # `agent.session_id`, so the NEXT turn sees this one. Restore
        # failure is non-fatal — degrade to a stateless turn, never worse.
        history = []
        try:
            history = self._session_db.get_messages_as_conversation(
                agent.session_id
            ) or []
        except Exception:  # noqa: BLE001 - continuity best-effort, never fatal
            history = []

        loop = asyncio.get_running_loop()
        asm = IncrementalUnitAssembler()
        q: "asyncio.Queue" = asyncio.Queue()
        cumulative = [""]  # rebuilt cumulative reply (well-tested asm path)

        def _cb(delta: str) -> None:
            # Agent worker thread → event loop (run_conversation is blocking
            # and calls this synchronously per text delta).
            loop.call_soon_threadsafe(q.put_nowait, ("delta", delta or ""))

        def _run() -> str:
            # The cached AIAgent is REUSED across turns (FR-012). A prior
            # turn's barge-in left `_interrupt_requested=True`;
            # conversation_loop deliberately PRESERVES a pending interrupt
            # at turn start (it does not auto-clear) and expects the caller
            # to clear it once handled — exactly as cli.py does. Without
            # this, every turn after the first barge-in ends instantly
            # `interrupted_by_user` (api_calls=0, response_len=0) → no
            # reply, no audio. This NEW user utterance is the fresh-start
            # signal, so clear the stale interrupt before running.
            try:
                agent.clear_interrupt()
            except Exception:  # noqa: BLE001 - best-effort, never block a turn
                pass
            result = agent.run_conversation(
                user_text, conversation_history=history, stream_callback=_cb
            )
            if isinstance(result, dict):
                return (
                    result.get("final_response")
                    or result.get("response")
                    or result.get("text")
                    or ""
                )
            return result if isinstance(result, str) else ""

        run_task = asyncio.create_task(asyncio.to_thread(_run))

        def _on_done(t: "asyncio.Task") -> None:
            # Fires on the loop thread when the worker finishes. If it was
            # cancelled (barge-in / consumer teardown) the consumer is
            # already gone — deliver nothing (calling .result()/.exception()
            # on a cancelled task re-raises CancelledError; never let this
            # callback leak — FR-004/teardown).
            if t.cancelled():
                return
            exc = t.exception()
            if exc is not None:
                q.put_nowait(("error", exc))
            else:
                q.put_nowait(("done", t.result() or ""))

        run_task.add_done_callback(_on_done)

        # Feature 010: stamp the 3 agent/synth instants only this seam sees,
        # onto the turn (first write wins; no-op if turn is None). Pure
        # timestamp capture — does not alter 008 streaming / 009 strip /
        # barge-in behaviour (FR-007).
        import time as _t  # noqa: WPS433 - host-only seam

        def _lat(name: str) -> None:
            if turn is not None:
                turn.lat_instants.setdefault(name, _t.monotonic())

        interrupted = False
        try:
            while True:
                kind, payload = await q.get()
                if kind == "error":
                    raise payload  # perceptible turn failure (FR-008/H6)
                if kind == "done":
                    units = asm.flush(payload or cumulative[0])
                else:  # "delta"
                    if payload:
                        _lat("agent_first_output")  # first agent text delta
                    cumulative[0] += payload
                    units = asm.push(cumulative[0])
                if units:
                    _lat("first_unit_ready")  # first complete speakable unit
                for unit in units:
                    if not unit or not unit.strip():
                        continue  # never synth an empty/whitespace unit:
                        # Hermes Piper writes a 0-frame WAV → wave.Error
                        # "# channels not specified" (no half/empty audio,
                        # FR-003); nothing to speak.
                    try:
                        audio = await self.tts_synthesize(unit, ctx=ctx)
                    except AllProvidersUnavailable:
                        raise  # turn-level handling (FR-006/FR-008)
                    except Exception:  # noqa: BLE001 - skip a bad unit (FR-007)
                        continue
                    _lat("first_audio_synth")  # first unit synthesized
                    yield audio
                if kind == "done":
                    if turn is not None:
                        turn.agent_text = payload or cumulative[0]
                    break
        except (asyncio.CancelledError, GeneratorExit):
            interrupted = True
            raise
        finally:
            if not run_task.done():
                # Barge-in / failure with the agent still generating: stop
                # Hermes's OWN generation (no orphan — FR-004/SC-004), THEN
                # abandon the worker.
                if interrupted:
                    try:
                        agent.interrupt()
                    except Exception:  # noqa: BLE001
                        pass
                run_task.cancel()
            try:
                await run_task
            except BaseException:  # noqa: BLE001 - teardown must not leak
                pass
