"""``transports.grpc`` — gRPC bidirectional-streaming satellite transport
(feature 021), sibling of ``transports.esphome``.

Phase 1 hosts the ``aivg.satellite.v1.Audio`` service: one bidi
``Audio.Stream`` per voice session (mic PCM up; synthesized audio +
transcripts + turn events down). Inbound audio is routed through the
canonical :class:`aivg_core.webrtc.session.Session` and the
:class:`~aivg_core.platforms.base.AgentPlatform` Protocol exactly like every
other transport — no ``platforms/`` or ``webrtc/session.py`` change.

Consumers import the concrete transport explicitly::

    from aivg_core.transports.grpc import GrpcAudioTransport

The canonical wire schema lives at repo-root
``proto/aivg/satellite/v1/audio.proto`` (vendored by the ``aivg-devices``
C++ client); checked-in Python stubs live under ``_generated/``.
"""

from __future__ import annotations

__all__ = ["GrpcAudioTransport"]


def __getattr__(name: str):  # PEP 562 — defer the grpc import until used.
    if name == "GrpcAudioTransport":
        from .server import GrpcAudioTransport

        return GrpcAudioTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
