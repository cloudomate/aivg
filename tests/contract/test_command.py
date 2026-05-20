"""Contract: POST /satellite/{id}/command (feature 011 T072, US5).

Closed CommandVerb enum (R-14): 202 on accepted, 400 on unknown verb,
404 on unknown device, 503 on offline.
"""

from __future__ import annotations

import pytest

from aivg_core.config import SatelliteAdapterConfig
from aivg_core.logsink import LogSink
from aivg_core.management import ManagementService
from aivg_core.models import ClientStatus, CommandVerb
from aivg_core.registry import Registry


def _svc(tmp_path):
    return ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"),
        SatelliteAdapterConfig(),
    )


@pytest.mark.parametrize("verb", [v.value for v in CommandVerb])
def test_each_verb_in_the_closed_enum_is_accepted(tmp_path, verb):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    status, payload = svc.command("d1", {"command": verb})
    assert status == 202, f"verb {verb!r} should be accepted"
    assert payload["accepted"] is True
    assert payload["command"] == verb


def test_unknown_verb_returns_400(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    status, payload = svc.command("d1", {"command": "not_a_verb"})
    assert status == 400
    assert payload["error"] == "bad_input"


def test_unknown_device_returns_404(tmp_path):
    svc = _svc(tmp_path)
    status, payload = svc.command("ghost", {"command": "reboot"})
    assert status == 404
    assert payload["error"] == "unknown_device"


def test_offline_device_returns_503(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    svc._reg.get_client("d1").status = ClientStatus.OFFLINE
    status, payload = svc.command("d1", {"command": "reboot"})
    assert status == 503
    assert payload["error"] == "device_offline"


def test_command_broadcasts_command_frame_on_device_ws(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    seen = []
    svc.subscribe_ws(seen.append)
    svc.command("d1", {"command": "identify", "args": {"duration_s": 3}})
    frames = [m for m in seen if m.get("type") == "command"]
    assert len(frames) == 1
    assert frames[0]["command"] == "identify"
    assert frames[0]["args"] == {"duration_s": 3}


def test_legacy_string_shape_still_works(tmp_path):
    """Pre-US5 callers passed the verb as a bare string. The shim
    converts it to the body dict shape so existing voice-path tests
    don't break."""
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    status, payload = svc.command("d1", "factory_reset")
    assert status == 202
    assert payload["command"] == "factory_reset"
