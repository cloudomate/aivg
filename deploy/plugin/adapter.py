"""Plugin entry point for the satellite_webrtc platform.

Verified against hermes-agent v0.13.0 (read-only, feature 003 Phase 0 /
implement): the plugin contract is

    def register(ctx):
        ctx.register_platform(name=..., label=..., adapter_factory=...,
                              check_fn=..., ...)

NOT `platform_registry.register(PlatformEntry(...))` (that was feature 001's
reconstruction). This shim is the seam the plan said would change; feature
001's package and tests are untouched.

The deploy script copies feature 001's `hermes_satellite_adapter` package in
beside this file, so it imports as a sibling subpackage.
"""

from __future__ import annotations

try:  # deployed layout: plugins/platforms/satellite_webrtc/hermes_satellite_adapter/
    from .hermes_satellite_adapter.adapter import build_platform_entry  # type: ignore
except Exception:  # dev/local fallback if installed on PYTHONPATH
    from hermes_satellite_adapter.adapter import build_platform_entry  # type: ignore


def _aiortc_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("aiortc") is not None


def register(ctx):
    """Called by the Hermes plugin system. Builds the adapter via feature
    001's verified factory and registers it through the real `ctx`
    contract (constitution IV — reuse, don't rebuild)."""
    entry = build_platform_entry()  # 001's _SatellitePlatformAdapter factory
    ctx.register_platform(
        name="satellite_webrtc",
        label="Satellite WebRTC",
        adapter_factory=entry.adapter_factory,
        check_fn=_aiortc_available,
        install_hint="Requires aiortc/aiohttp/av (already present on this host).",
    )
