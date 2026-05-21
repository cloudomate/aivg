"""Feature 018 / FR-009 — assert pyproject.toml has every required PyPI field.

Pure-static. Runs in <0.5s in the regular pytest suite. Catches
metadata drift (someone deletes the `license` key, adds a classifier
typo, points the Documentation URL at a 404) BEFORE the wheel ever
leaves the repo.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPROJECT = _REPO_ROOT / "pyproject.toml"


def _project() -> dict:
    with _PYPROJECT.open("rb") as f:
        return tomllib.load(f)["project"]


def test_distribution_name_is_canonical_aivg():
    """Spec Clarification Q2: PyPI distribution name MUST be `aivg`."""
    p = _project()
    assert p["name"] == "aivg", (
        f"Expected PyPI distribution name 'aivg', got {p['name']!r}. "
        "Spec 018 Clarification Q2 locks the canonical short name."
    )


def test_version_matches_public_baseline_or_later():
    """Spec Clarification Q1: first PyPI release is 0.2.0; subsequent
    releases evolve forward. Reject any 0.1.x or 0.0.x (pre-baseline)."""
    p = _project()
    version = p["version"]
    parts = version.split(".")
    assert len(parts) >= 2, f"Expected semver-like version, got {version!r}"
    major, minor = int(parts[0]), int(parts[1])
    # 0.2.0 baseline: forbid 0.0.x and 0.1.x
    assert (major, minor) >= (0, 2), (
        f"Version {version!r} predates the 0.2.0 public baseline "
        "(Spec 018 Clarification Q1). Bump pyproject.toml [project] version."
    )


def test_required_pypi_fields_present():
    """FR-009 binding: every required PyPI metadata field present."""
    p = _project()
    required = {
        "name", "version", "description", "requires-python",
        "license", "readme", "authors", "maintainers",
        "keywords", "classifiers", "dependencies",
    }
    missing = required - p.keys()
    assert not missing, f"pyproject.toml [project] missing required fields: {sorted(missing)}"


def test_license_is_mit():
    """Spec Clarification (research R-4): MIT, matching sdks/typescript/LICENSE."""
    p = _project()
    license_field = p["license"]
    # Accept either PEP 621 text form ({"text": "MIT"}) or SPDX string ("MIT")
    if isinstance(license_field, dict):
        assert license_field.get("text") == "MIT", f"License text != MIT: {license_field}"
    else:
        assert license_field == "MIT", f"License != MIT: {license_field}"


def test_classifiers_include_mit_and_python_311():
    p = _project()
    classifiers = p["classifiers"]
    assert "License :: OSI Approved :: MIT License" in classifiers, (
        "Missing MIT license classifier — PyPI sidebar facet won't show MIT badge."
    )
    py_classifiers = [c for c in classifiers if c.startswith("Programming Language :: Python :: 3.")]
    assert py_classifiers, "No Python 3.x classifier — PyPI version-facet will be empty."
    # Must cover the supported Python versions; 3.11 is the minimum per requires-python.
    assert any("3.11" in c for c in py_classifiers), "Python 3.11 classifier missing."


def test_project_urls_present():
    p = _project()
    urls = p.get("urls", {})
    required_urls = {"Repository", "Issues", "Changelog", "Documentation"}
    missing = required_urls - urls.keys()
    assert not missing, f"[project.urls] missing keys: {sorted(missing)}"
    # All URLs should target the canonical repo (no typos).
    for key, url in urls.items():
        assert "github.com/cloudomate/aivg" in url, (
            f"[project.urls] {key!r} = {url!r} doesn't point at cloudomate/aivg"
        )


def test_entry_points_declare_aivg_satellite():
    """The `aivg-satellite` entry-point is what Hermes auto-discovers
    under group `hermes_agent.plugins`. Without it, post-install Hermes
    can't find the plugin (the trap that requires `pip install` into
    the Hermes venv to work at all)."""
    p = _project()
    entry_points = p.get("entry-points", {})
    hermes_group = entry_points.get("hermes_agent.plugins", {})
    assert "aivg-satellite" in hermes_group, (
        "Missing entry-point 'aivg-satellite' under 'hermes_agent.plugins'. "
        "Without it, Hermes can't auto-discover the AIVG plugin post-install."
    )


def test_console_script_aivg_present():
    p = _project()
    scripts = p.get("scripts", {})
    assert "aivg" in scripts, "Missing console-script 'aivg' — `aivg --version` won't work post-install."
