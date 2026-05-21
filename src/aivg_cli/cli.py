"""``aivg`` Typer app — entry point ``aivg`` (see ``pyproject.toml``).

AIVG (AI Voice Gateway) management CLI — platform-neutral
(constitution v2.0.1 Principle IV). The legacy binary name ``sat-cli``
was removed in feature 012 Phase 9; consumers should use ``aivg``.

Contract: ``specs/011-satellite-management/contracts/cli-contract.md``.
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Optional

import typer

from . import __version__
from .exit_codes import (
    BAD_INPUT,
    GATEWAY_UNREACHABLE,
    map_error_to_exit_code,
    OK,
)
from .output import (
    emit_error,
    emit_ok,
    human_device_state,
    human_table_devices,
    set_context,
)
from .rest_client import ManagementClient, RestError
from .stream import stream_log_entries

CONTRACT_VERSION = "0.2.0"  # feature 018 — reset to public-baseline at first PyPI release (was "1.1.0" pre-PyPI; before that "1.0.0")
# The transports list is REPORTED by the gateway at runtime (it knows which
# listeners are bound). The CLI-side fallback emits both names because the
# enabled-state isn't queryable from the CLI without hitting the gateway;
# operators rely on this as a "what transports CAN the gateway speak?" hint.
SUPPORTED_TRANSPORTS = ["webrtc", "esphome_api"]

app = typer.Typer(
    name="aivg",
    help="AIVG (AI Voice Gateway) — platform-neutral satellite "
    "management CLI (constitution v2.0.1 Principle IV). Speaks the App. A "
    "REST surface; ships per-agent-platform skills alongside (Hermes v1; "
    "OpenClaw planned).",
    add_completion=False,
    # invoke_without_command lets --version / --contract-version fire from
    # the root callback without Typer's "missing command" rejection.
    invoke_without_command=True,
)

device_app = typer.Typer(no_args_is_help=True, help="Per-device operations.")
app.add_typer(device_app, name="device")

device_config_app = typer.Typer(
    no_args_is_help=True, help="Per-device configuration (get / set / schema)."
)
device_app.add_typer(device_config_app, name="config")

fleet_app = typer.Typer(no_args_is_help=True, help="Fleet-wide views.")
app.add_typer(fleet_app, name="fleet")

ota_app = typer.Typer(no_args_is_help=True, help="Per-device OTA firmware updates.")
app.add_typer(ota_app, name="ota")

# Feature 013 — `aivg setup` / `aivg deploy` (platform-agnostic host install).
from .setup import setup_app  # noqa: E402  (after `app` is defined)
app.add_typer(
    setup_app,
    name="setup",
    help="Install AIVG into the active agent platform (Hermes / OpenClaw / ...).",
)
app.add_typer(
    setup_app,
    name="deploy",
    help="Synonym for `aivg setup`. Same flags, same behavior.",
)


# --- Global state --------------------------------------------------------

class _Globals:
    gateway: str = os.environ.get("SAT_GATEWAY_URL", "http://localhost:8643")
    json_mode: bool = bool(os.environ.get("SAT_JSON"))
    timeout: float = float(os.environ.get("SAT_TIMEOUT", "10"))
    yes: bool = False


G = _Globals()


@app.callback()
def _root(
    ctx: typer.Context,
    gateway: str = typer.Option(
        G.gateway, "--gateway", envvar="SAT_GATEWAY_URL",
        help="Management plane base URL.",
    ),
    json_mode: bool = typer.Option(
        G.json_mode, "--json", envvar="SAT_JSON",
        help="Emit one JSON envelope per output unit (NDJSON for streams).",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip destructive confirmations."),
    timeout: float = typer.Option(G.timeout, "--timeout", envvar="SAT_TIMEOUT"),
    verbose: bool = typer.Option(False, "--verbose"),
    no_color: bool = typer.Option(False, "--no-color"),
    show_version: bool = typer.Option(
        False, "--version", help="Print binary version and exit.", is_eager=True
    ),
    show_contract: bool = typer.Option(
        False, "--contract-version", help="Print contract version and exit.", is_eager=True,
    ),
) -> None:
    set_context(json_mode=json_mode, no_color=no_color, verbose=verbose)
    if show_version:
        emit_ok({
            "version": __version__,
            "contract_version": CONTRACT_VERSION,
            "transports": SUPPORTED_TRANSPORTS,
        })
        raise typer.Exit(OK)
    if show_contract:
        emit_ok({
            "contract_version": CONTRACT_VERSION,
            "transports": SUPPORTED_TRANSPORTS,
        })
        raise typer.Exit(OK)

    G.gateway = gateway
    G.json_mode = json_mode
    G.yes = yes
    G.timeout = timeout

    # If no subcommand was invoked AND we didn't print version, show help.
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(BAD_INPUT)


# --- helpers -------------------------------------------------------------

def _run(coro) -> int:
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        return 130


async def _client() -> ManagementClient:
    return ManagementClient(G.gateway, timeout=G.timeout)


def _bail_on_rest_error(e: RestError) -> int:
    emit_error(e.code, e.message)
    return map_error_to_exit_code(e.code)


# --- commands ------------------------------------------------------------

@app.command("list")
def cmd_list(
    state: str = typer.Option("all", "--state", help="all | adopted | pending"),
) -> None:
    """List the fleet (or its pending devices)."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                rows = await c.list_devices(state=state)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(rows)
        else:
            human_table_devices(rows)
        return OK

    raise typer.Exit(_run(_do()))


@device_app.command("get")
def cmd_device_get(device_id: str) -> None:
    """Show one device's full state."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                st = await c.get_device_state(device_id)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(st)
        else:
            human_device_state(st)
        return OK

    raise typer.Exit(_run(_do()))


# --- aivg device config get / set / schema (feature 011 US3) -------------


def _coerce_field_value(raw: str):
    """Parse a `--field key=value` value: try JSON first (catches int,
    float, bool, null, lists, objects); fall back to raw string."""
    import json as _json

    try:
        return _json.loads(raw)
    except (ValueError, TypeError):
        return raw


@device_config_app.command("get")
def cmd_device_config_get(device_id: str) -> None:
    """Show a device's running configuration."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                cfg = await c.get_device_config(device_id)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(cfg)
        else:
            human_device_state(cfg)
        return OK

    raise typer.Exit(_run(_do()))


@device_config_app.command("set")
def cmd_device_config_set(
    device_id: str,
    field: list[str] = typer.Option(
        [], "--field", help="`key=value` (JSON-parsed; repeatable)."
    ),
    from_file: Optional[str] = typer.Option(
        None, "--from-file", help="JSON file with overrides."
    ),
    if_match: Optional[int] = typer.Option(
        None, "--if-match", help="Optimistic concurrency: fail if current config_version differs."
    ),
    queue: bool = typer.Option(
        False, "--queue",
        help="Allow queueing the write if the device is offline (else exits 2 device_offline).",
    ),
) -> None:
    """Update a device's configuration."""
    import json as _json

    overrides: dict = {}
    if from_file:
        try:
            overrides.update(_json.loads(open(from_file).read()))
        except (OSError, ValueError) as e:
            emit_error("bad_input", f"could not read --from-file {from_file!r}: {e}")
            raise typer.Exit(BAD_INPUT)
    for kv in field:
        if "=" not in kv:
            emit_error("bad_input", f"--field expects `key=value`, got {kv!r}")
            raise typer.Exit(BAD_INPUT)
        key, raw = kv.split("=", 1)
        overrides[key.strip()] = _coerce_field_value(raw)
    if not overrides:
        emit_error("bad_input", "no overrides supplied (use --field or --from-file)")
        raise typer.Exit(BAD_INPUT)

    async def _do() -> int:
        async with await _client() as c:
            try:
                payload = await c.post_device_config(
                    device_id, overrides, if_match=if_match, queue=queue
                )
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(payload)
        else:
            human_device_state(payload)
        return OK

    raise typer.Exit(_run(_do()))


@device_config_app.command("schema")
def cmd_device_config_schema(device_id: str) -> None:
    """Show the JSON Schema for the device's editable config fields."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                schema = await c.get_device_config_schema(device_id)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(schema)
        else:
            from rich.console import Console
            import json as _json
            Console().print_json(_json.dumps(schema))
        return OK

    raise typer.Exit(_run(_do()))


# --- aivg device command / delete (feature 011 US5) ---------------------

# Map dash-style verbs the CLI accepts to the underscore enum values.
_VERB_ALIASES = {
    "reboot": "reboot",
    "restart-voice": "restart_voice",
    "restart-manager": "restart_manager",
    "reset-config": "reset_config",
    "factory-reset": "factory_reset",
    "mute": "mute",
    "unmute": "unmute",
    "identify": "identify",
}
_DESTRUCTIVE_VERBS = {"factory_reset"}


def _confirm_destructive_or_bail(label: str) -> bool:
    """Ask the operator to confirm a destructive action.

    Under --json without --yes, refuses (FR-019); the agent/script must
    have explicit consent before piping --yes. Under interactive mode,
    prompts on stderr/stdin; non-`yes` cancels.
    """
    if G.yes:
        return True
    if G.json_mode:
        emit_error(
            "bad_input",
            f"refusing destructive action {label!r} under --json without --yes; "
            "ask the user to confirm in chat, then re-run with --yes",
        )
        return False
    sys.stderr.write(
        f"\n⚠️  Destructive: {label}\nType the device id or 'yes' to confirm, anything else to cancel: "
    )
    sys.stderr.flush()
    ans = sys.stdin.readline().strip()
    return ans.lower() in ("y", "yes") or len(ans) > 0 and label.endswith(ans)


@device_app.command("command")
def cmd_device_command(
    device_id: str,
    verb: str,
    args: Optional[str] = typer.Option(
        None, "--args", help="JSON dict of command args (e.g. `{\"duration_s\": 3}`)."
    ),
) -> None:
    """Send a command to a device (one of: reboot, restart-voice,
    restart-manager, reset-config, factory-reset, mute, unmute,
    identify). Destructive verbs require confirmation."""
    import json as _json

    enum_verb = _VERB_ALIASES.get(verb)
    if enum_verb is None:
        emit_error(
            "bad_input",
            f"unknown verb {verb!r}; expected one of: {', '.join(sorted(_VERB_ALIASES))}",
        )
        raise typer.Exit(BAD_INPUT)
    if enum_verb in _DESTRUCTIVE_VERBS and not _confirm_destructive_or_bail(
        f"command {verb} on {device_id!r}"
    ):
        raise typer.Exit(BAD_INPUT)

    parsed_args: Optional[dict] = None
    if args:
        try:
            parsed_args = _json.loads(args)
            if not isinstance(parsed_args, dict):
                raise ValueError("--args must be a JSON dict")
        except ValueError as e:
            emit_error("bad_input", f"bad --args JSON: {e}")
            raise typer.Exit(BAD_INPUT)

    async def _do() -> int:
        async with await _client() as c:
            try:
                payload = await c.post_device_command(device_id, enum_verb, parsed_args)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(payload)
        else:
            from rich.console import Console
            Console().print(payload)
        return OK

    raise typer.Exit(_run(_do()))


@device_app.command("delete")
def cmd_device_delete(device_id: str) -> None:
    """Unpair (remove) a device from the fleet — destructive."""
    if not _confirm_destructive_or_bail(f"delete {device_id!r} from the fleet"):
        raise typer.Exit(BAD_INPUT)

    async def _do() -> int:
        async with await _client() as c:
            try:
                await c.delete_device(device_id)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok({"deleted": device_id})
        else:
            from rich.console import Console
            Console().print(f"[red]✓[/] removed {device_id}")
        return OK

    raise typer.Exit(_run(_do()))


# --- aivg ota check / apply / manifest (feature 011 US4) ----------------


@ota_app.command("check")
def cmd_ota_check(device_id: str) -> None:
    """Check whether the device has a firmware update available."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                payload = await c.ota_check(device_id)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(payload)
        else:
            from rich.console import Console
            Console().print(payload)
        return OK

    raise typer.Exit(_run(_do()))


@ota_app.command("manifest")
def cmd_ota_manifest(device_id: str) -> None:
    """Show the firmware manifest for this device's type."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                payload = await c.ota_manifest(device_id)
            except RestError as e:
                return _bail_on_rest_error(e)
        if G.json_mode:
            emit_ok(payload)
        else:
            from rich.console import Console
            import json as _json
            Console().print_json(_json.dumps(payload))
        return OK

    raise typer.Exit(_run(_do()))


@ota_app.command("apply")
def cmd_ota_apply(
    device_id: str,
    version: str,
    follow: bool = typer.Option(
        False, "--follow", "-f",
        help="Stream device-reported OTA progress until terminal state.",
    ),
    url: Optional[str] = typer.Option(None, "--url", help="Override the manifest URL."),
) -> None:
    """Apply a firmware update (US4)."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                job = await c.ota_apply(device_id, version, url=url)
            except RestError as e:
                return _bail_on_rest_error(e)
            if not follow:
                if G.json_mode:
                    emit_ok(job)
                else:
                    from rich.console import Console
                    Console().print(job)
                return OK
            # --follow: open the SSE log stream filtered to source=ota,
            # emit each progress event as NDJSON until terminal state.
            from .output import emit_ndjson
            terminal_states = {"failed", "rolled_back"}
            success_terminal = False
            try:
                async for entry in c.follow_device_logs(device_id, source="ota"):
                    if G.json_mode:
                        emit_ndjson(entry)
                    else:
                        from .output import human_log_entry
                        human_log_entry(entry)
                    meta = (entry.get("metadata") or {})
                    result = meta.get("result")
                    if result == "success":
                        success_terminal = True
                        break
                    if result in terminal_states or meta.get("state") in terminal_states:
                        # Map terminal failure to exit 5 + typed error.
                        code = "rolled_back" if (result == "rolled_back" or meta.get("state") == "rolled_back") else "ota_failed"
                        emit_error(code, meta.get("failure_reason") or f"OTA terminated: {result or meta.get('state')}")
                        return map_error_to_exit_code(code)
            except RestError as e:
                return _bail_on_rest_error(e)
            return OK if success_terminal else OK  # OK if interrupted

    raise typer.Exit(_run(_do()))


@app.command("logs")
def cmd_logs(
    device_id: str,
    follow: bool = typer.Option(False, "--follow", "-f"),
    level: Optional[str] = typer.Option(None, "--level"),
    source: Optional[str] = typer.Option(None, "--source"),
    since: Optional[float] = typer.Option(None, "--since", help="Unix timestamp."),
) -> None:
    """Tail one device's logs (one-shot or live SSE)."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                if not follow:
                    entries = await c.get_fleet_logs(
                        device_id=device_id, level=level, source=source, since=since
                    )
                    if G.json_mode:
                        emit_ok(entries)
                    else:
                        from .output import human_log_entry
                        for e in entries:
                            human_log_entry(e)
                    return OK
                stream = c.follow_device_logs(
                    device_id, level=level, source=source, since=since
                )
                await stream_log_entries(stream)
                return OK
            except RestError as e:
                return _bail_on_rest_error(e)

    raise typer.Exit(_run(_do()))


@fleet_app.command("logs")
def cmd_fleet_logs(
    follow: bool = typer.Option(False, "--follow", "-f"),
    device_id: Optional[str] = typer.Option(None, "--device"),
    level: Optional[str] = typer.Option(None, "--level"),
    source: Optional[str] = typer.Option(None, "--source"),
    since: Optional[float] = typer.Option(None, "--since"),
) -> None:
    """Aggregate fleet log."""
    async def _do() -> int:
        async with await _client() as c:
            try:
                if not follow:
                    entries = await c.get_fleet_logs(
                        device_id=device_id, level=level, source=source, since=since
                    )
                    if G.json_mode:
                        emit_ok(entries)
                    else:
                        from .output import human_log_entry
                        for e in entries:
                            human_log_entry(e)
                    return OK
                stream = c.follow_fleet_logs(
                    device_id=device_id, level=level, source=source, since=since
                )
                await stream_log_entries(stream)
                return OK
            except RestError as e:
                return _bail_on_rest_error(e)

    raise typer.Exit(_run(_do()))


@app.command("onboard")
def cmd_onboard(
    ssid: str = typer.Option(..., "--ssid", help="Wi-Fi SSID for the device."),
    password: str = typer.Option(
        "", "--password", help="Wi-Fi password (empty = open network).",
    ),
    name: str = typer.Option(
        ..., "--name",
        help="Human room name for the device (required under --json/--yes).",
    ),
    scan_timeout: float = typer.Option(30.0, "--scan-timeout"),
    register_timeout: float = typer.Option(90.0, "--register-timeout"),
) -> None:
    """Improv-over-BLE provisioning + adopt (US2)."""
    from .onboard.flow import OnboardError, OnboardProgress, OnboardResult, run_onboard

    async def _do() -> int:
        try:
            stream = run_onboard(
                ssid=ssid,
                password=password,
                name=name,
                gateway_url=G.gateway,
                scan_timeout=scan_timeout,
                register_timeout=register_timeout,
            )
            async for event in stream:
                if isinstance(event, OnboardProgress):
                    if G.json_mode:
                        from .output import emit_ndjson
                        emit_ndjson({"phase": event.phase, "detail": event.detail})
                    else:
                        from rich.console import Console
                        Console().print(f"[bold]{event.phase}[/]  {event.detail or ''}")
                elif isinstance(event, OnboardResult):
                    if G.json_mode:
                        emit_ok({
                            "device_id": event.device_id,
                            "name": event.name,
                            "device_state": event.device_state,
                        })
                    else:
                        from rich.console import Console
                        Console().print(
                            f"[green]✓[/] adopted [bold]{event.name}[/] "
                            f"(id {event.device_id})"
                        )
                    return OK
            return OK
        except OnboardError as e:
            emit_error(e.code, e.message)
            return map_error_to_exit_code(e.code)

    raise typer.Exit(_run(_do()))


@app.command("watch")
def cmd_watch(
    device_id: Optional[str] = typer.Option(None, "--device"),
    interval: float = typer.Option(2.0, "--interval", help="Polling interval (s)."),
) -> None:
    """Live NDJSON stream of fleet/device state changes.

    v1: poll-based watcher emitting one NDJSON envelope per *changed*
    snapshot (cheaper than wiring a second SSE stream for state). Future
    versions can upgrade to a dedicated state SSE without changing the
    output contract.
    """
    async def _do() -> int:
        prev_signature: dict[str, tuple] = {}
        async with await _client() as c:
            while True:
                try:
                    rows = await c.list_devices(state="all")
                except RestError as e:
                    return _bail_on_rest_error(e)
                changed: list[dict] = []
                next_sig: dict[str, tuple] = {}
                for r in rows:
                    if device_id and r.get("device_id") != device_id:
                        continue
                    sig = (
                        r.get("status"),
                        r.get("adoption_state"),
                        r.get("ota_state"),
                        round(r.get("last_seen") or 0, 2),
                    )
                    next_sig[r["device_id"]] = sig
                    if prev_signature.get(r["device_id"]) != sig:
                        changed.append(r)
                # Detect removals as terminal events.
                for old_id in prev_signature:
                    if old_id not in next_sig:
                        changed.append({"device_id": old_id, "status": "removed"})
                prev_signature = next_sig
                for r in changed:
                    if G.json_mode:
                        emit_ok({"event": "state_update", "device": r})
                    else:
                        from .output import human_log_entry
                        # Reuse log-line look for compact human stream.
                        human_log_entry(
                            {
                                "timestamp": r.get("last_seen"),
                                "level": "INFO",
                                "source": "system",
                                "device_id": r.get("device_id"),
                                "message": f"state={r.get('status','?')} "
                                f"adoption={r.get('adoption_state','?')} "
                                f"ota={r.get('ota_state','?')}",
                            }
                        )
                await asyncio.sleep(interval)

    raise typer.Exit(_run(_do()))


if __name__ == "__main__":  # pragma: no cover
    app()
