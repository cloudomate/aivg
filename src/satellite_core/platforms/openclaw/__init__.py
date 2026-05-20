"""OpenClaw agent-platform plugin — STUB.

Placeholder that proves the constitution v2.0.0 Principle IV plugin seam
works. The full implementation is a future feature; every method raises
:class:`NotImplementedError` with a pointer.
"""

from __future__ import annotations

__all__ = ["PLATFORM"]


class OpenClawAgentPlatform:  # pragma: no cover - stub
    name = "openclaw"

    async def startup(self, *, gateway_config: dict) -> None:
        raise NotImplementedError(
            "OpenClaw plugin: planned for a future feature. "
            "See specs/011-satellite-management/contracts/agent-platform.md."
        )

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        raise NotImplementedError("OpenClaw plugin: stub")

    def agent_step(self, text: str, session_id: str, *, history=None):
        raise NotImplementedError("OpenClaw plugin: stub")

    async def synthesize(self, text: str) -> bytes:
        raise NotImplementedError("OpenClaw plugin: stub")

    async def endpoint(self, frame: bytes) -> bool:
        raise NotImplementedError("OpenClaw plugin: stub")

    async def shutdown(self) -> None:
        return None


PLATFORM = OpenClawAgentPlatform()
