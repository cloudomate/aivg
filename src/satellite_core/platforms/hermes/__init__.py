"""Hermes agent-platform plugin (v1 canonical implementation).

Reuses Hermes's existing ``~/.hermes/config.yaml``, ``~/.hermes/.env``,
its STT/TTS provider abstractions, its server-side silence algorithm, and
``~/.hermes/logs/gateway.log`` verbatim (constitution IV v2.0.0).

The :class:`HermesBridge` :class:`Protocol` already in :mod:`.bridge` has
all the behavior we need; :class:`HermesAgentPlatform` is a thin adapter
that renames its methods to the canonical
:class:`satellite_core.platforms.base.AgentPlatform` names — so the
satellite core's *future* AgentPlatform-targeted code paths can call this
plugin (or any other) uniformly. The existing
:mod:`satellite_core.webrtc.session` / :mod:`satellite_core.webrtc.signaling`
still talk to ``HermesBridge`` directly; the rewire-to-AgentPlatform is a
follow-up in a later phase.
"""

from __future__ import annotations

from typing import AsyncIterator, Optional

from . import bridge  # re-export the bridge module (existing import paths)
from .bridge import AgentReply, HermesBridge, SessionCtx, UnboundHermesBridge

__all__ = ["bridge", "HermesAgentPlatform", "PLATFORM"]


class HermesAgentPlatform:
    """:class:`AgentPlatform` adapter over a :class:`HermesBridge`.

    Structural typing — this class does not inherit from
    :class:`AgentPlatform`; ``isinstance(plat, AgentPlatform)`` works at
    runtime via :func:`typing.runtime_checkable`.
    """

    name = "hermes"

    def __init__(self, bridge_instance: Optional[HermesBridge] = None) -> None:
        # Lazy: a real bridge is wired by the gateway on startup; the
        # default (None) makes the class importable and constructable in
        # tests without forcing the Hermes runtime to be present.
        self._bridge: Optional[HermesBridge] = bridge_instance

    def attach_bridge(self, bridge_instance: HermesBridge) -> None:
        self._bridge = bridge_instance

    async def startup(self, *, gateway_config: dict) -> None:
        # No-op by default; production wiring constructs the bridge with
        # the gateway's already-loaded Hermes config and calls
        # :meth:`attach_bridge`. Importing this module performs ZERO
        # engine construction (constitution I).
        return None

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        if self._bridge is None:
            raise RuntimeError("HermesAgentPlatform: no bridge attached")
        ctx = SessionCtx(device_id="-", session_id="-", sample_rate=sample_rate)
        return await self._bridge.stt_transcribe(audio, ctx=ctx)

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        if self._bridge is None:
            raise RuntimeError("HermesAgentPlatform: no bridge attached")
        return self._agent_step_impl(text, session_id, history)

    async def _agent_step_impl(
        self,
        text: str,
        session_id: str,
        history: Optional[list[dict]],
    ) -> AsyncIterator[str]:
        # The existing HermesBridge returns a whole AgentReply; surface it
        # as a single-yield stream for the AgentPlatform contract. Tokens-
        # as-deltas are the streaming variant from feature 008, surfaced
        # by the bridge's own deltastream API where available.
        ctx = SessionCtx(device_id="-", session_id=session_id)
        reply: AgentReply = await self._bridge.agent_turn(text, ctx=ctx)  # type: ignore[union-attr]
        if not reply.is_empty:
            yield reply.text

    async def synthesize(self, text: str) -> bytes:
        if self._bridge is None:
            raise RuntimeError("HermesAgentPlatform: no bridge attached")
        ctx = SessionCtx(device_id="-", session_id="-")
        return await self._bridge.tts_synthesize(text, ctx=ctx)

    async def endpoint(self, frame: bytes) -> bool:
        # The HermesBridge endpoint API takes an async stream; this
        # one-frame shim is intentionally minimal for the v1 surface and
        # is not yet wired into the voice path (which still calls
        # ``HermesBridge.detect_endpoint`` directly).
        return False

    async def shutdown(self) -> None:
        return None


PLATFORM = HermesAgentPlatform()
