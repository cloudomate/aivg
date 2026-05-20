"""Contract: POST /satellite/{id}/adopt (feature 011 T038, US2).

Adopt is the operator step that promotes a ``PendingDevice`` to an
adopted :class:`ConnectedClient`. Behavior matrix:

* missing/empty ``name`` → 400 ``bad_input``
* no pending device for this id → 404 ``unknown_device``
* device already adopted → 409 ``already_adopted``
* fleet at ``device_limit`` → 409 ``device_limit_reached`` (+ ``current``,
  ``limit``)
* happy path → 200 ``DeviceState`` (now adopted)
"""

from __future__ import annotations

import pytest

from satellite_core.config import SatelliteAdapterConfig
from satellite_core.logsink import LogSink
from satellite_core.management import ManagementService
from satellite_core.registry import Registry


def _svc(tmp_path, *, device_limit=10, auto_adopt_on_register=False):
    cfg = SatelliteAdapterConfig(
        default_config={"wake_word": "Jarvis"},
        device_limit=device_limit,
        auto_adopt_on_register=auto_adopt_on_register,
    )
    return ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), cfg
    )


def _register_pending(svc, device_id="bedroom", device_type="rpi"):
    return svc.register({"device_id": device_id, "device_type": device_type})


def test_adopt_promotes_pending_to_adopted(tmp_path):
    svc = _svc(tmp_path)
    res = _register_pending(svc)
    assert res["adoption_state"] == "pending"

    status, payload = svc.adopt("bedroom", {"name": "bedroom"})
    assert status == 200
    assert payload["adoption_state"] == "adopted"
    assert payload["name"] == "bedroom"


def test_adopt_unknown_device_returns_404(tmp_path):
    svc = _svc(tmp_path)
    status, payload = svc.adopt("ghost", {"name": "ghost"})
    assert status == 404
    assert payload["error"] == "unknown_device"


def test_adopt_missing_name_returns_400(tmp_path):
    svc = _svc(tmp_path)
    _register_pending(svc)
    status, payload = svc.adopt("bedroom", {})
    assert status == 400
    assert payload["error"] == "bad_input"

    status, payload = svc.adopt("bedroom", {"name": "   "})
    assert status == 400
    assert payload["error"] == "bad_input"


def test_adopt_already_adopted_returns_409(tmp_path):
    svc = _svc(tmp_path)
    _register_pending(svc)
    svc.adopt("bedroom", {"name": "bedroom"})

    status, payload = svc.adopt("bedroom", {"name": "again"})
    assert status == 409
    assert payload["error"] == "already_adopted"


def test_adopt_device_limit_reached_returns_409(tmp_path):
    svc = _svc(tmp_path, device_limit=2)
    for i in range(3):
        svc.register({"device_id": f"d{i}", "device_type": "rpi"})
    # Adopt the first two — both succeed.
    assert svc.adopt("d0", {"name": "first"})[0] == 200
    assert svc.adopt("d1", {"name": "second"})[0] == 200
    # Third hits the limit.
    status, payload = svc.adopt("d2", {"name": "third"})
    assert status == 409
    assert payload["error"] == "device_limit_reached"
    assert payload["current"] == 2
    assert payload["limit"] == 2


def test_adopt_pushes_default_config_with_overrides(tmp_path):
    svc = _svc(tmp_path)
    _register_pending(svc)
    seen: list[dict] = []
    svc.subscribe_ws(seen.append)

    status, _ = svc.adopt(
        "bedroom",
        {"name": "bedroom", "config_overrides": {"wake_word": "alexa"}},
    )
    assert status == 200
    cfg_changed = [m for m in seen if m["type"] == "config_changed"]
    assert cfg_changed
    assert cfg_changed[-1]["config"]["wake_word"] == "alexa"
