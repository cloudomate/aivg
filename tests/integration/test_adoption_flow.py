"""Integration: full adoption lifecycle (feature 011 T039, US2).

register (pending) → list shows pending → adopt → list shows adopted →
re-register (no factory_reset) keeps adopted → re-register
``factory_reset=True`` demotes back to pending (R-7). Persistence file
matches in-memory state at every step.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from satellite_core.config import SatelliteAdapterConfig
from satellite_core.logsink import LogSink
from satellite_core.management import ManagementService
from satellite_core.persistence import write_snapshot, load_snapshot
from satellite_core.registry import Registry


@pytest.fixture
def state_path(tmp_path) -> Path:
    return tmp_path / "state.json"


def _wire(tmp_path, state_path):
    cfg = SatelliteAdapterConfig(
        default_config={"wake_word": "Jarvis"},
        device_limit=10,
        auto_adopt_on_register=False,  # US2 pending-first mode
    )
    reg = Registry()
    # Hook persistence so every mutation lands in state_path.
    reg.attach_persist_hook(
        lambda r: write_snapshot(
            list(r._clients.values()), device_limit=cfg.device_limit, path=state_path
        )
    )
    svc = ManagementService(reg, LogSink(gateway_log=tmp_path / "g.log"), cfg)
    return svc, reg


def test_full_adoption_lifecycle(tmp_path, state_path):
    svc, reg = _wire(tmp_path, state_path)

    # 1. First register lands as pending.
    res = svc.register({"device_id": "bedroom", "device_type": "rpi"})
    assert res["adoption_state"] == "pending"
    assert {p.device_id for p in reg.list_pending()} == {"bedroom"}
    assert reg.list_clients() == []
    # State file has no adopted yet.
    assert load_snapshot(state_path) == []

    # 2. List filter: pending only.
    rows = svc.list_clients(state="pending")
    assert [r["device_id"] for r in rows] == ["bedroom"]
    assert rows[0]["adoption_state"] == "pending"

    # 3. Adopt → moves to clients; pending list empty.
    status, payload = svc.adopt("bedroom", {"name": "bedroom"})
    assert status == 200 and payload["name"] == "bedroom"
    assert reg.list_pending() == []
    assert [c.device_id for c in reg.list_clients()] == ["bedroom"]
    # State file persisted the adoption.
    persisted = load_snapshot(state_path)
    assert len(persisted) == 1 and persisted[0].name == "bedroom"

    # 4. Re-register without factory_reset → stays adopted, refreshes.
    res = svc.register(
        {"device_id": "bedroom", "device_type": "rpi", "firmware_version": "0.2.0"}
    )
    assert res["adoption_state"] == "adopted"
    assert [c.device_id for c in reg.list_clients()] == ["bedroom"]
    assert reg.get_client("bedroom").firmware_version == "0.2.0"

    # 5. Re-register WITH factory_reset → demote back to pending.
    res = svc.register(
        {"device_id": "bedroom", "device_type": "rpi", "factory_reset": True}
    )
    assert res["adoption_state"] == "pending"
    assert reg.list_clients() == []
    assert {p.device_id for p in reg.list_pending()} == {"bedroom"}
    # Persistence reflects the demotion (no adopted clients left).
    assert load_snapshot(state_path) == []


def test_pending_unaffected_by_device_limit(tmp_path, state_path):
    svc, reg = _wire(tmp_path, state_path)
    # Adopt 1 device, configured limit is 10 — pending count is unrestricted.
    for i in range(20):
        svc.register({"device_id": f"d{i}", "device_type": "esp32"})
    assert len(reg.list_pending()) == 20
    assert len(reg.list_clients()) == 0
