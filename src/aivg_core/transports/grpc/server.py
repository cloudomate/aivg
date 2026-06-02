"""``GrpcAudioTransport`` — the ``grpc.aio`` server + ``Audio`` servicer
(feature 021). Lifecycle owner the gateway adapter starts/stops alongside
its aiohttp sites, mirroring ``transports.esphome.EsphomeTransport``.

Construction is side-effect-free; :meth:`start` binds the port and begins
serving; :meth:`stop` drains gracefully and is idempotent.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

import grpc

from ...logsink import LogSink
from ._generated import audio_pb2, audio_pb2_grpc
from .stream_handler import serve_stream

if TYPE_CHECKING:
    from ...platforms.base import AgentPlatform
    from ...registry import Registry

_LOG = logging.getLogger(__name__)


class _AudioServicer(audio_pb2_grpc.AudioServicer):
    """Thin servicer — every ``Audio.Stream`` call delegates to
    :func:`stream_handler.serve_stream`."""

    def __init__(self, transport: "GrpcAudioTransport") -> None:
        self._t = transport

    async def Stream(self, request_iterator, context):  # noqa: N802 - gRPC name
        async for frame in serve_stream(
            request_iterator,
            context,
            platform=self._t._platform,
            sink=self._t._sink,
            downstream_codec_name=self._t._downstream_codec,
            ui_broadcast=self._t._ui_broadcast,
        ):
            yield frame


class GrpcAudioTransport:
    """gRPC audio-plane server. One instance per gateway."""

    def __init__(
        self,
        *,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: LogSink,
        host: str = "0.0.0.0",
        port: int = 8645,
        tls: str = "insecure",
        downstream_codec: str = "pcm",
        api_key_file: str = "~/.aivg/devices/keys.json",
        ui_broadcast: Optional[Callable[[dict], None]] = None,
    ) -> None:
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._host = host
        self._port = port
        self._tls = tls
        self._downstream_codec = downstream_codec
        self._api_key_file = api_key_file
        self._ui_broadcast = ui_broadcast
        self._server: Optional[grpc.aio.Server] = None

    async def start(self) -> None:
        if self._server is not None:
            return  # already started
        server = grpc.aio.server()
        audio_pb2_grpc.add_AudioServicer_to_server(_AudioServicer(self), server)
        self._enable_reflection(server)

        addr = f"{self._host}:{self._port}"
        if self._tls == "mtls":
            creds = self._mtls_credentials()
            server.add_secure_port(addr, creds)
        else:
            server.add_insecure_port(addr)

        await server.start()
        self._server = server
        _LOG.info("grpc: Audio transport listening on %s (tls=%s)", addr, self._tls)

    async def stop(self) -> None:
        if self._server is None:
            return
        await self._server.stop(grace=1.0)
        self._server = None

    # --- helpers --------------------------------------------------------

    def _enable_reflection(self, server: "grpc.aio.Server") -> None:
        """Enable server reflection so a stuck link is inspectable with
        ``grpcurl`` (FR-013/FR-023). Best-effort: skipped if grpcio-reflection
        isn't installed."""
        try:
            from grpc_reflection.v1alpha import reflection  # noqa: WPS433

            names = (
                audio_pb2.DESCRIPTOR.services_by_name["Audio"].full_name,
                reflection.SERVICE_NAME,
            )
            reflection.enable_server_reflection(names, server)
        except Exception:  # noqa: BLE001
            _LOG.debug("grpc: server reflection unavailable (grpcio-reflection missing)")

    def _mtls_credentials(self) -> "grpc.ServerCredentials":
        """Build mutual-TLS server credentials from the device keystore dir.

        FR-022: fleet deployments authenticate both ends. We require the cert
        material to be present and NEVER silently downgrade to insecure — an
        operator who asked for mtls gets a hard error if certs are missing.
        Expected files alongside ``api_key_file``: ``ca.pem``,
        ``server.pem``, ``server.key``.
        """
        base = Path(self._api_key_file).expanduser().parent
        ca = base / "ca.pem"
        cert = base / "server.pem"
        key = base / "server.key"
        missing = [str(p) for p in (ca, cert, key) if not p.exists()]
        if missing:
            raise RuntimeError(
                "transports.grpc.tls=mtls but TLS material is missing: "
                + ", ".join(missing)
                + " — refusing to downgrade to insecure (FR-022)."
            )
        return grpc.ssl_server_credentials(
            [(key.read_bytes(), cert.read_bytes())],
            root_certificates=ca.read_bytes(),
            require_client_auth=True,
        )
