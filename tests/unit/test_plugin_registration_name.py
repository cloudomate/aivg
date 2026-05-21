"""Feature 019 — assert the plugin registers under the canonical name.

Pre-019 baseline: 333 tests collected. Post-019 target: 333 + N new tests.

The plugin entry-point shim at
``aivg_core.platforms.hermes.plugin_entrypoint.adapter.register`` is the
single call site that hands the registration name to Hermes via
``ctx.register_platform(name=…)``. This test pins the post-019 value
(``aivg_satellite``) and the back-compat alias surface against any future
drift.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def test_register_uses_canonical_aivg_satellite_name():
    """The post-019 plugin entry-point's register() MUST call
    ``ctx.register_platform`` with ``name="aivg_satellite"``.

    This is the binding rename assertion (SC-001).
    """
    from aivg_core.platforms.hermes.plugin_entrypoint.adapter import register

    ctx = MagicMock()
    register(ctx)

    ctx.register_platform.assert_called_once()
    kwargs = ctx.register_platform.call_args.kwargs
    assert kwargs["name"] == "aivg_satellite"
    # Pre-019 value MUST NOT leak through (regression guard).
    assert kwargs["name"] != "satellite_webrtc"


def test_adapter_class_name_attribute_is_canonical():
    """The class attribute ``name`` on the renamed adapter class returns
    the canonical post-019 string."""
    from aivg_core.adapter import AivgSatelliteAdapter

    assert AivgSatelliteAdapter.name == "aivg_satellite"


def test_back_compat_alias_identity():
    """``SatelliteWebRTCAdapter`` is preserved as an *identity* alias —
    not a subclass, not equality — so existing
    ``isinstance(x, SatelliteWebRTCAdapter)`` checks downstream keep
    working without divergence."""
    from aivg_core.adapter import AivgSatelliteAdapter, SatelliteWebRTCAdapter

    assert SatelliteWebRTCAdapter is AivgSatelliteAdapter
