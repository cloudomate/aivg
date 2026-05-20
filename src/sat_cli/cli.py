"""Legacy ``sat-cli`` binary dispatcher.

One-release compat alias (feature 012 FR-004, R-2). The
``[project.scripts] sat-cli`` entry in ``pyproject.toml`` points here.
On invocation:

1. Writes one **stderr** line (cached via :attr:`sys.__dict__` so it
   only prints once per process — JSON consumers piping stdout stay
   clean).
2. Forwards execution to :data:`aivg_cli.cli.app` with the original
   ``sys.argv``.

Removed in the release after feature 012.
"""

from __future__ import annotations

import sys

from aivg_cli.cli import app as _aivg_app

_LEGACY_NOTICE = (
    "sat-cli is renamed to aivg (feature 012, AIVG rebrand). "
    "The legacy binary still works for this release; please migrate "
    "your scripts to call `aivg` directly.\n"
)


def _emit_legacy_notice() -> None:
    if "_aivg_sat_cli_legacy_warned" in sys.__dict__:
        return
    sys.stderr.write(_LEGACY_NOTICE)
    sys.stderr.flush()
    sys.__dict__["_aivg_sat_cli_legacy_warned"] = True


def legacy_app() -> None:
    """Console-script entry point for the legacy ``sat-cli`` binary."""
    _emit_legacy_notice()
    _aivg_app()


# Module-level ``app`` re-export so ``from sat_cli.cli import app`` keeps
# working for callers that imported the Typer app directly (rather than
# the binary entry point).
app = _aivg_app
