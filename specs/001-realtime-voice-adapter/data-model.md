# Phase 1 Data Model: Realtime Voice Platform Adapter

Process-lifetime, in-memory only (no database). Models mirror design Appendix B
and are used **unchanged for every device type** (constitution II). Only the
subset relevant to this gateway adapter is detailed; the full device-side
fields remain part of the shared schema.

## Entity: ConnectedClient

A registered voice endpoint known to the gateway.

| Field | Type | Notes |
|-------|------|-------|
| `device_id` | str | Stable identity, e.g. `browser-yash-01`. Registry key. |
| `device_type` | str | `rpi` \| `esp32` \| `browser`. Informational only — MUST NOT drive protocol branching. |
| `status` | enum | `online` \| `offline` \| `connecting` \| `error` |
| `last_seen` | float (epoch s) | Updated on heartbeat / any control message |
| `ip_address` | str | From register |
| `firmware_version` | str | From register |
| `active_session_id` | str \| None | FK → VoiceSession when a call is up |

**Relationships**: 1 ConnectedClient → 0..1 active VoiceSession.

**State transitions**: `connecting → online` (register/first heartbeat) ·
`online → offline` (missed heartbeats / WS drop) · `offline → online`
(re-register) · `* → error` (fatal control error, last_error set).

## Entity: VoiceSession

One client's live conversation context (one active call).

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | str | Unique per call |
| `device_id` | str | FK → ConnectedClient |
| `state` | enum | `idle` \| `listening` \| `thinking` \| `speaking` \| `error` |
| `started_at` | float | Call start |
| `last_activity` | float | Last inbound/outbound audio or state change |
| `current_turn` | ConversationTurn \| None | At most one in flight |
| `webrtc_state` | str | aiortc PC connection state |
| `bitrate_tx` / `bitrate_rx` | int | Telemetry |
| `last_error` | str \| None | |

**Invariant**: at most **one** `current_turn` per session at any time
(FR-012). Inbound speech while `speaking` ⇒ barge-in (cancel turn → `listening`).

**State machine**:

```
idle ──connect──▶ listening
listening ──user speech (Hermes end-of-utterance)──▶ thinking
thinking ──agent reply ready──▶ speaking
speaking ──playback done──▶ listening
speaking ──inbound speech (barge-in, ≤300ms cancel)──▶ listening
any ──fatal──▶ error ──teardown/re-offer──▶ idle
listening/thinking ──empty/tool-only agent turn──▶ listening
```

## Entity: ConversationTurn

One user-utterance → agent-reply exchange.

| Field | Type | Notes |
|-------|------|-------|
| `turn_id` | str | |
| `session_id` | str | FK → VoiceSession |
| `user_text` | str | From Hermes STT (via bridge) |
| `agent_text` | str \| None | From Hermes agent (via bridge); None until ready |
| `outcome` | enum | `completed` \| `interrupted` \| `failed` |
| `started_at` / `ended_at` | float | For SC-001 latency measurement |

## Entity: SatelliteConfig (running config, per device)

Pushed on register / via `/satellite/{id}/config`. Defaults per Appendix B.

| Field | Default | Notes |
|-------|---------|-------|
| `wake_word` | `"Hey Jarvis"` | Device-side; adapter just stores/pushes |
| `wake_word_engine` | per device | `porcupine`\|`openwakeword`\|`xmos_vad` |
| `vad_threshold` | `0.5` | Device gating only — not turn-end |
| `vad_mode` | `adaptive` | |
| `routing_mode` | `preferred` | route through Hermes |
| `input_volume` / `output_volume` | `1.0` | |
| `echo_strategy` | per device | enum `hardware_xmos`\|`software_speex`\|`half_duplex`\|`browser_aec3` |
| `webrtc_enabled` | `true` | |
| `log_level` | `INFO` | |
| `heartbeat_interval` | `30` | seconds |

`echo_strategy` is per-device, never a single global ducking value
(constitution II / design §2.5).

## Entity: LogEntry

Per-session diagnostics written to Hermes's existing `gateway.log` stream and
tailed by `/satellite/{id}/logs`.

| Field | Type | Notes |
|-------|------|-------|
| `device_id` | str | |
| `timestamp` | float | |
| `level` | enum | `DEBUG`\|`INFO`\|`WARN`\|`ERROR` |
| `source` | enum | `vad`\|`wakeword`\|`asr`\|`tts`\|`webrtc`\|`system`\|`ota` |
| `message` | str | |
| `metadata` | dict \| None | e.g. `{"latency_ms": 1180}` |

## Non-entities (reused, NOT modeled here)

Hermes agent, Hermes STT/TTS providers + fallback order, and the server-side
silence/end-of-utterance algorithm are **Hermes-owned** and reached via
`hermes_bridge` only (constitution I/IV). This feature defines no schema for
them.
