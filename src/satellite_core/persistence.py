"""Atomic JSON persistence of the adopted-device registry (R-5).

Writes ``~/.satellite/state.json`` via ``tmp + os.replace`` so a partial
write cannot corrupt the file. Pending devices are **not** persisted —
they're transient by design (R-7); the device's next register repopulates
them. Constitution v2.0.0: this file lives under ``~/.satellite/``, NOT
``~/.hermes/``, because the satellite core is no longer Hermes-tied.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import time
from pathlib import Path
from typing import Any, Optional

from .models import (
    AdoptionState,
    ClientStatus,
    ConnectedClient,
    OtaState,
    RegistrySnapshot,
    SatelliteConfig,
)

DEFAULT_STATE_PATH = Path("~/.satellite/state.json").expanduser()
SCHEMA_VERSION = 1

_LOCK = asyncio.Lock()


def _client_to_dict(c: ConnectedClient) -> dict[str, Any]:
    d = dataclasses.asdict(c)
    # Enums round-trip as their string value.
    d["status"] = c.status.value
    d["adoption_state"] = c.adoption_state.value
    d["ota_state"] = c.ota_state.value
    return d


def _client_from_dict(d: dict[str, Any]) -> ConnectedClient:
    cfg_d = d.get("config") or {}
    cfg = SatelliteConfig(
        **{k: v for k, v in cfg_d.items() if k in SatelliteConfig.__dataclass_fields__}
    )
    return ConnectedClient(
        device_id=d["device_id"],
        device_type=d["device_type"],
        firmware_version=d.get("firmware_version", ""),
        ip_address=d.get("ip_address", ""),
        status=ClientStatus(d.get("status", ClientStatus.OFFLINE.value)),
        last_seen=d.get("last_seen", time.time()),
        active_session_id=d.get("active_session_id"),
        config=cfg,
        last_error=d.get("last_error"),
        name=d.get("name"),
        adoption_state=AdoptionState(d.get("adoption_state", AdoptionState.ADOPTED.value)),
        config_version=d.get("config_version", 0),
        config_updated_at=d.get("config_updated_at", time.time()),
        ota_state=OtaState(d.get("ota_state", OtaState.IDLE.value)),
        ota_version=d.get("ota_version"),
        ota_job_id=d.get("ota_job_id"),
    )


def write_snapshot(
    clients: list[ConnectedClient],
    *,
    device_limit: int,
    path: Optional[Path] = None,
) -> Path:
    """Atomic write. Synchronous (no event loop required). Returns the
    path that was written."""
    target = path or DEFAULT_STATE_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    snapshot = RegistrySnapshot(
        schema_version=SCHEMA_VERSION,
        saved_at=time.time(),
        clients=[_client_to_dict(c) for c in clients],
        device_limit=device_limit,
    )
    payload = json.dumps(dataclasses.asdict(snapshot), indent=2, sort_keys=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(payload)
    os.replace(tmp, target)  # atomic on POSIX & Win
    return target


def load_snapshot(path: Optional[Path] = None) -> list[ConnectedClient]:
    """Read the snapshot back into ``ConnectedClient`` instances.

    Missing file or unknown schema_version → empty list (R-5 safe-start).
    """
    target = path or DEFAULT_STATE_PATH
    if not target.exists():
        return []
    try:
        raw = json.loads(target.read_text())
    except (OSError, json.JSONDecodeError):
        return []
    if raw.get("schema_version") != SCHEMA_VERSION:
        return []
    out: list[ConnectedClient] = []
    for d in raw.get("clients", []):
        try:
            out.append(_client_from_dict(d))
        except (KeyError, ValueError):
            # Skip malformed rows; never fail the whole load.
            continue
    return out
