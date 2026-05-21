"""Contract: `aivg setup` CLI surface (feature 013 T013, US1).

Typer help contract, mutually-exclusive flag rejection, refusal under
--json without --yes (FR-010), --preflight is read-only against the
echo fixture (binding for SC-002).
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ECHO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "platforms" / "echo"


def _aivg(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, "-m", "aivg_cli.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )


@pytest.fixture
def echo_host(tmp_path, monkeypatch):
    """Spin up the echo fixture as `aivg_core.platforms.echo` by
    symlinking it into the platforms package for the duration of the
    test. This works for subprocess-invoked CLI tests because the
    symlink is on disk, not just sys.modules.

    Also points the fixture's per-instance `host_root` at a tmp dir via
    `ECHO_HOST_ROOT` so detect()/install() operate on isolated state
    (the env var propagates to `_aivg(...)` subprocess via os.environ).
    """
    target_dir = REPO_ROOT / "src" / "aivg_core" / "platforms" / "echo"
    host_root = tmp_path / "echo-host"
    host_root.mkdir()
    monkeypatch.setenv("ECHO_HOST_ROOT", str(host_root))
    created_link = False
    if not target_dir.exists():
        os.symlink(ECHO_FIXTURE, target_dir, target_is_directory=True)
        created_link = True
    try:
        yield host_root
    finally:
        if created_link and target_dir.is_symlink():
            target_dir.unlink()


# --- help / flag contract ----------------------------------------------------


def test_setup_help_lists_every_documented_flag():
    res = _aivg("setup", "--help")
    assert res.returncode == 0, res.stderr
    for flag in (
        "--platform", "--preflight", "--uninstall", "--restore-backup",
        "--parity-check", "--yes", "--force", "--legacy-hermes", "--no-tune",
        "--phrase",
    ):
        assert flag in res.stdout, f"`aivg setup --help` missing {flag!r}"


def test_deploy_is_synonym_for_setup():
    """FR-001: `aivg deploy` is an exact synonym."""
    setup_help = _aivg("setup", "--help").stdout
    deploy_help = _aivg("deploy", "--help").stdout
    # Both should list the same flag set.
    for flag in ("--platform", "--preflight", "--uninstall", "--yes"):
        assert flag in setup_help and flag in deploy_help


# --- mutually-exclusive modes -----------------------------------------------


def test_preflight_and_uninstall_are_mutually_exclusive():
    res = _aivg("--json", "setup", "--preflight", "--uninstall")
    assert res.returncode == 1
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["error"]["code"] == "bad_input"
    assert "mutually exclusive" in env["error"]["message"]


def test_legacy_hermes_and_no_tune_are_mutually_exclusive():
    res = _aivg("--json", "setup", "--preflight", "--legacy-hermes", "--no-tune")
    assert res.returncode == 1
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["error"]["code"] == "bad_input"


def test_parity_check_requires_phrase():
    res = _aivg("--json", "setup", "--parity-check")
    assert res.returncode == 1
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["error"]["code"] == "bad_input"
    assert "phrase" in env["error"]["message"].lower()


# --- destructive-confirm gate under --json without --yes (FR-010) -----------


def test_install_under_json_without_yes_refused(echo_host):
    res = _aivg("--json", "setup", "--platform", "echo")
    assert res.returncode == 1, res.stdout
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["error"]["code"] == "bad_input"
    assert "without --yes" in env["error"]["message"]


def test_uninstall_under_json_without_yes_refused(echo_host):
    res = _aivg("--json", "setup", "--platform", "echo", "--uninstall")
    assert res.returncode == 1
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["error"]["code"] == "bad_input"


# --- detection precedence (R-2) ----------------------------------------------


def test_explicit_platform_takes_precedence(echo_host):
    """`--platform echo` selects the echo plugin even with Hermes
    detectable on the host."""
    res = _aivg("--json", "setup", "--platform", "echo", "--preflight")
    assert res.returncode == 0, res.stdout
    # First envelope should be the detecting/started for echo.
    envs = [json.loads(ln) for ln in res.stdout.strip().splitlines() if ln.startswith("{")]
    detecting_ok = next(
        e for e in envs if e["data"].get("phase") == "detecting" and e["data"].get("status") == "ok"
    )
    assert detecting_ok["data"]["detail"]["platform"] == "echo"


def test_unknown_platform_refused():
    res = _aivg("--json", "setup", "--platform", "does_not_exist", "--preflight")
    assert res.returncode == 1
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["error"]["code"] in ("no_platform_detected", "setup_not_supported_for_platform")


# --- closed error-code set --------------------------------------------------


def test_setup_error_codes_in_exit_code_map():
    """Every documented setup error.code is mapped to an exit code."""
    from aivg_cli.exit_codes import _ERROR_CODE_TO_EXIT

    for code in (
        "no_platform_detected",
        "multiple_platforms_detected",
        "setup_not_supported_for_platform",
        "setup_lock_held",
        "setup_partial_failure",
        "permission_denied",
        "host_state_drifted",
    ):
        assert code in _ERROR_CODE_TO_EXIT, f"feature 013 error.code {code!r} missing from exit-code map"
