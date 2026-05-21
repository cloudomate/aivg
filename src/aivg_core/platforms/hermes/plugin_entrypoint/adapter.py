"""Plugin entry point for the aivg_satellite platform (Hermes side).

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

import logging

try:  # deployed layout: aivg_core/ is on PYTHONPATH in the Hermes venv
    from aivg_core.adapter import build_platform_entry  # type: ignore
except Exception:  # noqa: BLE001 - local dev fallback (running uninstalled)
    from .adapter_local_fallback import build_platform_entry  # type: ignore  # pragma: no cover

_log = logging.getLogger(__name__)

# Manifest name of the pre-rebrand bundled satellite plugin (the `name:`
# field in its plugin.yaml — distinct from the registration name
# ``satellite_webrtc`` which is the Hermes platform-registry key).
# Feature 019 R-1: detect-by-manifest-name lets us see the conflict via
# Hermes's already-loaded plugin manifest list rather than re-walking the
# filesystem.
_LEGACY_BUNDLED_MANIFEST_NAME = "satellite-webrtc-platform"


def _check_no_legacy_bundled_plugin() -> None:
    """Refuse to register if a pre-rebrand satellite_webrtc bundled plugin
    is also loaded by Hermes (Feature 019 / FR-004 / R-1, R-2).

    Reads the already-loaded plugin manifest list via the Hermes plugin
    manager API. Looks for a plugin whose manifest name is
    ``satellite-webrtc-platform`` AND whose source is ``bundled``. On
    match: raise ``RuntimeError`` with the operator-actionable cleanup
    message naming the offending directory and the recommended verb.

    Honors Constitution Principle IV by consuming Hermes's own plugin
    discovery rather than re-walking the filesystem. Wrapped in a broad
    try/except so a malfunctioning Hermes API never blocks the rename's
    primary outcome (the registration); on API failure we log a warning
    and return silently — see data-model.md § 2 "Hermes plugin manager
    API unavailable" edge case.

    Raises:
        RuntimeError: when the pre-019 bundled satellite plugin is also
            present, with a multi-line message naming each conflicting
            directory path and the cleanup verb.
    """
    try:
        from hermes_cli.plugins import (  # type: ignore
            discover_plugins,
            get_plugin_manager,
        )
        discover_plugins(force=False)
        manager = get_plugin_manager()
        plugins = manager.list_plugins()
    except Exception as exc:  # noqa: BLE001
        _log.warning(
            "Conflict-detector: Hermes plugin manager unavailable (%s); "
            "proceeding with registration without coexistence check.",
            exc,
        )
        return

    conflicts = [
        p for p in plugins
        if isinstance(p, dict)
        and p.get("name") == _LEGACY_BUNDLED_MANIFEST_NAME
        and p.get("source") == "bundled"
    ]
    if not conflicts:
        return

    # Build a precise, actionable error message.
    paths = []
    for p in conflicts:
        path = p.get("path") or "(unknown — check ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/)"
        paths.append(f"  - {path}")
    paths_str = "\n".join(paths)

    raise RuntimeError(
        "aivg-satellite plugin refuses to register: a pre-rebrand bundled "
        "`satellite-webrtc-platform` plugin is ALSO present in Hermes's "
        "plugin scan path. Both plugins would bind to the same management "
        "(8643) and signaling (8644) ports; the bundled one would silently "
        "win, shadowing the entry-point plugin (the trap that consumed "
        "hours of the 2026-05-21 deploy session). Conflicting plugin "
        "directory(ies):\n"
        f"{paths_str}\n"
        "Cleanup: move the legacy directory out of the plugin scan path, "
        "e.g.:\n"
        "    mv ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/ "
        "~/.hermes/backups/\n"
        "Then restart the gateway."
    )


def _aiortc_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("aiortc") is not None


def register(ctx):
    """Called by the Hermes plugin system. Builds the adapter via feature
    001's verified factory and registers it through the real `ctx`
    contract (constitution IV — reuse, don't rebuild).

    Feature 019 / FR-004: BEFORE registering, check that a pre-rebrand
    `satellite_webrtc` bundled plugin is not also loaded — if it is, the
    two plugins would bind to the same ports and the bundled one would
    silently shadow this one. Raises with a clear cleanup message on
    conflict.

    Auth: feature 013 — the satellite handles its own per-device adoption
    (PENDING → ADOPTED via `aivg device adopt`), so we wire BOTH the
    per-platform allow-list env (``SATELLITE_ALLOWED_USERS``) and the
    skip-allowlist env (``SATELLITE_ALLOW_ALL_USERS``) into Hermes's
    `_is_user_authorized()`. Without these, gateway-wide
    ``GATEWAY_ALLOW_ALL_USERS=false`` (default) silently drops every
    voice turn between STT and the agent loop — symptom we hit in
    live testing.

    Default behavior matches IRC's pattern: empty env → allow all (the
    satellite's own adoption state IS the device-level allowlist; the
    Hermes user gate would be a redundant second perimeter).
    """
    _check_no_legacy_bundled_plugin()
    entry = build_platform_entry()  # 001's _SatellitePlatformAdapter factory
    ctx.register_platform(
        name="aivg_satellite",
        label="Satellite WebRTC",
        adapter_factory=entry.adapter_factory,
        check_fn=_aiortc_available,
        install_hint="Requires aiortc/aiohttp/av (already present on this host).",
        # Auth wiring — see docstring above. Env-var names are unchanged
        # by feature 019 (the rename is scoped to the internal plugin
        # registration name; operator-facing wire surfaces — env vars,
        # REST paths, config block — stay byte-identical).
        allowed_users_env="SATELLITE_ALLOWED_USERS",
        allow_all_env="SATELLITE_ALLOW_ALL_USERS",
    )
