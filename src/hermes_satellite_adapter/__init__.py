"""Compatibility shim. Renamed to :mod:`satellite_core` in feature 011.

Under constitution v2.0.0 the satellite system is **agent-platform-
agnostic**; the package was renamed from ``hermes_satellite_adapter`` to
``satellite_core`` and the Hermes-specific code moved to
``satellite_core.platforms.hermes`` (the v1 canonical plugin).

This shim re-exports the public surface from the new locations and emits a
:class:`DeprecationWarning` so any external consumer (or any straggler in
this repo) gets a one-release window to migrate. Scheduled for deletion in
feature 011 Phase 8 task **T081**.
"""

from __future__ import annotations

import warnings as _warnings

_warnings.warn(
    "hermes_satellite_adapter is renamed to satellite_core (feature 011, "
    "constitution v2.0.0). Update imports to satellite_core.* — the Hermes "
    "bridge lives at satellite_core.platforms.hermes.bridge. This shim is "
    "removed in Phase 8 (T081).",
    DeprecationWarning,
    stacklevel=2,
)

# Module re-exports (so `from hermes_satellite_adapter.X import Y` still works).
from satellite_core import (  # noqa: F401,E402  pragma: no cover
    adapter,
    config,
    logsink,
    models,
    registry,
    turnlatency,
)
from satellite_core import management  # noqa: F401,E402
from satellite_core.webrtc import (  # noqa: F401,E402
    media,
    session,
    signaling,
    streamasm,
    textseg,
)
from satellite_core.platforms.hermes import bridge as hermes_bridge  # noqa: F401,E402

__all__ = [
    "adapter",
    "config",
    "logsink",
    "management",
    "models",
    "registry",
    "turnlatency",
    "media",
    "session",
    "signaling",
    "streamasm",
    "textseg",
    "hermes_bridge",
]
__version__ = "0.2.0-shim"
