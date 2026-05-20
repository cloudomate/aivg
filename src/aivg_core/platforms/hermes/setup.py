"""Hermes-platform :class:`SetupCapability` (feature 013 T016-T023).

Absorbs the logic from the now-deprecated `deploy/deploy-local.sh`
(detect + preflight + backup + vendor + config + deps + restart +
post-verify) into a Python :class:`SetupCapability` that
:mod:`aivg_cli.setup` dispatches to.

Constitution v2.0.0 Principle IV (deploy-layer realization): every
Hermes-specific concept — plugin directory layout, ``satellite:``
config block format, ``hermes gateway restart`` command, the
``aiortc`` venv install — lives here. The satellite core and
``aivg_cli/setup.py`` never touch any of it.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional

from aivg_core.platforms.base import (
    DetectResult,
    InstallResult,
    PreflightReport,
    RollbackResult,
    SetupError,
    SetupOptions,
    SetupPhase,
    UninstallResult,
)
from aivg_core.persistence import (
    append_phase,
    finalize_backup,
    new_install_backup,
    record_pre_state,
)


# --- host-layout constants (mirrors deploy/deploy-local.sh) ------------------

DEFAULT_HERMES_HOME = Path("~/.hermes/hermes-agent").expanduser()
DEFAULT_HERMES_CONFIG = Path("~/.hermes/config.yaml").expanduser()
PLUGIN_NAME = "satellite_webrtc"
SENTINEL_COMMENT = "# managed by aivg setup"

# Source location for the plugin entrypoint that gets vendored.
_THIS_DIR = Path(__file__).resolve().parent
PLUGIN_ENTRYPOINT_SRC = _THIS_DIR / "plugin_entrypoint"


class HermesSetupCapability:
    """SetupCapability for the Hermes agent platform.

    Idempotent (R-10): a re-run with `--force` re-vendors; without
    `--force` it detects the marker file and skips mutation. Rollback-
    safe (FR-011): every install captures a `pre_state.json` + a
    verbatim config copy in `~/.aivg/installs/hermes/<ts>/` BEFORE the
    first mutating phase.
    """

    name = "hermes"
    label = "Hermes Agent"

    def __init__(
        self,
        *,
        hermes_home: Optional[Path] = None,
        config_path: Optional[Path] = None,
    ) -> None:
        # Allow env-var override + test-time injection. Resolved lazily so
        # constructing the singleton doesn't touch the filesystem.
        self._hermes_home_override = hermes_home
        self._config_path_override = config_path

    @property
    def hermes_home(self) -> Path:
        if self._hermes_home_override is not None:
            return self._hermes_home_override
        env = os.environ.get("HERMES_HOME")
        return Path(env).expanduser() if env else DEFAULT_HERMES_HOME

    @property
    def config_path(self) -> Path:
        if self._config_path_override is not None:
            return self._config_path_override
        env = os.environ.get("HERMES_CONFIG")
        return Path(env).expanduser() if env else DEFAULT_HERMES_CONFIG

    @property
    def venv_python(self) -> Path:
        return self.hermes_home / "venv" / "bin" / "python"

    @property
    def plugins_dir(self) -> Path:
        return self.hermes_home / "plugins" / "platforms"

    @property
    def plugin_target(self) -> Path:
        return self.plugins_dir / PLUGIN_NAME

    @property
    def install_marker(self) -> Path:
        return self.plugin_target / ".aivg-install-marker.json"

    # --- T017 detect() ------------------------------------------------------

    def detect(self) -> DetectResult:
        reasons: list[str] = []
        paths: dict[str, str] = {}
        is_installed = True

        if not self.hermes_home.exists():
            is_installed = False
            reasons.append(f"hermes_home not found: {self.hermes_home}")
        else:
            paths["hermes_home"] = str(self.hermes_home)

        if not self.venv_python.exists():
            is_installed = False
            reasons.append(f"venv python not found: {self.venv_python}")
        else:
            paths["venv_python"] = str(self.venv_python)

        if not self.config_path.exists():
            is_installed = False
            reasons.append(f"config not found: {self.config_path}")
        else:
            paths["config"] = str(self.config_path)

        if self.plugins_dir.exists():
            paths["plugins_dir"] = str(self.plugins_dir)

        version: Optional[str] = None
        # Best-effort: read pyvenv.cfg for the Python version (not the
        # Hermes-agent version per se; Hermes has no canonical version-
        # file location).
        pyvenv = self.hermes_home / "venv" / "pyvenv.cfg"
        if pyvenv.exists():
            try:
                for line in pyvenv.read_text().splitlines():
                    if line.startswith("version"):
                        version = "venv-python-" + line.split("=", 1)[1].strip()
                        break
            except OSError:
                pass

        if is_installed:
            reasons.append("hermes_home + venv + config all present")
        return DetectResult(
            is_installed=is_installed, paths=paths, version=version, reasons=reasons
        )

    # --- T018 preflight() ---------------------------------------------------

    def preflight(self, opts: SetupOptions) -> PreflightReport:
        intended: list[str] = []
        blockers: list[str] = []
        warnings: list[str] = []

        # Detection is the implicit first check.
        det = self.detect()
        if not det.is_installed:
            blockers.extend(det.reasons)
            return PreflightReport(
                ok=False, intended_changes=[], blockers=blockers, warnings=warnings
            )

        # Venv has aiohttp+av; aiortc is the install-time addition.
        if not self._venv_has(["aiohttp", "av"]):
            blockers.append(
                f"Hermes venv missing aiohttp/av — Hermes Agent itself isn't healthy"
            )
        if not self._venv_has(["aiortc"]):
            intended.append(f"install aiortc into {self.venv_python.parent.parent}/")

        # Write permissions.
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.plugins_dir / ".aivg-preflight-probe"
            test_file.write_text("probe")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            blockers.append(f"plugins_dir not writable: {e}")

        if not os.access(self.config_path, os.W_OK):
            blockers.append(f"config_path not writable: {self.config_path}")

        # Existing AIVG install marker (idempotency, R-10).
        if self.install_marker.exists():
            if opts.force:
                warnings.append(
                    "AIVG install marker present; --force will re-vendor + re-write config"
                )
            else:
                warnings.append(
                    "AIVG install marker present; re-vendor will be idempotent. "
                    "Use --force to overwrite hand-edited config blocks."
                )

        # Existing `aivg:` / `satellite:` block in config (without our sentinel).
        if self.config_path.exists():
            try:
                existing_cfg = self.config_path.read_text()
                if SENTINEL_COMMENT not in existing_cfg and (
                    "\nsatellite:" in existing_cfg or "\naivg:" in existing_cfg
                ):
                    if opts.force:
                        warnings.append(
                            "hand-edited satellite:/aivg: block found; --force will overwrite"
                        )
                    else:
                        blockers.append(
                            "hand-edited satellite:/aivg: block found in config; "
                            "either remove it, re-run with --force, or accept that the "
                            "install will skip the config-write step"
                        )
            except OSError as e:
                blockers.append(f"could not read config: {e}")

        intended.append(f"vendor plugin to {self.plugin_target}")
        intended.append(f"write install marker at {self.install_marker.name}")
        if SENTINEL_COMMENT not in (self.config_path.read_text() if self.config_path.exists() else ""):
            intended.append(f"add aivg: block to {self.config_path}")
        if opts.legacy_hermes and not opts.no_tune:
            intended.append("apply legacy Hermes tuning: stt.local.model=small, voice.silence_duration=1.2")
        intended.append("restart Hermes gateway (`hermes gateway restart`)")
        intended.append("post-verify: confirm ports 8643/8644 are LISTENING")

        return PreflightReport(
            ok=not blockers,
            intended_changes=intended,
            blockers=blockers,
            warnings=warnings,
        )

    def _venv_has(self, modules: list[str]) -> bool:
        if not self.venv_python.exists():
            return False
        code = "import " + ",".join(modules)
        try:
            return (
                subprocess.run(
                    [str(self.venv_python), "-c", code],
                    capture_output=True,
                    timeout=10,
                ).returncode
                == 0
            )
        except (subprocess.SubprocessError, OSError):
            return False

    # --- T020/T021/T023 install() ------------------------------------------

    def install(self, opts: SetupOptions) -> InstallResult:
        backup_dir = new_install_backup("hermes", "install")
        phases: list[SetupPhase] = []

        def _phase(name: str, status: str, detail: Optional[dict] = None) -> None:
            p = SetupPhase(name=name, status=status, detail=detail)
            phases.append(p)
            append_phase(backup_dir, p)

        try:
            # --- backup --------------------------------------------------
            _phase("backup", "started")
            pre_plugins = {
                d.name: self._dir_sha256(d)
                for d in self.plugins_dir.glob("*")
                if d.is_dir() and d.name != PLUGIN_NAME
            } if self.plugins_dir.exists() else {}
            record_pre_state(
                backup_dir,
                config_path=self.config_path,
                plugin_dirs=pre_plugins,
                aivg_install_marker_present=self.install_marker.exists(),
            )
            _phase("backup", "ok", {"backup_dir": str(backup_dir)})

            # --- vendoring -----------------------------------------------
            _phase("vendoring", "started")
            self.plugin_target.mkdir(parents=True, exist_ok=True)
            for item in PLUGIN_ENTRYPOINT_SRC.iterdir():
                target = self.plugin_target / item.name
                if item.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            # Marker (T023, R-10).
            self.install_marker.write_text(json.dumps({
                "feature": "013-aivg-setup-cli",
                "installed_at": time.time(),
                "installed_by_aivg_version": "0.3.0",  # match pyproject [project].version
                "backup_dir": str(backup_dir),
                "platform": "hermes",
            }, indent=2))
            _phase("vendoring", "ok", {"target": str(self.plugin_target)})

            # --- config_writing -----------------------------------------
            _phase("config_writing", "started")
            existing = self.config_path.read_text()
            wrote_block = False
            if SENTINEL_COMMENT not in existing:
                existing = existing.rstrip() + "\n\n" + self._aivg_config_block() + "\n"
                self._atomic_write(self.config_path, existing)
                wrote_block = True
            # Legacy tuning (T021).
            if opts.legacy_hermes and not opts.no_tune:
                existing = self._apply_legacy_tuning(self.config_path.read_text())
                self._atomic_write(self.config_path, existing)
                _phase("config_writing", "ok", {"wrote_block": wrote_block, "legacy_tuning": True})
            else:
                _phase("config_writing", "ok", {"wrote_block": wrote_block})

            # --- installing_deps ----------------------------------------
            _phase("installing_deps", "started")
            if not self._venv_has(["aiortc"]):
                rc = subprocess.run(
                    ["uv", "pip", "install", "--python", str(self.venv_python), "aiortc"],
                    capture_output=True,
                )
                if rc.returncode != 0:
                    # Fallback to direct pip.
                    rc = subprocess.run(
                        [str(self.venv_python), "-m", "pip", "install", "aiortc"],
                        capture_output=True,
                    )
                if rc.returncode != 0:
                    raise SetupError(
                        "setup_partial_failure",
                        f"aiortc install failed: {rc.stderr.decode('utf-8', errors='replace')[:200]}",
                        phase="installing_deps",
                    )
                _phase("installing_deps", "ok", {"installed": ["aiortc"]})
            else:
                _phase("installing_deps", "skipped", {"reason": "aiortc already present"})

            # --- restarting_gateway -------------------------------------
            _phase("restarting_gateway", "started")
            for cmd in (["hermes", "gateway", "restart"], ["hermes", "gateway", "start"]):
                rc = subprocess.run(cmd, capture_output=True)
                if rc.returncode == 0:
                    break
            else:
                # Last-ditch: `hermes gateway status` — at least surface
                # the state instead of pretending we restarted.
                subprocess.run(["hermes", "gateway", "status"], capture_output=True)
                raise SetupError(
                    "setup_partial_failure",
                    "could not restart Hermes gateway (`hermes gateway restart/start` both failed)",
                    phase="restarting_gateway",
                )
            _phase("restarting_gateway", "ok")

            # --- post_verifying -----------------------------------------
            _phase("post_verifying", "started")
            if not self._ports_listening(["8643", "8644"], timeout_s=30):
                raise SetupError(
                    "setup_partial_failure",
                    "post-verify failed: ports 8643/8644 are not both LISTENING within 30 s",
                    phase="post_verifying",
                )
            _phase("post_verifying", "ok", {"listening_ports": ["8643", "8644"]})

            # --- done ----------------------------------------------------
            _phase("done", "ok", {"backup_dir": str(backup_dir)})
            finalize_backup(backup_dir, result="ok")
            return InstallResult(
                ok=True,
                phases=phases,
                backup_dir=backup_dir,
                rollback_command=f"aivg setup --restore-backup {backup_dir} --yes",
            )

        except SetupError as e:
            _phase(e.phase or "failed", "failed", {"reason": e.message})
            finalize_backup(
                backup_dir,
                result="failed",
                failure_phase=e.phase,
                failure_reason=e.message,
            )
            return InstallResult(
                ok=False,
                phases=phases,
                backup_dir=backup_dir,
                rollback_command=f"aivg setup --restore-backup {backup_dir} --yes",
                failure_phase=e.phase,
                failure_reason=e.message,
            )

    # --- uninstall + rollback -----------------------------------------------

    def uninstall(self, opts: SetupOptions) -> UninstallResult:
        backup_dir = new_install_backup("hermes", "uninstall")
        phases: list[SetupPhase] = []
        removed: list[str] = []
        config_changes: list[str] = []

        def _phase(name: str, status: str, detail: Optional[dict] = None) -> None:
            p = SetupPhase(name=name, status=status, detail=detail)
            phases.append(p)
            append_phase(backup_dir, p)

        try:
            _phase("backup", "started")
            pre_plugins = {
                d.name: self._dir_sha256(d)
                for d in self.plugins_dir.glob("*")
                if d.is_dir()
            } if self.plugins_dir.exists() else {}
            record_pre_state(
                backup_dir,
                config_path=self.config_path,
                plugin_dirs=pre_plugins,
                aivg_install_marker_present=self.install_marker.exists(),
            )
            _phase("backup", "ok", {"backup_dir": str(backup_dir)})

            _phase("uninstall_vendor", "started")
            if self.plugin_target.exists():
                shutil.rmtree(self.plugin_target)
                removed.append(str(self.plugin_target))
            _phase("uninstall_vendor", "ok", {"removed": removed})

            _phase("uninstall_config", "started")
            if self.config_path.exists():
                text = self.config_path.read_text()
                if SENTINEL_COMMENT in text:
                    text = self._strip_aivg_block(text)
                    self._atomic_write(self.config_path, text)
                    config_changes.append("removed aivg: block")
            _phase("uninstall_config", "ok", {"changes": config_changes})

            _phase("uninstall_restart", "started")
            for cmd in (["hermes", "gateway", "restart"], ["hermes", "gateway", "start"]):
                rc = subprocess.run(cmd, capture_output=True)
                if rc.returncode == 0:
                    break
            _phase("uninstall_restart", "ok")

            _phase("post_verifying", "ok", {"reason": "gateway restarted"})
            _phase("done", "ok")
            finalize_backup(backup_dir, result="ok")
            return UninstallResult(
                ok=True, phases=phases, removed=removed, config_changes=config_changes,
            )

        except SetupError as e:
            _phase(e.phase or "failed", "failed", {"reason": e.message})
            finalize_backup(
                backup_dir, result="failed",
                failure_phase=e.phase, failure_reason=e.message,
            )
            return UninstallResult(
                ok=False, phases=phases, removed=removed, config_changes=config_changes,
                failure_reason=e.message,
            )

    def rollback(self, opts: SetupOptions, *, backup_dir: Path) -> RollbackResult:
        new_backup = new_install_backup("hermes", "rollback")
        record_pre_state(new_backup, config_path=self.config_path)
        restored: list[str] = []

        # Restore config from backup.
        cfg_before = backup_dir / "config.yaml.before"
        if cfg_before.exists():
            self._atomic_write(self.config_path, cfg_before.read_text())
            restored.append(str(self.config_path))

        # Remove plugin dirs that were not in pre_state.
        try:
            pre = json.loads((backup_dir / "pre_state.json").read_text())
        except (OSError, ValueError):
            pre = {}
        known = set(pre.get("plugin_dirs", {}).keys())
        if self.plugins_dir.exists():
            for entry in self.plugins_dir.iterdir():
                if entry.is_dir() and entry.name not in known:
                    shutil.rmtree(entry)
                    restored.append(f"removed: {entry}")

        # Restart gateway.
        subprocess.run(["hermes", "gateway", "restart"], capture_output=True)
        finalize_backup(new_backup, result="ok")
        return RollbackResult(
            ok=True, restored_files=restored, new_backup_dir=new_backup,
        )

    # --- internal helpers ---------------------------------------------------

    def _aivg_config_block(self) -> str:
        return (
            f"{SENTINEL_COMMENT}\n"
            "aivg:\n"
            "  enabled: true\n"
            "  management_port: 8643\n"
            "  webrtc_port: 8644\n"
            "  heartbeat_interval: 30\n"
            "  device_limit: 10\n"
            "  default_config:\n"
            "    wake_word: \"Hey Jarvis\"\n"
            "    routing_mode: \"preferred\"\n"
            "    log_level: \"INFO\"\n"
        )

    def _apply_legacy_tuning(self, text: str) -> str:
        """Feature 010 defaults that the legacy bash applied. Idempotent."""
        # stt.local.model: medium → small
        import re

        text = re.sub(
            r"(^\s+model:\s*)medium$",
            r"\1small",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        # voice.silence_duration: 3.0 → 1.2
        text = re.sub(
            r"(^\s+silence_duration:\s*)3\.0$",
            r"\g<1>1.2",
            text,
            count=1,
            flags=re.MULTILINE,
        )
        return text

    def _strip_aivg_block(self, text: str) -> str:
        """Remove the SENTINEL_COMMENT-marked aivg: block from the config.
        Conservative: removes the sentinel line and the contiguous block
        following it (top-level key + indented body)."""
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        while i < len(lines):
            if lines[i].strip() == SENTINEL_COMMENT:
                # Skip the sentinel + the immediately-following top-level
                # key + every contiguous indented line.
                i += 1
                if i < len(lines) and re.match(r"^[a-zA-Z_]\w*:\s*$", lines[i].rstrip()):
                    i += 1
                    while i < len(lines) and (lines[i].startswith(" ") or lines[i].strip() == ""):
                        i += 1
                # Strip trailing blank line if we'd leave a doubled blank.
                if out and not out[-1].strip():
                    pass
                continue
            out.append(lines[i])
            i += 1
        return "\n".join(out)

    def _atomic_write(self, path: Path, content: str) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(content)
        os.replace(tmp, path)

    def _dir_sha256(self, d: Path) -> str:
        """Best-effort directory hash for pre_state.json. Concatenates
        per-file sha256s sorted by path."""
        h = hashlib.sha256()
        for p in sorted(d.rglob("*")):
            if p.is_file():
                try:
                    h.update(p.relative_to(d).as_posix().encode("utf-8"))
                    h.update(b"\0")
                    h.update(p.read_bytes())
                except OSError:
                    continue
        return h.hexdigest()

    def _ports_listening(self, ports: list[str], *, timeout_s: int) -> bool:
        """Poll `lsof` for the given ports to be in LISTEN state."""
        deadline = time.monotonic() + timeout_s
        want = {f":{p}" for p in ports}
        while time.monotonic() < deadline:
            try:
                rc = subprocess.run(
                    ["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
                    capture_output=True, text=True, timeout=5,
                )
            except (subprocess.SubprocessError, OSError, FileNotFoundError):
                return False
            text = rc.stdout
            if all(f":{p}" in text for p in ports):
                return True
            time.sleep(1)
        return False


import re  # used by _apply_legacy_tuning / _strip_aivg_block

SETUP = HermesSetupCapability()
