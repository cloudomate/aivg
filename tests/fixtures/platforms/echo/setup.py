"""Fake ``echo`` :class:`SetupCapability` (feature 013 T034 early-land).

In-memory SetupCapability used by the install/uninstall/lifecycle
integration tests so they don't mutate the real Hermes install on the
host. "Installs" by writing files into a tmp dir; "uninstalls" by
removing them. No subprocess, no real config writes.

Exposes ``SETUP`` at module load so ``PluginRegistry.load_setup_capability("echo")``
finds it. The test fixture stitches it into ``aivg_core.platforms.echo``
via ``sys.modules`` (mirroring tests/integration/test_agent_platform_seam.py).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from aivg_core.platforms.base import (
    DetectResult,
    InstallResult,
    PreflightReport,
    RollbackResult,
    SetupOptions,
    SetupPhase,
    UninstallResult,
)


class _EchoState:
    """Per-instance config: the fake host's directories live here so
    each test gets its own isolated FS without monkey-patching globals.
    Plain class (not a dataclass) so dynamic module loading in the test
    fixture doesn't trip the dataclass-decorator's sys.modules lookup."""

    __slots__ = ("host_root", "plugins_dir", "config_path")

    def __init__(self, host_root: Path) -> None:
        self.host_root = host_root
        self.plugins_dir = host_root / "plugins"
        self.config_path = host_root / "config.yaml"


class EchoSetupCapability:
    """The minimum-viable :class:`SetupCapability` for testing.

    Behavior: detect always reports installed (the host_root is the
    "platform" — if the test creates it, the platform is "installed");
    install writes ``plugins/satellite_webrtc/.aivg-install-marker.json``
    + an `aivg:` config block; uninstall removes both.
    """

    name = "echo"
    label = "Echo Test Platform"

    def __init__(self, host_root: Optional[Path] = None) -> None:
        # The test passes a tmp host_root via env var ECHO_HOST_ROOT.
        if host_root is None:
            env = os.environ.get("ECHO_HOST_ROOT")
            host_root = Path(env) if env else Path("/tmp/aivg-echo-test")
        self._st = _EchoState(host_root=host_root)
        # Idempotency: track whether we've installed (by marker presence).

    def detect(self) -> DetectResult:
        is_inst = self._st.host_root.exists()
        return DetectResult(
            is_installed=is_inst,
            paths={
                "host_root": str(self._st.host_root),
                "plugins_dir": str(self._st.plugins_dir),
                "config": str(self._st.config_path),
            },
            version="echo-0.1.0",
            reasons=["host_root exists"] if is_inst else ["host_root absent"],
        )

    def preflight(self, opts: SetupOptions) -> PreflightReport:
        plugin_target = self._st.plugins_dir / "satellite_webrtc"
        marker = plugin_target / ".aivg-install-marker.json"
        intended: list[str] = []
        warnings: list[str] = []
        blockers: list[str] = []

        if not self._st.host_root.exists():
            blockers.append(f"host_root {self._st.host_root} does not exist")

        if marker.exists() and not opts.force:
            warnings.append(
                "AIVG install marker already present — re-vendor will be idempotent"
            )

        intended.append(f"vendor plugin to {plugin_target}")
        intended.append(f"add aivg: block to {self._st.config_path}")

        return PreflightReport(
            ok=not blockers,
            intended_changes=intended,
            blockers=blockers,
            warnings=warnings,
        )

    def install(self, opts: SetupOptions) -> InstallResult:
        from aivg_core.persistence import (
            append_phase,
            finalize_backup,
            new_install_backup,
            record_pre_state,
        )

        phases: list[SetupPhase] = []
        backup_dir = new_install_backup("echo", "install")

        def _phase(name: str, status: str, detail: Optional[dict] = None) -> None:
            p = SetupPhase(name=name, status=status, detail=detail)
            phases.append(p)
            append_phase(backup_dir, p)

        _phase("backup", "started")
        # Record pre-state.
        pre_plugin_dirs = {
            d.name: "<sha-unused-in-fixture>"
            for d in self._st.plugins_dir.glob("*")
            if d.is_dir()
        } if self._st.plugins_dir.exists() else {}
        record_pre_state(
            backup_dir,
            config_path=self._st.config_path if self._st.config_path.exists() else None,
            plugin_dirs=pre_plugin_dirs,
        )
        _phase("backup", "ok", {"backup_dir": str(backup_dir)})

        # Vendor.
        _phase("vendoring", "started")
        plugin_target = self._st.plugins_dir / "satellite_webrtc"
        plugin_target.mkdir(parents=True, exist_ok=True)
        (plugin_target / "plugin.yaml").write_text("name: satellite-webrtc\nlabel: Echo Satellite\n")
        # Marker (R-10).
        import json, time
        (plugin_target / ".aivg-install-marker.json").write_text(json.dumps({
            "feature": "013-aivg-setup-cli",
            "installed_at": time.time(),
            "installed_by_aivg_version": "test",
            "backup_dir": str(backup_dir),
            "platform": "echo",
        }))
        _phase("vendoring", "ok", {"target": str(plugin_target)})

        # Config block.
        _phase("config_writing", "started")
        existing = self._st.config_path.read_text() if self._st.config_path.exists() else ""
        if "# managed by aivg setup" not in existing:
            existing += "\n# managed by aivg setup\naivg:\n  enabled: true\n"
            self._st.config_path.write_text(existing)
            _phase("config_writing", "ok", {"added_block": True})
        else:
            _phase("config_writing", "skipped", {"reason": "block already present"})

        # No real deps / restart in the fixture.
        _phase("installing_deps", "skipped", {"reason": "fixture has no deps"})
        _phase("restarting_gateway", "skipped", {"reason": "fixture has no gateway"})
        _phase("post_verifying", "ok", {"reason": "fixture is always healthy"})
        _phase("done", "ok")

        finalize_backup(backup_dir, result="ok")
        return InstallResult(
            ok=True,
            phases=phases,
            backup_dir=backup_dir,
            rollback_command=f"aivg setup --restore-backup {backup_dir}",
        )

    def uninstall(self, opts: SetupOptions) -> UninstallResult:
        from aivg_core.persistence import (
            append_phase,
            finalize_backup,
            new_install_backup,
            record_pre_state,
        )

        phases: list[SetupPhase] = []
        removed: list[str] = []
        config_changes: list[str] = []
        backup_dir = new_install_backup("echo", "uninstall")

        def _phase(name: str, status: str, detail: Optional[dict] = None) -> None:
            p = SetupPhase(name=name, status=status, detail=detail)
            phases.append(p)
            append_phase(backup_dir, p)

        _phase("backup", "started")
        record_pre_state(
            backup_dir,
            config_path=self._st.config_path if self._st.config_path.exists() else None,
        )
        _phase("backup", "ok", {"backup_dir": str(backup_dir)})

        # Remove vendored plugin.
        _phase("uninstall_vendor", "started")
        plugin_target = self._st.plugins_dir / "satellite_webrtc"
        if plugin_target.exists():
            shutil.rmtree(plugin_target)
            removed.append(str(plugin_target))
        _phase("uninstall_vendor", "ok", {"removed": removed})

        # Remove config block.
        _phase("uninstall_config", "started")
        if self._st.config_path.exists():
            text = self._st.config_path.read_text()
            # Strip the sentinel-marked block (single line + the aivg: ... block).
            new = []
            skip = False
            for line in text.splitlines():
                if line.strip().startswith("# managed by aivg setup"):
                    skip = True
                    continue
                if skip:
                    if line.startswith("aivg:") or line.startswith("  "):
                        continue
                    skip = False
                new.append(line)
            self._st.config_path.write_text("\n".join(new))
            config_changes.append("removed aivg: block")
        _phase("uninstall_config", "ok", {"changes": config_changes})

        _phase("uninstall_restart", "skipped", {"reason": "fixture has no gateway"})
        _phase("post_verifying", "ok", {"reason": "fixture is always healthy"})
        _phase("done", "ok")

        finalize_backup(backup_dir, result="ok")
        return UninstallResult(
            ok=True,
            phases=phases,
            removed=removed,
            config_changes=config_changes,
        )

    def rollback(self, opts: SetupOptions, *, backup_dir: Path) -> RollbackResult:
        import json
        from aivg_core.persistence import (
            new_install_backup,
            record_pre_state,
            finalize_backup,
        )

        new_backup = new_install_backup("echo", "rollback")
        record_pre_state(
            new_backup,
            config_path=self._st.config_path if self._st.config_path.exists() else None,
        )
        restored: list[str] = []

        # Restore config from backup.
        cfg_before = backup_dir / "config.yaml.before"
        if cfg_before.exists():
            self._st.config_path.write_text(cfg_before.read_text())
            restored.append(str(self._st.config_path))

        # Remove any plugin dirs that were not in the backup's pre_state.
        try:
            pre = json.loads((backup_dir / "pre_state.json").read_text())
        except (OSError, ValueError):
            pre = {}
        known_plugins = set(pre.get("plugin_dirs", {}).keys())
        if self._st.plugins_dir.exists():
            for entry in self._st.plugins_dir.iterdir():
                if entry.is_dir() and entry.name not in known_plugins:
                    shutil.rmtree(entry)
                    restored.append(f"removed: {entry}")

        finalize_backup(new_backup, result="ok")
        return RollbackResult(ok=True, restored_files=restored, new_backup_dir=new_backup)


SETUP = EchoSetupCapability()
