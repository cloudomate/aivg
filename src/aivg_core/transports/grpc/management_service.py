"""``GrpcManagementService`` — the management/control plane over gRPC
(feature 021, Phase 2 / US2).

Mirrors the always-on ``/satellite/ws`` WebSocket handler
(``management/service.py``) onto a long-lived gRPC ``Management`` service,
kept SEPARATE from the per-session ``Audio.Stream`` (Constitution III intent:
durable control is never multiplexed into the per-session audio stream). It
REUSES the existing :class:`ManagementService` verbatim — register, heartbeat,
and the ``_broadcast`` fan-out — so the observable control semantics are
identical to the WebSocket (FR-014). No new control logic.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

import grpc

from ...logsink import LogSink
from ...models import LogLevel, LogSource
from ._generated import management_pb2, management_pb2_grpc

if TYPE_CHECKING:
    from ...management.service import ManagementService
    from ...registry import Registry

_LOG = logging.getLogger(__name__)


def _to_control_message(msg: dict):
    """Convert a management ``_broadcast`` dict into a ``ControlMessage``.

    The dict shapes are exactly those the WebSocket fan-out emits (FR-014):
    ``state_update`` / ``config_changed`` / ``command``. Anything else
    (e.g. OTA frames, not part of the Phase-2 contract) returns ``None`` and
    is skipped.
    """
    t = msg.get("type")
    if t == "state_update":
        return management_pb2.ControlMessage(
            state_update=management_pb2.DeviceState(
                device_id=str(msg.get("device_id", "")),
                state=str(msg.get("adoption_state", "")),
            )
        )
    if t == "config_changed":
        cfg = msg.get("config")
        return management_pb2.ControlMessage(
            config_changed=management_pb2.ConfigChanged(
                device_id=str(msg.get("device_id", "")),
                config_json=json.dumps(cfg) if cfg is not None else "",
                config_version=str(msg.get("config_version", "")),
            )
        )
    if t == "command":
        return management_pb2.ControlMessage(
            command=management_pb2.Command(
                device_id=str(msg.get("device_id", "")),
                command=str(msg.get("command", "")),
                args={str(k): str(v) for k, v in (msg.get("args") or {}).items()},
            )
        )
    return None


class GrpcManagementService(management_pb2_grpc.ManagementServicer):
    """gRPC servicer bridging onto the existing :class:`ManagementService`."""

    def __init__(
        self,
        *,
        service: "ManagementService",
        registry: "Registry",
        sink: LogSink,
    ) -> None:
        self._svc = service
        self._reg = registry
        self._sink = sink

    async def Register(self, request, context):  # noqa: N802 - gRPC name
        body = {
            "device_id": request.device_id,
            "device_type": request.device_type or "browser",
        }
        caps = list(request.transport_capabilities)
        if caps:
            body["transport_capabilities"] = caps
        resp = self._svc.register(body)
        if "error" in resp:
            await context.abort(
                grpc.StatusCode.FAILED_PRECONDITION,
                resp.get("detail", resp["error"]),
            )
            return  # pragma: no cover - abort raises
        client = self._reg.get_client(request.device_id)
        return management_pb2.RegisterReply(
            adoption_state=str(resp.get("adoption_state", "")),
            chosen_transport=str(resp.get("chosen_transport", "")),
            config_version=str(getattr(client, "config_version", "") if client else ""),
        )

    async def Control(self, request_iterator, context):  # noqa: N802 - gRPC name
        """Long-lived bidi control channel — the gRPC equivalent of the
        ``/satellite/ws`` WebSocket. Device pushes heartbeat/state/turn up;
        the gateway pushes config_changed/command/state_update down via the
        SAME ``_broadcast`` fan-out the WebSocket uses."""
        loop = asyncio.get_event_loop()
        out: asyncio.Queue = asyncio.Queue()

        def _push(msg: dict) -> None:
            cm = _to_control_message(msg)
            if cm is not None:
                # _broadcast may fire from another thread (voice-plane UI
                # fan-out); hop back onto this loop, mirroring the WS handler.
                loop.call_soon_threadsafe(out.put_nowait, cm)

        unsubscribe = self._svc.subscribe_ws(_push)

        async def _read_inbound() -> None:
            try:
                async for upd in request_iterator:
                    body = upd.WhichOneof("body")
                    if body == "heartbeat":
                        if upd.heartbeat.device_id:
                            self._svc.heartbeat(upd.heartbeat.device_id)
                        out.put_nowait(
                            management_pb2.ControlMessage(
                                ack=management_pb2.StateAck(ok=True)
                            )
                        )
                    elif body == "state":
                        # Device-reported lifecycle state; acked (no durable
                        # change is owned here — same as the WS handler).
                        out.put_nowait(
                            management_pb2.ControlMessage(
                                ack=management_pb2.StateAck(ok=True)
                            )
                        )
                    elif body == "turn":
                        # T031 / FR-012 — explicit, precise turn/session-start
                        # signal. The session_id ties to the Audio.Stream
                        # (FR-006). Recorded; acked.
                        te = upd.turn
                        self._sink.emit(
                            te.session_id or "?", LogLevel.INFO, LogSource.SYSTEM,
                            "grpc: turn event",
                            {"kind": te.kind, "session_id": te.session_id},
                        )
                        out.put_nowait(
                            management_pb2.ControlMessage(
                                ack=management_pb2.StateAck(ok=True)
                            )
                        )
            except (asyncio.CancelledError, grpc.aio.AioRpcError):
                pass
            except Exception:  # noqa: BLE001 - reader must not crash the call
                _LOG.exception("grpc: management inbound reader error")
            finally:
                out.put_nowait(None)  # signal the downstream loop to stop

        reader = asyncio.create_task(_read_inbound())
        try:
            while True:
                cm = await out.get()
                if cm is None:
                    break
                yield cm
        finally:
            unsubscribe()
            reader.cancel()
