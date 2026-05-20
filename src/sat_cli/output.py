"""Human and JSON formatters for ``sat-cli`` (contract: cli-contract.md).

The JSON envelope is the **stable v1 contract** consumed by agents and
scripts: one newline-terminated JSON object per output unit, shape
``{ "ok": bool, "data": ..., "error": null | { code, message }, "v": 1 }``.
Streaming commands emit one envelope per line (NDJSON).
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from typing import Any, Optional

ENVELOPE_VERSION = 1


@dataclass
class CliContext:
    """Carried through Typer commands via a module-level set/get pattern
    (lightweight; we don't depend on Typer Context for testability)."""

    json_mode: bool = False
    no_color: bool = False
    verbose: bool = False


_CTX = CliContext()


def set_context(*, json_mode: bool, no_color: bool, verbose: bool) -> None:
    _CTX.json_mode = json_mode
    _CTX.no_color = no_color or json_mode
    _CTX.verbose = verbose


def context() -> CliContext:
    return _CTX


def _envelope(ok: bool, data: Any, error: Optional[dict[str, str]] = None) -> dict[str, Any]:
    return {"ok": ok, "data": data, "error": error, "v": ENVELOPE_VERSION}


def emit_ok(data: Any) -> None:
    """One envelope on stdout. JSON-newline; humans get the same on
    stdout in JSON mode and a human render via the Rich formatters in
    non-JSON mode."""
    payload = _envelope(True, data, None)
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def emit_error(code: str, message: str) -> None:
    payload = _envelope(False, None, {"code": code, "message": message})
    sys.stdout.write(json.dumps(payload, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def emit_ndjson(data: Any) -> None:
    """One NDJSON line for streaming commands (logs follow, watch, ota
    apply --follow). Same envelope shape per line."""
    emit_ok(data)


# Human formatters (Rich). Imported lazily so the JSON-only consumer path
# does not pull Rich's large dep graph.

def human_table_devices(rows: list[dict]) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console(no_color=_CTX.no_color)
    table = Table(show_header=True, header_style="bold", box=None)
    for col in ("name", "id", "type", "status", "state", "last seen", "ota"):
        table.add_column(col)
    for r in rows:
        status_color = {
            "online": "green",
            "offline": "red",
            "connecting": "yellow",
            "error": "red",
        }.get(r.get("status", ""), "")
        status = f"[{status_color}]{r.get('status', '')}[/]" if status_color else r.get("status", "")
        table.add_row(
            r.get("name") or "—",
            r.get("device_id", ""),
            r.get("device_type", ""),
            status,
            r.get("adoption_state", ""),
            _human_age(r.get("last_seen")),
            r.get("ota_state", "idle"),
        )
    console.print(table)


def human_device_state(d: dict) -> None:
    from rich.console import Console
    from rich.table import Table

    console = Console(no_color=_CTX.no_color)
    table = Table(show_header=False, box=None)
    for k, v in d.items():
        table.add_row(str(k), str(v))
    console.print(table)


def human_log_entry(e: dict) -> None:
    import time
    from rich.console import Console

    console = Console(no_color=_CTX.no_color)
    ts = time.strftime("%H:%M:%S", time.localtime(e.get("timestamp", 0)))
    level = e.get("level", "")
    color = {"ERROR": "red", "WARN": "yellow", "INFO": "", "DEBUG": "dim"}.get(level, "")
    head = f"[{color}]{ts} {level:<5} {e.get('source','')} {e.get('device_id','')}[/]"
    console.print(f"{head}  {e.get('message','')}")


def _human_age(ts: Optional[float]) -> str:
    import time

    if ts is None:
        return "—"
    delta = time.time() - ts
    if delta < 0:
        return "future"
    if delta < 60:
        return f"{int(delta)}s ago"
    if delta < 3600:
        return f"{int(delta/60)}m ago"
    if delta < 86400:
        return f"{int(delta/3600)}h ago"
    return f"{int(delta/86400)}d ago"
