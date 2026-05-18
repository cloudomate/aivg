from hermes_satellite_adapter.config import SatelliteAdapterConfig
from hermes_satellite_adapter.models import (
    ClientStatus,
    ConversationTurn,
    SatelliteConfig,
    SessionState,
)
from hermes_satellite_adapter.registry import Registry


def test_satellite_config_defaults_match_appendix_b():
    c = SatelliteConfig()
    assert c.wake_word == "Hey Jarvis"
    assert c.heartbeat_interval == 30
    assert c.echo_strategy is None  # per-device, not a global ducking flag


def test_config_merge_only_known_keys():
    merged = SatelliteConfig().merged({"wake_word": "computer", "bogus": 1})
    assert merged.wake_word == "computer"
    assert not hasattr(merged, "bogus")


def test_adapter_config_rejects_equal_ports():
    import pytest

    with pytest.raises(ValueError):
        SatelliteAdapterConfig(management_port=9000, webrtc_port=9000).validate()


def test_mini_yaml_parses_satellite_block(tmp_path):
    from hermes_satellite_adapter.config import load_adapter_config

    p = tmp_path / "config.yaml"
    p.write_text(
        "voice:\n  x: 1\nsatellite:\n  enabled: true\n  management_port: 8643\n"
        "  webrtc_port: 8644\n  default_config:\n    wake_word: Jarvis\n"
    )
    cfg = load_adapter_config(p)
    assert cfg.enabled is True
    assert cfg.management_port == 8643
    assert cfg.default_config["wake_word"] == "Jarvis"


def test_registry_register_and_session_lifecycle():
    r = Registry()
    c = r.register("dev1", "browser")
    assert c.status == ClientStatus.ONLINE
    s = r.open_session("dev1")
    assert s.state == SessionState.LISTENING
    assert r.session_for_device("dev1") is s
    r.close_session(s.session_id)
    assert r.session_for_device("dev1") is None


def test_registry_marks_stale_offline_but_keeps_entry():
    r = Registry()
    c = r.register("dev1", "browser")
    c.last_seen = 0  # ancient
    flipped = r.mark_stale(now=10_000)
    assert c in flipped and c.status == ClientStatus.OFFLINE
    assert r.get_client("dev1") is not None  # retained for re-register (FR-014)


def test_conversation_turn_latency():
    t = ConversationTurn(turn_id="t", session_id="s", started_at=1.0)
    assert t.latency_ms is None
    t.ended_at = 1.5
    assert t.latency_ms == 500.0
