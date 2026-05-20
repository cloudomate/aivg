"""Contract: extended /satellite/list (feature 011 T020) + SSE log stream.

The pre-existing ``test_list_state_logs.py`` covers the v0.1 surface; this
file covers the v1.0 feature-011 additions: state filter, pending devices
in the list, and the new fields on every row.
"""

from __future__ import annotations

import pytest

from satellite_core.config import SatelliteAdapterConfig
from satellite_core.logsink import LogSink
from satellite_core.management import ManagementService
from satellite_core.registry import Registry


def _svc(tmp_path):
    return ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), SatelliteAdapterConfig()
    )


def test_list_default_returns_adopted_and_pending(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "kitchen", "device_type": "rpi"})  # legacy direct-adopt
    svc._reg.register_pending("bedroom", "esp32", firmware_version="0.1.0")
    rows = svc.list_clients(state="all")
    by_id = {r["device_id"]: r for r in rows}
    assert by_id["kitchen"]["adoption_state"] == "adopted"
    assert by_id["bedroom"]["adoption_state"] == "pending"


def test_list_state_adopted_only(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "kitchen", "device_type": "rpi"})
    svc._reg.register_pending("bedroom", "esp32")
    rows = svc.list_clients(state="adopted")
    ids = {r["device_id"] for r in rows}
    assert ids == {"kitchen"}


def test_list_state_pending_only(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "kitchen", "device_type": "rpi"})
    svc._reg.register_pending("bedroom", "esp32")
    rows = svc.list_clients(state="pending")
    ids = {r["device_id"] for r in rows}
    assert ids == {"bedroom"}


def test_list_unknown_state_rejected(tmp_path):
    svc = _svc(tmp_path)
    with pytest.raises(ValueError):
        svc.list_clients(state="zzz")


def test_each_row_has_v1_fields(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "kitchen", "device_type": "rpi"})
    row = svc.list_clients(state="adopted")[0]
    for field in (
        "device_id",
        "name",
        "device_type",
        "adoption_state",
        "status",
        "last_seen",
        "firmware_version",
        "active_routing_mode",
        "webrtc_state",
        "ota_state",
    ):
        assert field in row, f"missing field {field!r}"
