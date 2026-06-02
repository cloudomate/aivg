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

from ..config import SatelliteAdapterConfig
from ..logsink import LogSink
from ..models import ClientStatus, LogLevel, LogSource, SatelliteConfig
from ..registry import Registry


class ManagementService:
    def __init__(
        self, registry: Registry, sink: LogSink, cfg: SatelliteAdapterConfig
    ) -> None:
        # Feature 012 T009: run the legacy ~/.satellite/ → ~/.aivg/
        # one-shot migration before anything reads state.json. The
        # function is idempotent via a process-level sentinel; calling
        # it from every ManagementService construction is safe.
        from ..persistence import migrate_legacy_data_dir  # noqa: WPS433
        migrate_legacy_data_dir()

        self._reg = registry
        self._sink = sink
        self._cfg = cfg
        self._ws_subscribers: list[Callable[[dict], None]] = []
        # Feature 011 US4: OTA orchestration. The OtaService broadcasts
        # ``ota_apply`` frames over the device WS via the same `_broadcast`
        # path the rest of the management plane uses.
        from .ota import OtaService  # noqa: WPS433 (lazy to avoid circular)
        self._ota = OtaService(sink, broadcast=self._broadcast)

    # --- registration & lifecycle (REST + WS register) -------------------
    def register(self, body: dict[str, Any]) -> dict[str, Any]:
        """Device-driven register.

        Behavior is gated by ``cfg.auto_adopt_on_register`` (feature 011 US2):

        * ``True`` (default, back-compat) — new device is added directly to
          the adopted registry with a placeholder name. Existing voice-plane
          tests depend on this.
        * ``False`` — new device lands as ``PendingDevice``; an operator must
          POST ``/satellite/{id}/adopt`` to promote it. Same response shape
          either way; ``adoption_state`` in the payload tells the caller
          which path was taken.

        ``factory_reset=True`` always demotes an adopted record back to
        pending and discards the persisted config (R-7), regardless of
        ``auto_adopt_on_register``.
        """
        device_id = body["device_id"]
        device_type = body.get("device_type", "browser")
        firmware_version = body.get("firmware_version", "")
        ip_address = body.get("ip_address", "")
        factory_reset = bool(body.get("factory_reset", False))
        # Feature 021 / US3 — capability-based transport negotiation. A device
        # advertises which transports it can speak (best-first); an operator
        # MAY pin one. Absent on pre-021 clients → no negotiation (back-compat).
        transport_capabilities = body.get("transport_capabilities")
        transport_pin = body.get("transport_pin")

        # Surface an unsatisfiable transport pin as a clear, actionable error
        # rather than a silent fallback (FR-017).
        from ..transports import UnsatisfiableTransportPin  # noqa: WPS433

        adoption_state: str
        chosen_transport: "str | None" = None
        if factory_reset and self._reg.get_client(device_id) is not None:
            # Adopted → demote back to pending; drop persisted config.
            self._reg.demote_to_pending(
                device_id, device_type=device_type,
                firmware_version=firmware_version, ip_address=ip_address,
            )
            adoption_state = "pending"
        elif self._cfg.auto_adopt_on_register and not factory_reset:
            try:
                client = self._reg.register(
                    device_id=device_id,
                    device_type=device_type,
                    firmware_version=firmware_version,
                    ip_address=ip_address,
                    config=SatelliteConfig(**self._cfg.default_config)
                    if self._cfg.default_config
                    else SatelliteConfig(),
                    transport_capabilities=transport_capabilities,
                    transport_pin=transport_pin,
                )
            except UnsatisfiableTransportPin as exc:
                return {"error": "unsatisfiable_transport_pin", "detail": str(exc)}
            adoption_state = client.adoption_state.value
            chosen_transport = client.transport
        else:
            # auto_adopt_on_register=False OR factory_reset on an
            # unknown / pending device id.
            existing_adopted = self._reg.get_client(device_id)
            if existing_adopted is not None and not factory_reset:
                # Already-adopted refresh (config_overrides via /config).
                existing_adopted.device_type = device_type
                existing_adopted.firmware_version = firmware_version
                existing_adopted.ip_address = ip_address
                existing_adopted.status = existing_adopted.status.__class__.ONLINE
                existing_adopted.touch()
                adoption_state = "adopted"
            else:
                self._reg.register_pending(
                    device_id=device_id,
                    device_type=device_type,
                    firmware_version=firmware_version,
                    ip_address=ip_address,
                )
                adoption_state = "pending"

        self._sink.emit(
            device_id, LogLevel.INFO, LogSource.SYSTEM,
            "registered" if adoption_state == "adopted" else "registered_pending",
            {"device_type": device_type, "adoption_state": adoption_state},
        )
        self._broadcast(
            {
                "type": "state_update",
                "device_id": device_id,
                "adoption_state": adoption_state,
            }
        )
        resp = {
            "session_token": f"st-{device_id}-{int(time.time())}",  # reserved; auth deferred
            "management_server_url": f"http://0.0.0.0:{self._cfg.management_port}",
            "default_config": self._cfg.default_config,
            "adoption_state": adoption_state,
        }
        # Feature 021 / FR-015 — tell the device which transport the gateway
        # selected, so it knows whether to open a gRPC or WebRTC voice plane.
        if chosen_transport is not None:
            resp["chosen_transport"] = chosen_transport
        return resp

    # --- adoption (feature 011 US2) -------------------------------------
    def adopt(
        self,
        device_id: str,
        body: dict[str, Any],
    ) -> tuple[int, dict[str, Any]]:
        """Promote a pending device to adopted (R-12, T044).

        Returns ``(status, payload)`` — the HTTP wiring lifts this onto
        the aiohttp response.

        * 400 — missing/empty ``name``
        * 404 — no pending device with that id
        * 409 — ``already_adopted`` or ``device_limit_reached``
        * 200 — full DeviceState of the now-adopted device
        """
        name = (body.get("name") or "").strip()
        if not name:
            return 400, {"error": "bad_input", "message": "name is required"}
        config_overrides = body.get("config_overrides") or {}
        default_config = (
            SatelliteConfig(**self._cfg.default_config)
            if self._cfg.default_config
            else SatelliteConfig()
        )
        if config_overrides:
            default_config = default_config.merged(config_overrides)
        try:
            client = self._reg.adopt(
                device_id,
                name=name,
                default_config=default_config,
                device_limit=self._cfg.device_limit,
            )
        except KeyError:
            return 404, {"error": "unknown_device", "message": f"no pending device {device_id!r}"}
        except RuntimeError as e:
            msg = str(e)
            if msg.startswith("already_adopted"):
                return 409, {"error": "already_adopted", "message": msg}
            if msg.startswith("device_limit_reached"):
                # Extract current/limit if present.
                parts = msg.split()
                cur = lim = None
                for p in parts:
                    if p.startswith("current="):
                        cur = int(p.split("=", 1)[1])
                    elif p.startswith("limit="):
                        lim = int(p.split("=", 1)[1])
                return 409, {
                    "error": "device_limit_reached",
                    "message": msg,
                    "current": cur,
                    "limit": lim,
                }
            return 409, {"error": "internal_error", "message": msg}

        self._sink.emit(
            device_id, LogLevel.INFO, LogSource.SYSTEM,
            f"adopted as {name!r}",
            {"name": name},
        )
        self._broadcast(
            {
                "type": "state_update",
                "device_id": device_id,
                "adoption_state": "adopted",
                "name": name,
            }
        )
        # Push the now-running config to the device WS subscribers.
        self._broadcast(
            {
                "type": "config_changed",
                "device_id": device_id,
                "config": client.config.__dict__,
                "config_version": client.config_version,
            }
        )
        return 200, self.get_state(device_id)

    def heartbeat(self, device_id: str) -> bool:
        return self._reg.heartbeat(device_id) is not None

    def list_clients(self, *, state: str = "all") -> list[dict[str, Any]]:
        """Return the fleet as device summaries.

        ``state``:
          - ``"adopted"`` → only adopted clients
          - ``"pending"`` → only pending devices (feature 011 US2)
          - ``"all"`` (default) → both, with ``adoption_state`` per row
        """
        if state not in ("all", "adopted", "pending"):
            raise ValueError(f"unknown state filter: {state!r}")
        out: list[dict[str, Any]] = []
        if state in ("all", "adopted"):
            for c in self._reg.list_clients():
                sess = self._reg.session_for_device(c.device_id)
                out.append(
                    {
                        "device_id": c.device_id,
                        "name": c.name,
                        "device_type": c.device_type,
                        # Feature 017 — which transport carried this device's
                        # registration. Default "webrtc" preserves back-compat
                        # for every pre-017 device record.
                        "transport": getattr(c, "transport", "webrtc"),
                        "adoption_state": c.adoption_state.value,
                        "status": c.status.value,
                        "last_seen": c.last_seen,
                        "firmware_version": c.firmware_version,
                        "active_routing_mode": c.config.routing_mode,
                        "webrtc_state": sess.webrtc_state if sess else "none",
                        "ota_state": c.ota_state.value,
                    }
                )
        if state in ("all", "pending"):
            for p in self._reg.list_pending():
                out.append(
                    {
                        "device_id": p.device_id,
                        "name": None,
                        "device_type": p.device_type,
                        # Pending devices haven't completed registration so
                        # the transport is unknown until they do; tag as
                        # "webrtc" by default (matches pre-017 behaviour).
                        "transport": "webrtc",
                        "adoption_state": "pending",
                        "status": "connecting",
                        "last_seen": p.last_seen,
                        "firmware_version": p.firmware_version,
                        "active_routing_mode": None,
                        "webrtc_state": "none",
                        "ota_state": "idle",
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
            "name": c.name,
            "device_type": c.device_type,
            # Feature 017 — transport discriminator (additive).
            "transport": getattr(c, "transport", "webrtc"),
            "adoption_state": c.adoption_state.value,
            "status": c.status.value,
            "last_seen": c.last_seen,
            "firmware_version": c.firmware_version,
            "ip_address": c.ip_address,
            "config_version": c.config_version,
            "ota_state": c.ota_state.value,
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

    def post_config(
        self,
        device_id: str,
        overrides: dict[str, Any],
        *,
        if_match: int | None = None,
        queue: bool = False,
    ) -> tuple[int, dict[str, Any]]:
        """Update a device's running configuration (feature 011 US3, R-11).

        Optimistic concurrency: pass ``if_match=<config_version>``; if the
        server's current version differs, returns 409 ``config_conflict``.
        Omitting ``if_match`` is last-writer-wins; ``config_version``
        always increments.

        Offline-write policy (FR-016): if the device is offline AND
        ``queue=False`` (the default), refuse with 503 ``device_offline``.
        With ``queue=True``, enqueue the override and apply it on the
        next register/heartbeat — the change is acknowledged with 202 and
        an ``adoption_state`` of the queued snapshot.

        Returns ``(status, payload)`` — the aiohttp wiring lifts these
        onto the response.
        """
        c = self._reg.get_client(device_id)
        if c is None:
            return 404, {"error": "unknown_device", "message": f"no adopted device {device_id!r}"}

        # Optimistic concurrency: stale base → 409.
        if if_match is not None and if_match != c.config_version:
            return 409, {
                "error": "config_conflict",
                "message": (
                    f"stale If-Match: {if_match} vs current {c.config_version}"
                ),
                "current_version": c.config_version,
            }

        # Offline write policy.
        if c.status != ClientStatus.ONLINE:
            if not queue:
                return 503, {
                    "error": "device_offline",
                    "message": (
                        f"device {device_id!r} is offline; pass ?queue=true to "
                        "queue the change for the next register/heartbeat"
                    ),
                }
            # Stash on the Registry's queued-writes dict; flushed in heartbeat().
            self._reg.queue_config_write(device_id, overrides)
            return 202, {
                "queued": True,
                "device_id": device_id,
                "pending_overrides": overrides,
            }

        # Apply + persist.
        c.config = c.config.merged(overrides)
        c.config_version += 1
        c.config_updated_at = time.time()
        # Persistence hook on the registry fires on adopt/delete/post_config —
        # invoke it explicitly here so the version bump survives a restart.
        self._reg._persist()  # noqa: SLF001 - feature 011 R-11
        payload = c.config.__dict__ | {
            "config_version": c.config_version,
            "config_updated_at": c.config_updated_at,
        }
        self._broadcast(
            {
                "type": "config_changed",
                "device_id": device_id,
                "config": payload,
                "config_version": c.config_version,
            }
        )
        return 200, payload

    def config_schema(self, device_id: str | None = None) -> dict[str, Any]:
        """JSON Schema for the editable fields of ``SatelliteConfig``.

        Same shape for every device type (constitution II — no per-type
        branching at the dashboard/schema layer). The ``device_id``
        parameter is accepted for symmetry with the REST route but not
        consumed in v1.
        """
        cfg = SatelliteConfig()
        properties: dict[str, dict[str, Any]] = {}
        for field, value in cfg.__dict__.items():
            t = type(value).__name__
            mapping = {
                "str": "string",
                "int": "integer",
                "float": "number",
                "bool": "boolean",
                "NoneType": "string",  # echo_strategy default is None until set
            }
            json_type = mapping.get(t, "string")
            properties[field] = {"type": json_type, "default": value}
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "SatelliteConfig",
            "type": "object",
            "additionalProperties": True,
            "properties": properties,
        }

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

    # --- commands (feature 011 US5, R-14) -------------------------------

    def command(
        self, device_id: str, body: dict[str, Any] | str
    ) -> tuple[int, dict[str, Any]]:
        """Issue a command to a device.

        Accepts either a string (legacy shape: ``command("d1", "reboot")``)
        or a body dict (US5 shape: ``command("d1", {"command": "...", "args": {...}})``).
        Returns ``(status, payload)``:

        * 404 — unknown device
        * 400 — unknown verb (closed CommandVerb enum, R-14)
        * 503 — device offline
        * 202 — accepted; ``command`` frame broadcast to the device WS

        Destructive-confirmation is the CLIENT's job (FR-019) — the
        server accepts without prompting.
        """
        from ..models import CommandVerb  # noqa: WPS433 (lazy)

        # Backward-compat: legacy shape was a bare verb string.
        if isinstance(body, str):
            body = {"command": body}
        verb = body.get("command")
        args = body.get("args") or {}

        try:
            verb_enum = CommandVerb(verb)
        except (ValueError, TypeError):
            return 400, {
                "error": "bad_input",
                "message": f"unknown command verb: {verb!r}",
            }
        c = self._reg.get_client(device_id)
        if c is None:
            return 404, {"error": "unknown_device", "message": f"no adopted device {device_id!r}"}
        if c.status != ClientStatus.ONLINE:
            return 503, {"error": "device_offline", "message": f"{device_id!r} is offline"}
        # Broadcast the `command` frame on the device WS (control plane).
        self._broadcast(
            {
                "type": "command",
                "device_id": device_id,
                "command": verb_enum.value,
                "args": args,
            }
        )
        self._sink.emit(
            device_id, LogLevel.INFO, LogSource.SYSTEM,
            f"command: {verb_enum.value}",
            {"args": args},
        )
        return 202, {
            "accepted": True,
            "scheduled_at": time.time(),
            "command": verb_enum.value,
        }

    # --- OTA (feature 011 US4) ------------------------------------------

    def ota_check(self, device_id: str) -> tuple[int, dict[str, Any]]:
        """Returns ``(status, payload)``. 404 unknown, 409 browser
        (sanctioned divergence), 200 with update flags otherwise.
        """
        c = self._reg.get_client(device_id)
        if c is None:
            return 404, {"error": "unknown_device", "message": f"no adopted device {device_id!r}"}
        return self._ota.check(c)

    def ota_apply(self, device_id: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        c = self._reg.get_client(device_id)
        if c is None:
            return 404, {"error": "unknown_device", "message": f"no adopted device {device_id!r}"}
        if c.status != ClientStatus.ONLINE:
            return 503, {"error": "device_offline", "message": f"{device_id!r} is offline"}
        version = body.get("version")
        if not version:
            return 400, {"error": "bad_input", "message": "version is required"}
        return self._ota.apply(c, version=version, url=body.get("url"))

    def ota_status_report(
        self, device_id: str, body: dict[str, Any]
    ) -> tuple[int, dict[str, Any]]:
        c = self._reg.get_client(device_id)
        if c is None:
            return 404, {"error": "unknown_device", "message": f"no adopted device {device_id!r}"}
        return self._ota.status_report(c, body)

    def ota_manifest(self, device_id: str) -> tuple[int, dict[str, Any]]:
        c = self._reg.get_client(device_id)
        if c is None:
            return 404, {"error": "unknown_device", "message": f"no adopted device {device_id!r}"}
        return self._ota.manifest_response(c)

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
        state = req.query.get("state", "all")
        try:
            return web.json_response(service.list_clients(state=state))
        except ValueError as e:
            return web.json_response({"error": "bad_input", "message": str(e)}, status=400)

    async def _state(req):
        st = service.get_state(req.match_info["id"])
        return web.json_response(st) if st else web.Response(status=404)

    async def _delete(req):
        ok = service.delete(req.match_info["id"])
        return web.Response(status=204 if ok else 404)

    async def _adopt(req):
        status, payload = service.adopt(req.match_info["id"], await req.json())
        return web.json_response(payload, status=status)

    async def _get_cfg(req):
        c = service.get_config(req.match_info["id"])
        return web.json_response(c) if c else web.Response(status=404)

    async def _post_cfg(req):
        # Feature 011 US3: optional If-Match header (optimistic
        # concurrency) + ?queue=true (offline-write opt-in).
        if_match_h = req.headers.get("If-Match")
        if_match: int | None = None
        if if_match_h is not None:
            try:
                if_match = int(if_match_h)
            except ValueError:
                return web.json_response(
                    {"error": "bad_input", "message": "If-Match must be an integer"},
                    status=400,
                )
        queue = req.query.get("queue") in ("1", "true", "yes")
        status, payload = service.post_config(
            req.match_info["id"], await req.json(), if_match=if_match, queue=queue
        )
        return web.json_response(payload, status=status)

    async def _config_schema(req):
        return web.json_response(service.config_schema(req.match_info["id"]))

    # --- OTA (US4) ---------------------------------------------------
    async def _ota_check(req):
        status, payload = service.ota_check(req.match_info["id"])
        return web.json_response(payload, status=status)

    async def _ota_apply(req):
        status, payload = service.ota_apply(req.match_info["id"], await req.json())
        return web.json_response(payload, status=status)

    async def _ota_status(req):
        status, payload = service.ota_status_report(req.match_info["id"], await req.json())
        # 204 has no body per HTTP spec.
        if status == 204:
            return web.Response(status=204)
        return web.json_response(payload, status=status)

    async def _ota_manifest(req):
        status, payload = service.ota_manifest(req.match_info["id"])
        return web.json_response(payload, status=status)

    async def _command(req):
        status, payload = service.command(req.match_info["id"], await req.json())
        return web.json_response(payload, status=status)

    async def _logs(req):
        # Feature 011 T027: follow=true switches to SSE live tail.
        if req.query.get("follow") in ("1", "true", "yes"):
            from .log_sse import sse_logs  # lazy
            resp = web.StreamResponse(
                status=200,
                reason="OK",
                headers={
                    "Content-Type": "text/event-stream",
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                },
            )
            await resp.prepare(req)
            kwargs = {
                k: req.query.get(k)
                for k in ("device_id", "level", "source")
                if req.query.get(k)
            }
            since = req.query.get("since")
            if since:
                try:
                    kwargs["since"] = float(since)
                except ValueError:
                    pass
            # If the path included a device id, prefer it.
            if "id" in req.match_info:
                kwargs["device_id"] = req.match_info["id"]
            async for frame in sse_logs(service._sink, **kwargs):
                await resp.write(frame.encode("utf-8"))
            return resp
        # One-shot snapshot. Only forward query params LogSink.query knows
        # about — passing an unknown kwarg (e.g. `?follow=` left from the
        # SSE call shape) would 500 the route. `tail` and `since` get
        # coerced to numeric.
        filters: dict[str, Any] = {}
        for key in ("device_id", "level", "source"):
            v = req.query.get(key)
            if v:
                filters[key] = v
        since_raw = req.query.get("since")
        if since_raw:
            try:
                filters["since"] = float(since_raw)
            except ValueError:
                pass
        tail_raw = req.query.get("tail")
        if tail_raw:
            try:
                filters["tail"] = max(0, int(tail_raw))
            except ValueError:
                pass
        if "id" in req.match_info:
            filters["device_id"] = req.match_info["id"]
        return web.json_response(service.query_logs(**filters))

    async def _ws(req):
        """Always-on control-plane WebSocket (constitution III): register,
        heartbeat, and server→client fan-out (state/config/barge-in). Separate
        from the voice PeerConnection; survives with no active call. Reuses
        ``ManagementService`` (constitution IV) — no new state."""
        import asyncio  # noqa: WPS433
        import json  # noqa: WPS433

        ws = web.WebSocketResponse(heartbeat=55.0)
        await ws.prepare(req)
        loop = asyncio.get_event_loop()

        async def _safe_send(msg: dict) -> None:
            try:
                if not ws.closed:
                    await ws.send_json(msg)
            except Exception:  # noqa: BLE001 - dead socket must not crash fan-out
                pass

        def _push(msg: dict) -> None:
            # _broadcast invokes this synchronously; hop back onto the loop.
            if not ws.closed:
                asyncio.run_coroutine_threadsafe(_safe_send(msg), loop)

        unsubscribe = service.subscribe_ws(_push)
        try:
            async for raw in ws:
                if raw.type != web.WSMsgType.TEXT:
                    continue
                try:
                    msg = json.loads(raw.data)
                except Exception:  # noqa: BLE001 - ignore malformed frames
                    continue
                kind = msg.get("type")
                if kind == "register":
                    try:
                        await ws.send_json(
                            {"type": "registered", **service.register(msg)}
                        )
                    except Exception:  # noqa: BLE001
                        pass
                elif kind == "heartbeat":
                    dev = msg.get("device_id")
                    if dev:
                        service.heartbeat(dev)
                # other client message types are non-durable / ignored here
        finally:
            unsubscribe()
            if not ws.closed:
                await ws.close()
        return ws

    app.add_routes(
        [
            web.get("/satellite/ws", _ws),
            web.post("/satellite/register", _register),
            web.get("/satellite/list", _list),
            web.get("/satellite/{id}/state", _state),
            web.delete("/satellite/{id}", _delete),
            web.post("/satellite/{id}/adopt", _adopt),
            web.get("/satellite/{id}/config", _get_cfg),
            web.post("/satellite/{id}/config", _post_cfg),
            web.get("/satellite/{id}/config/schema", _config_schema),
            web.post("/satellite/{id}/ota/check", _ota_check),
            web.post("/satellite/{id}/ota/apply", _ota_apply),
            web.post("/satellite/{id}/ota/status", _ota_status),
            web.get("/satellite/{id}/ota/manifest", _ota_manifest),
            web.post("/satellite/{id}/command", _command),
            web.get("/satellite/{id}/logs", _logs),
            web.get("/satellite/logs", _logs),
        ]
    )
    return app
