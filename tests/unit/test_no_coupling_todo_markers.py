"""Feature 015 / FR-012 / SC-001: zero ``# AgentPlatform-coupling-TODO``
markers may remain anywhere in ``src/aivg_core/``.

This is the CI-runnable grep gate that prevents the three markers
removed in feature 015 (in ``adapter.py``, ``webrtc/session.py``,
``webrtc/signaling.py``) from drifting back in any future refactor.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _REPO_ROOT / "src" / "aivg_core"


def test_no_agent_platform_coupling_todo_markers_in_core() -> None:
    """Grep ``src/aivg_core/`` for the coupling marker. Expect zero hits."""
    proc = subprocess.run(
        ["rg", "-n", "# AgentPlatform-coupling-TODO", str(_CORE_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )
    # rg exits 0 on match, 1 on no match, 2 on error.
    assert proc.returncode in (1, 2), (
        f"# AgentPlatform-coupling-TODO marker(s) found in {_CORE_DIR}:\n"
        f"{proc.stdout}\n"
        "Feature 015 closed the runtime side of the AgentPlatform seam; "
        "any re-introduction is a constitutional Principle IV regression "
        "(see specs/015-agentplatform-runtime-closure/contracts/agent-platform.md)."
    )
