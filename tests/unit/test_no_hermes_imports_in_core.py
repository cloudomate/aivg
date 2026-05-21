"""Feature 015 / FR-011 / SC-006: no ``aivg_core/`` module outside the
Hermes plugin directory may import any ``hermes``-prefixed symbol from
``aivg_core.platforms.hermes``.

The plugin's own submodules (``platforms/hermes/__init__.py``,
``platform.py``, ``bridge.py``, ``setup.py``) freely cross-import each
other — that's expected. What is forbidden is the satellite core
(``adapter.py``, ``webrtc/*``, ``management/*``, etc.) naming the
Hermes plugin directly: those callers must go through the
:class:`~aivg_core.platforms.base.AgentPlatform` Protocol via
:class:`~aivg_core.platforms.base.PluginRegistry`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORE_DIR = _REPO_ROOT / "src" / "aivg_core"
_PLUGIN_DIR_PREFIX = "src/aivg_core/platforms/hermes/"


def test_no_hermes_imports_in_aivg_core_outside_plugin() -> None:
    """``grep -rE 'from.*\\.hermes\\.' src/aivg_core/`` outside the
    plugin directory MUST return zero matches."""
    proc = subprocess.run(
        [
            "rg",
            "-n",
            r"from\s+[\.\w]+\.platforms\.hermes\.",
            str(_CORE_DIR),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode == 1:
        return  # zero matches → PASS
    if proc.returncode == 2:
        raise AssertionError(f"ripgrep failed: {proc.stderr}")

    # Filter the matches: anything under src/aivg_core/platforms/hermes/
    # is plugin-internal and allowed.
    offending = []
    for line in proc.stdout.splitlines():
        # rg output: "<abs-path>:<lineno>:<content>"
        try:
            path = line.split(":", 1)[0]
        except IndexError:
            continue
        rel = str(Path(path).resolve().relative_to(_REPO_ROOT))
        if not rel.startswith(_PLUGIN_DIR_PREFIX):
            offending.append(line)

    assert not offending, (
        "Hermes plugin imports leaked into aivg_core/ outside the plugin "
        "directory (feature 015 / FR-011 / SC-006):\n"
        + "\n".join(offending)
        + "\nThe satellite core MUST consume the agent platform through "
        "the AgentPlatform Protocol via PluginRegistry.load(), never by "
        "naming the Hermes plugin directly. See "
        "specs/015-agentplatform-runtime-closure/contracts/agent-platform.md."
    )
