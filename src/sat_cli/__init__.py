"""Compatibility shim. Renamed to :mod:`aivg_cli` in feature 012.

Re-exports the public surface from :mod:`aivg_cli` and emits **one**
:class:`DeprecationWarning` per process. Scheduled for deletion in the
release after feature 012.
"""

from __future__ import annotations

import sys as _sys
import warnings as _warnings

if "_aivg_sat_cli_shim_warned" not in _sys.__dict__:
    _warnings.warn(
        "sat_cli is renamed to aivg_cli (feature 012, AIVG rebrand). "
        "Update imports to aivg_cli.*. This shim is removed in the next "
        "release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _sys.__dict__["_aivg_sat_cli_shim_warned"] = True

from aivg_cli import *  # noqa: F401,F403,E402

__version__ = "0.2.0-shim"
