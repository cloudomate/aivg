# Data Model — `@aivg/sat-sdk` (Phase 1)

**Feature**: 014-aivg-sat-sdk-ts · **Date**: 2026-05-20

This document defines every exported TypeScript type, the state machine
transition table, and the wire-shape mappings the SDK consumes. Every
type lands in `sdks/typescript/src/proto/` or `sdks/typescript/src/index.ts`
exactly as written below; the contract tests in
`tests/contract/public-api.test.ts` assert byte-for-byte parity.

## 1. Top-level handle — `Satellite`

The `Satellite` class is the single entry point.

```ts
export interface SatelliteOptions {
  /** Gateway base URL — e.g. "http://localhost:8643". HTTPS-aware. */
  gatewayUrl: string;
  /** Stable per-device identity. Persists across sessions. */
  deviceId: string;
  /** Display label in `aivg list` (free-text). */
  deviceName?: string;
  /** One of the documented device classes. */
  deviceType: "browser" | "electron" | "node" | "rpi" | "esp32" | "custom";
  /** Default firmware version reported via heartbeat. */
  firmwareVersion?: string;

  /** WebRTC factory (DI hole — R-1). Defaults to globalThis.RTCPeerConnection. */
  webrtcFactory?: () => RTCPeerConnection;
  /** Audio sink factory (DI hole — R-9). Defaults to a managed <audio> in browser. */
  audioSinkFactory?: () => AudioSink;
  /** Mic constraints applied to getUserMedia() (R-10). */
  micConstraints?: MediaTrackConstraints;

  /** Heartbeat cadence override; defaults to gateway-suggested (30 s). */
  heartbeatIntervalMs?: number;
  /** Auto-reconnect policy override (R-6). */
  reconnectPolicy?: ReconnectPolicy;
}

export class Satellite {
  constructor(opts: SatelliteOptions);

  /** Open the control plane WS, register, and stay connected. Idempotent. */
  connect(): Promise<void>;
  /** Close the control plane WS and any in-flight voice session. */
  disconnect(): Promise<void>;

  /** Current adoption state. Reactive — also emitted via `on("adoption", …)`. */
  readonly adoptionState: AdoptionState;
  /** Current high-level lifecycle state. */
  readonly state: SatelliteState;

  /** Begin a voice session (offerer flow). Idempotent — returns the active one. */
  beginSession(): Promise<VoiceSession>;
  /** End the active voice session, releasing PC + audio resources. */
  endSession(): Promise<void>;

  /** Read the current SatelliteConfig from the gateway. */
  getConfig(): Promise<SatelliteConfig>;
  /** Push a partial config update to the gateway. */
  setConfig(patch: Partial<SatelliteConfig>): Promise<SatelliteConfig>;

  // -------- typed event surface (R-4) ---------------------------------
  on<E extends keyof SatelliteEvents>(
    event: E,
    handler: (payload: SatelliteEvents[E]) => void,
  ): () => void;        // returns unsubscribe fn
  off<E extends keyof SatelliteEvents>(event: E, handler: Function): void;

  // -------- syntactic-sugar async-iterator streams (R-4) ----------------
  transcripts(): AsyncIterableIterator<TranscriptDelta>;
  logs(): AsyncIterableIterator<LogEntry>;
  states(): AsyncIterableIterator<SatelliteState>;
}
```

## 2. Lifecycle state machine

```text
       ┌───────────────────────────────────────────────────┐
       │                                                   │
       ▼                                                   │
   ┌────────┐  beginSession()   ┌─────────────┐            │
   │  idle  │ ────────────────► │  listening  │            │
   └────────┘                   └──────┬──────┘            │
       ▲                               │ first remote frame│
       │ endSession()                  ▼                   │
       │                        ┌──────────────┐           │
       │                        │  speaking    │           │
       │                        └──────┬───────┘           │
       │                               │ session ended     │
       │                               ▼                   │
       └───────────────────────────────┘                   │
                                                           │
   ┌───────────┐  any fatal error from any state           │
   │   error   │ ◄─────────────────────────────────────────┘
   └──────┬────┘
          │ explicit recover()/reset
          ▼  →  idle (preserves WS; clears voice resources)
```

```ts
export type SatelliteState =
  | "idle"
  | "listening"
  | "speaking"
  | "error";
```

| From          | Event                              | To           |
|---------------|------------------------------------|--------------|
| `idle`        | `beginSession()` resolves          | `listening`  |
| `listening`   | first inbound audio frame          | `speaking`   |
| `listening`   | `endSession()` resolves            | `idle`       |
| `speaking`    | session naturally ends             | `idle`       |
| `speaking`    | `endSession()` resolves            | `idle`       |
| any           | fatal `SdkError` (closed set R-11) | `error`      |
| `error`       | `recover()`                        | `idle`       |

Non-fatal errors (transient WS disconnect, ICE retry) do NOT transition
to `error`; they're emitted on the `transient_error` event and the state
machine stays where it was.

## 3. Adoption

```ts
export type AdoptionState = "pending" | "adopted";

export interface AdoptionEvent {
  state: AdoptionState;
  /** True the first time we observe `adopted` for this device. */
  firstApproval: boolean;
}
```

State persists in the gateway's registry (feature 011 entity). The SDK
reflects whatever the gateway reports; it does NOT cache. Adoption can
only proceed `pending → adopted` (R-2 from spec); never the reverse.

## 4. Configuration

```ts
export interface SatelliteConfig {
  /** Wake word phrase, if the device supports always-on wake. */
  wakeWord: string;
  /** Routing mode for incoming voice turns. */
  routingMode: "preferred" | "any" | "off";
  /** Log verbosity. */
  logLevel: "debug" | "info" | "warn" | "error";
  /** Seconds between heartbeats. */
  heartbeatInterval: number;
  /** Free-form extensions reserved for forward compat. */
  extra: Record<string, unknown>;
  /** Server-assigned monotonic version; bumped on every change. */
  version: number;
}
```

Wire shape mirrors the management plane's `GET /satellite/{id}/config`
response and `POST /satellite/{id}/config` request body. The SDK uses
the `version` field for optimistic concurrency (PATCH semantics with
`If-Match: <version>`).

## 5. Voice session

```ts
export interface VoiceSession {
  /** Session id assigned by the gateway in the offer/answer exchange. */
  sessionId: string;
  /** Local timestamp when beginSession() resolved. */
  startedAt: number;
  /** Closed when endSession() resolves or the session fails. */
  ended: Promise<VoiceSessionResult>;
}

export interface VoiceSessionResult {
  endedAt: number;
  turnCount: number;
  /** Reason the session ended. */
  reason:
    | "operator_ended"     // consumer called endSession()
    | "gateway_closed"     // remote side closed cleanly
    | "ice_failed"
    | "ws_disconnected"
    | "fatal_error";
  error?: SdkError;
}
```

A session is exactly one WebRTC PeerConnection. Multiple "turns" (user
spoke → agent replied) can happen within one session.

## 6. Agent telemetry

```ts
export interface TranscriptDelta {
  /** Whose text: 'user' (STT) or 'assistant' (agent). */
  speaker: "user" | "assistant";
  /** Incremental text chunk; concat across deltas for full transcript. */
  text: string;
  /** True when this delta is the final chunk for the current speaker turn. */
  final: boolean;
  /** Monotonic per-session sequence number. */
  seq: number;
  /** Gateway-side timestamp (Unix seconds, fractional). */
  ts: number;
}

export interface ToolCallEvent {
  type: "tool_call_started" | "tool_call_completed" | "tool_call_failed";
  toolName: string;
  /** Brief summary of result, when available. Not the full result body. */
  resultSummary?: string;
  /** Error message when type=tool_call_failed. */
  error?: string;
  ts: number;
}

export interface SkillEvent {
  type: "skill_loaded";
  skillName: string;
  source: "built-in" | "plugin" | "tap";
  ts: number;
}
```

## 7. Commands (operator → device)

```ts
export interface CommandEvent {
  /** Closed set of verbs from feature 011 R-14. */
  verb: "reboot" | "restart" | "refresh_config" | "tail_logs" | "ping";
  /** Per-verb arguments. Free-form. */
  args: Record<string, unknown>;
  /** Reply channel — call this with the result and the SDK forwards it. */
  reply: (result: CommandResult) => void;
}

export interface CommandResult {
  ok: boolean;
  message?: string;
  data?: Record<string, unknown>;
}
```

The SDK never executes a command — it forwards every command to the
consumer's handler via `on("command", …)`. The consumer decides what
"reboot" means in its host environment (browser → `location.reload()`,
Electron → `app.relaunch()`, Node → `process.exit(0)` then external
supervisor, etc).

## 8. Logs (gateway → device)

```ts
export interface LogEntry {
  /** ISO-8601 timestamp. */
  ts: string;
  level: "DEBUG" | "INFO" | "WARN" | "ERROR";
  source: string;        // e.g. "asr", "agent", "gateway"
  message: string;
  /** Free-form structured payload. */
  meta?: Record<string, unknown>;
}
```

Wire shape mirrors `aivg logs <device>`'s SSE stream output.

## 9. OTA

```ts
export interface OtaManifest {
  /** Version of the OTA bundle. */
  version: string;
  /** Source URL. The SDK forwards but does not fetch. */
  url: string;
  /** Optional SHA-256 of the bundle. */
  sha256?: string;
  /** Gateway-assigned manifest id. */
  manifestId: string;
  /** Apply-deadline hint (ISO-8601). */
  applyBy?: string;
}

export interface OtaProgress {
  manifestId: string;
  state: "checking" | "downloading" | "flashing" | "rebooting" | "idle" | "failed";
  progress?: number;     // 0..1
  message?: string;
}
```

Browser/Electron consumers will typically forward OTA events to the user
and reload the app, since they have no firmware partitions.

## 10. Errors

```ts
export type SdkErrorCode =
  | "no_webrtc_impl"
  | "no_microphone_api"
  | "permission_denied"
  | "ice_failed"
  | "ice_gathering_timeout"
  | "ws_disconnected"
  | "ws_max_retries_exceeded"
  | "signaling_failed"
  | "mixed_content"
  | "not_adopted"
  | "protocol_mismatch"
  | "duplicate_device";

export interface SdkError {
  code: SdkErrorCode;
  message: string;
  /** Optional underlying cause (Error from the runtime). */
  cause?: unknown;
  /** When did it fire? */
  ts: number;
}

export interface TransientError {
  code: "ws_disconnected" | "signaling_retry" | "ice_retry";
  message: string;
  /** Back-off ms until the next attempt. */
  retryInMs: number;
  attempt: number;
}
```

Fatal `SdkError` transitions the FSM to `error`. `TransientError` does
not — it's informational so consumers can show a UI "reconnecting…" banner.

## 11. Event bus shape

```ts
export interface SatelliteEvents {
  state: { previous: SatelliteState; current: SatelliteState };
  adoption: AdoptionEvent;
  config_changed: SatelliteConfig;
  command: CommandEvent;
  log: LogEntry;
  ota_manifest: OtaManifest;
  ota_progress: OtaProgress;
  transcript: TranscriptDelta;
  tool_call: ToolCallEvent;
  skill: SkillEvent;
  remote_stream: { stream: MediaStream };
  session_started: VoiceSession;
  session_ended: VoiceSessionResult;
  error: SdkError;            // fatal — FSM → error
  transient_error: TransientError;  // not fatal
}
```

## 12. Reconnect policy

```ts
export interface ReconnectPolicy {
  initialMs: number;     // default 500
  factor: number;        // default 1.5
  maxMs: number;         // default 30_000
  jitter: number;        // default 0.2 (±20%)
  resetAfterMs: number;  // default 60_000
  maxRetries?: number;   // undefined = infinite
}
```

## 13. Wire → SDK mapping table

| Wire (gateway)                                    | SDK type / event              |
|---------------------------------------------------|-------------------------------|
| `POST /satellite/register` request                | derived from `SatelliteOptions` |
| `POST /satellite/register` response               | sets initial `adoptionState`  |
| `GET /satellite/list` row (this device)           | `adoptionState` + `state` reflection |
| `GET /satellite/{id}/state` response              | reflection only (not surfaced) |
| WS `register` message                             | sent on `connect()`           |
| WS `heartbeat` message                            | sent every `heartbeatInterval` |
| WS `config_changed` message                       | `on("config_changed", …)` event |
| WS `command` message                              | `on("command", …)` event      |
| WS `log_entry` message                            | `on("log", …)` event          |
| WS `ota_manifest` message                         | `on("ota_manifest", …)` event |
| WS `ota_progress` message                         | `on("ota_progress", …)` event |
| WS `agent_event` { kind: tool_call_started } etc. | `on("tool_call", …)` event    |
| WS `agent_event` { kind: skill_loaded }           | `on("skill", …)` event        |
| WS `agent_event` { kind: transcript_delta }       | `on("transcript", …)` event   |
| `POST /webrtc/offer` request                      | issued internally by `beginSession()` |
| `POST /webrtc/offer` response (sdp answer)        | consumed internally           |
| `POST /webrtc/candidate` (fallback)               | issued only if gathering times out |
| `GET /webrtc/status/{device_id}`                  | not consumed in v1            |

Every WS message has a `type` discriminant; the SDK's parser is a
single discriminated-union switch. Unknown `type` values produce a
`transient_error` (code `protocol_mismatch`) the first time per session
but do not throw — forward-compat policy.
