# Phase 1 Data Model: libaivg-sat-embedded

**Feature**: 020-cpp-webrtc-sdk | **Date**: 2026-05-22

C++ entities mirror `@aivg/sat-sdk`. Wire-shaped structs reuse the frozen
contract (`0.2.0`) verbatim — names/fields match the TS proto modules.

## Core SDK entities

### Satellite

The primary object. Owns one always-on control-plane WS and ≤ 1 active
WebRTC voice session.

- **Constructed from**: `SatelliteOptions`.
- **Lifecycle methods** (mirror TS): `connect()`, `disconnect()`, `beginSession()`, `endSession()`, `mute()`, `unmute()`.
- **Inspectors**: `state() → SatelliteState`, `isAdopted() → bool`, `isMicLive() → bool`.
- **Invariants**: at most one live `PeerConnection`; `beginSession()` while a session is active is a no-op or typed transient error; the control WS reconnects independently of session state (Principle III).

### SatelliteOptions

- `gatewayUrl: string` — management-plane base (control WS + REST).
- `signalingUrl: string` (optional) — voice-plane signaling base; defaults to `gatewayUrl`'s voice port if unset.
- `deviceId: string`, `deviceName: string`, `deviceType: string`, `firmwareVersion: string` — identity sent at register.
- `reconnect: ReconnectPolicy` — `{ baseDelayMs, maxDelayMs, jitter }` (exponential + jitter, capped).
- `audioInput: AudioInputCallback`, `audioOutput: AudioOutputCallback` — caller-owned drivers.
- `onEvent: EventHandler` — receives `SatEvent`.
- `timeouts` — ICE gather, media-track-first-audio, signaling.

### AudioInputCallback / AudioOutputCallback

- **Input**: `(int16_t* buf, size_t frames) → size_t produced` — yields PCM16 mono at the negotiated rate; returns 0 / sets end-of-stream when muted or done.
- **Output**: `(const int16_t* buf, size_t frames) → void` — consumes one PCM16 mono reply frame for playback.
- The SDK handles Opus encode (input → wire) and decode (wire → output); the callback boundary is always raw PCM16 mono (FR-005/006).

### SatEvent (discriminated union — full TS parity, 17 variants)

`state`, `gateway_state`, `adoption`, `config_changed`, `command`,
`log`, `ota_manifest`, `ota_progress`, `transcript`, `tool_call`,
`skill`, `barge_in`, `remote_stream`, `session_started`,
`session_ended`, `error`, `transient_error`.

Each payload matches the TS interface field-for-field (see
contracts/public-api.md for the per-variant field tables). OTA events
are forwarded to the consumer only — the SDK implements no update flow
(OOS-005).

### SatError

- `code: SatErrorCode` — stable string enum (R7 list), part of the contract.
- `message: string` — human-readable.
- `context: optional<map<string,string>>` — e.g. failing URL, retry count.
- Two delivery channels: terminal (`error` event) vs recoverable (`transient_error` event).

### DeviceTierProfile (build-time only)

Not a runtime object — a compile-time selection (`AIVG_SAT_TIER_ESP32S3`
vs `AIVG_SAT_TIER_POSIX`, or IDF Kconfig) choosing the WS-client shim,
threading model, and memory ceilings. Never changes the public API
(FR-004a).

## Wire-shaped entities (reused from contract `0.2.0`, unchanged)

### SatelliteState (local FSM)

`idle | listening | speaking | error` (4 states). Transitions driven by
internal events (`begin_session_resolved`, `first_remote_audio`,
mute/unmute, error). **`thinking` is NOT a local state** — it arrives as
a `gateway_state` value. `StateChangePayload` carries `{ previous, current }`.

### SatelliteConfig

Gateway-pushed config block (wake word, routing mode, log level, …),
delivered via the `config_changed` event. Shape identical to the TS
`SatelliteConfig` and the constitution's Appendix-B model (Principle II).

### LogEntry

`{ ts, level, source, msg, meta }` — gateway log lines forwarded over the
control plane; shape identical across all satellites (Principle II).

### OtaManifest / OtaProgress

Forwarded verbatim to the consumer; the SDK does not act on them (OOS-005).

## State transitions (local FSM)

```text
idle ──beginSession()/resolved──▶ listening
listening ──first_remote_audio──▶ speaking
speaking ──reply complete / endSession()──▶ idle
listening ──unmute/mute──▶ listening (mic gating; no teardown — FR-010)
any ──fatal error──▶ error ──reconnect/reset──▶ idle
```

Adoption is orthogonal to the FSM: `adoption` events carry
`pending → adopted` (and back); a turn is only attempted when adopted
(else `not_adopted` error).
