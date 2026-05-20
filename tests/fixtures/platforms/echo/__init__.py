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

# Feature 015: the canonical Protocol's ``endpoint`` returns
# :class:`EndpointResult`, not bare ``bool``. Import lazily inside the
# method so the fixture stays load-able from a stripped package
# context (the seam test uses ``spec_from_file_location``).


# Sentinel byte sequences a test can push to drive the echo platform's
# endpoint state machine without a real VAD. Symmetric with
# ``tests/fakes.py`` markers (EOU / SPEECH).
ECHO_EOU = b"<ECHO_EOU>"
ECHO_SPEECH = b"<ECHO_SPEECH>"


class EchoAgentPlatform:
    name = "echo"

    def __init__(self) -> None:
        # Configurable canned reply deltas. Tests can override via
        # ``PLATFORM.reply_deltas = [...]`` to assert assembly.
        self.reply_deltas: list[str] = []

    async def startup(self, *, gateway_config: dict) -> None:
        return None

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        # Strip any endpoint markers so the resulting transcript is
        # deterministic for assembly assertions.
        stripped = audio.replace(ECHO_EOU, b"").replace(ECHO_SPEECH, b"")
        try:
            return stripped.decode("utf-8")
        except UnicodeDecodeError:
            return f"echo:transcribe({len(audio)}b@{sample_rate}Hz)"

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        deltas = self.reply_deltas or [f"echo:reply to {text!r} in {session_id!r}"]
        return _yield_each(deltas)

    async def synthesize(self, text: str) -> bytes:
        return f"echo:synth({text!r})".encode("utf-8")

    async def endpoint(self, frame: bytes):
        # Lazy import so this module loads even when imported by
        # ``spec_from_file_location`` (which strips package context and
        # would break a top-level relative import).
        from aivg_core.platforms.base import EndpointResult  # noqa: WPS433
        return EndpointResult(
            end_of_utterance=(frame == ECHO_EOU),
            speech_started=(frame == ECHO_SPEECH),
        )

    async def shutdown(self) -> None:
        return None


async def _yield_once(s: str):
    yield s


async def _yield_each(items):
    for s in items:
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
