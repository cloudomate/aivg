"""Feature 021 — US3: transport coexistence & capability negotiation.

Covers acceptance scenarios 1–4 plus the T039 regression guard, exercised
through the real negotiation path (the ``select_transport`` helper + the
registry's adoption flow). No ``device_type`` branching anywhere — a browser
is steered to WebRTC purely because it only advertises WebRTC (Constitution II).
"""

from __future__ import annotations

import pytest

from aivg_core.registry import Registry
from aivg_core.transports import (
    SUPPORTED_TRANSPORTS,
    UnsatisfiableTransportPin,
    select_transport,
)

_SUP = SUPPORTED_TRANSPORTS  # ("webrtc", "esphome_api", "grpc")


# --- select_transport: the negotiation rule (R-5) -----------------------

def test_native_advertising_both_gets_grpc():
    # Acceptance 1: a satellite advertising both is served gRPC.
    assert select_transport(["grpc", "webrtc"], supported=_SUP) == "grpc"


def test_browser_webrtc_only_stays_webrtc():
    # Acceptance 2: a browser (WebRTC only) is served WebRTC — no device_type
    # branching; it simply never advertises grpc.
    assert select_transport(["webrtc"], supported=_SUP) == "webrtc"


def test_legacy_esphome_unaffected():
    # Acceptance 3 (part): an esphome client keeps esphome_api.
    assert select_transport(["esphome_api"], supported=_SUP) == "esphome_api"


def test_legacy_non_advertising_device_stays_webrtc():
    # T039 regression: a pre-021 device that advertises nothing is NEVER
    # auto-upgraded to grpc (FR-016/FR-018).
    assert select_transport([], supported=_SUP) == "webrtc"
    assert select_transport(None, supported=_SUP) == "webrtc"


def test_pin_is_honored_when_satisfiable():
    # Acceptance 4: operator pin honored.
    assert select_transport(["grpc", "webrtc"], supported=_SUP, pin="webrtc") == "webrtc"


def test_pin_unsatisfiable_by_device_raises():
    with pytest.raises(UnsatisfiableTransportPin):
        select_transport(["webrtc"], supported=_SUP, pin="grpc")  # device can't do grpc


def test_pin_unsupported_by_gateway_raises():
    with pytest.raises(UnsatisfiableTransportPin):
        select_transport(["mqtt"], supported=_SUP, pin="mqtt")  # gateway can't serve mqtt


def test_gateway_prefers_grpc_over_webrtc_order():
    # Preference is grpc-first regardless of the advertised order.
    assert select_transport(["webrtc", "grpc"], supported=_SUP) == "grpc"


# --- registry adoption flow plumbs capabilities (FR-015) ----------------

def test_register_with_grpc_capabilities_selects_grpc_and_persists():
    reg = Registry()
    c = reg.register(
        "rpi-1", "rpi", transport_capabilities=["grpc", "webrtc"]
    )
    assert c.transport == "grpc"
    assert c.transport_capabilities == ["grpc", "webrtc"]
    # Survives a re-fetch from the registry.
    assert reg.get_client("rpi-1").transport == "grpc"


def test_register_browser_selects_webrtc():
    reg = Registry()
    c = reg.register("tab-1", "browser", transport_capabilities=["webrtc"])
    assert c.transport == "webrtc"


def test_register_without_capabilities_leaves_transport_default():
    # Back-compat: a legacy register (no capabilities) must not move the
    # device onto grpc.
    reg = Registry()
    c = reg.register("legacy-1", "rpi")
    assert c.transport == "webrtc"
    assert c.transport_capabilities == []


def test_register_with_pin_override():
    reg = Registry()
    c = reg.register(
        "rpi-2", "rpi", transport_capabilities=["grpc", "webrtc"], transport_pin="webrtc"
    )
    assert c.transport == "webrtc"
    assert c.transport_pin == "webrtc"


def test_register_with_unsatisfiable_pin_raises():
    reg = Registry()
    with pytest.raises(UnsatisfiableTransportPin):
        reg.register("rpi-3", "rpi", transport_capabilities=["webrtc"], transport_pin="grpc")


def test_grpc_is_in_supported_transports():
    assert "grpc" in SUPPORTED_TRANSPORTS
    assert "webrtc" in SUPPORTED_TRANSPORTS
    assert "esphome_api" in SUPPORTED_TRANSPORTS
