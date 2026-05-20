"""Contract: OTA endpoints (feature 011 T063, US4).

/ota/check, /ota/apply, /ota/status, /ota/manifest behavior. Browser
device → 409 browser_not_ota_eligible on every endpoint (constitution II
sanctioned divergence).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aivg_core.config import SatelliteAdapterConfig
from aivg_core.logsink import LogSink
from aivg_core.management import ManagementService
from aivg_core.management.ota import OtaService, BrowserNotOtaEligible
from aivg_core.models import ClientStatus, OtaState
from aivg_core.registry import Registry


@pytest.fixture
def firmware_dir(tmp_path) -> Path:
    """Build a firmware/ tree with manifests for rpi and esp32."""
    (tmp_path / "rpi").mkdir()
    (tmp_path / "esp32").mkdir()
    (tmp_path / "rpi" / "manifest.json").write_text(json.dumps({
        "device_type": "rpi",
        "version": "0.2.0",
        "url": "http://hermes/firmware/rpi-0.2.0.img",
        "sha256": "a" * 64,
        "signature": None,
        "changelog": "Initial rpi firmware",
    }))
    (tmp_path / "esp32" / "manifest.json").write_text(json.dumps({
        "device_type": "esp32",
        "version": "0.3.0",
        "url": "http://hermes/firmware/esp32-0.3.0.bin",
        "sha256": "b" * 64,
        "signature": None,
        "changelog": "Initial esp32 firmware",
    }))
    return tmp_path


@pytest.fixture
def svc(tmp_path, firmware_dir):
    cfg = SatelliteAdapterConfig()
    s = ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), cfg
    )
    # Point the OtaService at the test firmware dir.
    s._ota._firmware_dir = firmware_dir
    return s


# --- /ota/check ----------------------------------------------------------


def test_ota_check_unknown_device_404(svc):
    status, payload = svc.ota_check("ghost")
    assert status == 404
    assert payload["error"] == "unknown_device"


def test_ota_check_browser_409(svc):
    svc.register({"device_id": "b1", "device_type": "browser"})
    status, payload = svc.ota_check("b1")
    assert status == 409
    assert payload["error"] == "browser_not_ota_eligible"


def test_ota_check_update_available(svc):
    svc.register({"device_id": "r1", "device_type": "rpi", "firmware_version": "0.1.0"})
    status, payload = svc.ota_check("r1")
    assert status == 200
    assert payload["update_available"] is True
    assert payload["latest_version"] == "0.2.0"


def test_ota_check_no_update(svc):
    svc.register({"device_id": "r1", "device_type": "rpi", "firmware_version": "0.2.0"})
    status, payload = svc.ota_check("r1")
    assert status == 200
    assert payload["update_available"] is False
    assert payload["latest_version"] is None


# --- /ota/apply ----------------------------------------------------------


def test_ota_apply_browser_409(svc):
    svc.register({"device_id": "b1", "device_type": "browser"})
    status, payload = svc.ota_apply("b1", {"version": "0.1.0"})
    assert status == 409
    assert payload["error"] == "browser_not_ota_eligible"


def test_ota_apply_offline_503(svc):
    svc.register({"device_id": "r1", "device_type": "rpi"})
    svc._reg.get_client("r1").status = ClientStatus.OFFLINE
    status, payload = svc.ota_apply("r1", {"version": "0.2.0"})
    assert status == 503
    assert payload["error"] == "device_offline"


def test_ota_apply_missing_version_400(svc):
    svc.register({"device_id": "r1", "device_type": "rpi"})
    status, payload = svc.ota_apply("r1", {})
    assert status == 400
    assert payload["error"] == "bad_input"


def test_ota_apply_happy_path_202(svc):
    svc.register({"device_id": "r1", "device_type": "rpi", "firmware_version": "0.1.0"})
    seen = []
    svc.subscribe_ws(seen.append)
    status, payload = svc.ota_apply("r1", {"version": "0.2.0"})
    assert status == 202
    assert payload["target_version"] == "0.2.0"
    assert payload["state"] == "downloading"
    # ota_apply frame broadcast to the device WS.
    assert any(m["type"] == "ota_apply" for m in seen)
    # Client state updated.
    c = svc._reg.get_client("r1")
    assert c.ota_state == OtaState.DOWNLOADING
    assert c.ota_version == "0.2.0"


def test_ota_apply_already_in_progress_409(svc):
    svc.register({"device_id": "r1", "device_type": "rpi"})
    svc.ota_apply("r1", {"version": "0.2.0"})  # first apply
    status, payload = svc.ota_apply("r1", {"version": "0.2.1"})
    assert status == 409
    assert payload["error"] == "ota_in_progress"


# --- /ota/status (device-reported) --------------------------------------


def test_ota_status_unknown_device_404(svc):
    status, payload = svc.ota_status_report("ghost", {"state": "downloading"})
    assert status == 404


def test_ota_status_bad_state_400(svc):
    svc.register({"device_id": "r1", "device_type": "rpi"})
    status, payload = svc.ota_status_report("r1", {"state": "not_a_real_state"})
    assert status == 400
    assert payload["error"] == "bad_input"


def test_ota_status_progression_emits_log_entries(svc):
    svc.register({"device_id": "r1", "device_type": "rpi", "firmware_version": "0.1.0"})
    svc.ota_apply("r1", {"version": "0.2.0"})
    for state in ("downloading", "flashing", "rebooting"):
        s, _ = svc.ota_status_report("r1", {"state": state, "version": "0.2.0"})
        assert s == 204
    # Terminal success.
    s, _ = svc.ota_status_report(
        "r1", {"state": "idle", "version": "0.2.0", "result": "success"}
    )
    assert s == 204
    c = svc._reg.get_client("r1")
    assert c.ota_state == OtaState.IDLE
    assert c.firmware_version == "0.2.0"  # bumped to the OTA'd version
    # Every status hit emitted an OTA log entry (R-6 / T068).
    ota_logs = [e for e in svc._sink._buf if e.source.value == "ota"]
    assert len(ota_logs) >= 4


def test_ota_status_failed_records_reason(svc):
    svc.register({"device_id": "r1", "device_type": "rpi"})
    svc.ota_apply("r1", {"version": "0.2.0"})
    s, _ = svc.ota_status_report(
        "r1", {"state": "failed", "failure_reason": "bad sha"}
    )
    assert s == 204
    job = svc._ota.get_job("r1")
    assert job.result == "failed"
    assert job.failure_reason == "bad sha"


# --- /ota/manifest -------------------------------------------------------


def test_ota_manifest_browser_409(svc):
    svc.register({"device_id": "b1", "device_type": "browser"})
    status, payload = svc.ota_manifest("b1")
    assert status == 409


def test_ota_manifest_returns_loaded(svc):
    svc.register({"device_id": "r1", "device_type": "rpi"})
    status, payload = svc.ota_manifest("r1")
    assert status == 200
    assert payload["version"] == "0.2.0"
    assert payload["device_type"] == "rpi"
    assert payload["sha256"] == "a" * 64
