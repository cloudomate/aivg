"""``sat-cli --json`` envelope contract (feature 011 T022).

Golden-files the v1 envelope shape:
``{ok, data, error, v}``.
Failing this test is a deliberate contract bump (R-8).
"""

from __future__ import annotations

import json

from aivg_cli import output


def _last_json_line(captured_stdout: str) -> dict:
    """Pull the last newline-terminated JSON object out of stdout."""
    return json.loads(captured_stdout.strip().splitlines()[-1])


def test_emit_ok_envelope_shape(capsys):
    output.set_context(json_mode=True, no_color=True, verbose=False)
    output.emit_ok({"hello": "world"})
    env = _last_json_line(capsys.readouterr().out)
    assert env == {
        "ok": True,
        "data": {"hello": "world"},
        "error": None,
        "v": 1,
    }


def test_emit_error_envelope_shape(capsys):
    output.set_context(json_mode=True, no_color=True, verbose=False)
    output.emit_error("device_offline", "kitchen is offline")
    env = _last_json_line(capsys.readouterr().out)
    assert env == {
        "ok": False,
        "data": None,
        "error": {"code": "device_offline", "message": "kitchen is offline"},
        "v": 1,
    }


def test_emit_ndjson_is_one_envelope_per_call(capsys):
    output.set_context(json_mode=True, no_color=True, verbose=False)
    output.emit_ndjson({"a": 1})
    output.emit_ndjson({"a": 2})
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["data"]["a"] == 1
    assert json.loads(lines[1])["data"]["a"] == 2


def test_envelope_version_is_v1(capsys):
    output.set_context(json_mode=True, no_color=True, verbose=False)
    output.emit_ok("x")
    env = _last_json_line(capsys.readouterr().out)
    assert env["v"] == 1


def test_error_code_set_is_documented_in_cli_contract():
    """Sanity: every code the CLI emits should appear in the exit_codes
    mapping. Catches accidental new codes that nothing maps."""
    from aivg_cli.exit_codes import _ERROR_CODE_TO_EXIT

    documented = set(_ERROR_CODE_TO_EXIT.keys())
    emitted = {
        "bad_input",
        "unknown_device",
        "config_conflict",
        "device_limit_reached",
        "already_adopted",
        "browser_not_ota_eligible",
        "device_offline",
        "gateway_unreachable",
        "ble_unavailable",
        "ble_provisioning_failed",
        "improv_timeout",
        "wifi_join_failed",
        "ota_failed",
        "rolled_back",
        "ota_in_progress",
        "internal_error",
    }
    missing = emitted - documented
    assert not missing, f"emitted codes not in exit_codes map: {missing}"
