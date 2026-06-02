# Phase 1 Data Model: gRPC Satellite Transport

Entities are split into **wire entities** (defined by the `.proto`, the
cross-language contract) and **runtime/registry entities** (existing
`aivg_core.models` types this feature extends). Existing types are reused
unchanged wherever possible (Constitution II).

---

## Wire entities (defined in `contracts/audio.proto` — Phase 1)

### ClientFrame (device → gateway, streamed)
`oneof body`:
| Field | Type | Notes |
|---|---|---|
| `session` | `SessionHeader` | **First frame only.** Carries `session_id` + downstream codec prefs. |
| `pcm` | `PcmChunk` | 16 kHz s16le mono, 20 ms (640 B) frames. |
| `event` | `ClientEvent` | `WAKE_FIRED` \| `END_OF_UTTERANCE` \| `BARGE_IN_START`. |

**Validation**: first frame MUST be `session`; `session_id` MUST match an
adopted satellite's open session minted by the management plane (FR-006). PCM
frames before a valid `SessionHeader` are rejected (`FAILED_PRECONDITION`).

### ServerFrame (gateway → device, streamed)
`oneof body`:
| Field | Type | Notes |
|---|---|---|
| `audio` | `AudioChunk` | `codec` explicit (`OPUS` \| `PCM_S16LE_16K`), `payload`, monotonic `seq`. |
| `event` | `ServerEvent` | `SPEAKING_STARTED` \| `SPEAKING_ENDED` \| `VAD_DETECTED`. |
| `transcript` | `Transcript` | streaming partial/final recognized text. |

### Supporting messages
- `PcmChunk { bytes samples; uint64 ts_ns; }`
- `AudioChunk { Codec codec; bytes payload; uint64 seq; }`
- `Transcript { string text; bool is_final; }`
- `SessionHeader { string session_id; repeated Codec downstream_codec_pref; }`
- `ClientEvent { Kind kind; map<string,string> attrs; }`
- `ServerEvent { Kind kind; map<string,string> attrs; }`
- `enum Codec { CODEC_UNSPECIFIED=0; CODEC_OPUS=1; CODEC_PCM_S16LE_16K=2; }`

**Mapping to the existing `MediaTransport`/`Session` seam** (research R-3):
`pcm`→`receive()`; `event{END_OF_UTTERANCE}`→`push_eof()`;
`event{WAKE_FIRED}`→session start; `event{BARGE_IN_START}`→barge-in;
`Session.send_audio`→`AudioChunk`; `Session._ui(state/partial)`→
`ServerEvent`/`Transcript`.

---

## Wire entities (defined in `contracts/management.proto` — Phase 2, design-ahead)

`Management` service (long-lived, separate from `Audio.Stream`):
- `rpc Register(RegisterRequest) returns (RegisterReply)`
- `rpc Adopt(AdoptRequest) returns (AdoptReply)` *(operator-initiated; mirrors REST `/adopt`)*
- `rpc StreamState(stream StateUpdate) returns (stream ControlMessage)` — bidi:
  device pushes state/heartbeat/wake-turn events up; gateway pushes
  `config_changed`/`command`/`state_update` down. Mirrors today's `/satellite/ws`
  message set exactly (FR-014).

**Validation/semantics**: lifecycle states and control actions MUST be
identical to the WebSocket contract (FR-014) — `register`, `heartbeat`,
`state_update`, `config_changed`, `command`. No new observable semantics; this
is a transport move, not a redesign.

---

## Runtime / registry entities (existing types, extended)

### Transport capability set (NEW concept; minimal model change)
Each satellite advertises supported transports at adoption.
| Attribute | Type | Notes |
|---|---|---|
| `transport_capabilities` | `list[str]` | e.g. `["grpc","webrtc"]`, `["webrtc"]` (browser), `["esphome_api"]`. |
| `transport` (chosen) | `str` | **Already exists** on `ConnectedClient` (`models.py:220`) and `VoiceSession` (`models.py:262`), default `"webrtc"`. Now one of `webrtc|esphome_api|grpc`. |
| `transport_pin` | `Optional[str]` | operator override (FR-017); unsatisfiable → clear error. |

**Selection rule** (R-5): chosen `transport` = pin if set & satisfiable, else
the gateway-preferred transport in the intersection of advertised capabilities
and `SUPPORTED_TRANSPORTS` (prefer `grpc` for native, `webrtc` for browser).

### VoiceSession (existing — `models.py:248`)
Reused unchanged. The `session_id` (uuid hex, minted by `Registry.open_session`)
keys the gRPC `Audio.Stream` via `SessionHeader.session_id` (FR-006). The
`transport` field is set to `"grpc"` for gRPC sessions. `webrtc_state` is a
WebRTC-specific field; for gRPC sessions a parallel notion is the stream's
`connection_state` exposed by `GrpcMediaAdapter` (no model change required —
`webrtc_state` stays WebRTC-only; gRPC liveness is observed via the adapter).

### SatelliteState / SatelliteConfig / LogEntry (existing)
Used **unchanged** (Constitution II). `echo_strategy` unaffected.

---

## State transitions

The per-session conversation state machine is **unchanged** — it lives in
`Session` and is transport-agnostic:

```
idle → listening → thinking → speaking → listening
speaking → listening        (barge-in, ≤300 ms)
any → error → teardown → idle
```

New transport-lifecycle transitions (gRPC stream, handled in `stream_handler`):
```
stream-open → (SessionHeader validated) → session-bound → [conversation SM runs]
                     │ invalid/missing header → FAILED_PRECONDITION → stream-close
stream-drop (mid-turn) → session ends → client surfaces tone cue (FR-020)
                       → next wake → new stream
gateway-restart → all streams end → satellites reconnect on next turn (FR-019)
```

---

## Key relationships

- **1 satellite (`ConnectedClient`) → 0..1 active `VoiceSession`** (existing
  `active_session_id`). **1 `VoiceSession` → 1 gRPC `Audio.Stream`** (one stream
  per session, opened at session start, closed at end — FR-007).
- **`session_id`** is the join key across planes: minted by the management plane
  (Phase 1: WebSocket; Phase 2: `Management.StreamState`), carried into the
  audio plane via `SessionHeader` (FR-006).
- **Transport selection** is data on `ConnectedClient`, never gateway control
  flow branching (Constitution II).
