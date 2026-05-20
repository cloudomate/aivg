"""AgentPlatform contract gate (feature 011 T016).

Asserts every shipped plugin under ``aivg_core.platforms.<name>``
exposes a module-level ``PLATFORM`` whose ``name`` matches the package
name and that conforms (structurally) to
:class:`aivg_core.platforms.base.AgentPlatform`.
"""

from __future__ import annotations

import importlib
import inspect

import pytest

from aivg_core.platforms.base import AgentPlatform, PluginRegistry

SHIPPED_PLUGINS = ["hermes", "openclaw"]


@pytest.mark.parametrize("name", SHIPPED_PLUGINS)
def test_plugin_exposes_PLATFORM(name: str) -> None:
    mod = importlib.import_module(f"aivg_core.platforms.{name}")
    assert hasattr(mod, "PLATFORM"), f"{name}: missing module-level PLATFORM"


@pytest.mark.parametrize("name", SHIPPED_PLUGINS)
def test_plugin_name_matches_package(name: str) -> None:
    mod = importlib.import_module(f"aivg_core.platforms.{name}")
    assert mod.PLATFORM.name == name


@pytest.mark.parametrize("name", SHIPPED_PLUGINS)
def test_plugin_is_AgentPlatform_runtime_check(name: str) -> None:
    mod = importlib.import_module(f"aivg_core.platforms.{name}")
    # Protocol with runtime_checkable + structural typing.
    assert isinstance(mod.PLATFORM, AgentPlatform), (
        f"{name}: PLATFORM does not satisfy AgentPlatform protocol"
    )


@pytest.mark.parametrize("name", SHIPPED_PLUGINS)
def test_plugin_has_required_methods(name: str) -> None:
    """Belt-and-braces vs Protocol's structural check: assert each method
    exists (so a typo in the plugin surfaces clearly)."""
    mod = importlib.import_module(f"aivg_core.platforms.{name}")
    plat = mod.PLATFORM
    for method in ("startup", "transcribe", "agent_step", "synthesize", "endpoint", "shutdown"):
        attr = getattr(plat, method, None)
        assert attr is not None and callable(attr), f"{name}: missing {method}()"


def test_PluginRegistry_loads_hermes() -> None:
    plat = PluginRegistry.load("hermes")
    assert plat.name == "hermes"


def test_PluginRegistry_rejects_unknown() -> None:
    with pytest.raises(RuntimeError, match="Unknown agent platform"):
        PluginRegistry.load("does_not_exist")


def test_PluginRegistry_rejects_garbage_name() -> None:
    with pytest.raises(RuntimeError, match="Invalid agent platform name"):
        PluginRegistry.load("../whatever")
