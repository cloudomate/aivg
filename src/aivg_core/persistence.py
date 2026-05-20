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


# =============================================================================
# Feature 013 — Install-backup folders + lock file (R-4, R-5)
# =============================================================================

DEFAULT_INSTALLS_DIR = Path("~/.aivg/installs").expanduser()
DEFAULT_SETUP_LOCK = Path("~/.aivg/setup.lock").expanduser()


def new_install_backup(platform: str, mode: str, *, root: Optional[Path] = None) -> Path:
    """Create a fresh timestamped backup folder for an install/uninstall/
    rollback run. Returns the folder path.

    Layout (data-model.md §3):
        ~/.aivg/installs/<platform>/<UTC-YYYYMMDDTHHMMSSZ>/
            manifest.json   (mode, started_at, opts)
    """
    if mode not in ("install", "uninstall", "rollback"):
        raise ValueError(f"unknown install-backup mode: {mode!r}")
    base = (root or DEFAULT_INSTALLS_DIR) / platform
    base.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    # If a folder with this exact UTC second already exists, append a
    # short suffix so we never overwrite.
    target = base / ts
    suffix = 0
    while target.exists():
        suffix += 1
        target = base / f"{ts}-{suffix}"
    target.mkdir()
    _atomic_write_json(
        target / "manifest.json",
        {
            "feature": "013-aivg-setup-cli",
            "mode": mode,
            "platform": platform,
            "started_at": time.time(),
            "finished_at": None,
            "result": None,
            "failure_phase": None,
        },
    )
    return target


def record_pre_state(
    backup_dir: Path,
    *,
    config_path: Optional[Path] = None,
    plugin_dirs: Optional[dict[str, str]] = None,
    aivg_install_marker_present: bool = False,
) -> None:
    """Capture the pre-mutation host state into the backup folder."""
    import hashlib

    config_sha = None
    if config_path is not None and config_path.exists():
        config_sha = hashlib.sha256(config_path.read_bytes()).hexdigest()
        # Copy the config file verbatim so the operator has a true-source
        # for rollback (not just a hash).
        shutil.copy2(config_path, backup_dir / "config.yaml.before")
    payload = {
        "config_file": str(config_path) if config_path else None,
        "config_sha256": config_sha,
        "plugin_dirs": dict(plugin_dirs or {}),
        "aivg_install_marker_present": aivg_install_marker_present,
    }
    _atomic_write_json(backup_dir / "pre_state.json", payload)


def append_phase(backup_dir: Path, phase) -> None:  # phase: SetupPhase
    """Append one SetupPhase JSON line to ``phases.ndjson``."""
    rec = {
        "name": phase.name,
        "status": phase.status,
        "detail": phase.detail,
        "at": time.time(),
    }
    with (backup_dir / "phases.ndjson").open("a") as fh:
        fh.write(json.dumps(rec, separators=(",", ":")) + "\n")


def finalize_backup(
    backup_dir: Path,
    *,
    result: str,
    failure_phase: Optional[str] = None,
    failure_reason: Optional[str] = None,
) -> None:
    """Update manifest.json with terminal state; write
    failure_reason.txt if the run failed."""
    manifest_path = backup_dir / "manifest.json"
    try:
        m = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        m = {}
    m["finished_at"] = time.time()
    m["result"] = result
    m["failure_phase"] = failure_phase
    _atomic_write_json(manifest_path, m)
    if failure_reason:
        (backup_dir / "failure_reason.txt").write_text(failure_reason + "\n")


def _atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True))
    os.replace(tmp, path)


# --- Lock file (R-4) ---------------------------------------------------------


class SetupLockHeld(RuntimeError):
    """Raised when another `aivg setup` invocation already holds the
    process-mutex on this host.

    Carries the prior invocation's metadata for diagnostics. The CLI
    maps this to error.code = setup_lock_held.
    """

    def __init__(self, lock_path: Path, running_meta: dict) -> None:
        super().__init__(
            f"another `aivg setup` is running (pid={running_meta.get('pid')}, "
            f"started_at={running_meta.get('started_at')}); lock at {lock_path}"
        )
        self.lock_path = lock_path
        self.meta = running_meta


class _SetupLock:
    """Context manager wrapping `fcntl.flock(LOCK_EX | LOCK_NB)` on the
    AIVG setup lock file. Single-host scope; multi-host is out of scope
    per the spec."""

    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self._fh = None

    def __enter__(self):
        import fcntl

        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        # Open for read+write+create (don't truncate yet — we want to
        # preserve any prior content so we can surface it on contention).
        self._fh = open(self.lock_path, "a+")
        self._fh.seek(0)
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Someone else holds the flock. Read whatever they wrote so
            # we can identify them in the error.
            prior = {}
            try:
                self._fh.seek(0)
                prior = json.loads(self._fh.read() or "{}")
            except (OSError, ValueError):
                pass
            self._fh.close()
            self._fh = None
            raise SetupLockHeld(self.lock_path, prior) from None
        # Acquired. Rewrite our identity so a future contender knows who
        # we are.
        try:
            import sys as _sys
            self._fh.seek(0)
            self._fh.truncate()
            json.dump(
                {
                    "pid": os.getpid(),
                    "argv": list(_sys.argv),
                    "started_at": time.time(),
                    "host": os.uname().nodename if hasattr(os, "uname") else "",
                },
                self._fh,
            )
            self._fh.flush()
        except OSError:
            pass
        return self

    def __exit__(self, *exc):
        import fcntl

        if self._fh is None:
            return
        try:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
        finally:
            self._fh.close()
            self._fh = None


def acquire_setup_lock(*, lock_path: Optional[Path] = None) -> _SetupLock:
    """Acquire the AIVG-setup mutex for the duration of an install/
    uninstall/rollback. Use as a context manager."""
    return _SetupLock(lock_path or DEFAULT_SETUP_LOCK)
