"""Integration: destructive-confirm gate (feature 011 T073, US5, FR-019).

`aivg device command DEVICE_ID factory-reset` and `aivg device delete`
require explicit confirmation:

* Under interactive mode, the CLI prompts; non-`yes` cancels (exit 1).
* Under `--json` without `--yes`, refuses with `error.code=bad_input`
  (the agent must ask the user first, then re-run with `--yes`).
* Under `--json --yes`, proceeds (the agent has consent).

We drive the CLI in subprocesses so the real stdin/stderr behavior is
exercised.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _aivg(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-m", "aivg_cli.cli", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        input=stdin,
        timeout=15,
    )


def test_factory_reset_under_json_without_yes_refused():
    """JSON consumer that did NOT pass --yes must NOT see a prompt;
    instead, get error.code=bad_input on stdout."""
    res = _aivg(
        "--json", "--gateway", "http://127.0.0.1:1", "--timeout", "1",
        "device", "command", "kitchen", "factory-reset",
    )
    assert res.returncode == 1, res.stderr
    envelope = json.loads(res.stdout.strip().splitlines()[-1])
    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "bad_input"
    assert "without --yes" in envelope["error"]["message"]


def test_device_delete_under_json_without_yes_refused():
    res = _aivg(
        "--json", "--gateway", "http://127.0.0.1:1", "--timeout", "1",
        "device", "delete", "kitchen",
    )
    assert res.returncode == 1
    envelope = json.loads(res.stdout.strip().splitlines()[-1])
    assert envelope["error"]["code"] == "bad_input"


def test_interactive_factory_reset_cancelled_by_typing_no():
    """Type 'no' at the prompt → CLI aborts (exit 1) and does not call
    the gateway."""
    res = _aivg(
        "--gateway", "http://127.0.0.1:1", "--timeout", "1",
        "device", "command", "kitchen", "factory-reset",
        stdin="no\n",
    )
    assert res.returncode == 1
    # The prompt itself went to stderr; the action was cancelled before
    # any HTTP call (so no "gateway_unreachable" surfaces).
    assert "Destructive" in res.stderr


def test_non_destructive_verb_does_not_prompt():
    """`identify` is non-destructive; goes straight to the gateway. With
    no gateway listening we get gateway_unreachable (exit 3), not a
    confirmation refusal."""
    res = _aivg(
        "--json", "--gateway", "http://127.0.0.1:1", "--timeout", "1",
        "device", "command", "kitchen", "identify",
    )
    assert res.returncode == 3, res.stdout
    envelope = json.loads(res.stdout.strip().splitlines()[-1])
    assert envelope["error"]["code"] == "gateway_unreachable"


def test_unknown_verb_returns_bad_input():
    res = _aivg(
        "--json", "--gateway", "http://127.0.0.1:1", "--timeout", "1",
        "device", "command", "kitchen", "not-a-verb",
    )
    assert res.returncode == 1
    envelope = json.loads(res.stdout.strip().splitlines()[-1])
    assert envelope["error"]["code"] == "bad_input"
    assert "unknown verb" in envelope["error"]["message"]
