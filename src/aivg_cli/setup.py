"""``aivg setup`` / ``aivg deploy`` — platform-agnostic install CLI.

Constitution v2.0.0/v2.0.1 Principle IV at the deploy layer. This
module is the operator entry-point; it dispatches to per-platform
:class:`aivg_core.platforms.base.SetupCapability` plugins for every
host-mutating step. It MUST NOT import any concrete platform plugin —
all access goes through ``PluginRegistry.load_setup_capability``.

See:
  * ``specs/013-aivg-setup-cli/contracts/setup-cli-contract.md``
  * ``specs/013-aivg-setup-cli/contracts/platform-setup.md``
  * ``specs/013-aivg-setup-cli/research.md`` (R-1 through R-12)
"""

from __future__ import annotations

import importlib
import os
import sys
from dataclasses import asdict
from typing import Optional

import typer

from aivg_core.platforms.base import (
    DetectResult,
    InstallResult,
    PreflightReport,
    SetupCapability,
    SetupError,
    SetupOptions,
    SetupPhase,
    UninstallResult,
)
from aivg_core.persistence import (
    SetupLockHeld,
    acquire_setup_lock,
)

from .exit_codes import (
    BAD_INPUT,
    OK,
    SETUP_PARTIAL_FAILURE,
    map_error_to_exit_code,
)
from .output import emit_error, emit_ndjson, emit_ok, set_context, context

# Shipped plugins to probe when --platform is not specified.
# Alphabetical (R-2).
SHIPPED_PLUGINS: tuple[str, ...] = ("hermes", "openclaw")


setup_app = typer.Typer(no_args_is_help=False, invoke_without_command=True)


@setup_app.callback(invoke_without_command=True)
def setup_command(
    ctx: typer.Context,
    platform: Optional[str] = typer.Option(
        None, "--platform",
        help="Force a specific plugin (e.g. `hermes`, `openclaw`).",
    ),
    preflight: bool = typer.Option(
        False, "--preflight",
        help="Read-only: list intended changes and exit; no mutation.",
    ),
    uninstall: bool = typer.Option(
        False, "--uninstall",
        help="Remove an existing AIVG install (inverse of default install).",
    ),
    restore_backup: Optional[str] = typer.Option(
        None, "--restore-backup",
        help="Restore the host from a backup folder under ~/.aivg/installs/.../",
    ),
    parity_check: bool = typer.Option(
        False, "--parity-check",
        help="Compare a Hermes-spoken phrase against operator input.",
    ),
    yes: bool = typer.Option(
        False, "--yes", "-y",
        help="Skip the destructive-action confirmation prompt.",
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Re-run install over an existing AIVG marker; overwrite "
        "hand-edited config blocks.",
    ),
    legacy_hermes: bool = typer.Option(
        False, "--legacy-hermes",
        help="Apply Hermes-specific legacy tuning (feature 010 defaults). "
        "Set automatically when invoked via the deprecated `deploy/*.sh` "
        "wrappers.",
    ),
    no_tune: bool = typer.Option(
        False, "--no-tune",
        help="Inverse of --legacy-hermes: explicitly skip the Hermes "
        "tuning step.",
    ),
    phrase: Optional[str] = typer.Option(
        None, "--phrase",
        help="Required when --parity-check.",
    ),
) -> None:
    """`aivg setup` — install AIVG into the active agent platform.

    Modes (mutually exclusive): default install · `--preflight` ·
    `--uninstall` · `--restore-backup PATH` · `--parity-check`.

    Under `--json --yes` for any mutating mode, the CLI proceeds
    without prompting. Under `--json` without `--yes`, mutating modes
    refuse with `error.code = bad_input` (FR-019 safety net).
    """
    # Mode is mutually exclusive (R-1).
    mode_flags = sum(int(b) for b in (preflight, uninstall, parity_check, bool(restore_backup)))
    if mode_flags > 1:
        emit_error(
            "bad_input",
            "modes are mutually exclusive: pick one of --preflight, "
            "--uninstall, --restore-backup, --parity-check",
        )
        raise typer.Exit(BAD_INPUT)

    if parity_check and not phrase:
        emit_error("bad_input", "--parity-check requires --phrase")
        raise typer.Exit(BAD_INPUT)

    if legacy_hermes and no_tune:
        emit_error("bad_input", "--legacy-hermes and --no-tune are mutually exclusive")
        raise typer.Exit(BAD_INPUT)

    # Build the SetupOptions handed to every plugin call.
    opts = SetupOptions(
        yes=yes,
        force=force,
        legacy_hermes=legacy_hermes,
        no_tune=no_tune,
        json_mode=context().json_mode,
    )

    # FR-019 safety net (T010): refuse host-mutating modes under `--json`
    # without `--yes` BEFORE platform detection. The gate is independent
    # of host state — the agent must ask the operator first, regardless
    # of which platform is (or isn't) installed.
    mutating = uninstall or bool(restore_backup) or not (preflight or parity_check)
    if mutating and opts.json_mode and not opts.yes:
        emit_error(
            "bad_input",
            "refusing host-mutating action under --json without --yes; "
            "have the user confirm in chat, then re-run with --yes",
        )
        raise typer.Exit(BAD_INPUT)

    # --restore-backup is the only mode that doesn't need platform
    # detection (the backup folder name carries the platform).
    if restore_backup:
        raise typer.Exit(_run_restore(restore_backup, opts))

    # Platform detection / dispatch.
    try:
        cap = _resolve_platform(platform)
    except SetupError as e:
        emit_error(e.code, e.message)
        raise typer.Exit(map_error_to_exit_code(e.code))

    if preflight:
        raise typer.Exit(_run_preflight(cap, opts))
    if uninstall:
        raise typer.Exit(_run_uninstall(cap, opts))
    if parity_check:
        raise typer.Exit(_run_parity_check(cap, opts, phrase or ""))

    # Default mode = install.
    raise typer.Exit(_run_install(cap, opts))


# --- platform detection / dispatch (R-2, T008) -------------------------------


def _resolve_platform(explicit: Optional[str]) -> SetupCapability:
    """Return the SetupCapability to dispatch to.

    R-2 precedence: explicit `--platform <name>` wins; else probe every
    shipped plugin's `detect()` in alphabetical order; multi-detect →
    `multiple_platforms_detected`; zero-detect → `no_platform_detected`.

    NEVER imports a concrete plugin directly — only through
    `aivg_core.platforms.base.PluginRegistry`.
    """
    from aivg_core.platforms.base import PluginRegistry

    if explicit is not None:
        # Explicit: only that plugin; surface a specific error if it's
        # not installed.
        try:
            cap = PluginRegistry.load_setup_capability(explicit)
        except RuntimeError as e:
            msg = str(e)
            if "setup_not_supported_for_platform" in msg:
                raise SetupError("setup_not_supported_for_platform", msg) from None
            raise SetupError("no_platform_detected", msg) from None
        # Probe to make sure it's actually installed.
        det = cap.detect()
        if not det.is_installed:
            raise SetupError(
                "no_platform_detected",
                f"--platform {explicit!r} but `{cap.label}` is not installed "
                f"on this host: " + "; ".join(det.reasons or ["no install found"]),
            )
        return cap

    # Probe every shipped plugin's detect() in alphabetical order.
    found: list[tuple[str, SetupCapability]] = []
    for name in sorted(SHIPPED_PLUGINS):
        try:
            cap = PluginRegistry.load_setup_capability(name)
        except RuntimeError:
            # Plugin without SETUP capability is fine; skip silently.
            continue
        det = cap.detect()
        if det.is_installed:
            found.append((name, cap))

    if not found:
        raise SetupError(
            "no_platform_detected",
            "no supported agent platform detected on this host. "
            "Looked for: " + ", ".join(sorted(SHIPPED_PLUGINS)) + ". "
            "Pass --platform <name> explicitly if your install is at "
            "a non-default location.",
        )
    if len(found) > 1:
        names = ", ".join(n for n, _ in found)
        raise SetupError(
            "multiple_platforms_detected",
            f"multiple agent platforms installed: {names}. "
            "Pass --platform <name> to pick one.",
        )
    return found[0][1]


# --- phase emitter (R-6, T009) ----------------------------------------------


def _emit_phase_started(phase_name: str, detail: Optional[dict] = None) -> None:
    _emit_phase(SetupPhase(name=phase_name, status="started", detail=detail))


def _emit_phase_ok(phase_name: str, detail: Optional[dict] = None) -> None:
    _emit_phase(SetupPhase(name=phase_name, status="ok", detail=detail))


def _emit_phase_skipped(phase_name: str, reason: str) -> None:
    _emit_phase(SetupPhase(name=phase_name, status="skipped", detail={"reason": reason}))


def _emit_phase_failed(phase_name: str, detail: Optional[dict] = None) -> None:
    _emit_phase(SetupPhase(name=phase_name, status="failed", detail=detail))


def _emit_phase(phase: SetupPhase) -> None:
    """One NDJSON envelope per phase event under --json; human-friendly
    one-liner under interactive mode."""
    if context().json_mode:
        emit_ndjson({
            "phase": phase.name,
            "status": phase.status,
            "detail": phase.detail,
        })
        return
    # Interactive mode: print a compact one-liner. Keep this lightweight;
    # the rich progress UI is a polish item.
    bullet = {"started": "·", "ok": "✓", "skipped": "○", "failed": "✗"}.get(phase.status, "·")
    line = f"  {bullet} {phase.name}"
    if phase.status == "failed":
        sys.stderr.write(line + "\n")
    else:
        print(line)


# --- destructive-confirm gate (T010) ----------------------------------------


def _confirm_or_bail(opts: SetupOptions, *, summary: str) -> bool:
    """Reuse the destructive-confirm pattern from feature 011:

    * `opts.yes=True` → pass through.
    * `opts.json_mode=True` without `opts.yes` → refuse with
      `error.code=bad_input` (the agent must ask the user first).
    * Interactive: prompt with the preflight summary; non-`yes` cancels.
    """
    if opts.yes:
        _emit_phase_skipped("confirming", "--yes passed")
        return True
    if opts.json_mode:
        emit_error(
            "bad_input",
            "refusing host-mutating action under --json without --yes; "
            "have the user confirm in chat, then re-run with --yes",
        )
        return False
    # Interactive prompt.
    _emit_phase_started("confirming")
    print()
    print(summary)
    print()
    sys.stderr.write("Type 'yes' to proceed (anything else cancels): ")
    sys.stderr.flush()
    ans = sys.stdin.readline().strip().lower()
    if ans in ("y", "yes"):
        _emit_phase_ok("confirming")
        return True
    _emit_phase_failed("confirming", {"reason": "operator cancelled"})
    sys.stderr.write("Cancelled. Host is unchanged.\n")
    return False


# --- subcommand bodies (T011 lock wiring + dispatch) ------------------------


def _run_preflight(cap: SetupCapability, opts: SetupOptions) -> int:
    """Preflight is the one mode that doesn't need the lock — it's
    read-only by contract (SC-002)."""
    _emit_phase_started("detecting")
    det = cap.detect()
    _emit_phase_ok("detecting", {
        "platform": cap.name,
        "label": cap.label,
        "paths": det.paths,
        "version": det.version,
    })
    _emit_phase_started("preflight")
    report = cap.preflight(opts)
    _emit_phase_ok("preflight", {
        "ok": report.ok,
        "intended_changes": report.intended_changes,
        "blockers": report.blockers,
        "warnings": report.warnings,
    })
    _emit_phase_started("done")
    emit_ok({
        "phase": "done",
        "platform": cap.name,
        "intended_changes": report.intended_changes,
        "blockers": report.blockers,
        "warnings": report.warnings,
    })
    return OK if report.ok else BAD_INPUT


def _run_install(cap: SetupCapability, opts: SetupOptions) -> int:
    """Install mode — needs the lock; runs detect+preflight inside it
    so the operator-confirmation summary reflects fresh state."""
    try:
        with acquire_setup_lock():
            return _install_under_lock(cap, opts)
    except SetupLockHeld as e:
        emit_error(
            "setup_lock_held",
            f"another `aivg setup` is running (pid={e.meta.get('pid')}); "
            f"lock at {e.lock_path}",
        )
        return BAD_INPUT


def _install_under_lock(cap: SetupCapability, opts: SetupOptions) -> int:
    _emit_phase_started("detecting")
    det = cap.detect()
    _emit_phase_ok("detecting", {
        "platform": cap.name,
        "paths": det.paths,
        "version": det.version,
    })
    _emit_phase_started("preflight")
    report = cap.preflight(opts)
    _emit_phase_ok("preflight", {
        "intended_changes": report.intended_changes,
        "blockers": report.blockers,
        "warnings": report.warnings,
    })
    if report.blockers:
        emit_error(
            "host_state_drifted" if any("marker" in b.lower() for b in report.blockers)
            else "permission_denied" if any("perm" in b.lower() for b in report.blockers)
            else "bad_input",
            "preflight reports blockers: " + "; ".join(report.blockers),
        )
        return BAD_INPUT

    summary = (
        f"AIVG will install into {cap.label} ({cap.name}). The following "
        f"changes will be made:\n\n"
        + "\n".join(f"  - {line}" for line in report.intended_changes)
    )
    if not _confirm_or_bail(opts, summary=summary):
        return BAD_INPUT

    try:
        result: InstallResult = cap.install(opts)
    except SetupError as e:
        emit_error(e.code, e.message)
        return map_error_to_exit_code(e.code)
    except Exception as e:  # noqa: BLE001 - any plugin-side surprise → partial failure
        emit_error("setup_partial_failure", f"install raised: {e}")
        return SETUP_PARTIAL_FAILURE

    # Replay every phase the plugin recorded onto the NDJSON stream so
    # the operator (or supervising agent) sees the full sequence in
    # stdout. The plugin's persistence-side log is the source of truth;
    # the CLI's stdout is the streamed mirror. We drop the terminal
    # "done" phase here — it is emitted as the final `ok` envelope
    # below with backup_dir/rollback_command attached.
    for ph in result.phases:
        if ph.name == "done":
            continue
        _emit_phase(ph)

    if result.ok:
        emit_ok({
            "phase": "done",
            "platform": cap.name,
            "backup_dir": str(result.backup_dir) if result.backup_dir else None,
            "rollback_command": result.rollback_command,
        })
        return OK
    emit_error(
        "setup_partial_failure",
        result.failure_reason or "install failed (no reason)",
    )
    return SETUP_PARTIAL_FAILURE


def _run_uninstall(cap: SetupCapability, opts: SetupOptions) -> int:
    try:
        with acquire_setup_lock():
            return _uninstall_under_lock(cap, opts)
    except SetupLockHeld as e:
        emit_error(
            "setup_lock_held",
            f"another `aivg setup` is running (pid={e.meta.get('pid')}); "
            f"lock at {e.lock_path}",
        )
        return BAD_INPUT


def _uninstall_under_lock(cap: SetupCapability, opts: SetupOptions) -> int:
    _emit_phase_started("detecting")
    det = cap.detect()
    _emit_phase_ok("detecting", {"platform": cap.name, "paths": det.paths})

    _emit_phase_started("preflight")
    report = cap.preflight(opts)
    _emit_phase_ok("preflight", {
        "intended_changes": [f"REMOVE: {c}" for c in report.intended_changes],
    })

    summary = (
        f"AIVG will be uninstalled from {cap.label} ({cap.name}). The "
        f"following artifacts will be removed:\n\n"
        + "\n".join(f"  - {line}" for line in report.intended_changes)
    )
    if not _confirm_or_bail(opts, summary=summary):
        return BAD_INPUT

    try:
        result: UninstallResult = cap.uninstall(opts)
    except SetupError as e:
        emit_error(e.code, e.message)
        return map_error_to_exit_code(e.code)
    except Exception as e:  # noqa: BLE001
        emit_error("setup_partial_failure", f"uninstall raised: {e}")
        return SETUP_PARTIAL_FAILURE

    # Replay phases for the stdout stream; terminal `done` becomes the
    # final `ok` envelope below.
    for ph in result.phases:
        if ph.name == "done":
            continue
        _emit_phase(ph)

    if result.ok:
        emit_ok({
            "phase": "done",
            "platform": cap.name,
            "removed": result.removed,
            "config_changes": result.config_changes,
        })
        return OK
    emit_error(
        "setup_partial_failure",
        result.failure_reason or "uninstall failed (no reason)",
    )
    return SETUP_PARTIAL_FAILURE


def _run_restore(backup_path: str, opts: SetupOptions) -> int:
    """Restore from a backup folder under `~/.aivg/installs/<platform>/<ts>/`."""
    from pathlib import Path

    bdir = Path(backup_path).expanduser()
    if not bdir.exists() or not (bdir / "manifest.json").exists():
        emit_error(
            "bad_input",
            f"backup folder not found or missing manifest.json: {bdir}",
        )
        return BAD_INPUT
    # Derive platform from the manifest, then load that plugin's
    # rollback method.
    import json
    try:
        manifest = json.loads((bdir / "manifest.json").read_text())
    except (OSError, ValueError) as e:
        emit_error("bad_input", f"could not read backup manifest: {e}")
        return BAD_INPUT
    platform_name = manifest.get("platform")
    if not platform_name:
        emit_error("bad_input", "backup manifest missing `platform` field")
        return BAD_INPUT

    from aivg_core.platforms.base import PluginRegistry
    try:
        cap = PluginRegistry.load_setup_capability(platform_name)
    except RuntimeError as e:
        emit_error("setup_not_supported_for_platform", str(e))
        return BAD_INPUT

    if not hasattr(cap, "rollback"):
        emit_error(
            "setup_not_supported_for_platform",
            f"plugin {platform_name!r} does not implement rollback",
        )
        return BAD_INPUT

    try:
        with acquire_setup_lock():
            _emit_phase_started("preflight")
            _emit_phase_ok("preflight", {"backup_dir": str(bdir)})

            summary = (
                f"Restore {cap.label} from backup at\n    {bdir}\n"
                "This will overwrite the current config + remove plugin dirs "
                "not present in the backup's pre-state."
            )
            if not _confirm_or_bail(opts, summary=summary):
                return BAD_INPUT

            try:
                result = cap.rollback(opts, backup_dir=bdir)  # type: ignore[attr-defined]
            except SetupError as e:
                emit_error(e.code, e.message)
                return map_error_to_exit_code(e.code)
            except Exception as e:  # noqa: BLE001
                emit_error("setup_partial_failure", f"rollback raised: {e}")
                return SETUP_PARTIAL_FAILURE

            if result.ok:
                emit_ok({
                    "phase": "done",
                    "platform": cap.name,
                    "restored_files": result.restored_files,
                    "new_backup_dir": str(result.new_backup_dir) if result.new_backup_dir else None,
                })
                return OK
            emit_error("setup_partial_failure", "rollback failed")
            return SETUP_PARTIAL_FAILURE
    except SetupLockHeld as e:
        emit_error(
            "setup_lock_held",
            f"another `aivg setup` is running (pid={e.meta.get('pid')}); "
            f"lock at {e.lock_path}",
        )
        return BAD_INPUT


def _run_parity_check(cap: SetupCapability, opts: SetupOptions, phrase: str) -> int:
    if not hasattr(cap, "parity_check"):
        emit_error(
            "setup_not_supported_for_platform",
            f"plugin {cap.name!r} does not implement parity_check",
        )
        return BAD_INPUT
    _emit_phase_started("parity_check")
    try:
        result = cap.parity_check(opts, phrase=phrase)  # type: ignore[attr-defined]
    except SetupError as e:
        emit_error(e.code, e.message)
        return map_error_to_exit_code(e.code)
    if result.ok:
        _emit_phase_ok("parity_check", {
            "expected": result.expected,
            "observed": result.observed,
            "notes": result.notes,
        })
        emit_ok({"phase": "done", "platform": cap.name, **asdict(result)})
        return OK
    emit_error(
        "setup_partial_failure",
        f"parity mismatch: expected={result.expected!r} observed={result.observed!r}",
    )
    return SETUP_PARTIAL_FAILURE
