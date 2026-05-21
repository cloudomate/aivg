"""Client-mode supervisor for the ESPHome transport.

Real ESPHome firmware devices ARE the API server (they listen on port
6053 and advertise ``_esphomelib._tcp`` via mDNS). For AIVG to talk to
them we need to **dial out** — open a TCP connection to each
configured device's host:port and run an :class:`EsphomeConnection`
co-routine in ``direction="client"`` mode.

This dialer maintains one :class:`asyncio.Task` per configured device
(R-2 — same per-task model as the server-side listener), with
reconnect-with-exponential-backoff on disconnect (devices reboot,
WiFi flaps, etc.). When a device is unreachable for an extended
window the task stays alive but waits longer between dial attempts.

The dialer is OPTIONAL — operators who run AIVG against
:mod:`linux-voice-assistant`-style satellites (where the satellite
dials AIVG) keep only the server-side listener. Operators with real
ESPHome hardware enable the dialer by populating
``transports.esphome_api.devices`` in the satellite config.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import TYPE_CHECKING, Callable, Optional

from ...logsink import LogSink
from .auth import KeystoreResolver
from .connection import EsphomeConnection

if TYPE_CHECKING:
    from ...platforms.base import AgentPlatform
    from ...registry import Registry

_LOG = logging.getLogger(__name__)

# Exponential-backoff bounds for reconnect attempts.
_MIN_BACKOFF_S = 1.0
_MAX_BACKOFF_S = 60.0


class EsphomeDeviceDialer:
    """Maintains outbound ESPHome native API connections to a fixed
    list of devices. One ``asyncio.Task`` per device; each task loops
    forever (until :meth:`stop`), dialing the device's port 6053,
    running the connection co-routine, and reconnecting with backoff
    when the connection drops."""

    def __init__(
        self,
        *,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: LogSink,
        devices: list[dict],  # [{host, port, device_id, api_key}, ...]
        ui_broadcast: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._devices = devices
        self._ui_broadcast = ui_broadcast
        self._tasks: dict[str, asyncio.Task] = {}
        self._stopped = asyncio.Event()
        # KeystoreResolver isn't used for dialer auth (we have the
        # api_key directly in the device config), but EsphomeConnection
        # still requires a resolver instance — pass a stub.
        self._stub_keystore = KeystoreResolver()

    async def start(self) -> None:
        for dev in self._devices:
            device_id = str(dev.get("device_id") or dev.get("host") or "?")
            task = asyncio.create_task(
                self._dial_loop(dev), name=f"esphome-dial-{device_id}"
            )
            self._tasks[device_id] = task
        _LOG.info(
            "esphome: dialer started for %d device(s): %s",
            len(self._devices),
            ", ".join(str(d.get("device_id") or d.get("host")) for d in self._devices),
        )

    async def stop(self) -> None:
        self._stopped.set()
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            try:
                await asyncio.wait(self._tasks.values(), timeout=2.0)
            except Exception:  # noqa: BLE001
                pass
        self._tasks.clear()

    async def _dial_loop(self, dev: dict) -> None:
        """Per-device task: dial + run + reconnect-with-backoff."""
        host = str(dev["host"])
        port = int(dev.get("port", 6053))
        device_id = str(dev["device_id"])
        api_key = str(dev.get("api_key") or "")
        backoff = _MIN_BACKOFF_S
        while not self._stopped.is_set():
            try:
                reader, writer = await asyncio.open_connection(host, port)
            except (ConnectionRefusedError, OSError) as exc:
                _LOG.info(
                    "esphome dialer: %s:%d unreachable (%s); retry in %.1fs",
                    host, port, exc, backoff,
                )
                await self._sleep_with_jitter(backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF_S)
                continue

            # Connection established — reset backoff for next failure.
            backoff = _MIN_BACKOFF_S
            conn = EsphomeConnection(
                reader, writer,
                registry=self._registry,
                platform=self._platform,
                sink=self._sink,
                keystore=self._stub_keystore,
                bootstrap_key=None,
                ui_broadcast=self._ui_broadcast,
                direction="client",
                device_id_override=device_id,
                api_key_override=api_key,
            )
            try:
                await conn.run()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                _LOG.exception(
                    "esphome dialer: connection to %s:%d errored", host, port
                )

            if self._stopped.is_set():
                return

            _LOG.info(
                "esphome dialer: connection to %s:%d closed; reconnecting in %.1fs",
                host, port, backoff,
            )
            await self._sleep_with_jitter(backoff)
            backoff = min(backoff * 2, _MAX_BACKOFF_S)

    async def _sleep_with_jitter(self, base: float) -> None:
        """Backoff with ±20% jitter to avoid thundering-herd reconnects
        when many devices come back online simultaneously."""
        jitter = base * (0.8 + 0.4 * random.random())
        try:
            await asyncio.wait_for(self._stopped.wait(), timeout=jitter)
        except asyncio.TimeoutError:
            pass  # backoff complete, loop again
