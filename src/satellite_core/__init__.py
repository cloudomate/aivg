"""``satellite_core`` — platform-agnostic satellite management plane.

Renamed from ``hermes_satellite_adapter`` in feature 011 under constitution
v2.0.0. The core never imports a concrete agent-platform plugin; all
platform-specific code lives under ``satellite_core.platforms.<name>/``
(constitution IV v2.0.0). Hermes is the v1 canonical plugin.
"""

__all__ = ["__version__"]
__version__ = "0.2.0"
