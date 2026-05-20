"""``SatelliteWebRTCAdapter`` — registered like the telegram/discord adapters.

Constitution IV: this is a platform adapter loaded BY the Hermes gateway, not a
standalone daemon. It owns transport + registry only; all intelligence is
behind ``hermes_bridge``. The production registration shim against the running
Hermes platform-adapter base is verification gate VG-4 (research.md / T039).
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from .config import SatelliteAdapterConfig, load_adapter_config
from .logsink import LogSink
from .management.service import ManagementService, build_management_app
from .platforms.hermes.bridge import HermesBridge, UnboundHermesBridge  # AgentPlatform-coupling-TODO
from .registry import Registry
from .webrtc.signaling import SignalingService, aiortc_transport_factory


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
            self.registry, self.bridge, self.sink, transport_factory,
            # Fan call-scoped UI events (state/partial transcript/barge-in)
            # onto the control-plane WS subscribers (constitution III).
            ui_broadcast=self.management._broadcast,
        )
        self._sites: list = []

    # --- Hermes platform-adapter lifecycle (VG-4 shim) -------------------
    async def start(self) -> None:  # pragma: no cover - needs aiohttp
        """Start the two aiohttp sites. In production the Hermes gateway calls
        this after registering the adapter (telegram/discord parity)."""
        if not self.cfg.enabled:
            return
        from aiohttp import web  # noqa: WPS433

        from .webrtc.signaling import build_signaling_app

        # 1) Control plane (always-on) on management_port.
        mgmt_runner = web.AppRunner(build_management_app(self.management))
        await mgmt_runner.setup()
        await web.TCPSite(mgmt_runner, "0.0.0.0", self.cfg.management_port).start()
        self._sites.append(mgmt_runner)

        # 2) WebRTC voice plane on webrtc_port — a SEPARATE site/port
        #    (constitution III / FR-003). If it fails to bind, tear the
        #    control plane back down and raise: the adapter must NEVER present
        #    itself ready in a control-up/signaling-down state (FR-005/SC-005)
        #    — the exact defect feature 003's live deploy surfaced.
        try:
            sig_runner = web.AppRunner(build_signaling_app(self.signaling))
            await sig_runner.setup()
            await web.TCPSite(sig_runner, "0.0.0.0", self.cfg.webrtc_port).start()
            self._sites.append(sig_runner)
        except Exception as exc:
            for r in self._sites:
                await r.cleanup()
            self._sites.clear()
            raise RuntimeError(
                f"satellite_webrtc not ready: signaling site failed to bind "
                f"on :{self.cfg.webrtc_port} ({exc}). Control plane torn down "
                f"to avoid a half-up adapter (FR-005)."
            ) from exc

    async def stop(self) -> None:  # pragma: no cover - needs aiohttp
        for runner in self._sites:
            await runner.cleanup()
        self._sites.clear()


def _aiortc_available() -> bool:
    import importlib.util

    return importlib.util.find_spec("aiortc") is not None


def build_platform_entry():  # pragma: no cover - host-only (needs hermes pkg)
    """Construct the Hermes ``PlatformEntry`` (VG-4 / research.md D17).

    Verified contract (hermes-agent v0.13.0,
    ``gateway.platform_registry.PlatformEntry`` / ``BasePlatformAdapter`` at
    ``gateway/platforms/base.py:1265``):

    - ``adapter_factory(config: PlatformConfig) -> BasePlatformAdapter``
    - the adapter subclasses ``BasePlatformAdapter(config, platform)``,
      implements ``connect() -> bool`` and ``send(chat_id, text, reply_to=…)``,
      and feeds each finished utterance to the base ``handle_message`` so the
      **gateway** drives the agent (constitution IV); the agent reply arrives
      back via ``send()``, where we run TTS through the bridge and push it to
      the WebRTC track.
    """
    # Verified against hermes-agent v0.13.0:
    #  - gateway.config.Platform is a CLOSED enum (no SATELLITE member);
    #    plugin platforms reuse Platform.LOCAL (the generic/uncategorised one).
    #  - PlatformRegistry.create_adapter() passes only `config` to the factory;
    #    the adapter supplies `platform` itself to BasePlatformAdapter.
    #  - inbound routing is MessageEvent(text, source=SessionSource(...));
    #    there is NO `chat_id` kwarg on MessageEvent.
    from gateway.config import Platform  # type: ignore
    from gateway.platform_registry import PlatformEntry  # type: ignore
    from gateway.platforms.base import (  # type: ignore
        BasePlatformAdapter,
        MessageEvent,
        SendResult,
    )
    from gateway.session import SessionSource  # type: ignore

    from .platforms.hermes.bridge import HermesV013Bridge, SessionCtx  # AgentPlatform-coupling-TODO

    class _SatellitePlatformAdapter(BasePlatformAdapter):
        def __init__(self, config) -> None:
            super().__init__(config, Platform.LOCAL)

            # agent_runner bridges the gateway's async handle_message→send
            # path into the value HermesV013Bridge.agent_turn awaits.
            async def _run_agent(text: str, ctx: SessionCtx) -> str:
                fut: "asyncio.Future[str]" = asyncio.get_event_loop().create_future()
                self._satellite_reply_futs[ctx.session_id] = fut
                await self.handle_message(self._make_event(text, ctx))
                return await fut

            self._satellite_reply_futs: dict = {}
            # Feature 008: the agent text-delta seam + barge-in's
            # AIAgent.interrupt() live INSIDE HermesV013Bridge.agent_stream
            # (research.md D2/D5). The adapter only retains the
            # handle_message→send-future path, used solely as the FR-005
            # feature-006 fallback when the delta seam is unavailable; the
            # gateway draft-streaming hook is NOT implemented here (it was
            # proven unreachable for the LOCAL/voice path — research.md D1).
            self._bridge = HermesV013Bridge(agent_runner=_run_agent)
            self._impl = SatelliteWebRTCAdapter(bridge=self._bridge)

        def _make_event(self, text: str, ctx: SessionCtx):
            source = SessionSource(
                platform=Platform.LOCAL,
                chat_id=ctx.session_id,
                user_id=ctx.device_id,
                chat_type="dm",
            )
            return MessageEvent(text=text, source=source)

        # BasePlatformAdapter.__abstractmethods__ (v0.13.0) =
        #   {connect, disconnect, get_chat_info, send} — all implemented.
        async def connect(self) -> bool:
            await self._impl.start()
            return True

        async def disconnect(self) -> None:
            await self._impl.stop()

        async def get_chat_info(self, chat_id):
            # chat_id == VoiceSession.session_id; this is a 1:1 voice "dm".
            return {"chat_id": chat_id, "chat_type": "dm", "platform": "satellite_webrtc"}

        async def send(self, chat_id, content, reply_to=None, metadata=None, **kw):
            # Hermes calls send(chat_id=, content=, reply_to=, metadata=) and
            # consumes a SendResult (gateway/platforms/base.py:2485). Verified
            # against hermes-agent v0.13.0 (telegram adapter parity).
            #
            # Feature 008: the only consumer of this path is the FR-005
            # feature-006 fallback — HermesV013Bridge.agent_turn awaits the
            # per-session reply future the gateway resolves here with the
            # completed reply. The streaming path never uses send() (it runs
            # Hermes's AIAgent directly via the text-delta seam).
            fut = self._satellite_reply_futs.pop(chat_id, None)
            if fut and not fut.done():
                fut.set_result(content)  # agent_turn() fallback path
            return SendResult(success=True, message_id=None)

    return PlatformEntry(
        name="satellite_webrtc",
        label="Satellite WebRTC",
        adapter_factory=_SatellitePlatformAdapter,
        check_fn=_aiortc_available,
        source="plugin",
        plugin_name="hermes_satellite_adapter",
    )


def register(gateway=None):  # pragma: no cover - host-only
    """Mount the adapter on the running Hermes gateway (VG-4).

    Registers with the global ``PlatformRegistry``; lifecycle is the standard
    ``hermes gateway`` / configuration ``hermes gateway setup``. The
    ``satellite:`` block is read by the existing ``GatewayConfig`` loader —
    no new config or secret store (constitution IV).
    """
    from gateway.platform_registry import platform_registry  # type: ignore

    entry = build_platform_entry()
    platform_registry.register(entry)
    return entry
