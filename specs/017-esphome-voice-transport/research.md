# Research — ESPHome Voice Assistant transport (Phase 0)

**Feature**: 017-esphome-voice-transport · **Date**: 2026-05-21

Three architectural decisions were locked in `/speckit-clarify`
Session 2026-05-20. This document captures the rationale, the
references that backed each, and a fourth implementation note (R-4)
on the voice-pipeline event mapping that is implied by the spec but
worth pinning before tasks.md.

---

## R-1 — Proto schemas + framing: depend on `aioesphomeapi`

**Decision**: add `aioesphomeapi` as a runtime PyPI dependency
(pinned `>=23.0,<28.0`) and consume:

- `aioesphomeapi.api_pb2` — the proto-generated message types
  (`HelloRequest`, `HelloResponse`, `ConnectRequest`,
  `AuthenticationRequest`, `PingRequest`, `DeviceInfoResponse`,
  `ListEntitiesRequest`, `ListEntitiesDoneResponse`,
  `SubscribeStatesRequest`, `VoiceAssistantAudio`,
  `VoiceAssistantEventResponse`, `VoiceAssistantConfigurationRequest`,
  `VoiceAssistantConfigurationResponse`,
  `VoiceAssistantAnnounceRequest`, etc.).
- `aioesphomeapi.core` — varint length-prefix encoding (`varuint_to_bytes`,
  `bytes_to_varuint`), message-type opcode mapping
  (`MESSAGE_TYPE_TO_PROTO`, `PROTO_TO_MESSAGE_TYPE`), and the plain-text
  packet helpers (`make_plain_text_packets`).

**Rationale**:

- The OHF-Voice `linux-voice-assistant/api_server.py` does precisely
  this. Their pattern is the closest extant reference for the
  server-side role this feature is building. We're not on the bleeding
  edge of "is this even possible" — we're walking a proven path.
- `aioesphomeapi` is the canonical home of these schemas — every
  ESPHome firmware bump that touches the proto definitions lands here
  first; pinning to a version range gives us a clean upgrade signal.
- The package itself is small and stable. Adding it does not
  meaningfully expand AIVG's transitive-dependency surface (it pulls
  in `protobuf` and a small async TCP helper).

**Alternatives considered**:

- **Vendor the `.proto` files into `src/aivg_core/transports/esphome/proto/`**
  and run `protoc` at build time. Rejected: introduces a build-time
  toolchain step (`protoc`), creates a quarterly schema-refresh
  burden, and there's no behavioural win because `aioesphomeapi`
  is doing the same thing — we'd just be duplicating it.
- **Hand-roll a minimal Python serializer for just the
  voice-assistant messages**. Rejected: tiny in scope (~15 message
  types), but every protocol drift becomes a custom bug. Wrong
  build-vs-buy tradeoff.

**Implementation note**: aioesphomeapi exposes both a high-level
async client (`APIClient`, `APIConnection`) and the lower-level
proto + framing utilities. **We use only the lower-level utilities**
— the high-level `APIClient` is designed for a Home Assistant
*consuming* devices, which is the inverse direction of what we need.

---

## R-2 — Concurrency: one `asyncio.Task` per connected device

**Decision**: `EsphomeTransport.serve()` calls
`asyncio.start_server(self._on_connect, host, port)`. The
`_on_connect(reader, writer)` callback spawns one
`asyncio.Task(EsphomeConnection(reader, writer, ...).run())` per
inbound connection and returns immediately. The task owns the
connection's full lifecycle (handshake → auth → voice sessions →
teardown).

**Rationale**:

- Mirrors how the existing aiortc-based WebRTC sessions are handled
  in `webrtc/signaling.py` — each accepted offer spawns one task
  per session (see `signaling.py::SignalingService._tasks`). Same
  pattern, same cleanup story.
- Each device's connection lifecycle is naturally serial: handshake
  → voice sessions interleaved → teardown. A per-task model fits
  the natural shape; no need to invent a multiplexer.
- Cancellation is the simplest possible story: cancel the task,
  `Session.stop()` is awaited, the socket is closed in the task's
  `finally`. Mirrors WebRTC teardown exactly.

**Alternatives considered**:

- **Single pooled task with a per-device state map**. Rejected:
  more complex teardown (state-map cleanup races with in-flight
  message handling); marginal task-count savings (~3-20 devices in
  v1's expected scale → trivial); harder to debug a stuck device.
- **Thread-per-device**. Rejected: would force a thread-bridging
  layer between the per-device socket and the asyncio-based
  `Session`. Massive complication for zero benefit.

**Scaling note**: the one-task-per-device model scales to ~100
devices on a modest server (Python asyncio's task overhead is in the
single-digit KB range). Beyond that scale, a different transport
might be warranted — that's a v2+ concern, well past v1's homelab
scope.

---

## R-3 — Session reuse: adapt to `MediaTransport`, no `Session` changes

**Decision**: ESPHome's per-device voice-session lifecycle reuses
`aivg_core.webrtc.session.Session` **verbatim**, by providing a
class `EsphomeMediaTransport` that satisfies the existing
`MediaTransport` Protocol:

```python
# src/aivg_core/webrtc/session.py:70-83 (existing surface)
class MediaTransport(Protocol):
    async def receive(self) -> Optional[bytes]: ...
    async def send_audio(self, pcm: bytes) -> None: ...
    async def stop_playback(self) -> None: ...
    @property
    def connection_state(self) -> str: ...
    async def close(self) -> None: ...
```

`EsphomeMediaTransport` implements those five members against the
ESPHome connection's inbound/outbound PCM queues. The
`EsphomeConnection` constructs a `Session(model, EsphomeMediaTransport,
platform, sink)` exactly the way `SignalingService.handle_offer`
constructs one today for WebRTC.

**Rationale**:

- The `MediaTransport` Protocol is **already** transport-neutral by
  design — feature 001's contract C1-C8 explicitly anticipated a
  fake (in-memory) transport and a real (aiortc) transport. ESPHome
  is just a third implementation.
- The per-turn state machine
  (`idle → listening → thinking → speaking`) is the part most
  expensive to reimplement and most dangerous to fork — reusing it
  guarantees behavioural parity across transports.
- Feature 015's runtime closure made the `Session` consume
  `AgentPlatform` directly (not `HermesBridge`). That cleanup is the
  exact precondition that makes this reuse possible.

**Alternatives considered**:

- **Extract a transport-neutral `Session` base class** with
  `WebRTCSession` and `EsphomeSession` subclasses. Rejected: ~2×
  the code churn for no behaviour delta. If `MediaTransport` leaks
  during implementation we'll patch that — but premature
  abstraction was the rejected outcome.
- **Build a parallel `EsphomeSession` class** with its own turn
  machine. Rejected outright: diverges the per-turn behaviour and
  defeats Principle II's "identical semantics" rule.

**What "verbatim" means here**: no edits to `webrtc/session.py`
are part of this feature's source delta. If the implementation
discovers a real abstraction leak in `MediaTransport`, the minimal
patch IS allowed (and would be a separate small commit) — but the
plan budgets zero `webrtc/session.py` lines.

---

## R-4 — Voice-assistant pipeline event mapping (implementation note)

**Decision**: map ESPHome's `VoiceAssistantEventResponse` event
types to the existing `Session` state-machine transitions as
follows:

| ESPHome event | Session state transition | Notes |
|---|---|---|
| `VOICE_ASSISTANT_RUN_START` | `idle` → enter pipeline (no state change yet) | Mirrors aiortc transport's session-open event. The actual `LISTENING` transition fires when the device sends its first `VoiceAssistantAudio`. |
| `VOICE_ASSISTANT_WAKE_WORD_START` / `_END` | (informational only) | We do not run a gateway-side wake-word; the device's wake-word event is logged but does not drive state. |
| `VOICE_ASSISTANT_STT_START` | `LISTENING` | First `VoiceAssistantAudio` frame arrives. |
| `VOICE_ASSISTANT_STT_END` | `LISTENING` → `THINKING` | Triggered by `AgentPlatform.endpoint(frame)` returning `end_of_utterance=True`, NOT by the device. ESPHome's STT_END from the device is treated as a hint, not authoritative (Principle I: server-side endpointing wins). |
| `VOICE_ASSISTANT_INTENT_START` | (informational; the platform's `agent_step` IS the intent stage) | |
| `VOICE_ASSISTANT_INTENT_END` | (informational; the platform's `agent_step` returning is the actual signal) | |
| `VOICE_ASSISTANT_TTS_START` | `THINKING` → `SPEAKING` | Fires when `AgentPlatform.synthesize` (or `agent_stream`) yields the first audio chunk. |
| `VOICE_ASSISTANT_TTS_END` | `SPEAKING` → `idle` | Fires when the last `VoiceAssistantAudio` outbound frame has been queued for transmission. |
| `VOICE_ASSISTANT_RUN_END` | `idle` (terminal for this pipeline run) | We emit this after `RUN_END` so the device knows the turn is fully over. |
| `VOICE_ASSISTANT_ERROR` | `* → ERROR` | On `AllProvidersUnavailable` or any unhandled exception; cleanup follows. |

**Rationale**: the device firmware uses these events to drive its
LEDs, screen, and audio playback state. Mapping them correctly is
the difference between "the box works" and "the box looks like it's
broken even though audio is flowing." The mapping above is consistent
with what OHF-Voice's `linux-voice-assistant` emits (verified by
reading its `satellite.py`).

**Authoritative endpoint**: this preserves constitutional Principle I
— the **gateway**'s server-side endpointing decides when the user
stops speaking, NOT the device's STT_END signal. The device's
event is logged-and-ignored for state purposes.

---

## Cross-cutting: Authentication

**Decision** (covered by FR-010 / FR-011, no clarification needed):

- v1 uses ESPHome's **plaintext API-key** auth (`AuthenticationRequest`
  message with `password` field).
- The API key is per-device, stored at `~/.aivg/devices/keys.json`
  (created on first device registration; rotated by re-running the
  registration flow). One key per device; not a single shared key
  across the gateway.
- The encrypted Noise-protocol mode is OOS-001 — deferred to v1.1.
  Encrypted mode is wire-incompatible with the plaintext mode at
  the connection level (different handshake) — the v1.1 work is
  scoped as a second handshake variant the listener can
  shape-detect.

**Rationale**: ESPHome's plaintext API auth is the same one Home
Assistant uses by default (when "API encryption" is left off in the
device's YAML). Starting with it ensures the broadest device
compatibility on day one. Encryption is a polish upgrade, not a
blocking gate.

---

## Cross-cutting: Sample-rate negotiation

**Decision**: AIVG advertises in
`VoiceAssistantConfigurationResponse` that it accepts **16 kHz mono
PCM16** inbound (matching ESPHome's voice-satellite default) and
emits **16 kHz mono PCM16** outbound. Audio frames flow as raw PCM
bytes in `VoiceAssistantAudio.data` (no Opus, no compression — same
as Home Assistant's pipeline).

`EsphomeMediaTransport.receive()` resamples to 48 kHz mono before
returning, to match the existing `Session._handle_turn`'s
expectation (which calls `platform.transcribe(audio, sample_rate=48000)`
post-feature-015). The resampling is a simple in-process step using
the existing `aivg_core.webrtc.media` framer scaffolding, or a tiny
`audioop.ratecv` call (stdlib).

**Rationale**: ESPHome's voice satellite ships 16 kHz; AIVG's
existing pipeline uses 48 kHz internally. Resampling at the
transport boundary is the cleanest place — it keeps `Session`
sample-rate-agnostic and matches how the WebRTC `AiortcTransport`
already resamples (Opus 48 kHz → s16 mono 48 kHz, see
`signaling.py::AiortcTransport._decode_inbound`).

---

## Open implementation questions (deferred to tasks.md / impl)

These are not blocking the plan but should be answered when the
relevant task is implemented:

- **Discovery**: do we expose an mDNS `_aivg._tcp` service record so
  ESPHome devices configured with mDNS lookup find us? Spec
  OOS-003 defers this; v1 uses configured-hostname-only. Reconsider
  in v1.1.
- **Per-device API-key bootstrap**: how does the operator first add
  a key for a brand-new device? Options: (a) device-side
  ESPHome `password:` field is matched against a server-side
  per-device-record key set during `aivg device adopt`; (b)
  first-connect TOFU. Plan recommends (a). Final UX shape resolves
  in tasks.md / quickstart.md.
- **Multi-session-per-device**: ESPHome's voice-assistant protocol
  is one turn at a time per device. We do not need to support
  concurrent turns from the same device. Single `Session` per
  `EsphomeConnection` at any moment.
