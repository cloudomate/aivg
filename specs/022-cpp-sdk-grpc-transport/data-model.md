# Phase 1 Data Model: C++ SDK gRPC Transport

Entities split into **SDK-internal types** (C++ classes/structs this feature
adds or changes) and **wire entities** (defined by feature 021's `proto/`,
consumed unchanged). Existing public types are reused; the public API change is
additive.

---

## SDK-internal entities

### Transport (NEW — abstract interface, the seam)
The realization of the device's voice plane. One per active session.
| Member | Purpose |
|---|---|
| `begin(session_id) -> bool` | Open the voice link (WebRTC offer/answer, or gRPC `Audio.Stream` open). |
| `send_mic(pcm16, samples)` | Push captured mic audio (16 kHz s16le). |
| `ready() -> bool` | Safe to pump mic? (WebRTC: DTLS-SRTP complete; gRPC: stream open + `SessionHeader` sent). |
| `stop()` | Tear down the voice link. |
| `set_on_remote_audio(cb)` | Downstream audio: `(payload, size, codec)`. |
| `set_on_event(cb)` | Lifecycle/transcript events → mapped to `SatEvent`. |

**Implementations**: `LibpeerTransport` (existing, refactored behind the
interface — no behaviour change) and `GrpcTransport` (NEW, POSIX/grpc++).

**Validation**: `send_mic` before `ready()` is dropped (no buffering past a
small bound). `begin()` is idempotent-safe; a second `begin` on a live transport
is rejected.

### GrpcTransport (NEW)
`Transport` over `aivg.satellite.v1.Audio/Stream`.
| Field/behaviour | Notes |
|---|---|
| channel | gRPC channel to `host:grpc_port`; insecure (LAN) or SSL/mTLS (fleet). |
| stream | one bidi `Audio.Stream`; first `ClientFrame` is `SessionHeader{session_id, downstream_codec_pref}`. |
| upstream | `send_mic` → `ClientFrame.pcm` (`PcmChunk`, raw 16 kHz, 20 ms). |
| client events | wake / end-of-utterance / barge-in → `ClientFrame.event`. |
| downstream | `ServerFrame.audio` → `on_remote_audio`(codec); `ServerFrame.event`/`transcript` → `on_event`. |
| drop | stream error → session ends + `VoiceSessionResult{reason}` (FR-013). |

### VoiceSession (EXISTING — modified)
Holds `std::unique_ptr<Transport>` (was a concrete `LibpeerTransport` member).
The mic pump feeds `transport_->send_mic(...)`; on the gRPC path it sends **raw
PCM** (no Opus encode). All else (reconnect, event emission, FSM) unchanged.

### Transport capability set / selection (NEW concept)
| Attribute | Source | Notes |
|---|---|---|
| advertised capabilities | build flags | e.g. `["grpc","webrtc"]` (gRPC RPi build), `["webrtc"]` (ESP32-S3 / WebRTC-only). Honest per-binary. |
| `transport_pin` | `SatelliteOptions` (opt-in) | developer override; unsatisfiable → `SatError`. |
| `chosen_transport` | gateway register reply | which transport the gateway selected. |

### SatelliteOptions (EXISTING public struct — additive fields)
New **opt-in** fields only (no breaking change, FR-003): e.g.
`transport` (auto | grpc | webrtc), `grpc_port`, `grpc_tls`. Defaults preserve
feature-020 behaviour (WebRTC).

### SatEvent (EXISTING variant — unchanged)
The gRPC transport maps protobuf `ServerEvent`/`Transcript`/stream-drop onto the
**existing** `SatEvent` cases (`TranscriptDelta`, `StateChangePayload`,
`VoiceSession`, `VoiceSessionResult`, `SatError`). No new event type (FR-006).

---

## Wire entities (feature 021 `proto/aivg/satellite/v1/` — consumed verbatim)

- `Audio.Stream(stream ClientFrame) → (stream ServerFrame)` — the voice plane.
- `ClientFrame{ SessionHeader | PcmChunk | ClientEvent }`,
  `ServerFrame{ AudioChunk | ServerEvent | Transcript }`,
  `Codec{ OPUS | PCM_S16LE_16K }` (see feature 021 data-model).
- `RegisterRequest.transport_capabilities` / `RegisterReply.chosen_transport`
  (management.proto) — used for negotiation in Phase 1's WS register frame
  (advertised as a JSON field today; the full gRPC `Management` service is Phase 2).

No gateway or wire change — this feature is a new **consumer** of the contract.

---

## State transitions

The conversation FSM (`state_machine`: Idle → Listening → Speaking → Idle, +
Error/Reset) is **unchanged** — it is transport-agnostic and reused.

New transport-lifecycle transitions inside `GrpcTransport`:
```
begin() → stream-open → SessionHeader sent → ready()        [mic pump may run]
              │ open fails / no gRPC on gateway → SatError → fall back / surface
stream-drop (mid-turn) → stop() → VoiceSessionResult{reason} → next turn = new stream
gateway restart → ControlPlane.on_reconnected → end+rebuild session (existing hook)
```

## Key relationships

- **1 `Satellite` → 0..1 active `VoiceSession` → 1 `Transport` → 1 voice link**
  (one `Audio.Stream` per gRPC session — FR-007).
- **`session_id`** (from adoption/register) keys the gRPC stream via
  `SessionHeader.session_id` (FR-007), exactly as the gateway expects.
- **Transport selection** is data (advertised caps × gateway choice × optional
  pin), not a compile-time-only fork — runtime `unique_ptr<Transport>` (R-1/R-5).
