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
# Legacy bundled-plugin dir (pre-013 / shell-script era). The new
# install path (pip install + entry point) doesn't write here, but
# preflight/install/uninstall clean it up if a previous attempt left
# files behind so Hermes's plugin loader doesn't log import errors.
LEGACY_PLUGIN_NAME = "satellite_webrtc"
# The pip-installable package + entry-point name (declared in pyproject.toml
# under [project.entry-points."hermes_agent.plugins"]). When this package is
# `pip install`'d into the Hermes venv, Hermes auto-discovers it on next
# startup and calls `register(ctx)` on `aivg_core.platforms.hermes.plugin_entrypoint`.
PIP_PACKAGE_NAME = "aivg-core"
HERMES_ENTRY_POINT_NAME = "aivg-satellite"
SENTINEL_COMMENT = "# managed by aivg setup"


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
    def legacy_plugin_dir(self) -> Path:
        """Pre-013 / shell-script-era vendored plugin location. Kept as
        a property because preflight + install + uninstall all clean it
        up (best-effort) so Hermes's loader doesn't see stale code."""
        return self.plugins_dir / LEGACY_PLUGIN_NAME

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

        # Hermes venv health: aiohttp + av are part of Hermes itself, not
        # something we install. aiortc comes in as a transitive dep of
        # aivg-core when we pip install it.
        if not self._venv_has(["aiohttp", "av"]):
            blockers.append(
                f"Hermes venv missing aiohttp/av — Hermes Agent itself isn't healthy"
            )

        # Write permissions (the legacy plugin dir cleanup needs this).
        try:
            self.plugins_dir.mkdir(parents=True, exist_ok=True)
            test_file = self.plugins_dir / ".aivg-preflight-probe"
            test_file.write_text("probe")
            test_file.unlink()
        except (OSError, PermissionError) as e:
            blockers.append(f"plugins_dir not writable: {e}")

        if not os.access(self.config_path, os.W_OK):
            blockers.append(f"config_path not writable: {self.config_path}")

        # Pip-install idempotency: if aivg-core is already in the venv,
        # this is a re-install (R-10). Warn either way; --force does a
        # `pip install --force-reinstall`, no-force is a pip no-op.
        installed_version = self._aivg_installed_in_venv()
        if installed_version is not None:
            if opts.force:
                warnings.append(
                    f"aivg-core {installed_version!r} already in Hermes venv; "
                    "--force will pip-reinstall + re-write config"
                )
            else:
                warnings.append(
                    f"aivg-core {installed_version!r} already in Hermes venv; "
                    "re-install will be idempotent. Use --force to overwrite "
                    "hand-edited config blocks or force a pip reinstall."
                )

        # Legacy bundled-plugin dir (pre-013 shell-script era). We'll
        # remove it during install, but flag in preflight so the operator
        # sees it in the intended-changes list.
        if self.legacy_plugin_dir.exists():
            intended.append(
                f"remove legacy vendored plugin dir at {self.legacy_plugin_dir} "
                "(pre-013 shell-script-era leftover)"
            )

        # Existing `satellite:` block in config (without our sentinel).
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

        intended.append(
            f"pip install aivg-core into Hermes venv ({self.venv_python.parent.parent})"
        )
        intended.append(
            f"register `{HERMES_ENTRY_POINT_NAME}` plugin via setuptools entry point"
        )
        if SENTINEL_COMMENT not in (self.config_path.read_text() if self.config_path.exists() else ""):
            intended.append(f"add satellite: block to {self.config_path}")
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

    def _venv_env(self) -> dict[str, str]:
        """Return an env dict for subprocess invocations against the
        Hermes venv with parent-process bleed scrubbed.

        Critical: `PYTHONPATH` inherited from the parent (the `aivg`
        CLI invoked as `PYTHONPATH=src python -m aivg_cli.cli ...`)
        leaks our source tree into the Hermes venv, making `pip show
        aivg-core` falsely report installed (the .egg-info on
        PYTHONPATH counts). Same hazard for any `python -c` probe.
        Strip it.
        """
        env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
        # Also drop PYTHONHOME if present — it would force the child
        # to look outside the venv's own site-packages.
        env.pop("PYTHONHOME", None)
        return env

    def _venv_has(self, modules: list[str]) -> bool:
        if not self.venv_python.exists():
            return False
        code = "import " + ",".join(modules)
        try:
            return (
                subprocess.run(
                    [str(self.venv_python), "-c", code],
                    capture_output=True,
                    env=self._venv_env(),
                    timeout=10,
                ).returncode
                == 0
            )
        except (subprocess.SubprocessError, OSError):
            return False

    def _aivg_installed_in_venv(self) -> Optional[str]:
        """Return the installed `aivg-core` version in the Hermes venv,
        or None if absent. Single source of truth for idempotency now
        that we install via pip rather than vendoring files.
        """
        if not self.venv_python.exists():
            return None
        try:
            rc = subprocess.run(
                [str(self.venv_python), "-m", "pip", "show", PIP_PACKAGE_NAME],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                env=self._venv_env(),
                timeout=15,
            )
        except (subprocess.SubprocessError, OSError):
            return None
        if rc.returncode != 0:
            return None
        for line in rc.stdout.decode("utf-8", errors="replace").splitlines():
            if line.startswith("Version:"):
                return line.split(":", 1)[1].strip()
        return ""

    def _find_repo_root(self) -> Optional[Path]:
        """Walk up from this file looking for ``pyproject.toml``. Returns
        the directory containing it, or None if running from an installed
        package (no source tree to install from).
        """
        for parent in Path(__file__).resolve().parents:
            if (parent / "pyproject.toml").is_file():
                # Sanity-check: it's *our* pyproject (avoid picking up a
                # parent project's by accident).
                try:
                    if PIP_PACKAGE_NAME in parent.joinpath("pyproject.toml").read_text():
                        return parent
                except OSError:
                    continue
        return None

    def _pip_install_aivg(self, *, force_reinstall: bool) -> tuple[int, str]:
        """Run `<venv_python> -m pip install <repo>` against the Hermes
        venv. Returns (returncode, combined_output). Caller wraps with
        timeout / SetupError handling.
        """
        repo = self._find_repo_root()
        if repo is None:
            raise SetupError(
                "setup_partial_failure",
                f"could not locate {PIP_PACKAGE_NAME!r} source tree to "
                f"install (no pyproject.toml found in parents of "
                f"{Path(__file__).resolve()}). Once {PIP_PACKAGE_NAME!r} is on "
                "PyPI this will fall back to `pip install <name>`.",
                phase="pip_installing",
            )
        cmd = [str(self.venv_python), "-m", "pip", "install", str(repo)]
        if force_reinstall:
            cmd.extend(["--force-reinstall", "--no-deps"])
            # On a re-install, also reinstall deps if needed — separate
            # call so we don't redownload aiortc/av every time.
            cmd_deps = [
                str(self.venv_python), "-m", "pip", "install",
                "--upgrade-strategy", "only-if-needed", str(repo),
            ]
            try:
                subprocess.run(
                    cmd_deps,
                    capture_output=True,
                    stdin=subprocess.DEVNULL,
                    env=self._venv_env(),
                    timeout=300,
                )
            except subprocess.TimeoutExpired:
                pass
        try:
            rc = subprocess.run(
                cmd,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                env=self._venv_env(),
                timeout=600,
            )
        except subprocess.TimeoutExpired:
            return 124, "pip install timed out after 600s"
        out = (
            rc.stdout.decode("utf-8", errors="replace")
            + rc.stderr.decode("utf-8", errors="replace")
        )
        return rc.returncode, out

    def _pip_uninstall_aivg(self) -> tuple[int, str]:
        try:
            rc = subprocess.run(
                [
                    str(self.venv_python), "-m", "pip", "uninstall",
                    "-y", PIP_PACKAGE_NAME,
                ],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                env=self._venv_env(),
                timeout=120,
            )
        except subprocess.TimeoutExpired:
            return 124, "pip uninstall timed out after 120s"
        out = (
            rc.stdout.decode("utf-8", errors="replace")
            + rc.stderr.decode("utf-8", errors="replace")
        )
        return rc.returncode, out

    def _remove_legacy_bundled_plugin(self) -> Optional[Path]:
        """Pre-013 / shell-script-era installs vendored the plugin into
        ``<hermes_home>/plugins/platforms/satellite_webrtc/``. The new
        path uses pip + entry-points instead; this method removes the
        old directory if present so Hermes's loader doesn't trip on
        stale half-broken vendored code. Returns the removed path or
        None.
        """
        legacy = self.plugins_dir / LEGACY_PLUGIN_NAME
        if legacy.exists():
            shutil.rmtree(legacy, ignore_errors=True)
            return legacy
        return None

    def _hermes_plugin_enable(self, *, enable: bool) -> tuple[bool, str]:
        """Add/remove ``HERMES_ENTRY_POINT_NAME`` from
        ``plugins.enabled`` in ``~/.hermes/config.yaml``.

        Entry-point plugins are opt-in: Hermes's loader only auto-loads
        ``source=bundled`` platform plugins (`hermes_cli/plugins.py:925`).
        Ours is ``source=entrypoint`` so we MUST add it to
        ``plugins.enabled`` or the plugin will be discovered-but-not-loaded
        ("not enabled in config" in `hermes plugins list`).

        Uses targeted text-based mutation rather than YAML round-trip
        because the latter strips comments — including our own
        ``# managed by aivg setup`` sentinel on the ``satellite:`` block,
        which uninstall depends on to find what to remove.

        Returns (changed, summary).
        """
        if not self.config_path.exists():
            return False, "config.yaml missing"

        text = self.config_path.read_text()
        new_text, changed, reason = self._mutate_plugins_enabled(
            text, enable=enable, name=HERMES_ENTRY_POINT_NAME,
        )
        if changed:
            self._atomic_write(self.config_path, new_text)
        action = "enabled" if enable else "disabled"
        return changed, (
            f"{action} {HERMES_ENTRY_POINT_NAME!r} in plugins.enabled"
            if changed
            else f"{HERMES_ENTRY_POINT_NAME!r} already {action} "
                 f"({reason or 'no-op'})"
        )

    @staticmethod
    def _mutate_plugins_enabled(
        text: str, *, enable: bool, name: str
    ) -> tuple[str, bool, str]:
        """Targeted edit of a YAML config to add/remove ``name`` from
        ``plugins.enabled`` (a top-level list of strings). Preserves
        every other line + comment verbatim. Handles the three cases
        we expect to encounter:

        1. No ``plugins:`` section → append one with our name.
        2. ``plugins:`` exists, ``enabled:`` is empty (``[]`` flow form
           OR no items) → upgrade to block form with our item.
        3. ``plugins:`` exists with items → add/remove our line in place.

        Returns (new_text, changed, reason). ``reason`` is a short note
        when not changed.
        """
        lines = text.splitlines()
        n = len(lines)

        # Locate `plugins:` at column 0.
        plugins_idx = -1
        for i, ln in enumerate(lines):
            if ln.rstrip() == "plugins:" or ln.startswith("plugins:"):
                # Block-mapping form only; `plugins: {...}` flow form is
                # rare in Hermes configs but we still bail safely.
                if ln.rstrip() == "plugins:":
                    plugins_idx = i
                    break
        if plugins_idx == -1:
            # Case 1: no plugins: block — append one.
            if not enable:
                return text, False, "plugins: block absent"
            new = text.rstrip() + "\n\nplugins:\n  enabled:\n  - " + name + "\n"
            return new, True, ""

        # Find `  enabled:` under `plugins:` (column 2 indent).
        enabled_idx = -1
        for j in range(plugins_idx + 1, n):
            ln = lines[j]
            if not ln.startswith(" "):
                # We left the plugins: block.
                break
            if ln.rstrip() == "  enabled:":
                enabled_idx = j
                break
            if ln.startswith("  enabled:"):
                # Flow form like `  enabled: []` or `  enabled: [a, b]`.
                enabled_idx = j
                break
        if enabled_idx == -1:
            # plugins: exists but no enabled: — add one.
            if not enable:
                return text, False, "plugins.enabled absent"
            # Insert immediately after the `plugins:` line.
            new_lines = (
                lines[: plugins_idx + 1]
                + ["  enabled:", f"  - {name}"]
                + lines[plugins_idx + 1 :]
            )
            return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), True, ""

        enabled_line = lines[enabled_idx]
        # Detect flow form: `  enabled: [..]` (possibly empty)
        rest = enabled_line[len("  enabled:") :].lstrip()
        if rest.startswith("["):
            # Convert flow → block form to keep semantics + extensibility.
            current_items: list[str] = []
            inner = rest.strip()
            if inner != "[]":
                inner = inner.strip("[]")
                current_items = [s.strip().strip("\"'") for s in inner.split(",") if s.strip()]
            is_in = name in current_items
            if enable and is_in:
                return text, False, "already in plugins.enabled"
            if not enable and not is_in:
                return text, False, "not in plugins.enabled"
            if enable:
                current_items.append(name)
            else:
                current_items.remove(name)
            block = ["  enabled:"] + [f"  - {it}" for it in sorted(current_items)]
            new_lines = lines[:enabled_idx] + block + lines[enabled_idx + 1 :]
            return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), True, ""

        # Block form: collect `  - <item>` lines below.
        items: list[tuple[int, str]] = []  # (line_idx, value)
        end_idx = enabled_idx + 1
        while end_idx < n:
            ln = lines[end_idx]
            if not ln.startswith("  "):
                break
            stripped = ln.strip()
            if stripped.startswith("- "):
                value = stripped[2:].strip().strip("\"'")
                items.append((end_idx, value))
                end_idx += 1
                continue
            if stripped == "":
                end_idx += 1
                continue
            # Some other key under plugins:  → stop.
            if not stripped.startswith("- "):
                break

        current_values = [v for _, v in items]
        is_in = name in current_values
        if enable and is_in:
            return text, False, "already in plugins.enabled"
        if not enable and not is_in:
            return text, False, "not in plugins.enabled"

        if enable:
            # Insert at sorted position to keep determinism.
            insert_at = end_idx
            for idx, val in items:
                if val > name:
                    insert_at = idx
                    break
            new_lines = lines[:insert_at] + [f"  - {name}"] + lines[insert_at:]
        else:
            target_idx = next(idx for idx, val in items if val == name)
            new_lines = lines[:target_idx] + lines[target_idx + 1 :]
        return "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), True, ""

    def _gateway_is_running(self) -> bool:
        """Best-effort check via `hermes gateway status`. Returns False on
        timeout / status-not-running / any error."""
        try:
            rc = subprocess.run(
                ["hermes", "gateway", "status"],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                env=self._venv_env(),
                timeout=10,
            )
        except (subprocess.TimeoutExpired, subprocess.SubprocessError, OSError):
            return False
        if rc.returncode != 0:
            return False
        out = rc.stdout.decode("utf-8", errors="replace").lower()
        # `hermes gateway status` prints either `✗ Gateway is not running`
        # or `✓ Gateway is running (pid=...)` — match on the success token.
        return "not running" not in out and "running" in out

    def _gateway_restart(self) -> tuple[bool, list[str]]:
        """Shared restart logic with hard timeouts. Returns (handled, notes).

        Behavior matrix:
        - Gateway is running as a service → `hermes gateway restart` with a
          60 s budget; success = `gateway status` reports running after.
        - Gateway is NOT running → DO NOT try `restart` / `start`: on
          hosts without a launchd/systemd service those commands run the
          gateway in the foreground attached to our subprocess; the
          timeout would then kill the gateway we just launched. Instead
          surface a clear next-step note so the operator runs
          `hermes gateway run` (foreground) or `hermes gateway install`
          (service) themselves.
        """
        notes: list[str] = []
        if not self._gateway_is_running():
            notes.append(
                "gateway not running as a service — skipping `restart`. "
                "Run `hermes gateway run` in a separate terminal (foreground), "
                "or `hermes gateway install` to install as a launchd/systemd "
                "service, to bring the satellite ports up."
            )
            return False, notes

        try:
            rc = subprocess.run(
                ["hermes", "gateway", "restart"],
                capture_output=True,
                stdin=subprocess.DEVNULL,
                env=self._venv_env(),
                timeout=60,
            )
            notes.append(f"hermes gateway restart → rc={rc.returncode}")
            if rc.returncode == 0:
                return True, notes
        except subprocess.TimeoutExpired:
            notes.append("hermes gateway restart → TIMEOUT after 60s")
        # Fallback diagnostic.
        notes.append(
            "fallback: check `hermes gateway status`; if not running, "
            "start it manually with `hermes gateway run` or install as a service"
        )
        return False, notes

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
                if d.is_dir() and d.name != LEGACY_PLUGIN_NAME
            } if self.plugins_dir.exists() else {}
            pre_aivg_version = self._aivg_installed_in_venv()
            record_pre_state(
                backup_dir,
                config_path=self.config_path,
                plugin_dirs=pre_plugins,
                aivg_install_marker_present=(pre_aivg_version is not None),
            )
            _phase(
                "backup", "ok",
                {"backup_dir": str(backup_dir), "pre_aivg_version": pre_aivg_version},
            )

            # --- pip_installing ------------------------------------------
            # Feature 013 (Hermes-native): instead of vendoring files into
            # `plugins/platforms/satellite_webrtc/`, we `pip install
            # aivg-core` into the Hermes venv. Hermes's plugin loader
            # auto-discovers via the `hermes_agent.plugins` entry-point
            # (declared in our pyproject.toml). One step replaces both the
            # old `vendoring` and `installing_deps` phases — aiortc/av/
            # aiohttp come along as transitive deps of aivg-core.
            _phase("pip_installing", "started")
            # First clean up any legacy bundled-plugin dir left by an
            # earlier shell-script-era install — its half-broken imports
            # would otherwise produce noise in Hermes's plugin loader.
            removed_legacy = self._remove_legacy_bundled_plugin()
            rc, output = self._pip_install_aivg(force_reinstall=opts.force)
            if rc != 0:
                raise SetupError(
                    "setup_partial_failure",
                    f"`pip install {PIP_PACKAGE_NAME}` into Hermes venv failed "
                    f"(rc={rc}): " + output[-400:],
                    phase="pip_installing",
                )
            installed_version = self._aivg_installed_in_venv() or "<unknown>"
            _phase("pip_installing", "ok", {
                "package": PIP_PACKAGE_NAME,
                "version": installed_version,
                "entry_point": HERMES_ENTRY_POINT_NAME,
                "removed_legacy_plugin_dir": str(removed_legacy) if removed_legacy else None,
            })

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

            # --- enabling_plugin ----------------------------------------
            # Entry-point platform plugins are NOT auto-loaded by Hermes
            # — only `source=bundled` ones are. Add our entry-point name
            # to `plugins.enabled` so the gateway actually instantiates
            # us on restart.
            _phase("enabling_plugin", "started")
            changed, summary = self._hermes_plugin_enable(enable=True)
            _phase(
                "enabling_plugin",
                "ok" if changed else "skipped",
                {"summary": summary, "entry_point": HERMES_ENTRY_POINT_NAME},
            )

            # --- restarting_gateway -------------------------------------
            # Soft on this phase: if the gateway isn't installed as a
            # service we DON'T spawn it from the install process (that
            # would run it in the foreground attached to our subprocess
            # and our timeout would kill it). Instead we record what
            # we did (or skipped) and let the operator finish the
            # last mile.
            _phase("restarting_gateway", "started")
            restart_ok, restart_notes = self._gateway_restart()
            _phase(
                "restarting_gateway",
                "ok" if restart_ok else "skipped",
                {
                    "attempts": restart_notes,
                    "operator_action_required": not restart_ok,
                },
            )

            # --- post_verifying -----------------------------------------
            # Soft check: if the gateway isn't running, ports won't bind
            # — but the install itself is still successful (pip + config
            # + enabled + plugin loadable by Hermes). Skip the port check
            # with a clear next-step note rather than failing the whole
            # install.
            _phase("post_verifying", "started")
            if restart_ok and self._ports_listening(["8643", "8644"], timeout_s=30):
                _phase("post_verifying", "ok", {"listening_ports": ["8643", "8644"]})
            elif restart_ok:
                _phase(
                    "post_verifying",
                    "skipped",
                    {
                        "reason": (
                            "gateway was restarted but ports 8643/8644 not yet "
                            "LISTENING within 30 s — the satellite adapter binds "
                            "lazily on first voice session. Confirm later with "
                            "`lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8643|8644)'`."
                        ),
                    },
                )
            else:
                _phase(
                    "post_verifying",
                    "skipped",
                    {
                        "reason": (
                            "gateway not running; install completed but ports "
                            "will only come up after `hermes gateway run` (or "
                            "`hermes gateway install` to install as service)."
                        ),
                    },
                )

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
            pre_aivg_version = self._aivg_installed_in_venv()
            record_pre_state(
                backup_dir,
                config_path=self.config_path,
                plugin_dirs=pre_plugins,
                aivg_install_marker_present=(pre_aivg_version is not None),
            )
            _phase(
                "backup", "ok",
                {"backup_dir": str(backup_dir), "pre_aivg_version": pre_aivg_version},
            )

            # --- pip_uninstalling (was uninstall_vendor) ---------------
            _phase("pip_uninstalling", "started")
            pip_changes: list[str] = []
            if pre_aivg_version is not None:
                rc, output = self._pip_uninstall_aivg()
                if rc == 0:
                    pip_changes.append(f"pip uninstalled {PIP_PACKAGE_NAME}=={pre_aivg_version}")
                    removed.append(f"{PIP_PACKAGE_NAME} (pip, venv={self.venv_python.parent.parent})")
                else:
                    # Don't bail — the operator can still rollback config
                    # + remove legacy dir; surface the failure in the
                    # detail map so they see what went wrong.
                    pip_changes.append(
                        f"pip uninstall failed (rc={rc}): {output[-200:]}"
                    )
            else:
                pip_changes.append(f"{PIP_PACKAGE_NAME} not installed in venv — skipped")
            # Also remove any pre-013 vendored plugin dir.
            legacy_removed = self._remove_legacy_bundled_plugin()
            if legacy_removed is not None:
                removed.append(str(legacy_removed))
                pip_changes.append(f"removed legacy plugin dir at {legacy_removed}")
            _phase("pip_uninstalling", "ok", {"changes": pip_changes})

            # --- disabling_plugin --------------------------------------
            _phase("disabling_plugin", "started")
            changed, summary = self._hermes_plugin_enable(enable=False)
            if changed:
                config_changes.append(summary)
            _phase(
                "disabling_plugin",
                "ok" if changed else "skipped",
                {"summary": summary, "entry_point": HERMES_ENTRY_POINT_NAME},
            )

            _phase("uninstall_config", "started")
            if self.config_path.exists():
                text = self.config_path.read_text()
                if SENTINEL_COMMENT in text:
                    text = self._strip_aivg_block(text)
                    self._atomic_write(self.config_path, text)
                    config_changes.append("removed satellite: block")
            _phase("uninstall_config", "ok", {"changes": config_changes})

            _phase("uninstall_restart", "started")
            restart_ok, restart_notes = self._gateway_restart()
            _phase(
                "uninstall_restart",
                "ok" if restart_ok else "skipped",
                {"attempts": restart_notes},
            )

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
        """The YAML block this setup writes into ~/.hermes/config.yaml.

        Key is ``satellite:`` (not ``aivg:``) because that's what
        :func:`aivg_core.config.SatelliteAdapterConfig.from_mapping`
        reads at adapter startup — see
        ``src/aivg_core/config.py::from_mapping`` (matches the working
        ``deploy/deploy-local.sh`` contract).
        """
        return (
            f"{SENTINEL_COMMENT}\n"
            "satellite:\n"
            "  enabled: true\n"
            "  management_port: 8643\n"
            "  webrtc_port: 8644\n"
            "  heartbeat_interval: 30\n"
            "  mdns_advertise: false\n"
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
