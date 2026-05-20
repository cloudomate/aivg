"""Feature 011 T017 — fake-platform seam test (constitution v2.0.0 IV).

Proves the ``AgentPlatform`` plugin seam works against a third-party
plugin that lives **outside** ``aivg_core.platforms/``. The fixture
sits at ``tests/fixtures/platforms/echo/`` and the seam test mounts
it under ``aivg_core.platforms.echo`` so :class:`PluginRegistry` can
load it by name.

Caveat: the *runtime* voice loop in
:mod:`aivg_core.webrtc.session` still imports
:class:`aivg_core.platforms.hermes.bridge.HermesBridge` directly
(tagged with ``# AgentPlatform-coupling-TODO``); the proper rewire to
``AgentPlatform`` is feature-011 T019 partial. This test is the
narrower binding gate that the **plugin-load path** works without
importing the Hermes plugin.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "platforms"


@pytest.fixture
def echo_platform_loaded(monkeypatch):
    """Make ``import aivg_core.platforms.echo`` resolve to the
    EchoAgentPlatform fixture, then return the loaded module."""
    monkeypatch.syspath_prepend(str(FIXTURE.parent))
    # The fixture lives at tests/fixtures/platforms/echo; we want it to
    # resolve as aivg_core.platforms.echo. Simplest: register the loaded
    # module under that name in sys.modules.
    spec = importlib.util.spec_from_file_location(
        "aivg_core.platforms.echo", FIXTURE / "echo" / "__init__.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setitem(sys.modules, "aivg_core.platforms.echo", mod)
    yield mod
    sys.modules.pop("aivg_core.platforms.echo", None)


def test_echo_platform_loads_via_PluginRegistry(echo_platform_loaded):
    from aivg_core.platforms.base import PluginRegistry

    plat = PluginRegistry.load("echo")
    assert plat.name == "echo"
    # Structural-typing check via AgentPlatform Protocol.
    from aivg_core.platforms.base import AgentPlatform
    assert isinstance(plat, AgentPlatform)


def test_loading_echo_does_not_import_hermes_plugin(monkeypatch, echo_platform_loaded):
    """Constitution v2.0.0 Principle IV binding gate: selecting a non-
    Hermes platform MUST NOT cause the Hermes-plugin module to load."""
    # Drop any previously-imported Hermes plugin modules so the test
    # observes a fresh import graph.
    for name in list(sys.modules):
        if name.startswith("aivg_core.platforms.hermes"):
            monkeypatch.delitem(sys.modules, name)
    from aivg_core.platforms.base import PluginRegistry
    plat = PluginRegistry.load("echo")
    assert plat.name == "echo"
    # The Hermes plugin must not have been auto-imported.
    hermes_modules = [m for m in sys.modules if m.startswith("aivg_core.platforms.hermes")]
    assert not hermes_modules, (
        f"loading 'echo' triggered Hermes-plugin imports: {hermes_modules}"
    )


def test_config_load_platform_resolves_through_registry(echo_platform_loaded):
    """Closes feature-011 T011: ``cfg.load_platform()`` calls
    :class:`PluginRegistry`; the seam end-to-end works."""
    from aivg_core.config import SatelliteAdapterConfig

    cfg = SatelliteAdapterConfig.from_mapping({"platform": "echo"})
    plat = cfg.load_platform()
    assert plat.name == "echo"


def test_echo_platform_yields_a_streaming_reply(echo_platform_loaded):
    """Smoke-prove the structural contract: agent_step yields strings."""
    import asyncio
    from aivg_core.platforms.base import PluginRegistry

    plat = PluginRegistry.load("echo")

    async def collect():
        out = []
        async for chunk in plat.agent_step("hello", "s1"):
            out.append(chunk)
        return out

    assert asyncio.run(collect()) == ["echo:reply to 'hello' in 's1'"]
