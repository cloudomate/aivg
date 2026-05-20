"""Compatibility shim. Renamed twice — now :mod:`aivg_core`.

History:
``hermes_satellite_adapter`` (pre-feature-011) → ``satellite_core``
(feature 011 — the satellite system became agent-platform-agnostic) →
``aivg_core`` (feature 012 — the AIVG rebrand). This file is the
**two-hop** compat shim that forwards directly to ``aivg_core``,
skipping the intermediate ``satellite_core`` name.

Emits one :class:`DeprecationWarning` per process (cached on
``sys.__dict__``). Scheduled for deletion in the release after
feature 012.
"""

from __future__ import annotations

import sys as _sys
import warnings as _warnings

if "_aivg_hermes_satellite_adapter_shim_warned" not in _sys.__dict__:
    _warnings.warn(
        "hermes_satellite_adapter is renamed to aivg_core (feature 012, "
        "AIVG rebrand; first renamed to satellite_core in feature 011). "
        "Update imports to aivg_core.* — the Hermes-plugin bridge lives "
        "at aivg_core.platforms.hermes.bridge. This shim is removed in "
        "the next release.",
        DeprecationWarning,
        stacklevel=2,
    )
    _sys.__dict__["_aivg_hermes_satellite_adapter_shim_warned"] = True

# Module re-exports (so `from hermes_satellite_adapter.X import Y` still works).
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
from aivg_core.webrtc import (  # noqa: F401,E402
    media,
    session,
    signaling,
    streamasm,
    textseg,
)
from aivg_core.platforms.hermes import bridge as hermes_bridge  # noqa: F401,E402

__all__ = [
    "adapter",
    "config",
    "logsink",
    "management",
    "models",
    "persistence",
    "registry",
    "turnlatency",
    "media",
    "session",
    "signaling",
    "streamasm",
    "textseg",
    "hermes_bridge",
]
__version__ = "0.3.0-shim"
