"""Feature 012 T036/T037/T038 — rebrand lint (US5, FR-012).

Scans the working tree for the obsolete product-name regex
``\\bHermes Voice\\b | \\bhermes voice\\b`` across text suffixes and
fails on any non-allow-listed match outside a comment line.

The allow-list lives in ``docs/rebrand-allow-list.md``; the lint reads
it. Adding a path to the allow-list is the contributor-facing way to
record a legitimate historical reference; the test also asserts every
allow-list pattern resolves to at least one file (catches typos).
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLOW_LIST = REPO_ROOT / "docs" / "rebrand-allow-list.md"

# The obsolete product-name regex. `Hermes` alone is NOT matched — that
# legitimately refers to the agent-platform plugin per constitution
# v2.0.0 Principle IV.
LEGACY_NAME = re.compile(r"\bHermes Voice\b|\bhermes voice\b")

# Files we scan: text formats only; binary excluded.
SCAN_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml", ".cfg"}

# Directories we never descend into. ``.specify`` is intentionally NOT
# excluded — the constitution lives under it and must be scanned. The
# Spec Kit templates under ``.specify/templates/`` are clean of the
# obsolete product name (they're generic), so the lint stays cheap.
SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}


def _read_allow_list() -> list[str]:
    """Parse the gitignore-style patterns from
    ``docs/rebrand-allow-list.md``.

    Patterns are lines inside the fenced code block; whole-line ``#``
    starts a comment; blanks are ignored.
    """
    text = ALLOW_LIST.read_text()
    patterns: list[str] = []
    in_code_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            continue
        if not stripped or stripped.startswith("#"):
            continue
        # Trim trailing inline comments like `path  # explanation`.
        if "#" in stripped:
            stripped = stripped.split("#", 1)[0].strip()
        if stripped:
            patterns.append(stripped)
    return patterns


def _iter_repo_files():
    for path in REPO_ROOT.rglob("*"):
        if not path.is_file():
            continue
        # Skip any path that has a SKIP_DIRS segment.
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix not in SCAN_SUFFIXES:
            continue
        yield path


def _matches_allow(rel: Path, patterns: list[str]) -> bool:
    s = str(rel)
    for pat in patterns:
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if s == prefix or s.startswith(prefix + "/"):
                return True
        if fnmatch.fnmatch(s, pat):
            return True
    return False


def test_allow_list_patterns_resolve_to_real_paths():
    """Every pattern in the allow-list MUST resolve to at least one
    repo path. Orphaned patterns are typos that mask real lint hits."""
    patterns = _read_allow_list()
    assert patterns, "allow-list parsed empty — did the fenced code block break?"
    orphans = []
    repo_paths = [str(p.relative_to(REPO_ROOT)) for p in _iter_repo_files()]
    for pat in patterns:
        if pat.endswith("/**"):
            prefix = pat[:-3]
            if not any(p == prefix or p.startswith(prefix + "/") for p in repo_paths):
                orphans.append(pat)
            continue
        if not any(fnmatch.fnmatch(p, pat) for p in repo_paths):
            orphans.append(pat)
    assert not orphans, f"allow-list patterns matching no files (typos?): {orphans}"


def test_no_legacy_product_name_outside_allow_list():
    patterns = _read_allow_list()
    offenders: list[str] = []
    for path in _iter_repo_files():
        rel = path.relative_to(REPO_ROOT)
        if _matches_allow(rel, patterns):
            continue
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), 1):
            if LEGACY_NAME.search(line):
                # Comment-prefixed lines (whole-line `#`) are exempt;
                # they let a contributor write a one-line "(formerly
                # Hermes Voice)" note in a docstring without
                # allow-listing the whole file.
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                offenders.append(f"{rel}:{lineno}: {line.strip()}")
    if offenders:
        raise AssertionError(
            "Obsolete product-name 'Hermes Voice' found outside the "
            "rebrand allow-list (docs/rebrand-allow-list.md). Either "
            "rewrite the prose to 'AIVG' (and disambiguate any Hermes-"
            "as-plugin mentions) or add the file to the allow-list "
            "with a comment.\n\n" + "\n".join(offenders)
        )
