# Data Model — ESPHome Voice Assistant transport (Phase 1)

**Feature**: 017-esphome-voice-transport · **Date**: 2026-05-21

This document defines every type signature the feature introduces or
modifies. It is the binding reference for the contract tests in
[contracts/esphome-transport.md](./contracts/esphome-transport.md).

## 1. `EsphomeTransport` — the listener

Lives in `src/aivg_core/transports/esphome/__init__.py`. The single
public symbol the rest of `aivg_core` knows about.

```python
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING, Awaitable, Callable

if TYPE_CHECKING:
    from ..platforms.base import AgentPlatform
    from ..logsink import LogSink
    from ..registry import Registry


class EsphomeTransport:
    """ESPHome native API server (TCP, default port 6053).

    One instance per gateway. Spawns one ``asyncio.Task`` per
    accepted device connection. Routes per-device audio through
    the shared :class:`aivg_core.webrtc.session.Session` via an
    :class:`EsphomeMediaTransport` adapter.

    Construction is side-effect-free; :meth:`start` binds the
    listener socket. :meth:`stop` is idempotent.
    """

    def __init__(
        self,
        *,
        registry: "Registry",
        platform: "AgentPlatform",
        sink: "LogSink",
        host: str = "0.0.0.0",
        port: int = 6053,
        api_key_resolver: Callable[[str], Awaitable[str | None]] | None = None,
        ui_broadcast: Callable[[dict], None] | None = None,
    ) -> None:
        self._registry = registry
        self._platform = platform
        self._sink = sink
        self._host = host
        self._port = port
        self._api_key_resolver = api_key_resolver
        self._ui_broadcast = ui_broadcast
        self._server: asyncio.base_events.Server | None = None
        self._tasks: dict[str, asyncio.Task] = {}  # device_id → connection task

    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def _on_connect(self, reader, writer) -> None: ...
```

**Construction contract**:

- `platform: AgentPlatform` — the active plugin (resolved via
  `PluginRegistry.load` in `adapter.py`). Same instance the WebRTC
  path consumes; constitutional Principle IV preserved.
- `registry: Registry` — the existing in-memory device registry;
  ESPHome devices land here with `transport="esphome_api"`.
- `sink: LogSink` — existing JSON LogSink; ESPHome events flow with
  `source: "esphome"`.
- `api_key_resolver(device_id) → Optional[str]` — looks up the
  per-device API key from `~/.aivg/devices/keys.json`. `None` means
  the device is not registered → reject the auth.
- `ui_broadcast` — same fan-out hook used by the WebRTC path (FR-014).

## 2. `EsphomeConnection` — per-device task body

Lives in `src/aivg_core/transports/esphome/connection.py`. One
instance per accepted TCP connection, owned by one `asyncio.Task`
(R-2).

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ConnState(Enum):
    HANDSHAKING = "handshaking"      # before HelloRequest
    AUTHING = "authing"              # Hello done, Connect/Auth pending
    READY = "ready"                  # adopted; no active voice session
    VOICE_ACTIVE = "voice_active"    # one turn in flight
    CLOSING = "closing"              # graceful teardown
    CLOSED = "closed"                # terminal


@dataclass
class EsphomeConnection:
    """One connected ESPHome device. Owns:

    - the TCP reader/writer pair,
    - the protobuf framing state,
    - the per-device auth + adoption state,
    - at most one in-flight :class:`Session` (single-turn-per-device).
    """
    reader: "asyncio.StreamReader"
    writer: "asyncio.StreamWriter"
    transport_owner: "EsphomeTransport"
    state: ConnState = ConnState.HANDSHAKING
    device_id: Optional[str] = None             # set post-Hello
    device_info: dict = field(default_factory=dict)  # name, fw, board
    _media_adapter: Optional["EsphomeMediaTransport"] = None
    _session: Optional["Session"] = None        # active per-turn

    async def run(self) -> None:
        """Main co-routine: handshake → auth → voice loop → close."""

    # --- Internal phases (one method per state transition) ---
    async def _handshake(self) -> None: ...
    async def _authenticate(self) -> None: ...
    async def _serve_voice(self) -> None: ...
    async def _close(self) -> None: ...
```

**State machine** (the per-device task progresses through this):

```
   start
     │
     ▼
   HANDSHAKING ── HelloRequest received ──▶ AUTHING
     │ (timeout 5s)                          │
     ▼                                       │ AuthenticationRequest OK
   CLOSED                                    ▼
                                           READY ◀──── VoiceAssistantRunEnd ────┐
                                             │                                  │
                                             │ VoiceAssistantRunStart           │
                                             ▼                                  │
                                           VOICE_ACTIVE ──────────────────────┘
                                             │
                                             │ disconnect / error
                                             ▼
                                           CLOSING ──▶ CLOSED
```

**Single-turn invariant**: at any moment, an `EsphomeConnection`
holds at most one `Session`. The device's protocol is naturally
one-turn-at-a-time; we do not multiplex.

## 3. `EsphomeMediaTransport` — the seam to `webrtc.Session`

Lives in `src/aivg_core/transports/esphome/media_adapter.py`. Adapts
the ESPHome connection's PCM byte streams to the existing
`MediaTransport` Protocol (R-3).

```python
import asyncio
from typing import Optional


class EsphomeMediaTransport:
    """Satisfies :class:`aivg_core.webrtc.session.MediaTransport`.

    Backed by two asyncio.Queues: ``_in`` carries inbound PCM
    frames (decoded + resampled from ESPHome ``VoiceAssistantAudio``
    payloads); ``_out`` carries outbound audio to send to the device.
    """

    def __init__(self, connection: "EsphomeConnection") -> None:
        self._conn = connection
        self._in: asyncio.Queue[Optional[bytes]] = asyncio.Queue()
        self._out: asyncio.Queue[bytes] = asyncio.Queue()
        self._state = "connected"
        self._closed = False

    # --- MediaTransport Protocol surface (verbatim from webrtc/session.py) ---

    async def receive(self) -> Optional[bytes]:
        """Block until the next PCM16 mono @ 48 kHz frame from the
        device. Returns ``None`` when the connection closes. The
        bytes are resampled internally from ESPHome's 16 kHz wire."""
        return await self._in.get()

    async def send_audio(self, pcm: bytes) -> None:
        """Send one outbound PCM chunk. Internally re-frames into
        ESPHome's ``VoiceAssistantAudio`` messages at 16 kHz mono."""
        await self._out.put(pcm)

    async def stop_playback(self) -> None:
        """Drop any queued outbound audio (barge-in). Drains
        ``_out`` without sending."""
        try:
            while True:
                self._out.get_nowait()
        except asyncio.QueueEmpty:
            pass

    @property
    def connection_state(self) -> str:
        return self._state

    async def close(self) -> None:
        if self._closed:
            return  # idempotent (C7)
        self._closed = True
        self._state = "closed"
        # Wake up any pending receive() so Session.run() can exit.
        self._in.put_nowait(None)

    # --- ESPHome-side push hooks (called by EsphomeConnection) ---

    def push_inbound(self, esphome_audio_payload: bytes) -> None:
        """Called when ``VoiceAssistantAudio`` arrives from the device.
        Resamples 16k → 48k and frames to 20 ms (1920 byte) chunks
        matching the existing webrtc pipeline."""
        # Implementation: stdlib audioop.ratecv + framing.

    def push_eof(self) -> None:
        """Called on connection drop. ``_in`` gets a ``None`` so any
        in-flight ``receive()`` returns cleanly."""
        self._in.put_nowait(None)

    async def drain_outbound(self) -> bytes | None:
        """Called by :class:`EsphomeConnection`'s outbound writer
        loop to pull the next PCM chunk to wrap in ``VoiceAssistantAudio``.
        Returns ``None`` to signal end-of-stream."""
        return await self._out.get()
```

**Resampling contract**: ESPHome's wire format is 16 kHz mono PCM16
(matches Home Assistant's pipeline default). The existing
`webrtc.Session` calls `platform.transcribe(audio, sample_rate=48000)`
post-feature-015. To avoid touching `Session`, the adapter resamples
16 kHz inbound → 48 kHz at `push_inbound`, and 48 kHz outbound → 16
kHz at the outbound-writer side. Implementation uses
`audioop.ratecv` (stdlib, no new dep).

## 4. Wire-shape contracts (ESPHome subset)

The feature implements the **subset** of the ESPHome native API
needed for the voice-satellite role. Each message type below maps to
an `aioesphomeapi.api_pb2` class — we never define proto types
locally.

| Wire message (proto) | Direction | Handled in | Notes |
|---|---|---|---|
| `HelloRequest` / `HelloResponse` | both | `connection._handshake` | Initial protocol-version exchange; we advertise the highest API version `aioesphomeapi` reports. |
| `ConnectRequest` / `ConnectResponse` | both | `connection._authenticate` | Password field carries the per-device API key. |
| `AuthenticationRequest` / `AuthenticationResponse` | both | `connection._authenticate` | If the device uses the older auth flow; we accept either. |
| `PingRequest` / `PingResponse` | both | `connection.run` keepalive | Reply within 30 s or the device drops us. |
| `DisconnectRequest` / `DisconnectResponse` | both | `connection._close` | Graceful teardown. |
| `DeviceInfoRequest` / `DeviceInfoResponse` | both | `connection._handshake` | We report `name="aivg-gateway"`, friendly name, no entities. |
| `ListEntitiesRequest` / `ListEntitiesDoneResponse` | both | `connection._handshake` | We expose **no** entities (no sensors, no buttons) — just `ListEntitiesDoneResponse`. |
| `SubscribeStatesRequest` | inbound | (ignored — no entities) | |
| `VoiceAssistantConfigurationRequest` / `Response` | both | `voice_protocol.handle_config` | Advertises supported sample rates (16 kHz), wake-word availability (none server-side), audio codec (raw PCM). |
| `VoiceAssistantRequest` | inbound | `voice_protocol.start_pipeline` | "Run a voice pipeline" — we treat this as start-of-turn. |
| `VoiceAssistantResponse` | outbound | `voice_protocol.start_pipeline` | "Pipeline accepted" — gateway confirms it's listening. |
| `VoiceAssistantAudio` | both | `media_adapter.push_inbound` / outbound writer | Raw PCM payload (16 kHz mono) — this IS the audio. |
| `VoiceAssistantEventResponse` | outbound | `voice_protocol.emit_event` | Lifecycle events per R-4 mapping table. |
| `VoiceAssistantAnnounceRequest` / `Response` | outbound | (v1.1, OOS) | Out-of-turn TTS push. Defer. |
| `VoiceAssistantTimerEventResponse` | outbound | (v1.1, OOS) | Timer events; defer. |

Anything not in this table that arrives over the wire MUST be
silently ignored (logged at DEBUG only) — edge case in spec.

## 5. Config schema extension

`src/aivg_core/config.py` gains one new optional block. The existing
`SatelliteAdapterConfig` dataclass extends:

```python
from dataclasses import dataclass, field

@dataclass
class EsphomeTransportConfig:
    """Feature 017 config block. Default disabled — opt-in for v1
    deployments so existing satellites don't open a new port without
    the operator's consent (FR-003)."""
    enabled: bool = False
    host: str = "0.0.0.0"
    port: int = 6053
    api_key_file: str = "~/.aivg/devices/keys.json"
    # Optional: a "first-run" master key that lets an unregistered
    # device complete one Connect+Auth so the operator can adopt it.
    # When None, only pre-registered devices may connect.
    bootstrap_key: Optional[str] = None


@dataclass
class TransportsConfig:
    """Top-level transports block — additive in v1.1.0; absent in
    older configs (default-constructed)."""
    esphome_api: EsphomeTransportConfig = field(default_factory=EsphomeTransportConfig)


# Extend the existing root config (additive — old configs parse fine):
@dataclass
class SatelliteAdapterConfig:
    # ... existing fields ...
    transports: TransportsConfig = field(default_factory=TransportsConfig)
```

YAML shape:

```yaml
# ~/.satellite/config.yaml (additive — old configs unchanged work)
satellite:
  # ... existing fields ...
  transports:
    esphome_api:
      enabled: true
      port: 6053
      # bootstrap_key: "secret-bootstrap-key-here"  # optional
```

## 6. Registry / device-record extension

`src/aivg_core/registry.py` device records gain one new field:

```python
@dataclass
class Client:  # or whatever the existing class is
    # ... existing fields (device_id, device_type, last_seen, ...) ...
    transport: str = "webrtc"  # values: "webrtc" | "esphome_api"
```

Default is `"webrtc"` for back-compat. The ESPHome transport sets it
explicitly when registering a device.

**Operator-facing impact**: `aivg list` output gains a `transport`
column. The management-plane WS state-update message gains a
`transport` field on the device record. Both are additive (FR-013,
FR-014).

## 7. API-key store

A small JSON file at `~/.aivg/devices/keys.json`, parallel to the
existing config:

```json
{
  "_schema": "aivg.devices.keys/v1",
  "devices": {
    "kitchen-voice-1": { "api_key": "device-specific-secret-here" },
    "study-voice-1":   { "api_key": "another-secret" }
  }
}
```

Created lazily on first device adoption. Read by
`EsphomeTransport.api_key_resolver`. NOT in source control. The file
is created with mode `0600`.

**Key rotation**: re-running `aivg device adopt <device_id>`
overwrites the entry; the operator distributes the new key to the
device via its ESPHome config (`api: password: ...`).

## 8. Adapter wiring change

`src/aivg_core/adapter.py` gains one new section in `start()`:

```python
# After the existing two aiohttp sites (management 8643, voice 8644):
if self.cfg.transports.esphome_api.enabled:
    from .transports.esphome import EsphomeTransport  # local import
    esphome = EsphomeTransport(
        registry=self.registry,
        platform=self.platform,
        sink=self.sink,
        host=self.cfg.transports.esphome_api.host,
        port=self.cfg.transports.esphome_api.port,
        api_key_resolver=self._resolve_esphome_api_key,
        ui_broadcast=self.management._broadcast,
    )
    await esphome.start()
    self._esphome_transport = esphome  # stored for stop()
```

**Total adapter.py delta**: ~15 lines added, zero lines removed,
zero lines modified — purely additive.

## 9. Entity reference table

| Entity | Where | Status after this feature |
|---|---|---|
| `EsphomeTransport` | `aivg_core/transports/esphome/__init__.py` | NEW |
| `EsphomeConnection` | `aivg_core/transports/esphome/connection.py` | NEW |
| `EsphomeMediaTransport` | `aivg_core/transports/esphome/media_adapter.py` | NEW |
| `EsphomeTransportConfig` | `aivg_core/config.py` | NEW |
| `TransportsConfig` | `aivg_core/config.py` | NEW |
| `SatelliteAdapterConfig.transports` | `aivg_core/config.py` | NEW field (additive) |
| `Client.transport` | `aivg_core/registry.py` | NEW field (additive, default `"webrtc"`) |
| Per-device API key file | `~/.aivg/devices/keys.json` | NEW (created at first adopt) |
| `MediaTransport` Protocol | `aivg_core/webrtc/session.py:70-83` | Unchanged |
| `Session` class | `aivg_core/webrtc/session.py:101` | Unchanged |
| `AgentPlatform` Protocol | `aivg_core/platforms/base.py` | Unchanged |
| Hermes plugin | `aivg_core/platforms/hermes/` | Unchanged |
| WebRTC paths | `aivg_core/webrtc/signaling.py` | Unchanged |
