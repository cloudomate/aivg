"""Feature 021 — contract test: the checked-in generated stubs match the
canonical proto shape, and server reflection is enabled (FR-013/R-2/R-8).

Structural assertions (not a byte regen-diff) so the test is robust across
grpcio/protoc versions while still catching contract drift in messages,
oneofs, enums, services, and method streaming kinds.
"""

from __future__ import annotations

import socket

import pytest

pytest.importorskip("grpc")
import grpc  # noqa: E402

from aivg_core.logsink import LogSink  # noqa: E402
from aivg_core.registry import Registry  # noqa: E402
from aivg_core.transports.grpc import GrpcAudioTransport  # noqa: E402
from aivg_core.transports.grpc._generated import (  # noqa: E402
    audio_pb2,
    audio_pb2_grpc,
    management_pb2,
    management_pb2_grpc,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_audio_messages_and_oneofs():
    # Feature 025 adds the additive Opus mic arm `opus` (field 4).
    client_oneof = {f.name for f in audio_pb2.ClientFrame.DESCRIPTOR.oneofs_by_name["body"].fields}
    assert client_oneof == {"session", "pcm", "event", "opus"}
    assert audio_pb2.ClientFrame.DESCRIPTOR.fields_by_name["opus"].number == 4
    assert {f.name for f in audio_pb2.OpusChunk.DESCRIPTOR.fields} == {"payload", "ts_ns"}
    assert "upstream_codec_pref" in audio_pb2.SessionHeader.DESCRIPTOR.fields_by_name
    server_oneof = {f.name for f in audio_pb2.ServerFrame.DESCRIPTOR.oneofs_by_name["body"].fields}
    assert server_oneof == {"audio", "event", "transcript"}


def test_codec_and_event_enums():
    for name in ("CODEC_UNSPECIFIED", "CODEC_OPUS", "CODEC_PCM_S16LE_16K"):
        audio_pb2.Codec.Value(name)  # raises if missing
    for name in ("WAKE_FIRED", "END_OF_UTTERANCE", "BARGE_IN_START"):
        audio_pb2.ClientEvent.Kind.Value(name)
    for name in ("SPEAKING_STARTED", "SPEAKING_ENDED", "VAD_DETECTED"):
        audio_pb2.ServerEvent.Kind.Value(name)


def test_audio_stream_is_bidi():
    svc = audio_pb2.DESCRIPTOR.services_by_name["Audio"]
    method = svc.methods_by_name["Stream"]
    assert method.client_streaming and method.server_streaming, "Audio.Stream must be bidi"
    assert hasattr(audio_pb2_grpc, "AudioServicer")
    assert hasattr(audio_pb2_grpc, "AudioStub")


def test_management_service_shape():
    svc = management_pb2.DESCRIPTOR.services_by_name["Management"]
    assert "Register" in svc.methods_by_name
    assert "Control" in svc.methods_by_name
    ctrl = svc.methods_by_name["Control"]
    assert ctrl.client_streaming and ctrl.server_streaming, "Management.Control must be bidi"
    # Control-plane semantics equal the WebSocket message set (FR-014).
    control_oneof = {
        f.name for f in management_pb2.ControlMessage.DESCRIPTOR.oneofs_by_name["body"].fields
    }
    assert {"config_changed", "command", "state_update"} <= control_oneof
    assert hasattr(management_pb2_grpc, "ManagementServicer")


def test_package_is_v1():
    assert audio_pb2.DESCRIPTOR.package == "aivg.satellite.v1"
    assert management_pb2.DESCRIPTOR.package == "aivg.satellite.v1"


@pytest.mark.asyncio
async def test_server_reflection_lists_audio():
    """grpcurl-style reflection must expose Audio (FR-013/FR-023)."""
    reflection_pb2 = pytest.importorskip("grpc_reflection.v1alpha.reflection_pb2")
    from grpc_reflection.v1alpha import reflection_pb2_grpc

    registry = Registry()
    sink = LogSink()
    port = _free_port()
    transport = GrpcAudioTransport(
        registry=registry, platform=None, sink=sink, host="127.0.0.1", port=port
    )
    await transport.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            stub = reflection_pb2_grpc.ServerReflectionStub(channel)

            async def _req():
                yield reflection_pb2.ServerReflectionRequest(list_services="")

            services = []
            async for resp in stub.ServerReflectionInfo(_req()):
                services = [s.name for s in resp.list_services_response.service]
                break
        assert "aivg.satellite.v1.Audio" in services
    finally:
        await transport.stop()
