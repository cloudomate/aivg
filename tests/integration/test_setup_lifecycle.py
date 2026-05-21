"""Integration: `aivg setup` lifecycle against the echo fixture (T014/T015).

T014 — SC-002 binding gate: `aivg setup --preflight` is byte-equivalent
read-only against the host (sha256-walk before/after = identical).

T015 — phase-sequence contract: under `--json --yes`, the install run
emits the documented phase set; every envelope matches `{ok,data,error,v=1}`.

The echo SetupCapability lives at ``tests/fixtures/platforms/echo/setup.py``
and is exposed under ``aivg_core.platforms.echo`` via the on-disk symlink
fixture (same approach as ``tests/contract/test_setup_cli.py``) so the
subprocess-invoked CLI can find it.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
ECHO_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "platforms" / "echo"


def _aivg(*args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "aivg_cli.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.fixture
def echo_host(tmp_path, monkeypatch):
    """Mirror of tests/contract/test_setup_cli.py::echo_host: symlink the
    echo fixture into the platforms package and point its host_root at a
    tmp dir via ``ECHO_HOST_ROOT``."""
    target_dir = REPO_ROOT / "src" / "aivg_core" / "platforms" / "echo"
    host_root = tmp_path / "echo-host"
    host_root.mkdir()
    # Pre-seed an arbitrary file so the byte-equivalence walk has
    # something to checksum. Preflight MUST leave this untouched.
    (host_root / "untouched.txt").write_text("byte-equivalent baseline\n")
    monkeypatch.setenv("ECHO_HOST_ROOT", str(host_root))
    # Also point AIVG state at a tmp dir so we don't pollute ~/.aivg/.
    monkeypatch.setenv("HOME", str(tmp_path))

    created_link = False
    if not target_dir.exists():
        os.symlink(ECHO_FIXTURE, target_dir, target_is_directory=True)
        created_link = True
    try:
        yield host_root
    finally:
        if created_link and target_dir.is_symlink():
            target_dir.unlink()


def _sha_walk(root: Path) -> dict[str, str]:
    """Return {relative-path: sha256-hex} for every regular file under
    ``root``. Used to prove preflight is byte-equivalent read-only."""
    out: dict[str, str] = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h = hashlib.sha256(p.read_bytes()).hexdigest()
            out[str(p.relative_to(root))] = h
    return out


# --- T014: SC-002 binding gate ----------------------------------------------


def test_preflight_is_byte_equivalent_readonly(echo_host):
    """SC-002: `aivg setup --preflight` does not mutate the host.

    Walk the host directory before + after preflight and assert the
    sha256 map is unchanged.
    """
    before = _sha_walk(echo_host)

    res = _aivg("--json", "setup", "--platform", "echo", "--preflight")
    assert res.returncode == 0, res.stdout + res.stderr

    after = _sha_walk(echo_host)
    assert before == after, (
        f"preflight mutated the host:\n  before: {before}\n  after: {after}"
    )


# --- T015: phase-sequence contract ------------------------------------------


def _ndjson_envelopes(stdout: str) -> list[dict]:
    """Parse stdout as a stream of JSON envelopes, one per line."""
    return [
        json.loads(ln)
        for ln in stdout.strip().splitlines()
        if ln.startswith("{")
    ]


def test_install_emits_full_phase_sequence(echo_host):
    """Under `--json --yes`, the install run emits the documented phase
    sequence; every envelope matches the v1 shape `{ok,data,error,v=1}`.
    """
    res = _aivg("--json", "setup", "--platform", "echo", "--yes")
    assert res.returncode == 0, res.stdout + res.stderr

    envs = _ndjson_envelopes(res.stdout)
    assert envs, "no envelopes emitted"

    # Every envelope is shape-compliant: {ok, data, error, v=1}.
    for env in envs:
        assert set(env.keys()) >= {"ok", "data", "error", "v"}, env
        assert env["v"] == 1, env

    # Extract the ordered list of phase names from data.phase fields.
    phases_seen = [
        e["data"]["phase"]
        for e in envs
        if isinstance(e.get("data"), dict) and "phase" in e["data"]
    ]
    # The closed set we expect — at minimum these phase names must all
    # appear (order matters for the headline progression).
    expected_subseq = [
        "detecting",
        "preflight",
        "backup",
        "vendoring",
        "config_writing",
        "installing_deps",
        "restarting_gateway",
        "post_verifying",
        "done",
    ]
    # Each expected phase appears at least once, in order.
    i = 0
    for name in expected_subseq:
        try:
            j = phases_seen.index(name, i)
        except ValueError:
            pytest.fail(
                f"phase {name!r} missing or out of order in {phases_seen!r}"
            )
        i = j + 1

    # Final envelope is the terminal `ok` (phase=done).
    last = envs[-1]
    assert last["ok"] is True, last
    assert last["data"]["phase"] == "done", last
    assert last["data"]["platform"] == "echo", last
    # Backup dir was recorded for rollback (R-5).
    assert last["data"].get("backup_dir"), last
