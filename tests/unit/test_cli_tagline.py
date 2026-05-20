"""``aivg`` CLI tagline + version smoke test (feature 012 T016, US1).

After the AIVG rebrand the binary identifies itself as AIVG; the
contract version is unchanged at 1.0.0.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def _aivg(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "aivg_cli.cli", *args],
        cwd=REPO_ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(REPO_ROOT / "src")},
        capture_output=True,
        text=True,
    )


def test_version_json_envelope():
    res = _aivg("--json", "--version")
    assert res.returncode == 0, res.stderr
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["ok"] is True
    assert env["v"] == 1
    assert "version" in env["data"]
    assert env["data"]["contract_version"] == "1.0.0"  # unchanged in rebrand


def test_contract_version_unchanged():
    res = _aivg("--json", "--contract-version")
    assert res.returncode == 0
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["data"]["contract_version"] == "1.0.0"


def test_help_tagline_mentions_aivg_not_legacy_product_name():
    res = _aivg("--help")
    assert res.returncode == 0
    out = res.stdout
    # The tagline now identifies the product as AIVG.
    assert "AIVG" in out, "CLI help must identify the product as AIVG"
    # The legacy product name MUST NOT appear in the help tagline (the
    # binary identity changed in feature 012).
    assert "Hermes Voice" not in out, (
        "CLI help still mentions the legacy product name 'Hermes Voice' — "
        "expected AIVG after feature 012 rebrand"
    )
