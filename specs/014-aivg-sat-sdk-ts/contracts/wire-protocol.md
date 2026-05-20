# Contract — Wire protocol (gateway ↔ SDK)

**Feature**: 014-aivg-sat-sdk-ts · **Contract version**: `1.0.0` (matches
`aivg --contract-version` from feature 011). The SDK is a *consumer* of
this contract — it does not extend it. Any wire-shape change is a
gateway-side feature, not an SDK feature.

This file documents every byte the SDK sends or expects, so the contract
test `tests/contract/wire-protocol.test.ts` can replay recorded gateway
captures and assert parity.

## Transports

| Transport | Path                                | Direction        | Used for                       |
|-----------|-------------------------------------|------------------|--------------------------------|
| HTTP POST | `/satellite/register`               | SDK → gateway    | initial device registration    |
| HTTP GET  | `/satellite/{id}/config`            | SDK → gateway    | read current config            |
| HTTP POST | `/satellite/{id}/config`            | SDK → gateway    | push config update             |
| HTTP POST | `/webrtc/offer`                     | SDK → gateway    | per-session signaling          |
| HTTP POST | `/webrtc/candidate`                 | SDK → gateway    | trickle fallback (R-7)         |
| WS        | `/satellite/ws?device_id={id}`      | bidirectional    | control plane (long-lived)     |
| WebRTC PC | (per-session)                       | bidirectional    | voice plane                    |

The SDK NEVER calls `/satellite/list`, `/satellite/{id}/adopt`,
`/satellite/{id}/command`, `/satellite/{id}/ota/apply`, or
`/satellite/logs` — those are operator-side surfaces (CLI / skills).
The SDK only RECEIVES the consequences via the WS.

## HTTP shapes

### `POST /satellite/register`

```json
// request
{
  "device_id": "browser-ptt-demo",
  "name": "browser-ptt-demo",
  "device_type": "browser",
  "firmware_version": "0.1.0",
  "contract_version": "1.0.0",
  "capabilities": {
    "aec": "browser_aec3",
    "wake_word": "ptt"
  }
}

// response  (201 Created)
{
  "device_id": "browser-ptt-demo",
  "adoption_state": "pending"
}
```

### `GET /satellite/{id}/config`

```json
// response
{
  "wake_word": "Hey Jarvis",
  "routing_mode": "preferred",
  "log_level": "INFO",
  "heartbeat_interval": 30,
  "extra": {},
  "version": 7
}
```

### `POST /satellite/{id}/config`

```json
// request
{
  "patch": { "log_level": "DEBUG" },
  "if_match_version": 7
}

// response
{ "wake_word": "Hey Jarvis", "routing_mode": "preferred",
  "log_level": "DEBUG", "heartbeat_interval": 30, "extra": {}, "version": 8 }
```

Conflict response: `409 Conflict` with body
`{ "error": { "code": "version_conflict", "current_version": 9 } }`.

### `POST /webrtc/offer`

```json
// request
{ "device_id": "browser-ptt-demo",
  "sdp": "v=0\r\no=- ... (full SDP) ...",
  "type": "offer" }

// response
{ "device_id": "browser-ptt-demo",
  "session_id": "5e8b... (UUID)",
  "sdp": "v=0\r\no=- ... (answer SDP) ...",
  "type": "answer" }
```

### `POST /webrtc/candidate` (fallback)

```json
// request
{ "device_id": "...",
  "candidate": "candidate:1 1 udp 2122252543 192.168.1.42 56789 typ host",
  "sdp_mid": "0",
  "sdp_m_line_index": 0 }
// response: 204 No Content
```

## WebSocket protocol

URL: `ws://<gateway>/satellite/ws?device_id={id}` (or `wss://` mirror).
Every message is a single JSON object with a discriminant `type` field.

### SDK → gateway

```json
// type=register — sent immediately after WS open
{ "type": "register",
  "device_id": "...", "contract_version": "1.0.0" }

// type=heartbeat — sent every heartbeat_interval seconds
{ "type": "heartbeat",
  "device_id": "...",
  "state": "idle",                  // or listening|speaking|error
  "uptime_s": 173.4,
  "firmware_version": "0.1.0" }

// type=command_result — reply to a gateway command
{ "type": "command_result",
  "request_id": "...",              // echoed from the command message
  "ok": true,
  "message": "reboot acknowledged",
  "data": {} }
```

### Gateway → SDK

```json
// type=adoption — fires once at register, again on any transition
{ "type": "adoption", "state": "pending" | "adopted" }

// type=config_changed
{ "type": "config_changed", "config": { /* SatelliteConfig — see HTTP shape */ } }

// type=command
{ "type": "command", "request_id": "...", "verb": "reboot",
  "args": { "in_s": 5 } }

// type=log_entry
{ "type": "log_entry",
  "entry": { "ts": "2026-05-20T14:13:43.780Z", "level": "INFO",
             "source": "agent", "message": "conversation turn started",
             "meta": { "session_id": "..." } } }

// type=ota_manifest
{ "type": "ota_manifest",
  "manifest": { "version": "0.2.0", "url": "https://...", "sha256": "...",
                "manifest_id": "...", "apply_by": "2026-06-01T00:00:00Z" } }

// type=ota_progress
{ "type": "ota_progress",
  "manifest_id": "...", "state": "downloading", "progress": 0.42 }

// type=agent_event  (the umbrella for tool calls + skills + transcripts)
{ "type": "agent_event",
  "kind": "tool_call_started",          // or _completed / _failed / skill_loaded / transcript_delta
  "session_id": "...",
  "seq": 42,
  "ts": 1779276647.123,
  "payload": {
    // shape varies by `kind` — see below
  } }
```

### `agent_event` payload by `kind`

```json
// kind=tool_call_started
{ "tool_name": "web_search", "tool_id": "..." }

// kind=tool_call_completed
{ "tool_name": "web_search", "tool_id": "...",
  "result_summary": "Found 5 results" }

// kind=tool_call_failed
{ "tool_name": "web_search", "tool_id": "...",
  "error": "Timeout after 10 s" }

// kind=skill_loaded
{ "skill_name": "voice-friendly-replies", "source": "built-in" }

// kind=transcript_delta
{ "speaker": "assistant", "text": "Hello! ", "final": false }
```

## Wire-shape stability rules

1. New `agent_event` `kind` values: forward-compatible — SDK emits
   `transient_error(protocol_mismatch)` once per session and otherwise
   ignores. Contract change.
2. New top-level WS message `type` values: same — forward-compatible.
3. New fields on existing messages: ignored by SDK. Forward-compatible.
4. Removing/renaming `type` values OR existing field names: **breaking**;
   requires contract-version bump on the gateway side.
5. Changing field types (e.g., `string` → `number`): **breaking**.

## SDK parsing rules

- Every inbound JSON is parsed in a try/catch; malformed JSON emits
  `transient_error(signaling_retry)` and is dropped.
- Every message MUST have a string `type` field. Missing-field messages
  are dropped silently (treated as ping/keepalive).
- The SDK does NOT validate field types beyond the `type` discriminant
  — TypeScript types are aspirational at runtime. (This is a deliberate
  trade-off; runtime validators like zod were rejected to keep the
  package size under the SC budget.)
- Forward-compat: unknown fields are stored on the typed object as
  `_unknown: Record<string, unknown>` for diagnostic inspection.

## Captured fixture format

The test `tests/contract/wire-protocol.test.ts` replays JSON-lines files
of the shape:

```
{ "ts": 1779000001.0, "dir": "in",  "type": "ws_text",   "body": "{\"type\":\"adoption\", ...}" }
{ "ts": 1779000001.1, "dir": "out", "type": "http_post", "path": "/webrtc/offer", "body": {...} }
{ "ts": 1779000002.5, "dir": "in",  "type": "http_resp", "status": 200, "body": {...} }
```

Fixtures live under `tests/fixtures/wire/*.jsonl`. Each fixture
documents the gateway version it was captured against in a header
comment. The contract test asserts that replaying a fixture through
the SDK produces the same sequence of events on the public surface.

Initial fixtures (created during implementation):

- `tests/fixtures/wire/happy-path-one-turn.jsonl` — clean registration,
  adoption, one voice turn, clean disconnect.
- `tests/fixtures/wire/reconnect-after-drop.jsonl` — WS dropped + recovered.
- `tests/fixtures/wire/tool-call-turn.jsonl` — turn that invokes a tool.
- `tests/fixtures/wire/config-pushed-mid-call.jsonl` — operator changes
  config during an active voice session.
- `tests/fixtures/wire/ota-during-session.jsonl` — OTA manifest arrives
  while in `speaking` state.
- `tests/fixtures/wire/unknown-event-kind.jsonl` — forward-compat smoke.
