"""Loads the ``satellite:`` block from the EXISTING Hermes config file.

Constitution Principle IV: no new config or secret store. Secrets continue to
live in ``~/.hermes/.env`` (read by Hermes itself, not re-parsed here).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(os.path.expanduser("~/.hermes/config.yaml"))


@dataclass
class SatelliteAdapterConfig:
    enabled: bool = False
    management_port: int = 8643
    webrtc_port: int = 8644
    heartbeat_interval: int = 30
    mdns_advertise: bool = True
    default_config: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def from_mapping(data: dict[str, Any] | None) -> "SatelliteAdapterConfig":
        block = (data or {}).get("satellite", {}) or {}
        cfg = SatelliteAdapterConfig(
            enabled=bool(block.get("enabled", False)),
            management_port=int(block.get("management_port", 8643)),
            webrtc_port=int(block.get("webrtc_port", 8644)),
            heartbeat_interval=int(block.get("heartbeat_interval", 30)),
            mdns_advertise=bool(block.get("mdns_advertise", True)),
            default_config=dict(block.get("default_config", {})),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.management_port == self.webrtc_port:
            raise ValueError("management_port and webrtc_port must differ")
        for name in ("management_port", "webrtc_port"):
            port = getattr(self, name)
            if not (1 <= port <= 65535):
                raise ValueError(f"{name} out of range: {port}")
        if self.heartbeat_interval <= 0:
            raise ValueError("heartbeat_interval must be positive")


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
