"""``AgentPlatform`` — the constitution v2.0.0 Principle IV plugin seam.

See ``specs/011-satellite-management/contracts/agent-platform.md``.

This module is the **only** plugin-related symbol the satellite core
imports. Concrete plugins live under ``aivg_core/platforms/<name>/``
and expose a module-level ``PLATFORM: AgentPlatform`` singleton. The
loader selects one by name at startup via ``~/.satellite/config.yaml``
``platform:``; no other discovery mechanism in v1 (R-15).

Structural typing via ``typing.Protocol`` (PEP 544) means a plugin does
NOT need to inherit from ``AgentPlatform`` — exposing the named methods
is enough. Practical consequence: the existing
:class:`aivg_core.platforms.hermes.bridge.HermesBridge` is already
structurally close; a thin ``HermesAgentPlatform`` adapter (in
``platforms/hermes/__init__.py``) renames its methods to the canonical
``AgentPlatform`` names so a single core can target both plugins.
"""

from __future__ import annotations

import importlib
from typing import AsyncIterator, Optional, Protocol, runtime_checkable

__all__ = ["AgentPlatform", "PluginRegistry", "load_platform"]


@runtime_checkable
class AgentPlatform(Protocol):
    """Pluggable agent-platform integration (constitution v2.0.0 IV).

    Implementations MUST NOT leak provider/SDK types across this
    boundary — only the Python primitives below cross it.
    """

    name: str
    """Stable lowercase identifier, e.g. ``'hermes'``, ``'openclaw'``."""

    async def startup(self, *, gateway_config: dict) -> None:
        """Called once when the satellite adapter starts.

        Implementations open whatever long-lived resources the platform
        requires (provider warm-up, etc). MUST NOT raise on a recoverable
        error; the next call will retry."""

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        """ASR: PCM16 mono → text. Sample rates: 16000 or 48000."""

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """User text → streaming reply text deltas. Implementations
        stream as soon as the platform produces tokens (feature 008
        streaming seam) and yield clean prose suitable for TTS — markdown
        stripping is the platform's responsibility (constitution I)."""

    async def synthesize(self, text: str) -> bytes:
        """TTS: text → Opus or PCM (negotiated at startup)."""

    async def endpoint(self, frame: bytes) -> bool:
        """Server-side end-of-utterance for one incoming PCM frame.
        Returns ``True`` at the moment EOU is reached. Implementations
        delegate to the platform's existing silence algorithm
        (constitution I rule)."""

    async def shutdown(self) -> None:
        """Idempotent teardown."""


class PluginRegistry:
    """Tiny dynamic loader. Explicit-config, no entry-point magic in v1."""

    @staticmethod
    def load(name: str) -> AgentPlatform:
        """Import ``aivg_core.platforms.<name>`` and return its
        module-level ``PLATFORM`` attribute. Raises a clear ``RuntimeError``
        on missing/misconfigured plugins."""
        if not name or not name.isidentifier():
            raise RuntimeError(
                f"Invalid agent platform name {name!r} — expected a Python "
                f"identifier (e.g. 'hermes', 'openclaw')."
            )
        try:
            module = importlib.import_module(f"aivg_core.platforms.{name}")
        except ImportError as exc:
            raise RuntimeError(
                f"Unknown agent platform {name!r}: "
                f"aivg_core.platforms.{name} could not be imported "
                f"({exc}). Available plugins: hermes, openclaw."
            ) from exc
        plat = getattr(module, "PLATFORM", None)
        if plat is None:
            raise RuntimeError(
                f"Platform plugin {name!r} does not expose a module-level "
                f"`PLATFORM` symbol. See "
                f"specs/011-satellite-management/contracts/agent-platform.md."
            )
        if getattr(plat, "name", None) != name:
            raise RuntimeError(
                f"Platform plugin {name!r}: `PLATFORM.name` is "
                f"{getattr(plat, 'name', None)!r}, expected {name!r}."
            )
        return plat


def load_platform(name: str) -> AgentPlatform:
    """Convenience shim, identical to :meth:`PluginRegistry.load`."""
    return PluginRegistry.load(name)
