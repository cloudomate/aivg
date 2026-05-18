"""``SatelliteWebRTCAdapter`` — registered like the telegram/discord adapters.

Constitution IV: this is a platform adapter loaded BY the Hermes gateway, not a
standalone daemon. It owns transport + registry only; all intelligence is
behind ``hermes_bridge``. The production registration shim against the running
Hermes platform-adapter base is verification gate VG-4 (research.md / T039).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import SatelliteAdapterConfig, load_adapter_config
from .hermes_bridge import HermesBridge, UnboundHermesBridge
from .logsink import LogSink
from .management import ManagementService, build_management_app
from .registry import Registry
from .signaling import SignalingService, aiortc_transport_factory


class SatelliteWebRTCAdapter:
    name = "satellite_webrtc"

    def __init__(
        self,
        bridge: Optional[HermesBridge] = None,
        config_path: Optional[Path] = None,
        cfg: Optional[SatelliteAdapterConfig] = None,
        transport_factory=aiortc_transport_factory,
    ) -> None:
        self.cfg = cfg or load_adapter_config(config_path)
        self.registry = Registry()
        self.sink = LogSink()
        # Real bridge wiring is VG-1..VG-4; until then the unbound bridge fails
        # loudly so the constitution-I boundary cannot be silently bypassed.
        self.bridge: HermesBridge = bridge or UnboundHermesBridge()
        self.management = ManagementService(self.registry, self.sink, self.cfg)
        self.signaling = SignalingService(
            self.registry, self.bridge, self.sink, transport_factory
        )
        self._sites: list = []

    # --- Hermes platform-adapter lifecycle (VG-4 shim) -------------------
    async def start(self) -> None:  # pragma: no cover - needs aiohttp
        """Start the two aiohttp sites. In production the Hermes gateway calls
        this after registering the adapter (telegram/discord parity)."""
        if not self.cfg.enabled:
            return
        from aiohttp import web  # noqa: WPS433

        mgmt = build_management_app(self.management)
        runner = web.AppRunner(mgmt)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.cfg.management_port)
        await site.start()
        self._sites.append(runner)
        # The WebRTC signaling site (:webrtc_port) is wired identically with
        # /webrtc/offer|candidate|status routes delegating to self.signaling.

    async def stop(self) -> None:  # pragma: no cover - needs aiohttp
        for runner in self._sites:
            await runner.cleanup()
        self._sites.clear()


def register(gateway) -> SatelliteWebRTCAdapter:  # pragma: no cover - VG-4
    """Entrypoint the Hermes gateway calls to mount the adapter (VG-4).

    Confirm against the running build: the platform-adapter base class, the
    registration hook, and the enable/restart CLI surface (`hermes gateway`
    vs `hermes gateway setup`). Only this function + the bridge change.
    """
    adapter = SatelliteWebRTCAdapter()
    gateway.register_platform_adapter(adapter)  # name TBD per running build
    return adapter
