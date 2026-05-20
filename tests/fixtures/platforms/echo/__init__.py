"""Fake ``echo`` agent-platform plugin (feature 011 T017 fixture).

Lives **outside** ``src/aivg_core/platforms/`` to prove the plugin
seam can load a third-party plugin from any Python path. The seam test
adds this directory to ``sys.path`` and mocks
``aivg_core.platforms.<x>`` lookup to find ``echo`` here.

Exposes the structural ``AgentPlatform`` contract (PEP 544) with
deterministic strings.
"""

from __future__ import annotations

from typing import AsyncIterator, Optional


class EchoAgentPlatform:
    name = "echo"

    async def startup(self, *, gateway_config: dict) -> None:
        return None

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        return f"echo:transcribe({len(audio)}b@{sample_rate}Hz)"

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        return _yield_once(f"echo:reply to {text!r} in {session_id!r}")

    async def synthesize(self, text: str) -> bytes:
        return f"echo:synth({text!r})".encode("utf-8")

    async def endpoint(self, frame: bytes) -> bool:
        return False

    async def shutdown(self) -> None:
        return None


async def _yield_once(s: str):
    yield s


PLATFORM = EchoAgentPlatform()

# Feature 013: re-export SetupCapability so the symlink-based fixture also
# answers `PluginRegistry.load_setup_capability("echo")` in subprocesses.
# The seam test (test_agent_platform_seam.py) loads this module via
# `spec_from_file_location`, which strips package context and breaks the
# relative `from .setup` import — that's fine, the seam test only needs
# PLATFORM, not SETUP. Swallow the ImportError silently in that path.
try:
    from .setup import SETUP, EchoSetupCapability  # noqa: E402, F401
    __all__ = ["EchoAgentPlatform", "PLATFORM", "SETUP", "EchoSetupCapability"]
except ImportError:  # pragma: no cover - seam-test fallback
    __all__ = ["EchoAgentPlatform", "PLATFORM"]
