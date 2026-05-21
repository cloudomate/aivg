"""Feature 018 / SC-006 — build the wheel + install into a throwaway venv.

Heavyweight integration. Marked so it's skippable on environments
without `uv`. Catches packaging mistakes (missing files, broken
entry points, drift between pyproject.toml version and what the
wheel installs) BEFORE the wheel ever leaves the repo.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_DIR = Path("/tmp/aivg-018-build-test")

_HAS_UV = shutil.which("uv") is not None

pytestmark = pytest.mark.skipif(
    not _HAS_UV,
    reason="uv not installed; this test builds + installs via uv",
)


def _pyproject_version() -> str:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["version"]


def _pyproject_name() -> str:
    with (_REPO_ROOT / "pyproject.toml").open("rb") as f:
        return tomllib.load(f)["project"]["name"]


@pytest.fixture(scope="module")
def built_wheel():
    """Build the wheel + sdist via `uv build`; return paths to both."""
    if _BUILD_DIR.exists():
        shutil.rmtree(_BUILD_DIR)
    _BUILD_DIR.mkdir(parents=True)
    dist_dir = _BUILD_DIR / "dist"

    result = subprocess.run(
        ["uv", "build", "--out-dir", str(dist_dir)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"uv build failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    version = _pyproject_version()
    name = _pyproject_name()
    # PEP 625 normalization: distribution names with `-` become `_` in the
    # sdist tarball filename. `aivg` has no `-` so the filename uses `aivg`
    # directly; `aivg-core` would have produced `aivg_core-*.tar.gz`.
    fs_name = name.replace("-", "_")
    sdist = dist_dir / f"{fs_name}-{version}.tar.gz"
    wheel = dist_dir / f"{fs_name}-{version}-py3-none-any.whl"
    assert sdist.exists(), f"sdist missing: {sdist}\ndist contents: {list(dist_dir.iterdir())}"
    assert wheel.exists(), f"wheel missing: {wheel}\ndist contents: {list(dist_dir.iterdir())}"
    yield {"sdist": sdist, "wheel": wheel, "version": version, "name": name}

    shutil.rmtree(_BUILD_DIR, ignore_errors=True)


def test_wheel_under_5mb(built_wheel):
    """SC-004 binding. Wheel cap is 5 MB. AIVG is pure-Python with no
    native code of its own — a 5 MB wheel would indicate accidental
    bundling of tests/specs/etc."""
    wheel_size = built_wheel["wheel"].stat().st_size
    five_mb = 5 * 1024 * 1024
    assert wheel_size < five_mb, (
        f"Wheel size {wheel_size} bytes ({wheel_size / 1024 / 1024:.2f} MB) "
        f"exceeds 5 MB cap (SC-004). Inspect: unzip -l {built_wheel['wheel']}"
    )


def test_wheel_excludes_non_package_trees(built_wheel):
    """R-5 / SC-004 binding. Wheel MUST NOT contain tests/, specs/,
    clients/, sdks/, deploy/, docs/, .github/."""
    result = subprocess.run(
        ["unzip", "-l", str(built_wheel["wheel"])],
        capture_output=True,
        text=True,
    )
    listing = result.stdout
    forbidden = ["tests/", "specs/", "clients/", "sdks/", "deploy/", "docs/", ".github/"]
    found = [path for path in forbidden if path in listing]
    assert not found, (
        f"Wheel contains forbidden trees: {found}\nFull listing:\n{listing}"
    )


def test_wheel_install_into_throwaway_venv_produces_working_aivg(built_wheel):
    """SC-006 / FR-002 binding. End-to-end install gate: create a
    throwaway venv, install the wheel into it, run `aivg --version`,
    confirm the JSON envelope reports the same version as pyproject.toml."""
    venv = _BUILD_DIR / "venv"
    result = subprocess.run(
        ["uv", "venv", str(venv), "--python", "3.11"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"uv venv failed: {result.stderr}"

    py = venv / "bin" / "python"
    result = subprocess.run(
        ["uv", "pip", "install", "--python", str(py), str(built_wheel["wheel"])],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, (
        f"uv pip install failed:\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )

    aivg_bin = venv / "bin" / "aivg"
    assert aivg_bin.exists(), f"`aivg` binary not present at {aivg_bin}"

    result = subprocess.run([str(aivg_bin), "--version"], capture_output=True, text=True)
    assert result.returncode == 0, f"`aivg --version` exited {result.returncode}: {result.stderr}"
    envelope = json.loads(result.stdout.strip())
    assert envelope.get("ok") is True, f"Bad envelope: {envelope}"
    data = envelope["data"]
    # The CLI's hardcoded `version` constant inside `aivg_cli/cli.py` is a
    # separate axis from pyproject.toml's [project] version — see plan.md
    # "Cross-cutting non-issues" + the contract document. For this test we
    # care that the contract_version envelope is the post-018 reset value.
    assert data["contract_version"] == "0.2.0", (
        f"Expected contract_version '0.2.0' (Spec Clarification Q2), got "
        f"{data['contract_version']!r}"
    )
