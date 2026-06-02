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
    # Feature 018 reset the contract to 0.2.0 (public baseline); feature 021
    # bumps to 0.3.0 (ADDITIVE — adds the "grpc" transport). History:
    # 1.0.0 → (017) 1.1.0 → (018) 0.2.0 → (021) 0.3.0.
    assert env["data"]["contract_version"] == "0.3.0"


def test_contract_version_at_post_021_baseline():
    """Feature 021: the wire-contract version is 0.3.0 — an additive bump
    over the 018 public baseline (0.2.0) that adds the gRPC transport. The
    transports list MUST enumerate which wires the gateway can speak."""
    res = _aivg("--json", "--contract-version")
    assert res.returncode == 0
    env = json.loads(res.stdout.strip().splitlines()[-1])
    assert env["data"]["contract_version"] == "0.3.0"
    transports = env["data"].get("transports", [])
    assert "webrtc" in transports
    assert "esphome_api" in transports
    assert "grpc" in transports


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
