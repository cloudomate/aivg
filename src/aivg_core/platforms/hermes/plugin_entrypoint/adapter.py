"""Plugin entry point for the satellite_webrtc platform (Hermes side).

Verified against hermes-agent v0.13.0 (feature 003 Phase 0):

    def register(ctx):
        ctx.register_platform(name=..., label=..., adapter_factory=...,
                              check_fn=..., ...)

Moved here in feature 013 from the now-deprecated `deploy/plugin/` —
the Hermes plugin's setup module (`aivg_core/platforms/hermes/setup.py`)
vendors **this directory** into the Hermes plugin tree at install time.

Imports: at install time, ``aivg_core/`` is on PYTHONPATH inside the
Hermes venv (the install step adds it). The `build_platform_entry`
factory lives in ``aivg_core.adapter`` (renamed from
``hermes_satellite_adapter.adapter`` in features 011/012).
"""

from __future__ import annotations

try:  # deployed layout: aivg_core/ is on PYTHONPATH in the Hermes venv
    from aivg_core.adapter import build_platform_entry  # type: ignore
except Exception:  # noqa: BLE001 - local dev fallback (running uninstalled)
    from .adapter_local_fallback import build_platform_entry  # type: ignore  # pragma: no cover


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
