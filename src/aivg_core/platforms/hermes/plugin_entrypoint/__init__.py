"""Hermes platform plugin: satellite_webrtc.

Mirrors the verified `plugins/platforms/irc/__init__.py` shape on the host:
the gateway plugin loader imports this package and calls `register(ctx)`.
"""

from .adapter import register

__all__ = ["register"]
