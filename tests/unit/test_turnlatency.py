"""Feature 010 — the pure latency-breakdown assembly (locally provable
slice; real wall-clock reductions are host-proven, constitution V).

Asserts contracts L2/L3: ordered, contiguous, sums to total within
tolerance, dominant identifiable, and robust to missing / interrupted /
error / empty / duplicate / out-of-order instants (FR-008/SC-003).
"""

from aivg_core.turnlatency import (
    INSTANTS,
    build_breakdown,
)

_TOL = 1e-6


def _full(base=100.0):
    # 0.5, 1.2, 0.8, 0.3, 0.4, 0.2 s segments → total 3.4 s
    return {
        "end_of_speech": base + 0.0,
        "endpoint_detected": base + 0.5,
        "stt_done": base + 1.7,
        "agent_first_output": base + 2.5,
        "first_unit_ready": base + 2.8,
        "first_audio_synth": base + 3.2,
        "first_audio_delivered": base + 3.4,
    }


def test_full_turn_ordered_sums_to_total_dominant():
    b = build_breakdown(_full())
    assert b.complete is True
    assert [s.name for s in b.stages] == [
        "endpoint", "stt", "agent", "assemble", "synth", "playback"
    ]
    assert abs(sum(s.seconds for s in b.stages) - b.total_s) < _TOL  # L2
    assert abs(b.total_s - 3.4) < 1e-6
    assert b.dominant == "stt"  # 1.2 s is the largest segment


def test_missing_middle_instant_widens_gap_still_sums():
    inst = _full()
    del inst["agent_first_output"]  # agent/assemble merge into one gap
    b = build_breakdown(inst)
    assert b.complete is False
    assert abs(sum(s.seconds for s in b.stages) - b.total_s) < _TOL
    # the merged gap is labelled by where time began accumulating (stt_done)
    assert any(s.start == "stt_done" and s.end == "first_unit_ready"
               for s in b.stages)


def test_missing_tail_only_present_stages():
    inst = _full()
    for k in ("first_unit_ready", "first_audio_synth", "first_audio_delivered"):
        del inst[k]
    b = build_breakdown(inst)
    assert b.complete is False
    assert b.stages[-1].end == "agent_first_output"
    assert abs(sum(s.seconds for s in b.stages) - b.total_s) < _TOL


def test_empty_and_single_instant_no_raise():
    for inst in (None, {}, {"end_of_speech": 1.0}):
        b = build_breakdown(inst)
        assert b.stages == () and b.total_s == 0.0 and b.dominant is None
        assert b.complete is False


def test_out_of_order_clamped_not_negative():
    inst = {
        "end_of_speech": 10.0,
        "endpoint_detected": 9.0,            # earlier than start → clamp 0
        "stt_done": 12.0,
        "first_audio_delivered": 11.5,       # before stt_done → clamp 0
    }
    b = build_breakdown(inst)
    # Robustness contract: never negative, never raises (FR-008/L3).
    # The sum==total invariant deliberately does NOT hold once negative
    # gaps are clamped (a starved clock / barge-in can produce these) —
    # clamping safety wins over the accounting identity here.
    assert all(s.seconds >= 0.0 for s in b.stages)
    assert b.total_s >= 0.0


def test_duplicate_instants_are_idempotent():
    a = build_breakdown(_full())
    inst = _full()
    inst.update(_full())  # same values again (mapping dedups)
    b = build_breakdown(inst)
    assert b.as_log_fields() == a.as_log_fields()


def test_log_fields_coherent_record():
    b = build_breakdown(_full())
    f = b.as_log_fields()
    assert f["total_ms"] == 3400.0
    assert f["dominant"] == "stt" and f["complete"] is True
    assert set(f) >= {"endpoint_ms", "stt_ms", "agent_ms", "assemble_ms",
                       "synth_ms", "playback_ms", "total_ms"}


def test_canonical_instant_order_is_the_contract():
    assert INSTANTS[0] == "end_of_speech"
    assert INSTANTS[-1] == "first_audio_delivered"
    assert len(INSTANTS) == 7


def test_latency_log_mode_is_config_sourced_not_hardcoded(monkeypatch):
    """SC-009/FR-011/L7: the instrumentation verbosity is READ from the
    existing satellite config block, not a hardcoded constant — changing
    the config value changes the consumed mode (no code change)."""
    import aivg_core.webrtc.session as sess
    from aivg_core.config import SatelliteAdapterConfig

    for want in ("full", "off", "summary"):
        cfg = SatelliteAdapterConfig(default_config={"latency_log": want})
        monkeypatch.setattr(sess, "_LAT_MODE_CACHE", None)
        monkeypatch.setattr(sess, "load_adapter_config", lambda: cfg,
                            raising=False)
        # also patch the lazily-imported symbol path
        monkeypatch.setattr(
            "aivg_core.config.load_adapter_config",
            lambda *a, **k: cfg,
        )
        assert sess._latency_log_mode() == want

    # unknown / unreadable → safe default, never raises
    monkeypatch.setattr(sess, "_LAT_MODE_CACHE", None)
    monkeypatch.setattr(
        "aivg_core.config.load_adapter_config",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no config")),
    )
    assert sess._latency_log_mode() == "summary"
