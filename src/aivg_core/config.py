"""Loads the ``satellite:`` block from the EXISTING Hermes config file.

Constitution Principle IV: no new config or secret store. Secrets continue to
live in ``~/.hermes/.env`` (read by Hermes itself, not re-parsed here).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

DEFAULT_CONFIG_PATH = Path(os.path.expanduser("~/.hermes/config.yaml"))


# =============================================================================
# Feature 017 — additive transports config block.
# =============================================================================
#
# The existing single voice-plane WebRTC server (port 8644) is the v1.0.0
# transport. Feature 017 adds the ESPHome native API transport as an
# additive, opt-in sibling — its block defaults to ``enabled: false`` so
# pre-017 deployments don't open a new port without the operator's consent
# (FR-003). Disabled-by-default also keeps the contract-version envelope
# emitting ``transports: ["webrtc"]`` only, until the operator opts in.


@dataclass
class EsphomeTransportConfig:
    """ESPHome native API transport (feature 017).

    Two operating modes (can run simultaneously):

    - **Server mode** (``enabled: true``, ``host``/``port`` define the
      listener): AIVG listens on ``port`` for inbound connections.
      Works for OHF-Voice's `linux-voice-assistant` and any other
      ESPHome-API client that dials AIVG.

    - **Client mode** (``devices: [...]``): AIVG dials out to each
      configured device. Required for real ESPHome firmware devices
      (the device IS the API server; AIVG is the client). Each entry
      is ``{host, port, device_id, api_key}``.
    """
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 6053
    api_key_file: str = "~/.aivg/devices/keys.json"
    # Optional bootstrap key for server mode: when non-empty, lets an
    # unregistered device complete one Connect+Auth so the operator
    # can adopt it via ``aivg device adopt``. Empty / None means only
    # pre-registered devices may connect.
    bootstrap_key: Optional[str] = None
    # Client-mode device list. Each entry: {host: str, port: int (default 6053),
    # device_id: str, api_key: str}. Empty list means client mode disabled.
    devices: list[dict] = field(default_factory=list)


@dataclass
class GrpcTransportConfig:
    """gRPC satellite transport (feature 021).

    Off by default (like the esphome block) so pre-021 deployments don't
    open a new port without the operator's consent. When ``enabled``, the
    gateway hosts ``aivg.satellite.v1.Audio`` (Phase 1 audio plane) on
    ``host:port``.

    - ``tls``: ``"insecure"`` (trusted-LAN default) or ``"mtls"`` (fleet;
      reuses the device keystore at ``api_key_file``). Never silently
      downgrades from a required-auth posture.
    - ``downstream_codec``: ``"pcm"`` (safe Phase-1 default) or ``"opus"``.
    """
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 8645
    tls: str = "insecure"           # "insecure" | "mtls"
    downstream_codec: str = "pcm"   # "pcm" | "opus"
    api_key_file: str = "~/.aivg/devices/keys.json"
    # Feature 021 / US2 — also host the management/control plane over gRPC
    # (the `aivg.satellite.v1.Management` service), so a native satellite can
    # do its whole lifecycle without the `/satellite/ws` WebSocket. Off by
    # default; the WebSocket stays up regardless (browsers/legacy natives
    # keep using it — coexistence).
    management_over_grpc: bool = False


@dataclass
class TransportsConfig:
    """Top-level transports block. Additive in v1.1.0; absent in
    pre-017 configs (default-constructed)."""
    esphome_api: EsphomeTransportConfig = field(default_factory=EsphomeTransportConfig)
    # Feature 021 — additive gRPC transport sibling. Default-constructed
    # means "gRPC transport disabled"; pre-021 configs parse fine.
    grpc: GrpcTransportConfig = field(default_factory=GrpcTransportConfig)


@dataclass
class SatelliteAdapterConfig:
    enabled: bool = False
    management_port: int = 8643
    webrtc_port: int = 8644
    heartbeat_interval: int = 30
    mdns_advertise: bool = True
    default_config: dict[str, Any] = field(default_factory=dict)
    # Feature 011 (US2 onboarding) ----------------------------------------
    # auto_adopt_on_register=True keeps pre-v011 behavior: a device that
    # POSTs /satellite/register lands directly in the adopted registry.
    # Set to False to require an explicit POST /satellite/{id}/adopt step
    # before a registered device joins the fleet (constitution v2.0.0
    # adoption-gated flow used by the Improv-over-BLE onboard path).
    auto_adopt_on_register: bool = True
    # Maximum number of adopted devices the gateway will accept; the
    # /adopt endpoint refuses with 409 device_limit_reached past this. The
    # pending list is unrestricted (R-12).
    device_limit: int = 10
    # Feature 011 T011 (closes Phase 2 partial) ---------------------------
    # Which agent-platform plugin to load via
    # ``aivg_core.platforms.base.PluginRegistry``. Defaults to "hermes"
    # (the v1 canonical plugin); set to "openclaw" (stub) or a future
    # plugin name to switch.
    platform: str = "hermes"
    # Feature 017 — additive transports block. Default-constructed
    # means "ESPHome transport disabled"; pre-017 configs parse fine.
    transports: TransportsConfig = field(default_factory=TransportsConfig)
    # Strip markdown + emoji/smileys from agent replies before TTS so
    # Piper/Coqui don't literally pronounce `**bold**` or emit 0-frame
    # audio for emoji. On by default; set to false to keep raw text (the
    # pre-this-flag behaviour, useful for debugging the LLM output stream).
    # Env-var `AIVG_DISABLE_TTS_TEXT_FILTER=1` is a per-host override.
    tts_text_filter: bool = True

    @staticmethod
    def from_mapping(data: dict[str, Any] | None) -> "SatelliteAdapterConfig":
        block = (data or {}).get("satellite", {}) or {}
        # Feature 011 T011: top-level `platform:` key wins over a key
        # nested inside `satellite:` — the platform selection is a
        # whole-system decision, not a satellite-block detail.
        platform = (data or {}).get("platform") or block.get("platform", "hermes")
        # Feature 017: parse the optional transports block (additive).
        transports_block = (block.get("transports") or {})
        esphome_block = (transports_block.get("esphome_api") or {})
        grpc_block = (transports_block.get("grpc") or {})
        transports = TransportsConfig(
            esphome_api=EsphomeTransportConfig(
                enabled=bool(esphome_block.get("enabled", False)),
                host=str(esphome_block.get("host", "0.0.0.0")),
                port=int(esphome_block.get("port", 6053)),
                api_key_file=str(esphome_block.get(
                    "api_key_file", "~/.aivg/devices/keys.json"
                )),
                bootstrap_key=esphome_block.get("bootstrap_key") or None,
                devices=list(esphome_block.get("devices") or []),
            ),
            grpc=GrpcTransportConfig(
                enabled=bool(grpc_block.get("enabled", False)),
                host=str(grpc_block.get("host", "0.0.0.0")),
                port=int(grpc_block.get("port", 8645)),
                tls=str(grpc_block.get("tls", "insecure")),
                downstream_codec=str(grpc_block.get("downstream_codec", "pcm")),
                api_key_file=str(grpc_block.get(
                    "api_key_file", "~/.aivg/devices/keys.json"
                )),
                management_over_grpc=bool(grpc_block.get("management_over_grpc", False)),
            ),
        )
        cfg = SatelliteAdapterConfig(
            enabled=bool(block.get("enabled", False)),
            management_port=int(block.get("management_port", 8643)),
            webrtc_port=int(block.get("webrtc_port", 8644)),
            heartbeat_interval=int(block.get("heartbeat_interval", 30)),
            mdns_advertise=bool(block.get("mdns_advertise", True)),
            default_config=dict(block.get("default_config", {})),
            auto_adopt_on_register=bool(block.get("auto_adopt_on_register", True)),
            device_limit=int(block.get("device_limit", 10)),
            platform=str(platform),
            transports=transports,
            tts_text_filter=bool(block.get("tts_text_filter", True)),
        )
        cfg.validate()
        return cfg

    def load_platform(self):  # noqa: ANN201 - structural; returns AgentPlatform
        """Resolve and return the configured AgentPlatform plugin.

        Imports lazily to avoid forcing the plugin discovery at config-
        parse time. Feature 011 T011 closure.
        """
        from .platforms.base import PluginRegistry  # noqa: WPS433

        return PluginRegistry.load(self.platform)

    def validate(self) -> None:
        if self.management_port == self.webrtc_port:
            raise ValueError("management_port and webrtc_port must differ")
        for name in ("management_port", "webrtc_port"):
            port = getattr(self, name)
            if not (1 <= port <= 65535):
                raise ValueError(f"{name} out of range: {port}")
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")
        # Feature 021 — the gRPC audio port must not collide with the
        # management or WebRTC sites and must validate its enums.
        g = self.transports.grpc
        if g.enabled:
            if not (1 <= g.port <= 65535):
                raise ValueError(f"transports.grpc.port out of range: {g.port}")
            if g.port in (self.management_port, self.webrtc_port):
                raise ValueError(
                    "transports.grpc.port must differ from management_port "
                    "and webrtc_port"
                )
            if g.tls not in ("insecure", "mtls"):
                raise ValueError(f"transports.grpc.tls must be insecure|mtls: {g.tls}")
            if g.downstream_codec not in ("pcm", "opus"):
                raise ValueError(
                    f"transports.grpc.downstream_codec must be pcm|opus: "
                    f"{g.downstream_codec}"
                )


def _parse_yaml(text: str) -> dict[str, Any]:
    """Use PyYAML if present (Hermes ships it); else a tiny safe fallback that
    handles the shallow ``satellite:`` block shape used by this adapter."""
    try:  # pragma: no cover - exercised when PyYAML is installed
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _mini_yaml(text)


def _mini_yaml(text: str) -> dict[str, Any]:
    """Minimal nested mapping parser (2-space indent, scalars only).

    Sufficient for the documented ``satellite:`` block; not a general parser.
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        key, _, val = line.strip().partition(":")
        key = key.strip()
        val = val.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if val == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _coerce(val)
    return root


def _coerce(val: str) -> Any:
    low = val.lower()
    if low in ("true", "false"):
        return low == "true"
    if val.lstrip("-").isdigit():
        return int(val)
    return val.strip('"').strip("'")


def load_adapter_config(path: Path | None = None) -> SatelliteAdapterConfig:
    p = path or DEFAULT_CONFIG_PATH
    if not p.exists():
        return SatelliteAdapterConfig()
    return SatelliteAdapterConfig.from_mapping(_parse_yaml(p.read_text()))
