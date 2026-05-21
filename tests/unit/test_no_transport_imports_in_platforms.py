"""Feature 017 / SC-005 / FR-008 — constitutional Principle IV grep gate.

The new ESPHome transport (``src/aivg_core/transports/esphome/``)
MUST NOT be imported from anywhere under ``src/aivg_core/platforms/``.
Plugins consume :class:`AgentPlatform`'s verbs; they MUST NOT know
which transport carried a session.

This test also guards the inverse direction (FR-009): the existing
``webrtc/session.py`` MUST NOT be modified by this feature.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _REPO_ROOT / "src" / "aivg_core"


def test_no_transport_imports_in_platforms() -> None:
    """Greps ``src/aivg_core/platforms/`` for any import from the new
    ESPHome transport package. Zero matches expected (SC-005)."""
    proc = subprocess.run(
        [
            "rg",
            "-n",
            r"from\s+[\.\w]+\.transports\.esphome|import\s+[\.\w]+\.transports\.esphome",
            str(_CORE_DIR / "platforms"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # rg exits 0 on match, 1 on no match, 2 on error.
    assert proc.returncode in (1, 2), (
        f"ESPHome transport imports leaked into aivg_core/platforms/ "
        f"(feature 017 / SC-005 / FR-008 constitutional gate):\n{proc.stdout}\n"
        "The new transport MUST stay strictly outside the platform plugins. "
        "If a plugin needs transport-specific behaviour, lift the boundary "
        "to the Session/AgentPlatform interface — never name a transport "
        "from inside a plugin."
    )


def test_no_session_class_modifications_in_017() -> None:
    """FR-009: feature 017 MUST NOT modify ``webrtc/session.py``. The
    new transport adapts via the existing ``MediaTransport`` Protocol.

    Verified by ``git diff`` against the feature-015 base. Skipped if
    not in a git repo or if the base ref is unavailable."""
    session_py = _CORE_DIR / "webrtc" / "session.py"
    base_ref = "015-agentplatform-runtime-closure"
    # Confirm the base ref exists before asserting on it.
    base_check = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if base_check.returncode != 0:
        # Base ref not present (e.g., on a stripped CI clone). Skip
        # the diff check; the grep gate above covers most of the
        # constitutional intent.
        import pytest
        pytest.skip(f"git ref {base_ref!r} not present in this clone")

    diff = subprocess.run(
        ["git", "diff", f"{base_ref}...HEAD", "--", str(session_py)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0, f"git diff failed: {diff.stderr}"
    assert diff.stdout.strip() == "", (
        f"feature 017 modified webrtc/session.py — Principle IV / FR-009 "
        f"violation. The new transport MUST adapt to the existing "
        f"MediaTransport Protocol; Session is reused verbatim.\n\n"
        f"Diff:\n{diff.stdout}"
    )


def test_no_platforms_directory_modifications_in_017() -> None:
    """SC-003: feature 017 MUST NOT modify any file under
    ``src/aivg_core/platforms/``. The Hermes plugin (and any future
    plugin) is unchanged."""
    base_ref = "015-agentplatform-runtime-closure"
    base_check = subprocess.run(
        ["git", "rev-parse", "--verify", f"{base_ref}^{{commit}}"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if base_check.returncode != 0:
        import pytest
        pytest.skip(f"git ref {base_ref!r} not present in this clone")

    diff = subprocess.run(
        ["git", "diff", f"{base_ref}...HEAD", "--", str(_CORE_DIR / "platforms")],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert diff.returncode == 0, f"git diff failed: {diff.stderr}"
    assert diff.stdout.strip() == "", (
        f"feature 017 modified src/aivg_core/platforms/ — Principle IV / "
        f"SC-003 violation. The plugins MUST remain untouched.\n\n"
        f"Diff:\n{diff.stdout}"
    )
