"""``AivgSatelliteAdapter`` — registered like the telegram/discord adapters.

Constitution IV: this is a platform adapter loaded BY an agent-platform's
gateway, not a standalone daemon. Feature 015 closed the runtime side of
the AgentPlatform seam: this module imports only the platform-neutral
:class:`~aivg_core.platforms.base.AgentPlatform` Protocol and resolves
the active platform via :class:`PluginRegistry`. The Hermes-specific
registration shim against the Hermes platform-adapter base lives in
:func:`build_platform_entry` below.

Feature 019 renamed this from ``SatelliteWebRTCAdapter`` (which was
pre-rebrand AND misleadingly suffixed ``_webrtc`` even though feature
017 added the ESPHome transport under the same plugin). The old
``SatelliteWebRTCAdapter`` name is preserved as a back-compat alias at
the bottom of this module for one release.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from .config import SatelliteAdapterConfig, load_adapter_config
from .logsink import LogSink
from .management.service import ManagementService, build_management_app
from .platforms.base import (
    AgentPlatform,
    PluginRegistry,
    _validate_agent_platform,
)
from .platforms.hermes.setup import CANONICAL_PLUGIN_NAME
from .registry import Registry
from .webrtc.signaling import SignalingService, aiortc_transport_factory


class AivgSatelliteAdapter:
    name = CANONICAL_PLUGIN_NAME

    def __init__(
        self,
        platform: Optional[AgentPlatform] = None,
        config_path: Optional[Path] = None,
        cfg: Optional[SatelliteAdapterConfig] = None,
        transport_factory=aiortc_transport_factory,
    ) -> None:
        self.cfg = cfg or load_adapter_config(config_path)
        self.registry = Registry()
        self.sink = LogSink()
        # Propagate the TTS text-filter toggle (markdown + emoji stripping)
        # into the filter module — the Hermes bridge reads its effective
        # state per-call. Env-var `AIVG_DISABLE_TTS_TEXT_FILTER` still wins.
        from .webrtc.tts_text_filter import set_enabled as _set_tts_filter
        _set_tts_filter(self.cfg.tts_text_filter)
        # Feature 015 / FR-001 / FR-007: resolve the active agent
        # platform via the plugin registry (defaults to "hermes" via
        # adapter config). Validate the surface fail-fast at startup so
        # a misconfigured plugin can never accept a single inbound
        # frame.
        if platform is None:
            platform = PluginRegistry.load(self.cfg.platform)
        _validate_agent_platform(platform)
        self.platform: AgentPlatform = platform
        self.management = ManagementService(self.registry, self.sink, self.cfg)
        self.signaling = SignalingService(
            self.registry, self.platform, self.sink, transport_factory,
            # Fan call-scoped UI events (state/partial transcript/barge-in)
            # onto the control-plane WS subscribers (constitution III).
            ui_broadcast=self.management._broadcast,
        )
        self._sites: list = []
        # Feature 017 — optional ESPHome native API transport. Off by
        # default; opt-in via ``transports.esphome_api.enabled`` for
        # server mode or ``transports.esphome_api.devices`` for client
        # (dialer) mode. Constructed lazily in :meth:`start`.
        self._esphome_transport = None
        self._esphome_dialer = None

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
                f"{CANONICAL_PLUGIN_NAME} not ready: signaling site failed to bind "
                f"on :{self.cfg.webrtc_port} ({exc}). Control plane torn down "
                f"to avoid a half-up adapter (FR-005)."
            ) from exc

        # 3) Feature 017 — optional ESPHome native API transport. Two
        #    sub-modes (independent — both, either, or neither):
        #      a) server mode: AIVG listens on port 6053 (linux-voice-
        #         assistant-style satellites dial AIVG).
        #      b) client mode: AIVG dials out to configured ESPHome
        #         devices (the standard direction for real ESP32
        #         firmware that listens on 6053 and advertises mDNS).
        #    Both modes route through the same AgentPlatform via the
        #    shared ``Session`` class — Principle IV preserved.
        es_cfg = self.cfg.transports.esphome_api
        if es_cfg.enabled or es_cfg.devices:
            from pathlib import Path
            from .transports.esphome.auth import KeystoreResolver  # noqa: WPS433
            keystore = KeystoreResolver(Path(es_cfg.api_key_file).expanduser())

            if es_cfg.enabled:
                from .transports.esphome import EsphomeTransport  # noqa: WPS433
                self._esphome_transport = EsphomeTransport(
                    registry=self.registry,
                    platform=self.platform,
                    sink=self.sink,
                    host=es_cfg.host,
                    port=es_cfg.port,
                    api_key_resolver=keystore,
                    bootstrap_key=es_cfg.bootstrap_key,
                    ui_broadcast=self.management._broadcast,
                )
                await self._esphome_transport.start()

            if es_cfg.devices:
                # Feature 017 v1.1: client-mode uses
                # ``aioesphomeapi.APIClient`` via the library's
                # ``ReconnectLogic`` (handles noise + framing +
                # reconnect + version-skew). The original
                # hand-rolled :mod:`.dialer` had a subtle noise-
                # cipher-state drift bug against modern ESPHome
                # firmware (2026.5.0); switching to the upstream
                # library eliminates that whole class of issues.
                from .transports.esphome.api_client_dialer import (  # noqa: WPS433
                    EsphomeApiClientDialer,
                )
                self._esphome_dialer = EsphomeApiClientDialer(
                    registry=self.registry,
                    platform=self.platform,
                    sink=self.sink,
                    devices=es_cfg.devices,
                    ui_broadcast=self.management._broadcast,
                )
                await self._esphome_dialer.start()

    async def stop(self) -> None:  # pragma: no cover - needs aiohttp
        for runner in self._sites:
            await runner.cleanup()
        if self._esphome_transport is not None:
            await self._esphome_transport.stop()
            self._esphome_transport = None
        if self._esphome_dialer is not None:
            await self._esphome_dialer.stop()
            self._esphome_dialer = None
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

    class _SatellitePlatformAdapter(BasePlatformAdapter):
        def __init__(self, config) -> None:
            super().__init__(config, Platform.LOCAL)

            # Feature 015: the gateway-routing callback that used to be
            # injected into ``HermesV013Bridge(agent_runner=…)`` directly
            # is now plumbed through the AgentPlatform's ``startup``
            # ``gateway_config["agent_runner"]``. The Hermes plugin
            # (HermesAgentPlatform) reads it there and re-attaches it
            # onto its internal bridge. Adapter.py stays plugin-neutral:
            # it never names HermesV013Bridge.
            #
            # The runner's contract: ``async (text, ctx) -> str`` where
            # ``ctx`` carries ``session_id``/``device_id``. We keep the
            # SessionCtx-shaped argument because Hermes's
            # ``HermesV013Bridge.agent_turn`` calls runner with a
            # SessionCtx — plugin-internal detail.
            self._satellite_reply_futs: dict = {}

            async def _run_agent(text: str, ctx) -> str:
                fut: "asyncio.Future[str]" = asyncio.get_event_loop().create_future()
                self._satellite_reply_futs[ctx.session_id] = fut
                await self.handle_message(self._make_event(text, ctx))
                return await fut

            self._agent_runner = _run_agent
            # Load the active agent platform via the plugin registry
            # (constitution IV / FR-001). The adapter never names a
            # specific plugin class.
            from .platforms.base import PluginRegistry  # noqa: WPS433 - host-only path
            self._platform = PluginRegistry.load(self._impl_cfg_platform())
            self._impl = AivgSatelliteAdapter(platform=self._platform)

        def _impl_cfg_platform(self) -> str:
            """Resolve the adapter-config ``platform:`` key without
            forcing a full adapter construction. Loads the same
            ``~/.satellite/config.yaml`` block the inner
            :class:`AivgSatelliteAdapter` will read again — duplicated
            once here so we can pick the platform BEFORE handing it to
            the inner ctor."""
            from .config import load_adapter_config  # noqa: WPS433
            return load_adapter_config().platform

        def _make_event(self, text: str, ctx):
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
            # Feature 015: thread the gateway-routing agent_runner into
            # the platform via its ``startup`` gateway_config. The
            # Hermes plugin reads ``gateway_config["agent_runner"]`` and
            # attaches it onto its internal bridge; other plugins ignore
            # the key.
            await self._platform.startup(
                gateway_config={"agent_runner": self._agent_runner}
            )
            await self._impl.start()
            return True

        async def disconnect(self) -> None:
            await self._impl.stop()
            try:
                await self._platform.shutdown()
            except Exception:  # noqa: BLE001 - teardown must never raise
                pass

        async def get_chat_info(self, chat_id):
            # chat_id == VoiceSession.session_id; this is a 1:1 voice "dm".
            return {"chat_id": chat_id, "chat_type": "dm", "platform": CANONICAL_PLUGIN_NAME}

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
        name=CANONICAL_PLUGIN_NAME,
        label="Satellite WebRTC",
        adapter_factory=_SatellitePlatformAdapter,
        check_fn=_aiortc_available,
        source="plugin",
        plugin_name="aivg_core",
    )


# Back-compat alias (one-release window, per spec 019 R-3 / data-model § 3).
# External importers using ``from aivg_core.adapter import SatelliteWebRTCAdapter``
# keep working through one release. Slated for removal in the release after 019.
SatelliteWebRTCAdapter = AivgSatelliteAdapter


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
