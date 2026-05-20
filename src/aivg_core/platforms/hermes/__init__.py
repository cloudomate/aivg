"""Hermes agent-platform plugin (v1 canonical implementation).

Reuses Hermes's existing ``~/.hermes/config.yaml``, ``~/.hermes/.env``,
its STT/TTS provider abstractions, its server-side silence algorithm,
and ``~/.hermes/logs/gateway.log`` verbatim (constitution IV v2.0.0).

Public export surface (feature 015 / FR-008 / FR-011): only
:data:`PLATFORM` (the canonical
:class:`aivg_core.platforms.base.AgentPlatform` instance) and the
feature-013 :data:`SETUP` capability cross the plugin boundary.
:class:`HermesBridge`, :class:`HermesV013Bridge`,
:class:`UnboundHermesBridge`, :class:`EndpointSignal`,
:class:`AgentReply`, and :class:`SessionCtx` are plugin-internal —
importing them via ``aivg_core.platforms.hermes.bridge`` from inside
this plugin's own modules is fine, but no caller outside
``aivg_core/platforms/hermes/`` should reference them.
"""

from __future__ import annotations

from .platform import HermesAgentPlatform

# Feature 013 — deploy-layer SetupCapability for Hermes.
from .setup import SETUP, HermesSetupCapability  # noqa: F401

__all__ = [
    "PLATFORM",
    "HermesAgentPlatform",
    "SETUP",
    "HermesSetupCapability",
]


# The canonical AgentPlatform instance returned by
# ``PluginRegistry.load("hermes")``. Constructed at import time;
# importing this module performs ZERO engine construction
# (constitution I) — the underlying bridge is lazy and waits for
# ``startup(gateway_config=...)`` to receive the agent_runner.
PLATFORM = HermesAgentPlatform()
