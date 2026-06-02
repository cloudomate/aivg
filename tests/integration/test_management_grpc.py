"""Feature 021 — US2 binding test: the management/control plane works fully
over gRPC, with NO ``/satellite/ws`` WebSocket in the picture (the aiohttp
management app is never built here).

Covers acceptance scenarios 1–3: register/adopt over gRPC, state/control
fan-out over the bidi ``Control`` stream, and operator commands reaching the
device — all reusing the existing ``ManagementService`` (FR-011/FR-014).
"""

from __future__ import annotations

import asyncio
import socket

import pytest

pytest.importorskip("grpc")
import grpc  # noqa: E402

from aivg_core.config import SatelliteAdapterConfig  # noqa: E402
from aivg_core.logsink import LogSink  # noqa: E402
from aivg_core.management.service import ManagementService  # noqa: E402
from aivg_core.registry import Registry  # noqa: E402
from aivg_core.transports.grpc import GrpcAudioTransport  # noqa: E402
from aivg_core.transports.grpc._generated import (  # noqa: E402
    management_pb2,
    management_pb2_grpc,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_transport(tmp_path):
    registry = Registry()
    sink = LogSink(gateway_log=tmp_path / "g.log")
    cfg = SatelliteAdapterConfig(enabled=True)  # auto_adopt_on_register defaults True
    service = ManagementService(registry, sink, cfg)
    port = _free_port()
    transport = GrpcAudioTransport(
        registry=registry, platform=None, sink=sink, host="127.0.0.1", port=port,
        management_service=service, mount_management=True,
    )
    return transport, service, registry, port


@pytest.mark.asyncio
async def test_register_and_adopt_over_grpc(tmp_path):
    """Acceptance 1: a satellite registers + is adopted entirely over gRPC."""
    transport, service, registry, port = _make_transport(tmp_path)
    await transport.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
            stub = management_pb2_grpc.ManagementStub(ch)
            reply = await stub.Register(
                management_pb2.RegisterRequest(
                    device_id="rpi-1", device_type="rpi",
                    transport_capabilities=["grpc", "webrtc"],
                )
            )
        assert reply.adoption_state == "adopted"
        assert reply.chosen_transport == "grpc"      # negotiated (US3)
        assert registry.get_client("rpi-1") is not None
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_control_stream_heartbeat_and_command_fanout(tmp_path):
    """Acceptance 2/3: heartbeat up gets acked; an operator command broadcast
    on the gateway reaches the device down the same Control stream — the gRPC
    equivalent of the /satellite/ws fan-out, with no WebSocket."""
    transport, service, registry, port = _make_transport(tmp_path)
    await transport.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
            stub = management_pb2_grpc.ManagementStub(ch)
            call = stub.Control()  # manual bidi: we write/read explicitly

            # Heartbeat up -> ack down.
            await call.write(
                management_pb2.StateUpdate(
                    heartbeat=management_pb2.Heartbeat(device_id="rpi-1")
                )
            )
            ack = await call.read()
            assert ack.WhichOneof("body") == "ack" and ack.ack.ok

            # Operator command broadcast on the gateway -> Command down the
            # Control stream (FR-014: same _broadcast fan-out as the WS).
            service._broadcast({
                "type": "command", "device_id": "rpi-1",
                "command": "restart", "args": {"reason": "test"},
            })
            msg = await call.read()
            assert msg.WhichOneof("body") == "command"
            assert msg.command.command == "restart"
            assert msg.command.args["reason"] == "test"

            # A config_changed broadcast maps too.
            service._broadcast({
                "type": "config_changed", "device_id": "rpi-1",
                "config": {"wake_word": "hey"}, "config_version": 3,
            })
            msg2 = await call.read()
            assert msg2.WhichOneof("body") == "config_changed"
            assert msg2.config_changed.config_version == "3"

            await call.done_writing()
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_reflection_lists_management_when_mounted(tmp_path):
    """T033/FR-013 — when mounted, Management is grpcurl-introspectable."""
    reflection_pb2 = pytest.importorskip("grpc_reflection.v1alpha.reflection_pb2")
    from grpc_reflection.v1alpha import reflection_pb2_grpc

    transport, service, registry, port = _make_transport(tmp_path)
    await transport.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
            stub = reflection_pb2_grpc.ServerReflectionStub(ch)

            async def _req():
                yield reflection_pb2.ServerReflectionRequest(list_services="")

            services = []
            async for resp in stub.ServerReflectionInfo(_req()):
                services = [s.name for s in resp.list_services_response.service]
                break
        assert "aivg.satellite.v1.Management" in services
        assert "aivg.satellite.v1.Audio" in services
    finally:
        await transport.stop()


@pytest.mark.asyncio
async def test_management_not_mounted_when_flag_off(tmp_path):
    """The Management service is only served when mount_management=True; with
    it off, the audio plane still works but Management RPCs are unimplemented."""
    registry = Registry()
    sink = LogSink(gateway_log=tmp_path / "g.log")
    port = _free_port()
    transport = GrpcAudioTransport(
        registry=registry, platform=None, sink=sink, host="127.0.0.1", port=port,
        # mount_management defaults False
    )
    await transport.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
            stub = management_pb2_grpc.ManagementStub(ch)
            with pytest.raises(grpc.aio.AioRpcError) as ei:
                await stub.Register(management_pb2.RegisterRequest(device_id="x", device_type="rpi"))
            assert ei.value.code() == grpc.StatusCode.UNIMPLEMENTED
    finally:
        await transport.stop()
