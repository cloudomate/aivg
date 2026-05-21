"""``EsphomeTransport`` — the listener + lifecycle owner.

Wraps an :func:`asyncio.start_server` on the configured TCP port,
spawns one :class:`asyncio.Task` per accepted device connection
(R-2), and provides a clean :meth:`start` / :meth:`stop` lifecycle
the gateway adapter invokes alongside its existing aiohttp sites.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import TYPE_CHECKING, Callable, Optional

from ...logsink import LogSink
from .auth import KeystoreResolver
from .connection import EsphomeConnection

if TYPE_CHECKING:
    from ...platforms.base import AgentPlatform
    from ...registry import Registry

_LOG = logging.getLogger(__name__)


class EsphomeTransport:
    """ESPHome native API server. One instance per gateway.

    Construction is side-effect-free; :meth:`start` binds the listener
    socket. :meth:`stop` is idempotent and cancels all in-flight
    device tasks before closing the listener.
    """

    def __init__(
        self,
        *,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: LogSink,
        host: str = "0.0.0.0",
        port: int = 6053,
        api_key_resolver: Optional[KeystoreResolver] = None,
        bootstrap_key: Optional[str] = None,
        ui_broadcast: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._host = host
        self._port = port
        self._keystore = api_key_resolver or KeystoreResolver()
        self._bootstrap_key = bootstrap_key
        self._ui_broadcast = ui_broadcast

        self._server: Optional[asyncio.base_events.Server] = None
        # Per-connection task registry. Keyed by an opaque
        # task-handle uuid so a re-connecting device with the same
        # name doesn't overwrite an in-flight close path.
        self._tasks: dict[str, asyncio.Task] = {}

    async def start(self) -> None:
        """Bind the listener socket and start accepting connections."""
        if self._server is not None:
            return  # already started
        self._server = await asyncio.start_server(
            self._on_connect, host=self._host, port=self._port
        )
        _LOG.info(
            "esphome: transport listening on %s:%d (devices=0)",
            self._host,
            self._port,
        )

    async def stop(self) -> None:
        """Idempotent. Cancels all device tasks within ~1 s, then
        closes the listener socket."""
        if self._server is None:
            return
        # Stop accepting new connections.
        self._server.close()
        try:
            await self._server.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        self._server = None
        # Cancel every in-flight device task.
        for task in list(self._tasks.values()):
            task.cancel()
        if self._tasks:
            try:
                await asyncio.wait(self._tasks.values(), timeout=1.0)
            except Exception:  # noqa: BLE001
                pass
        self._tasks.clear()

    async def _on_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Per-connection callback. Spawn one task running the
        connection co-routine; the task self-removes from the
        registry on completion."""
        handle = uuid.uuid4().hex
        conn = EsphomeConnection(
            reader,
            writer,
            registry=self._registry,
            platform=self._platform,
            sink=self._sink,
            keystore=self._keystore,
            bootstrap_key=self._bootstrap_key,
            ui_broadcast=self._ui_broadcast,
        )
        task = asyncio.create_task(conn.run(), name=f"esphome-conn-{handle}")
        self._tasks[handle] = task

        def _done(_t: asyncio.Task, _h: str = handle) -> None:
            self._tasks.pop(_h, None)

        task.add_done_callback(_done)

    @property
    def device_count(self) -> int:
        """Number of currently-connected device tasks."""
        return len(self._tasks)
