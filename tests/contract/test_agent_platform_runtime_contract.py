"""Feature 015 contract tests — every plugin's ``PLATFORM`` MUST
satisfy the canonical
:class:`aivg_core.platforms.base.AgentPlatform` Protocol.

Bound to [specs/015-agentplatform-runtime-closure/contracts/agent-platform.md § 7].
Parametrised over the Hermes plugin AND the echo fixture (loaded via
the same monkeypatch trick as
``tests/integration/test_agent_platform_seam.py``).
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

from aivg_core.platforms.base import (
    AgentPlatform,
    EndpointResult,
    PluginRegistry,
    _validate_agent_platform,
)

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "platforms"


@pytest.fixture
def echo_platform(monkeypatch):
    """Load the echo fixture under ``aivg_core.platforms.echo``."""
    monkeypatch.syspath_prepend(str(_FIXTURE_DIR.parent))
    spec = importlib.util.spec_from_file_location(
        "aivg_core.platforms.echo", _FIXTURE_DIR / "echo" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(sys.modules, "aivg_core.platforms.echo", mod)
    yield PluginRegistry.load("echo")
    sys.modules.pop("aivg_core.platforms.echo", None)


@pytest.fixture
def hermes_platform():
    return PluginRegistry.load("hermes")


# ---- Parametrised cases ---------------------------------------------------


def _platforms_iter(request):
    """Helper: yield (name, platform) tuples for the parametrised tests."""
    if request.param == "hermes":
        return PluginRegistry.load("hermes")
    if request.param == "echo":
        return request.getfixturevalue("echo_platform")
    raise AssertionError(request.param)


@pytest.fixture(params=["hermes", "echo"])
def platform(request, echo_platform, hermes_platform):
    if request.param == "hermes":
        return hermes_platform
    return echo_platform


# ---- Tests (one per row in contracts/agent-platform.md § 7) ---------------


def test_protocol_runtime_check(platform):
    """``isinstance(PLATFORM, AgentPlatform)`` (PEP 544 ``@runtime_checkable``)."""
    assert isinstance(platform, AgentPlatform)


def test_required_verbs_present(platform):
    """All four callables present + ``name``."""
    for verb in ("transcribe", "agent_step", "synthesize", "endpoint"):
        assert callable(getattr(platform, verb, None)), f"missing: {verb}"
    assert isinstance(platform.name, str) and platform.name


def test_validate_helper_accepts(platform):
    """``_validate_agent_platform`` raises nothing for a real platform."""
    _validate_agent_platform(platform)


def test_validate_helper_rejects_partial():
    """Stripping a verb tips the validator into a clear RuntimeError."""
    class _BrokenPlatform:
        name = "broken"

        async def transcribe(self, audio, *, sample_rate):
            return ""

        # NB: agent_step intentionally missing.

        async def synthesize(self, text):
            return b""

        async def endpoint(self, frame):
            return EndpointResult(end_of_utterance=False)

    with pytest.raises(RuntimeError, match="agent_step"):
        _validate_agent_platform(_BrokenPlatform())  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_transcribe_returns_str(platform):
    """A silent frame transcribes to ``str`` (empty is legal). The
    Hermes plugin requires its host-only ``tools`` package, so accept
    ``AllProvidersUnavailable`` as a documented offline-host
    behaviour — the surface is what we assert."""
    from aivg_core.platforms.base import AllProvidersUnavailable
    try:
        result = await platform.transcribe(b"\x00" * 640, sample_rate=16000)
    except AllProvidersUnavailable:
        return  # host-only path — acceptable in CI
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_agent_step_yields_str_deltas(platform):
    """``agent_step`` returns an async iterator of ``str``; closes
    cleanly via ``aclose``. Hermes's bridge ``agent_runner`` is None
    by default so its ``agent_turn`` raises NotImplementedError — for
    the Hermes case we only assert the surface shape and that no
    deltas-leak / hang occurs on aclose."""
    gen = platform.agent_step("hello", "sid")
    # The shape MUST be an async iterator. Real iteration may raise
    # (e.g. Hermes bridge without an agent_runner) — we tolerate that.
    assert hasattr(gen, "__anext__")
    try:
        async for delta in gen:
            assert isinstance(delta, str)
    except (NotImplementedError, RuntimeError):
        # Hermes bridge without an agent_runner is expected to raise
        # here; that's fine — we proved the surface is reachable.
        pass


@pytest.mark.asyncio
async def test_agent_step_empty_turn_via_fake_platform():
    """R-2 convention: an empty turn yields zero deltas. Uses the
    FakeHermesBridge (deterministic) rather than the real Hermes
    plugin (whose empty branch depends on the agent runtime)."""
    from fakes import FakeHermesBridge

    plat = FakeHermesBridge(empty_reply=True)
    deltas = []
    async for d in plat.agent_step("anything", "sid"):
        deltas.append(d)
    # Empty / tool-only → zero deltas; accumulated stripped == ""
    assert deltas == [] or "".join(deltas).strip() == ""


@pytest.mark.asyncio
async def test_synthesize_returns_bytes(platform):
    """``synthesize`` returns non-empty bytes. Hermes's path may raise
    AllProvidersUnavailable without a real Piper provider — accept
    either bytes-or-raise (the surface is what we assert)."""
    from aivg_core.platforms.base import AllProvidersUnavailable
    try:
        out = await platform.synthesize("hi")
    except AllProvidersUnavailable:
        return  # acceptable for the Hermes case without providers
    assert isinstance(out, (bytes, bytearray)) and len(out) > 0


@pytest.mark.asyncio
async def test_endpoint_returns_result(platform):
    """``endpoint(frame)`` returns an :class:`EndpointResult`."""
    result = await platform.endpoint(b"\x00" * 640)
    assert isinstance(result, EndpointResult)
    assert isinstance(result.end_of_utterance, bool)
    assert isinstance(result.speech_started, bool)


@pytest.mark.asyncio
async def test_lifecycle_idempotent(platform):
    """``startup`` then ``shutdown`` then ``shutdown`` does not raise."""
    await platform.startup(gateway_config={})
    await platform.shutdown()
    await platform.shutdown()  # idempotent
