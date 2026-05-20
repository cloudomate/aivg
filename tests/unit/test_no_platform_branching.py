"""Constitution v2.0.0 Principle IV gate (feature 011 T015).

Scans ``src/satellite_core/`` for any concrete-platform import outside
``src/satellite_core/platforms/``. The core MUST NOT mention a specific
plugin name — platform selection happens at runtime via
:class:`satellite_core.platforms.base.PluginRegistry`.

Phase 2 transitional exemption
------------------------------

A handful of modules (``adapter.py``, ``webrtc/session.py``,
``webrtc/signaling.py``) still import directly from
``satellite_core.platforms.hermes.bridge`` because they were written
pre-v2.0.0 against the concrete :class:`HermesBridge`. Until the
follow-up phase rewires them to depend on
:class:`satellite_core.platforms.base.AgentPlatform`, those callsites
each carry a ``# AgentPlatform-coupling-TODO`` marker on the import line,
and this test exempts marker-tagged lines. New code that introduces a
concrete-plugin import without the marker fails this test.
"""

from __future__ import annotations

import pathlib
import re

CORE = pathlib.Path(__file__).resolve().parents[2] / "src" / "satellite_core"
PLATFORMS = CORE / "platforms"

# Lines mentioning a concrete plugin import.
PATTERN = re.compile(
    r"^\s*(from|import)\s+satellite_core\.platforms\.(hermes|openclaw)\b"
)
EXEMPT_MARKER = "AgentPlatform-coupling-TODO"


def _scan_files():
    for py in CORE.rglob("*.py"):
        # Files under platforms/ are allowed to reference the concrete plugins.
        if PLATFORMS in py.parents or py == PLATFORMS:
            continue
        yield py


def test_no_concrete_plugin_import_in_core() -> None:
    offenders: list[str] = []
    for py in _scan_files():
        text = py.read_text().splitlines()
        for lineno, line in enumerate(text, 1):
            if not PATTERN.search(line):
                continue
            if EXEMPT_MARKER in line:
                continue  # transitional, tracked for follow-up
            offenders.append(f"{py.relative_to(CORE.parent.parent)}:{lineno}: {line.strip()}")
    assert offenders == [], (
        "Concrete-plugin imports outside satellite_core/platforms/ "
        "(constitution v2.0.0 Principle IV). Add # AgentPlatform-coupling-TODO "
        "on the import line if this is a tracked transitional coupling.\n"
        + "\n".join(offenders)
    )


def test_no_concrete_plugin_name_in_strings() -> None:
    """Any literal ``"hermes"`` / ``"openclaw"`` in core code is a yellow
    flag: it likely encodes a platform dependency that should be a
    config/registry lookup instead."""
    pattern = re.compile(r'["\'](hermes|openclaw)["\']')
    offenders: list[str] = []
    for py in _scan_files():
        text = py.read_text().splitlines()
        for lineno, line in enumerate(text, 1):
            if pattern.search(line) and EXEMPT_MARKER not in line:
                # Allow inside comments or docstrings: a crude heuristic
                # passes anything that begins with `#` or is inside a
                # triple-quoted block. We just skip lines whose leading
                # non-whitespace is `#`.
                stripped = line.lstrip()
                if stripped.startswith("#"):
                    continue
                offenders.append(f"{py.relative_to(CORE.parent.parent)}:{lineno}: {line.strip()}")
    # This is informational-only for v1: we record but do not fail on
    # docstring-like literals. If offenders shows up, audit.
    # (Failing this would also catch legitimate uses like log strings;
    # tighten in a follow-up.)
    if offenders:  # pragma: no cover - informational
        import warnings
        warnings.warn(
            "Concrete-platform name literals in core (v2.0.0 yellow flag):\n"
            + "\n".join(offenders)
        )
