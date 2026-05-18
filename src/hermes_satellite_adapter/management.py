"""Management plane (design Appendix A). The §2.1 control plane.

Transport-framework-agnostic: ``ManagementService`` holds all behaviour and is
unit/contract-tested directly; ``build_management_app`` is a thin aiohttp
wiring layer (lazy import) for production. The control WebSocket stays usable
when there is NO active voice call (constitution III / SC-006) — its handlers
live here and never touch the WebRTC plane.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from .config import SatelliteAdapterConfig
from .logsink import LogSink
from .models import LogLevel, LogSource, SatelliteConfig
from .registry import Registry


class ManagementService:
    def __init__(
        self, registry: Registry, sink: LogSink, cfg: SatelliteAdapterConfig
    ) -> None:
        self._reg = registry
        self._sink = sink
        self._cfg = cfg
        self._ws_subscribers: list[Callable[[dict], None]] = []

    # --- registration & lifecycle (REST + WS register) -------------------
    def register(self, body: dict[str, Any]) -> dict[str, Any]:
        device_id = body["device_id"]
        client = self._reg.register(
            device_id=device_id,
            device_type=body.get("device_type", "browser"),
            firmware_version=body.get("firmware_version", ""),
            ip_address=body.get("ip_address", ""),
            config=SatelliteConfig(**self._cfg.default_config)
            if self._cfg.default_config
            else SatelliteConfig(),
        )
        self._sink.emit(
            device_id, LogLevel.INFO, LogSource.SYSTEM, "registered",
            {"device_type": client.device_type},
        )
        self._broadcast({"type": "state_update", "device_id": device_id,
                         "status": client.status.value})
        return {
            "session_token": f"st-{device_id}-{int(time.time())}",  # reserved; auth deferred
            "management_server_url": f"http://0.0.0.0:{self._cfg.management_port}",
            "default_config": self._cfg.default_config,
        }

    def heartbeat(self, device_id: str) -> bool:
        return self._reg.heartbeat(device_id) is not None

    def list_clients(self) -> list[dict[str, Any]]:
        out = []
        for c in self._reg.list_clients():
            sess = self._reg.session_for_device(c.device_id)
            out.append(
                {
                    "device_id": c.device_id,
                    "device_type": c.device_type,
                    "status": c.status.value,
                    "last_seen": c.last_seen,
                    "firmware_version": c.firmware_version,
                    "active_routing_mode": c.config.routing_mode,
                    "webrtc_state": sess.webrtc_state if sess else "none",
                }
            )
        return out

    def get_state(self, device_id: str) -> dict[str, Any] | None:
        c = self._reg.get_client(device_id)
        if c is None:
            return None
        sess = self._reg.session_for_device(device_id)
        return {
            "device_id": c.device_id,
            "device_type": c.device_type,
            "status": c.status.value,
            "last_seen": c.last_seen,
            "session": (
                {
                    "session_id": sess.session_id,
                    "state": sess.state.value,
                    "webrtc_state": sess.webrtc_state,
                    "bitrate_tx": sess.bitrate_tx,
                    "bitrate_rx": sess.bitrate_rx,
                    "last_error": sess.last_error,
                }
                if sess
                else None
            ),
        }

    def delete(self, device_id: str) -> bool:
        return self._reg.remove_client(device_id)

    # --- configuration ---------------------------------------------------
    def get_config(self, device_id: str) -> dict[str, Any] | None:
        c = self._reg.get_client(device_id)
        return c.config.__dict__ if c else None

    def post_config(self, device_id: str, overrides: dict[str, Any]) -> dict[str, Any] | None:
        c = self._reg.get_client(device_id)
        if c is None:
            return None
        c.config = c.config.merged(overrides)
        self._broadcast(
            {"type": "config_changed", "device_id": device_id, "config": c.config.__dict__}
        )
        return c.config.__dict__

    def config_schema(self) -> dict[str, Any]:
        return {"fields": list(SatelliteConfig().__dict__.keys())}

    # --- logs (SSE source) ----------------------------------------------
    def query_logs(self, **filters) -> list[dict[str, Any]]:
        return [
            {
                "device_id": e.device_id,
                "timestamp": e.timestamp,
                "level": e.level.value,
                "source": e.source.value,
                "message": e.message,
                "metadata": e.metadata,
            }
            for e in self._sink.query(**filters)
        ]

    # --- commands & OTA (contract completeness; browser has no OTA) ------
    def command(self, device_id: str, command: str) -> dict[str, Any]:
        valid = {"reboot", "restart_voice", "restart_manager", "reset_config", "factory_reset"}
        accepted = command in valid and self._reg.get_client(device_id) is not None
        if accepted:
            self._broadcast(
                {"type": "command_response", "device_id": device_id, "command": command}
            )
        return {"accepted": accepted, "scheduled_at": time.time() if accepted else None}

    def ota_check(self, device_id: str) -> dict[str, Any]:
        return {"update_available": False, "latest_version": None, "changelog_url": None}

    # --- control WS fan-out ---------------------------------------------
    def subscribe_ws(self, cb: Callable[[dict], None]) -> Callable[[], None]:
        self._ws_subscribers.append(cb)
        return lambda: (
            self._ws_subscribers.remove(cb) if cb in self._ws_subscribers else None
        )

    def _broadcast(self, msg: dict) -> None:
        for cb in list(self._ws_subscribers):
            try:
                cb(msg)
            except Exception:
                pass


def build_management_app(service: "ManagementService"):  # pragma: no cover
    """Thin aiohttp wiring (lazy import; production only)."""
    from aiohttp import web  # noqa: WPS433

    app = web.Application()

    async def _register(req):
        return web.json_response(service.register(await req.json()))

    async def _list(req):
        return web.json_response(service.list_clients())

    async def _state(req):
        st = service.get_state(req.match_info["id"])
        return web.json_response(st) if st else web.Response(status=404)

    async def _delete(req):
        ok = service.delete(req.match_info["id"])
        return web.Response(status=204 if ok else 404)

    async def _get_cfg(req):
        c = service.get_config(req.match_info["id"])
        return web.json_response(c) if c else web.Response(status=404)

    async def _post_cfg(req):
        c = service.post_config(req.match_info["id"], await req.json())
        return web.json_response(c) if c else web.Response(status=404)

    async def _logs(req):
        return web.json_response(service.query_logs(**dict(req.query)))

    app.add_routes(
        [
            web.post("/satellite/register", _register),
            web.get("/satellite/list", _list),
            web.get("/satellite/{id}/state", _state),
            web.delete("/satellite/{id}", _delete),
            web.get("/satellite/{id}/config", _get_cfg),
            web.post("/satellite/{id}/config", _post_cfg),
            web.get("/satellite/{id}/logs", _logs),
            web.get("/satellite/logs", _logs),
        ]
    )
    return app
