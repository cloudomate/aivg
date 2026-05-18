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
from typing import Any, AsyncIterator, Protocol, runtime_checkable


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
