"""Unit: CLI help/contract surface (feature 011 T074).

Every command documented in cli-contract.md has --help; every flag
listed in the contract is present; --contract-version is unchanged.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _aivg(*args: str) -> str:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "aivg_cli.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    ).stdout


# --- commands documented in cli-contract.md ----------------------------


def test_root_help_lists_every_documented_top_level_command():
    out = _aivg("--help")
    for cmd in ("list", "watch", "logs", "device", "fleet", "ota", "onboard", "setup", "deploy"):
        assert cmd in out, f"top-level command {cmd!r} missing from --help"


# --- feature 013: setup / deploy commands -------------------------------


def test_setup_help_lists_every_setup_flag():
    """`aivg setup --help` lists every flag from setup-cli-contract.md."""
    out = _aivg("setup", "--help")
    for flag in (
        "--platform", "--preflight", "--uninstall", "--restore-backup",
        "--parity-check", "--yes", "--force", "--legacy-hermes", "--no-tune",
        "--phrase",
    ):
        assert flag in out, f"`aivg setup --help` missing {flag!r}"


def test_deploy_help_mirrors_setup_help():
    """FR-001: `aivg deploy` is an exact synonym of `aivg setup`."""
    out = _aivg("deploy", "--help")
    for flag in ("--platform", "--preflight", "--uninstall", "--yes"):
        assert flag in out, f"`aivg deploy --help` missing {flag!r}"


def test_device_subcommands():
    out = _aivg("device", "--help")
    for cmd in ("get", "config", "command", "delete"):
        assert cmd in out, f"`device {cmd}` missing from device --help"


def test_device_config_subcommands():
    out = _aivg("device", "config", "--help")
    for cmd in ("get", "set", "schema"):
        assert cmd in out, f"`device config {cmd}` missing"


def test_ota_subcommands():
    out = _aivg("ota", "--help")
    for cmd in ("check", "apply", "manifest"):
        assert cmd in out, f"`ota {cmd}` missing"


def test_fleet_subcommands():
    out = _aivg("fleet", "--help")
    assert "logs" in out


# --- global flags & version contract ------------------------------------


def test_global_flags_present():
    out = _aivg("--help")
    for flag in (
        "--gateway", "--json", "--yes", "--timeout",
        "--verbose", "--no-color", "--version", "--contract-version",
    ):
        assert flag in out, f"global flag {flag!r} missing"


def test_contract_version_at_post_021_baseline():
    """Feature 021 bumps the wire-contract version to 0.3.0 — an ADDITIVE
    minor over the 018 public baseline (0.2.0) that adds the gRPC transport.
    History: 1.0.0 → (017) 1.1.0 → (018) 0.2.0 → (021) 0.3.0."""
    out = _aivg("--json", "--contract-version")
    import json as _json
    env = _json.loads(out.strip().splitlines()[-1])
    assert env["data"]["contract_version"] == "0.3.0", (
        "Feature 021 bumps the contract envelope to 0.3.0 (additive: adds "
        "the grpc transport alongside webrtc + esphome_api)."
    )
    assert "grpc" in env["data"].get("transports", [])


def test_device_command_help_lists_args_flag():
    out = _aivg("device", "command", "--help")
    assert "--args" in out


def test_device_config_set_help_lists_optimistic_concurrency_flags():
    out = _aivg("device", "config", "set", "--help")
    for flag in ("--field", "--from-file", "--if-match", "--queue"):
        assert flag in out, f"`device config set` missing {flag!r}"


def test_ota_apply_help_has_follow_flag():
    out = _aivg("ota", "apply", "--help")
    assert "--follow" in out
