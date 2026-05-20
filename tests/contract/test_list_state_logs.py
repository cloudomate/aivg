"""Contract: /satellite/list, /{id}/state, logs SSE source, config push."""

from aivg_core.config import SatelliteAdapterConfig
from aivg_core.logsink import LogSink
from aivg_core.management import ManagementService
from aivg_core.models import LogLevel, LogSource
from aivg_core.registry import Registry


def _svc(tmp_path):
    return ManagementService(
        Registry(), LogSink(gateway_log=tmp_path / "g.log"), SatelliteAdapterConfig()
    )


def test_list_and_state_reflect_registry(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "esp32"})
    assert svc.get_state("d1")["device_type"] == "esp32"
    assert svc.get_state("missing") is None


def test_logs_query_filters(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "browser"})
    svc._sink.emit("d1", LogLevel.ERROR, LogSource.ASR, "boom")
    svc._sink.emit("d1", LogLevel.INFO, LogSource.TTS, "ok")
    errs = svc.query_logs(device_id="d1", level="ERROR")
    assert len(errs) == 1 and errs[0]["source"] == "asr"
    assert len(svc.query_logs(source="tts")) == 1


def test_config_post_pushes_config_changed_over_ws(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "browser"})
    seen = []
    svc.subscribe_ws(seen.append)
    # Feature 011 US3: post_config now returns (status, payload).
    status, out = svc.post_config("d1", {"wake_word": "computer"})
    assert status == 200
    assert out["wake_word"] == "computer"
    assert out["config_version"] == 1  # bumped from default 0
    assert any(m["type"] == "config_changed" for m in seen)


def test_command_validation(tmp_path):
    svc = _svc(tmp_path)
    svc.register({"device_id": "d1", "device_type": "browser"})
    # Feature 011 US5: command returns (status, payload) and validates
    # against the closed CommandVerb enum (R-14).
    status, payload = svc.command("d1", {"command": "factory_reset"})
    assert status == 202 and payload["accepted"] is True
    status, payload = svc.command("d1", {"command": "nope"})
    assert status == 400 and payload["error"] == "bad_input"


def test_gateway_log_file_written(tmp_path):
    svc = _svc(tmp_path)
    svc._sink.emit("d1", LogLevel.INFO, LogSource.SYSTEM, "hello")
    assert (tmp_path / "g.log").read_text().count("hello") == 1
