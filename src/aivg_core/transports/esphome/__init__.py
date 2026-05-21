"""ESPHome native API transport (feature 017).

Adds a TCP server (default port 6053) that speaks ESPHome's
plaintext-API wire protocol so any existing ESPHome voice satellite
(Home Assistant Voice Preview Edition, M5Stack Atom Echo, custom
ESP32 firmware built from ESPHome's voice-satellite YAML) talks to
AIVG with no client-side code from us.

The transport is **additive** — it runs alongside the existing
WebRTC voice plane, routing inbound audio through the same
:class:`aivg_core.platforms.base.AgentPlatform` (feature 015 runtime
closure) via the existing
:class:`aivg_core.webrtc.session.Session`.

Public surface (the only symbol the rest of ``aivg_core`` imports):

- :class:`EsphomeTransport` — the listener / lifecycle owner.

Plugin-internal modules (do NOT import from outside this package):

- :mod:`.framing` — wire encode/decode (uses ``aioesphomeapi`` proto + opcodes).
- :mod:`.auth` — per-device API-key keystore + verify.
- :mod:`.media_adapter` — adapts ESPHome PCM to the existing ``MediaTransport`` Protocol.
- :mod:`.connection` — per-device task body (one ``asyncio.Task`` each).
- :mod:`.voice_protocol` — voice_assistant_* message handlers + event mapping.
"""

from __future__ import annotations

# Lazy imports — the full class lands in US1 (T019/T020).
# Phase 2 ships the framing + auth + media-adapter sub-modules only.
__all__ = ["EsphomeTransport"]


def __getattr__(name: str):
    """Defer loading the concrete class until first reference (US1)."""
    if name == "EsphomeTransport":
        from .server import EsphomeTransport
        return EsphomeTransport
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
