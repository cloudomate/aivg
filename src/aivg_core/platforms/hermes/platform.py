"""``HermesAgentPlatform`` — the Hermes plugin's
:class:`aivg_core.platforms.base.AgentPlatform` implementation.

Feature 015 (constitution v2.0.0 Principle IV runtime closure): the
satellite voice loop sees this class via ``PluginRegistry.load("hermes")``
returning the module-level :data:`PLATFORM` symbol from
``__init__.py``. The :class:`HermesV013Bridge` it wraps stays
plugin-internal — no caller outside ``aivg_core/platforms/hermes/``
imports it after feature 015.

Constitution Principle I is preserved here, not weakened: every STT /
TTS / agent call still funnels through Hermes's existing provider
abstractions via the bridge — this file only renames the verbs to the
canonical Protocol surface.
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from ..base import EndpointResult
from .bridge import (
    AgentReply,
    AllProvidersUnavailable,
    HermesBridge,
    HermesV013Bridge,
    SessionCtx,
)


class HermesAgentPlatform:
    """Canonical Protocol wrapper over a :class:`HermesV013Bridge`.

    Structural typing — does not inherit from
    :class:`~aivg_core.platforms.base.AgentPlatform`;
    ``isinstance(plat, AgentPlatform)`` works at runtime via
    :func:`typing.runtime_checkable`.

    Construction is side-effect-free: the bridge is instantiated lazily
    with ``agent_runner=None``. The real ``agent_runner`` (the gateway
    routing callback) is injected via ``gateway_config["agent_runner"]``
    in :meth:`startup` — keeps ``aivg_core/adapter.py`` plugin-neutral.
    """

    name: str = "hermes"

    def __init__(self, bridge_instance: Optional[HermesBridge] = None) -> None:
        # ``bridge_instance`` is a test-injection seam. In production
        # the default-constructed bridge has ``agent_runner=None``; the
        # adapter calls ``startup`` with the runner-bearing config.
        self._bridge: HermesBridge = bridge_instance or HermesV013Bridge(
            agent_runner=None
        )
        # Single platform-scoped SessionCtx — the bridge's VAD state
        # keys off ``ctx.session_id``, and the satellite contract does
        # not pass session_id into ``endpoint(frame)``. A global VAD is
        # the documented choice (contracts/agent-platform.md § 2.4
        # "Statefulness").
        self._endpoint_ctx = SessionCtx(device_id="-", session_id="default")

    def attach_bridge(self, bridge_instance: HermesBridge) -> None:
        """Late-bind a different bridge (e.g. test fakes). Production
        code reaches the same bridge via :meth:`startup`'s gateway_config
        agent_runner injection."""
        self._bridge = bridge_instance

    # --- Lifecycle ------------------------------------------------------

    async def startup(self, *, gateway_config: dict) -> None:
        """Late-bind the agent runner from gateway_config.

        ``gateway_config["agent_runner"]`` is an ``async (text, ctx) -> str``
        callable supplied by ``aivg_core.adapter.build_platform_entry``:
        it routes ``user_text`` through the gateway's
        ``BasePlatformAdapter.handle_message`` path and awaits the
        agent's reply via a per-session future. Without it the bridge's
        ``agent_turn`` fallback raises. Importing this module performs
        ZERO engine construction (constitution I)."""
        runner = gateway_config.get("agent_runner") if gateway_config else None
        if runner is not None and isinstance(self._bridge, HermesV013Bridge):
            # Re-attach the runner without losing the bridge's other
            # state (VAD threshold, session DB, cached agents).
            self._bridge._agent_runner = runner  # type: ignore[attr-defined]

    async def shutdown(self) -> None:
        """Idempotent. The bridge has no daemon resources to release in
        v0.13.0 — provider handles are short-lived inside each verb."""
        return None

    # --- Required verbs (contracts/agent-platform.md § 2) ---------------

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        """ASR: PCM16 mono → text. The bridge's STT respects the
        sample rate the WebRTC adapter decoded the inbound frames to —
        currently fixed at 48000 Hz (see bridge ``pcm_sample_rate``)."""
        ctx = SessionCtx(device_id="-", session_id="transcribe-once")
        return await self._bridge.stt_transcribe(audio, ctx=ctx)

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """Yield reply text deltas. For Hermes the production streaming
        path is ``agent_stream`` (feature 008) — :meth:`agent_step` is
        the contract-required baseline used only when no
        ``agent_stream`` is exposed. We resolve via the bridge's
        non-streaming ``agent_turn`` and surface the whole reply as a
        single delta. R-2 convention: an empty turn yields nothing
        (caller treats accumulated ``.strip() == ""`` as "skip TTS")."""
        return self._agent_step_impl(text, session_id)

    async def _agent_step_impl(self, text: str, session_id: str) -> AsyncIterator[str]:
        ctx = SessionCtx(device_id="-", session_id=session_id)
        reply: AgentReply = await self._bridge.agent_turn(text, ctx=ctx)
        # R-2: empty / tool-only turn → zero deltas.
        if reply.is_empty or not (reply.text or "").strip():
            return
        yield reply.text

    async def synthesize(self, text: str) -> bytes:
        """TTS: text → audio bytes (Piper-rendered WAV from Hermes's
        tts_tool). Hermes's own markdown stripping runs inside the
        bridge (feature 009)."""
        ctx = SessionCtx(device_id="-", session_id="synth-once")
        return await self._bridge.tts_synthesize(text, ctx=ctx)

    async def endpoint(self, frame: bytes) -> EndpointResult:
        """Single-frame endpoint detection. The bridge's
        :meth:`detect_endpoint` consumes an async stream; wrap the
        single frame in a one-element generator. State is preserved
        across calls via :attr:`_endpoint_ctx` (constant ctx for the
        platform's lifetime; documented global-VAD choice)."""
        sig = await self._bridge.detect_endpoint(
            _one_frame(frame), ctx=self._endpoint_ctx
        )
        return EndpointResult(
            end_of_utterance=sig.end_of_utterance,
            speech_started=sig.speech_started,
        )

    # --- Optional extension (feature 008 streaming) ---------------------

    async def agent_stream(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
        turn=None,
    ) -> AsyncIterator[bytes]:
        """Forward to the bridge's existing :meth:`agent_stream` — the
        text-delta + per-sentence-synth streaming path that delivers
        the feature 008/010 latency win. The Hermes plugin exposes
        this; future plugins are NOT required to."""
        ctx = SessionCtx(device_id="-", session_id=session_id)
        async for audio in self._bridge.agent_stream(text, ctx=ctx, turn=turn):
            yield audio

    # --- Instrumentation passthrough (feature 010) ----------------------

    @property
    def _silence_secs(self) -> Optional[float]:
        """Expose the bridge's silence duration so the session's latency
        instrumentation can stamp ``end_of_speech = endpoint_detected -
        silence_secs`` (feature 010 / FR-011 — value inherited from
        Hermes config, not hardcoded). Plugin-internal API used by the
        voice loop via ``getattr(self._platform, "_silence_secs", None)``."""
        return getattr(self._bridge, "_silence_secs", None)


async def _one_frame(frame: bytes) -> AsyncIterator[bytes]:
    """One-shot async generator wrapping a single PCM frame so the
    bridge's stream-style ``detect_endpoint`` can consume it. Inlined
    here so the wrapper file has no module-level coupling beyond
    :class:`HermesBridge`."""
    yield frame
