"""Transports layer — sibling of ``aivg_core.platforms`` and
``aivg_core.webrtc``. Hosts non-WebRTC wire transports that route
inbound audio through the canonical :class:`AgentPlatform` Protocol
via the existing :class:`aivg_core.webrtc.session.Session`.

Feature 017 adds the first such sibling: ``transports.esphome`` (the
ESPHome native API server). Future transports (MQTT, gRPC, plain
WebSocket, …) plug in here without touching ``platforms/`` or
``webrtc/session.py``.

Consumers import the concrete transport class explicitly, e.g.::

    from aivg_core.transports.esphome import EsphomeTransport
    from aivg_core.transports.grpc import GrpcAudioTransport

This package also hosts the transport-negotiation helper (feature 021 / US3):
the gateway selects the best mutually-supported transport from what a
satellite advertises, WITHOUT branching on ``device_type`` (Constitution II).
"""

from __future__ import annotations

__all__ = [
    "SUPPORTED_TRANSPORTS",
    "GATEWAY_TRANSPORT_PREFERENCE",
    "UnsatisfiableTransportPin",
    "select_transport",
]

# Canonical list of transports this gateway BUILD can serve (feature 021
# adds "grpc"). Single source of truth — the CLI's ``--contract-version``
# envelope imports this. Runtime-*enabled* transports are a subset chosen by
# config; this is the "what CAN the gateway speak" capability set.
SUPPORTED_TRANSPORTS = ("webrtc", "esphome_api", "grpc")

# Gateway-side preference order (feature 021 / R-5). Browser satellites
# advertise only ``webrtc`` (a browser can't open a raw gRPC HTTP/2 stream),
# so capability-intersection naturally keeps them on WebRTC while native
# satellites that advertise ``grpc`` are preferred onto it — no per-device
# branching required.
GATEWAY_TRANSPORT_PREFERENCE = ("grpc", "webrtc", "esphome_api")

# Back-compat default for a device that advertises no capabilities (every
# pre-021 record). Such a device is NEVER auto-upgraded to gRPC.
_DEFAULT_TRANSPORT = "webrtc"


class UnsatisfiableTransportPin(ValueError):
    """Raised when an operator pins a transport the device can't speak or the
    gateway can't serve (FR-017)."""


def select_transport(
    capabilities,
    *,
    supported,
    pin: "str | None" = None,
) -> str:
    """Pick the transport for a satellite (feature 021, FR-015/FR-017).

    Args:
      capabilities: transports the device advertises it can speak
        (best-first), e.g. ``["grpc", "webrtc"]``. Empty/None means the
        device didn't advertise — treated as a legacy device.
      supported: transports this gateway build can actually serve
        (typically ``SUPPORTED_TRANSPORTS``).
      pin: optional operator override; must be both advertised by the device
        and supported by the gateway, else :class:`UnsatisfiableTransportPin`.

    Returns the chosen transport string. Never branches on ``device_type``
    (Constitution II) — a browser is steered to WebRTC purely because it
    only advertises WebRTC.
    """
    sup = set(supported or ())
    caps = [c for c in (capabilities or [])]

    if pin:
        if pin not in sup:
            raise UnsatisfiableTransportPin(
                f"pinned transport {pin!r} is not supported by this gateway "
                f"(supported: {sorted(sup)})"
            )
        if caps and pin not in caps:
            raise UnsatisfiableTransportPin(
                f"pinned transport {pin!r} is not advertised by the device "
                f"(advertises: {caps})"
            )
        return pin

    if not caps:
        # Legacy / non-advertising device: stay on the back-compat default
        # so introducing gRPC never silently moves an existing satellite
        # (FR-016/FR-018).
        return _DEFAULT_TRANSPORT

    for t in GATEWAY_TRANSPORT_PREFERENCE:
        if t in sup and t in caps:
            return t

    # No overlap between what the device speaks and what the gateway serves;
    # fall back to the safe default rather than failing the adoption.
    return _DEFAULT_TRANSPORT
