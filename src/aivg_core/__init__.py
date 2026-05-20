"""``aivg_core`` — AIVG (AI Voice Gateway) management plane.

Platform-agnostic core (constitution v2.0.1 Principle IV). The core
never imports a concrete agent-platform plugin; all platform-specific
code lives under ``aivg_core.platforms.<name>/``. Hermes is the v1
canonical plugin.

History: renamed from ``hermes_satellite_adapter`` in feature 011
(introducing the ``satellite_core`` name), then to ``aivg_core`` in
feature 012 (the AIVG rebrand). Both prior import paths remain as
deprecation-warned compat shims for one release.
"""

__all__ = ["__version__"]
__version__ = "0.3.0"
