# Contract — `Satellite` public API

**Feature**: 014-aivg-sat-sdk-ts · **Contract version**: `1.0.0` (matches
`aivg --contract-version`). Any breaking change here requires a major
SemVer bump of `@aivg/sat-sdk`.

This file is the binding specification for the SDK's public surface. The
test `tests/contract/public-api.test.ts` asserts byte-for-byte parity
against the shapes documented here.

## Package exports

```ts
// sdks/typescript/src/index.ts  — every name below is exported from here.

export { Satellite }
  from "./satellite";

export type {
  SatelliteOptions,
  SatelliteState,
  SatelliteEvents,
  AdoptionState,
  AdoptionEvent,
  SatelliteConfig,
  VoiceSession,
  VoiceSessionResult,
  CommandEvent,
  CommandResult,
  TranscriptDelta,
  ToolCallEvent,
  SkillEvent,
  LogEntry,
  OtaManifest,
  OtaProgress,
  ReconnectPolicy,
  AudioSink,
  SdkError,
  SdkErrorCode,
  TransientError,
} from "./types";

// Default factories — re-exported so consumers can compose them.
export { defaultWebrtcFactory } from "./webrtc/browser";
export { defaultAudioSinkFactory } from "./webrtc/audio-sink";

export const CONTRACT_VERSION = "1.0.0" as const;
export const SDK_VERSION: string;   // injected at build time
```

The barrel `index.ts` is the only public entry point. Deep imports
(`@aivg/sat-sdk/satellite`, `/control-plane`, etc) are NOT supported
and the package's `exports` map blocks them.

## Constructor

`new Satellite(options: SatelliteOptions): Satellite`

| Option              | Type                     | Required | Default | Notes |
|---------------------|--------------------------|----------|---------|-------|
| `gatewayUrl`        | `string`                 | yes      | —       | Must include scheme + host + port. No trailing slash. |
| `deviceId`          | `string`                 | yes      | —       | Stable, persisted by consumer. |
| `deviceName`        | `string`                 | no       | `deviceId` | Free-text label. |
| `deviceType`        | enum (see data-model)    | yes      | —       | Drives `device_type` field in registration. |
| `firmwareVersion`   | `string`                 | no       | `"0.0.0"` | Reported in heartbeat. |
| `webrtcFactory`     | `() => RTCPeerConnection` | no      | `globalThis.RTCPeerConnection`-based | R-1 |
| `audioSinkFactory`  | `() => AudioSink`        | no       | managed `<audio>` in browser, throws in Node | R-9 |
| `micConstraints`    | `MediaTrackConstraints`  | no       | `{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }` | R-10 |
| `heartbeatIntervalMs` | `number`               | no       | gateway-suggested (typically 30 000) | |
| `reconnectPolicy`   | `ReconnectPolicy`        | no       | see R-6 | |

Construction is side-effect-free — no network, no permissions, no DOM
mutation. All side effects happen at `connect()` / `beginSession()`.

## Lifecycle methods

### `connect(): Promise<void>`

Opens the control-plane WS, sends `register`, and stays connected.
Idempotent — second call resolves to the existing connection.
Resolves when registration is acknowledged. Rejects with `SdkError`
on permanent failure (e.g., `mixed_content`, `protocol_mismatch`).

### `disconnect(): Promise<void>`

Closes the control-plane WS, cancels heartbeat, ends any in-flight
voice session. Resolves once all resources are released. Always
succeeds.

### `beginSession(): Promise<VoiceSession>`

Idempotent. If a session is already active, returns it. Otherwise:

1. Acquires mic via `getUserMedia(micConstraints)` (browser/Electron).
2. Creates a peer connection via `webrtcFactory()`.
3. Attaches mic track(s); sets up remote track handler.
4. Creates an offer; full-gather ICE (R-7); POSTs `/webrtc/offer`.
5. Applies the answer.
6. Transitions FSM `idle → listening` once the PC reaches
   `connectionState === "connected"`.
7. Resolves with a `VoiceSession` handle.

Rejects with `SdkError` on `not_adopted` (R-2), `permission_denied`,
`no_webrtc_impl`, `ice_failed`, `ice_gathering_timeout`,
`signaling_failed`, or `duplicate_device`.

### `endSession(): Promise<void>`

Closes the active session. Releases mic tracks, closes the PC,
detaches the audio sink. Transitions FSM to `idle`. Always
succeeds (best-effort cleanup).

## Configuration methods

### `getConfig(): Promise<SatelliteConfig>`

`GET /satellite/{deviceId}/config`. Returns the current SatelliteConfig.

### `setConfig(patch: Partial<SatelliteConfig>): Promise<SatelliteConfig>`

`POST /satellite/{deviceId}/config` with the patch + the current
`version` (optimistic concurrency). Returns the updated config.
Rejects with a typed error on version conflict — consumer retries.

## Event surface

```ts
type Unsubscribe = () => void;

on<E extends keyof SatelliteEvents>(
  event: E,
  handler: (payload: SatelliteEvents[E]) => void,
): Unsubscribe;

off<E extends keyof SatelliteEvents>(event: E, handler: Function): void;
```

Every event listed in [data-model.md §11](../data-model.md) is dispatched
through this surface. Handler exceptions are caught and logged via
`console.error`; one bad handler MUST NOT break other handlers
(parity with browser `EventTarget`).

### Async-iterator sugar

```ts
transcripts(): AsyncIterableIterator<TranscriptDelta>;
logs():       AsyncIterableIterator<LogEntry>;
states():     AsyncIterableIterator<SatelliteState>;
```

Each iterator buffers events internally with a configurable bounded
queue (default 1024 entries); iterator consumers that fall behind drop
oldest events and emit a single `transient_error(buffer_overflow)`.
Closing the iterator unsubscribes.

## Error semantics

- **Fatal** (`SdkError`): emitted on `"error"` event; transitions FSM
  to `error`; in-flight `beginSession()` / `connect()` Promises reject
  with this error. Consumer can `recover()` to reset to `idle`.
- **Transient** (`TransientError`): emitted on `"transient_error"`
  event; FSM unchanged; the SDK retries automatically per the
  reconnect policy.

Codes are a closed string union (R-11). Adding a code is a minor
SemVer bump; removing/renaming is major.

## Forward compatibility

- Unknown WS message `type` values: emit `transient_error(protocol_mismatch)`
  ONCE per session; subsequent unknowns are silently dropped.
- Unknown fields in known messages: ignored (extension via `extra: Record<string, unknown>`).
- New events added to `SatelliteEvents`: minor bump.
- Removing/renaming events: major bump.

## Telemetry / observability

The SDK ships ZERO automatic telemetry. No analytics, no error
reporting, no remote logging. Consumer apps that want any of those
build them on top of the public event surface.

## Threading / concurrency

The SDK assumes a single-threaded event loop (browser, Electron
renderer, Node). All public methods are async; internal state
mutations are serialised on the event loop. The SDK is NOT thread-safe
in a Web Worker / SharedWorker / Worker-thread shared-state scenario;
each thread MUST construct its own `Satellite`.
