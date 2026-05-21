"""Hermes platform plugin: aivg_satellite (formerly satellite_webrtc).

Mirrors the verified `plugins/platforms/irc/__init__.py` shape on the host:
the gateway plugin loader imports this package and calls `register(ctx)`.

Feature 019 renamed the registration name; the PyPI entry-point manifest
name `aivg-satellite` (in pyproject.toml) is unchanged.
"""

from .adapter import register

__all__ = ["register"]
