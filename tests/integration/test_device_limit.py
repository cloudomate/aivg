"""Integration: device-limit enforcement (feature 011 T040, R-12).

Limit applies at ``/adopt`` only — not at ``/register`` — so pending
discovery is unrestricted but the operator-driven adoption step refuses
once the configured ``device_limit`` is reached.
"""

from __future__ import annotations

from aivg_core.config import SatelliteAdapterConfig
from aivg_core.logsink import LogSink
from aivg_core.management import ManagementService
from aivg_core.registry import Registry


def _svc(tmp_path, *, device_limit):
    cfg = SatelliteAdapterConfig(
        device_limit=device_limit, auto_adopt_on_register=False
    )
    return ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), cfg
    )


def test_register_is_unlimited_adopt_is_limited(tmp_path):
    svc = _svc(tmp_path, device_limit=3)
    # Register 5 devices — all OK because pending is unlimited.
    for i in range(5):
        res = svc.register({"device_id": f"d{i}", "device_type": "rpi"})
        assert res["adoption_state"] == "pending"

    # Adopt the first 3 — all succeed.
    for i in range(3):
        status, _ = svc.adopt(f"d{i}", {"name": f"d{i}-named"})
        assert status == 200

    # 4th adopt refuses with device_limit_reached.
    status, payload = svc.adopt("d3", {"name": "d3-named"})
    assert status == 409
    assert payload["error"] == "device_limit_reached"
    assert payload["current"] == 3
    assert payload["limit"] == 3


def test_unpair_then_adopt_again_works(tmp_path):
    svc = _svc(tmp_path, device_limit=1)
    svc.register({"device_id": "d0", "device_type": "rpi"})
    assert svc.adopt("d0", {"name": "first"})[0] == 200

    # 2nd adopt refused.
    svc.register({"device_id": "d1", "device_type": "rpi"})
    assert svc.adopt("d1", {"name": "second"})[0] == 409

    # Unpair the first → frees the slot.
    assert svc.delete("d0") is True

    # Now d1 can be adopted.
    status, _ = svc.adopt("d1", {"name": "second"})
    assert status == 200
