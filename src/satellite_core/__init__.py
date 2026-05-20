"""Compatibility shim. Renamed to :mod:`aivg_core` in feature 012.

The package was renamed twice on its way to its current home:
``hermes_satellite_adapter`` → ``satellite_core`` (feature 011, when
the satellite system became agent-platform-agnostic) → ``aivg_core``
(feature 012, the AIVG rebrand). This shim re-exports the public
surface from :mod:`aivg_core` and emits **one**
:class:`DeprecationWarning` per process so external consumers get a
one-release window to migrate. Scheduled for deletion in the release
after feature 012.
"""

from __future__ import annotations

import sys as _sys
import warnings as _warnings

# One warning per process (not per import). Cached on ``sys.__dict__``
# so the sentinel survives reloads. (Feature 012 R-1.)
if "_aivg_satellite_core_shim_warned" not in _sys.__dict__:
    _warnings.warn(
        "satellite_core is renamed to aivg_core (feature 012, AIVG "
        "rebrand). Update imports to aivg_core.*. This shim is removed "
        "in the next release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _sys.__dict__["_aivg_satellite_core_shim_warned"] = True

# Module re-exports so ``from satellite_core.X import Y`` still works.
from aivg_core import (  # noqa: F401,E402  pragma: no cover
    adapter,
    config,
    logsink,
    models,
    persistence,
    registry,
    turnlatency,
)
from aivg_core import management  # noqa: F401,E402
from aivg_core import platforms  # noqa: F401,E402
from aivg_core import webrtc  # noqa: F401,E402

# Sub-modules tested directly via ``from satellite_core.X.Y import Z``.
from aivg_core.platforms.hermes import bridge as _hermes_bridge  # noqa: F401,E402
from aivg_core.webrtc import (  # noqa: F401,E402
    media,
    session,
    signaling,
    streamasm,
    textseg,
)

__all__ = [
    "adapter",
    "config",
    "logsink",
    "management",
    "models",
    "persistence",
    "platforms",
    "registry",
    "turnlatency",
    "webrtc",
    "media",
    "session",
    "signaling",
    "streamasm",
    "textseg",
]
__version__ = "0.3.0-shim"
