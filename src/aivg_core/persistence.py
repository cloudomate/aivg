"""Atomic JSON persistence of the adopted-device registry.

Writes ``~/.aivg/state.json`` via ``tmp + os.replace`` so a partial
write cannot corrupt the file. Pending devices are **not** persisted —
they're transient by design; the device's next register repopulates
them. The data directory lives under ``~/.aivg/`` (renamed from
``~/.satellite/`` in feature 012); a one-shot
:func:`migrate_legacy_data_dir` runs on first start to atomically move
any pre-AIVG content to the new location.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import shutil
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

DEFAULT_STATE_PATH = Path("~/.aivg/state.json").expanduser()
LEGACY_STATE_PATH = Path("~/.satellite/state.json").expanduser()
DEFAULT_FIRMWARE_DIR = Path("~/.aivg/firmware").expanduser()
LEGACY_FIRMWARE_DIR = Path("~/.satellite/firmware").expanduser()
SCHEMA_VERSION = 1

_LOCK = asyncio.Lock()
_MIGRATION_DONE = False  # process-level sentinel (T009)


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


# --- Legacy data-dir migration (feature 012 T008/T009, R-3) -----------------


def migrate_legacy_data_dir(
    *,
    src: Optional[Path] = None,
    dst: Optional[Path] = None,
    legacy_firmware: Optional[Path] = None,
    new_firmware: Optional[Path] = None,
    force: bool = False,
) -> bool:
    """One-shot migration ``~/.satellite/`` → ``~/.aivg/`` on first
    AIVG start (feature 012).

    Behavior:

    * If ``dst/state.json`` exists and is at least as new as
      ``src/state.json`` (or ``src/state.json`` does not exist), no-op.
    * Otherwise, load ``src/state.json``, write to ``dst/state.json``
      via the existing atomic ``tmp + os.replace`` helper, then rename
      the legacy file to ``src/state.json.pre-aivg-rebrand.bak`` — never
      delete it, so the operator has a rollback rope (SC-005).
    * The ``firmware/`` subtree is migrated with the same atomic-rename
      pattern: copy each per-device-type ``manifest.json``, then leave
      a ``.pre-aivg-rebrand.bak`` next to each source.
    * Idempotent: a process-level sentinel prevents the function from
      doing work twice in the same process. Pass ``force=True`` to
      bypass the sentinel (used in tests).

    Returns ``True`` when a migration actually happened, ``False`` when
    it was a no-op.
    """
    global _MIGRATION_DONE
    if _MIGRATION_DONE and not force:
        return False

    src_state = (src or LEGACY_STATE_PATH)
    dst_state = (dst or DEFAULT_STATE_PATH)
    legacy_fw = (legacy_firmware or LEGACY_FIRMWARE_DIR)
    new_fw = (new_firmware or DEFAULT_FIRMWARE_DIR)

    did_something = False

    # 1. state.json — atomic copy then ".bak" the legacy.
    if src_state.exists():
        should_migrate = True
        if dst_state.exists():
            try:
                if dst_state.stat().st_mtime >= src_state.stat().st_mtime:
                    should_migrate = False
            except OSError:
                pass  # if stat fails, err on the side of migrating
        if should_migrate:
            try:
                payload = src_state.read_text()
                dst_state.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst_state.with_suffix(dst_state.suffix + ".tmp")
                tmp.write_text(payload)
                os.replace(tmp, dst_state)
                bak = src_state.with_suffix(src_state.suffix + ".pre-aivg-rebrand.bak")
                os.replace(src_state, bak)
                did_something = True
            except OSError:
                # Migration is best-effort; a failure must not block startup.
                pass

    # 2. firmware/<device_type>/manifest.json — same pattern, per file.
    if legacy_fw.exists() and legacy_fw.is_dir():
        for manifest in legacy_fw.rglob("manifest.json"):
            rel = manifest.relative_to(legacy_fw)
            target = new_fw / rel
            if target.exists():
                try:
                    if target.stat().st_mtime >= manifest.stat().st_mtime:
                        continue
                except OSError:
                    pass
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_suffix(target.suffix + ".tmp")
                tmp.write_text(manifest.read_text())
                os.replace(tmp, target)
                bak = manifest.with_suffix(manifest.suffix + ".pre-aivg-rebrand.bak")
                os.replace(manifest, bak)
                did_something = True
            except OSError:
                pass

    _MIGRATION_DONE = True
    return did_something


def reset_migration_sentinel_for_tests() -> None:
    """Test helper: clears the process-level migration sentinel so a
    second call to :func:`migrate_legacy_data_dir` actually runs.

    Not part of the public API.
    """
    global _MIGRATION_DONE
    _MIGRATION_DONE = False
