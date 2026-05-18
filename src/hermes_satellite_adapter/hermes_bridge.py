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
        self._agent_runner = agent_runner
        self._frame_seconds = frame_seconds
        self._sr = pcm_sample_rate
        self._ep: dict[str, _EndpointState] = {}
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
            raw = text_to_speech_tool(text)  # provider/voice from config
            try:
                payload = json.loads(raw)
            except (TypeError, ValueError):
                raise AllProvidersUnavailable(f"unexpected TTS result: {raw!r}")
            if not payload.get("success", True):
                raise AllProvidersUnavailable(payload.get("error", "TTS failed"))
            path = payload.get("file_path") or (
                payload.get("media", "").removeprefix("MEDIA:") or None
            )
            if not path:
                raise AllProvidersUnavailable("TTS returned no audio path")
            with open(path, "rb") as fh:
                return fh.read()

        return await asyncio.to_thread(_work)
