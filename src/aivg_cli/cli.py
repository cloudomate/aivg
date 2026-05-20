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

CONTRACT_VERSION = "1.0.0"

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

fleet_app = typer.Typer(no_args_is_help=True, help="Fleet-wide views.")
app.add_typer(fleet_app, name="fleet")


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
        emit_ok({"version": __version__, "contract_version": CONTRACT_VERSION})
        raise typer.Exit(OK)
    if show_contract:
        emit_ok({"contract_version": CONTRACT_VERSION})
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
