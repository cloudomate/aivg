"""Feature 012 T034 — constitution Principle byte-equivalence drift guard.

Principle text MUST be byte-equivalent (modulo product-name strings) to the
blessed fixture at ``tests/fixtures/constitution_principles_normalized.md``.
Drift means normative content changed; that is only legitimate alongside an
intentional, version-bumped amendment that re-blesses the fixture.

Baseline history: the fixture was first blessed at the AIVG rebrand (v2.0.1,
a PATCH that changed only product-name strings) and re-blessed at **v2.1.0**,
the MINOR amendment that generalized Principle III to be transport-neutral
(feature 021; gRPC `Management`/`Audio.Stream` realize the same two-connection
separation as WebSocket/WebRTC).

This test extracts the Principle region from the live constitution, applies
the same ``__PRODUCT__`` substitution, and diffs against the fixture.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSTITUTION = REPO_ROOT / ".specify" / "memory" / "constitution.md"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "constitution_principles_normalized.md"

_PRODUCT_REGEX = re.compile(r"\bAIVG\b|\bHermes Voice\b|\bhermes voice\b")


def _principle_region(text: str) -> str:
    """Slice from the first `### I. ` heading through (but not
    including) the `## Hardware` section heading."""
    lines = text.splitlines(keepends=True)
    start = end = None
    for i, line in enumerate(lines):
        if start is None and line.startswith("### I."):
            start = i
        elif start is not None and line.startswith("## Hardware"):
            end = i
            break
    if start is None or end is None:
        raise AssertionError(
            "Could not locate the Principle region in the constitution — "
            "did the heading structure change?"
        )
    return "".join(lines[start:end])


def _normalize(text: str) -> str:
    return _PRODUCT_REGEX.sub("__PRODUCT__", text)


def test_principles_byte_equivalent_to_fixture():
    current = _normalize(_principle_region(CONSTITUTION.read_text()))
    fixture = FIXTURE.read_text()
    if current == fixture:
        return
    # Produce a readable diff in the assertion message so a future
    # accidental drift is debuggable.
    import difflib

    diff = "\n".join(
        difflib.unified_diff(
            fixture.splitlines(),
            current.splitlines(),
            fromfile="fixture (v2.1.0 baseline, normalized)",
            tofile="current constitution (normalized)",
            lineterm="",
        )
    )
    raise AssertionError(
        "Principle text drifted vs the byte-equivalence fixture. Normative "
        "constitution content must not change silently. If the change is "
        "intentional, re-bless the fixture and bump the constitution version "
        "(MINOR/MAJOR per the governance rule).\n\n" + diff
    )


def test_constitution_version_is_2_1_0():
    """Sanity guard so a contributor doesn't bump Principle text without
    bumping the constitution version (or vice versa)."""
    text = CONSTITUTION.read_text()
    assert "**Version**: 2.1.0" in text, (
        "constitution footer must declare Version 2.1.0 after the feature-021 "
        "Principle III transport-neutrality amendment"
    )
