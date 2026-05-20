"""Contract: POST /satellite/{id}/config + GET /config/schema (feature 011 T053, US3).

Optimistic concurrency, offline-write policy, schema endpoint.
"""

from __future__ import annotations

import pytest

from aivg_core.config import SatelliteAdapterConfig
from aivg_core.logsink import LogSink
from aivg_core.management import ManagementService
from aivg_core.models import ClientStatus
from aivg_core.registry import Registry


def _svc(tmp_path):
    cfg = SatelliteAdapterConfig(default_config={"wake_word": "Jarvis"})
    return ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), cfg
    )


# --- happy paths ---------------------------------------------------------


def test_post_config_bumps_version_and_returns_running_value(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    status, out = svc.post_config("d1", {"wake_word": "computer"})
    assert status == 200
    assert out["wake_word"] == "computer"
    assert out["config_version"] == 1


def test_post_config_unknown_device_returns_404(tmp_path):
    svc = _svc(tmp_path)
    status, payload = svc.post_config("ghost", {"wake_word": "computer"})
    assert status == 404
    assert payload["error"] == "unknown_device"


# --- optimistic concurrency (If-Match) -----------------------------------


def test_if_match_fresh_succeeds(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    # version starts at 0; pass If-Match=0 → succeeds, bumps to 1.
    status, out = svc.post_config("d1", {"wake_word": "alexa"}, if_match=0)
    assert status == 200
    assert out["config_version"] == 1


def test_if_match_stale_returns_409(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    # First write bumps version to 1.
    svc.post_config("d1", {"wake_word": "alexa"})
    # Second writer thinks it's still at version 0 → stale.
    status, payload = svc.post_config("d1", {"wake_word": "siri"}, if_match=0)
    assert status == 409
    assert payload["error"] == "config_conflict"
    assert payload["current_version"] == 1


def test_no_if_match_is_last_writer_wins(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    svc.post_config("d1", {"wake_word": "alexa"})  # version → 1
    status, out = svc.post_config("d1", {"wake_word": "siri"})  # no If-Match
    assert status == 200
    assert out["wake_word"] == "siri"
    assert out["config_version"] == 2


# --- offline-write policy (FR-016) ---------------------------------------


def test_offline_device_refused_without_queue(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    svc._reg.get_client("d1").status = ClientStatus.OFFLINE
    status, payload = svc.post_config("d1", {"wake_word": "alexa"})
    assert status == 503
    assert payload["error"] == "device_offline"


def test_offline_device_with_queue_returns_202(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    svc._reg.get_client("d1").status = ClientStatus.OFFLINE
    status, payload = svc.post_config("d1", {"wake_word": "alexa"}, queue=True)
    assert status == 202
    assert payload["queued"] is True
    assert payload["pending_overrides"] == {"wake_word": "alexa"}


def test_queued_write_applied_on_heartbeat(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    svc._reg.get_client("d1").status = ClientStatus.OFFLINE
    svc.post_config("d1", {"wake_word": "alexa"}, queue=True)
    # Heartbeat brings the device online; the queued write applies.
    svc.heartbeat("d1")
    c = svc._reg.get_client("d1")
    assert c.config.wake_word == "alexa"
    assert c.config_version == 1
    assert not svc._reg.has_queued_write("d1")


def test_queued_write_applied_on_reregister(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    svc._reg.get_client("d1").status = ClientStatus.OFFLINE
    svc.post_config("d1", {"wake_word": "alexa"}, queue=True)
    # Re-register flushes the queue too.
    svc.register({"device_id": "d1", "device_type": "rpi"})
    c = svc._reg.get_client("d1")
    assert c.config.wake_word == "alexa"


# --- schema endpoint -----------------------------------------------------


def test_config_schema_is_json_schema(tmp_path):
    svc = _svc(tmp_path)
    schema = svc.config_schema()
    assert schema["type"] == "object"
    assert schema["title"] == "SatelliteConfig"
    assert "wake_word" in schema["properties"]
    # Per constitution II: same schema shape for every device type — no
    # device_type-conditioned branching here.
    schema_with_id = svc.config_schema("anything")
    assert schema_with_id == schema
