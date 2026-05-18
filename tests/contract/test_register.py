"""Contract: POST /satellite/register + lifecycle (contracts/management-api.md)."""

from hermes_satellite_adapter.config import SatelliteAdapterConfig
from hermes_satellite_adapter.logsink import LogSink
from hermes_satellite_adapter.management import ManagementService
from hermes_satellite_adapter.registry import Registry


def _svc(tmp_path):
    sink = LogSink(gateway_log=tmp_path / "gateway.log")
    cfg = SatelliteAdapterConfig(default_config={"wake_word": "Jarvis"})
    return ManagementService(Registry(), sink, cfg), sink


def test_register_returns_contract_fields_and_lists_online(tmp_path):
    svc, _ = _svc(tmp_path)
    res = svc.register(
        {"device_id": "browser-1", "device_type": "browser", "firmware_version": "1.0"}
    )
    assert set(res) == {"session_token", "management_server_url", "default_config"}
    assert res["default_config"] == {"wake_word": "Jarvis"}

    listing = svc.list_clients()
    assert listing[0]["device_id"] == "browser-1"
    assert listing[0]["status"] == "online"


def test_missed_heartbeat_then_reregister(tmp_path):
    svc, _ = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    client = svc._reg.get_client("d1")
    client.last_seen = 0
    svc._reg.mark_stale(now=10_000)
    assert svc.get_state("d1")["status"] == "offline"
    # re-register restores ONLINE; entry retained (FR-014)
    svc.register({"device_id": "d1", "device_type": "rpi"})
    assert svc.get_state("d1")["status"] == "online"


def test_delete_removes_from_registry(tmp_path):
    svc, _ = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "browser"})
    assert svc.delete("d1") is True
    assert svc.get_state("d1") is None
