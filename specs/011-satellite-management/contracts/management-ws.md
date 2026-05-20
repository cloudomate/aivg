# Contract: `WS /satellite/ws` — Gateway↔Device Control Channel

**Feature**: `011-satellite-management` · **Plan**: [../plan.md](../plan.md) ·
**Version**: 1.0.0 · **Companion**:
[management-api.yaml](./management-api.yaml)

This document specifies the **gateway↔device always-on control WebSocket**
that satellites maintain independent of any voice call (constitution III).
Operator surfaces (CLI / skills / optional UI) do **not** speak this
protocol — they use the REST API in `management-api.yaml`. The WS is
platform-agnostic per constitution v2.0.0 Principle IV.

## Connection

- URL: `ws://<gateway-host>:<management-port>/satellite/ws` (default port
  8643).
- Lifetime: long-lived. Devices auto-reconnect with exponential backoff
  (jitter 1–30 s).
- Keepalive: server sends pings every 55 s; client closes if it misses two
  consecutive pings.

## Direction of travel

```text
device ──(JSON frame, type)──► gateway
gateway ──(JSON frame, type)──► device  (and ──► all subscribed UI fan-outs)
```

All frames are UTF-8 JSON objects with a `type` field. Unknown `type`s MUST
be ignored, not error-closed (additive contract evolution).

## Client→server frames

| `type` | Required fields | Behavior |
|---|---|---|
| `register` | `device_id`, `device_type` (rpi/esp32/browser), `firmware_version`, `ip_address`, optional `capabilities`, optional `factory_reset: bool` | Same shape as `POST /satellite/register`; on connect, the device sends this. Server responds with `{type: "registered", ...RegisterResponse}` (see OpenAPI). Re-registers refresh `last_seen`; `factory_reset=true` demotes adopted → pending (R-7). |
| `heartbeat` | `device_id`, optional `state` (idle / listening / thinking / speaking / error) | Lightweight liveness ping; server updates `last_seen` and broadcasts `state_update` if the reported state differs. |
| `log_entry` | `device_id`, `timestamp`, `level`, `source`, `message`, optional `metadata` | Device-emitted log line; appended to `LogSink` and fanned out via SSE (`/satellite/{id}/logs?follow=true`). |
| `ota_status` | `device_id`, `state` (downloading/flashing/rebooting/failed/rolled_back/idle), optional `version`, optional `result`, optional `failure_reason` | Mirrors `POST /satellite/{id}/ota/status`; either path is valid (WS preferred during reboot windows). |
| `command_ack` | `device_id`, `command`, `accepted: bool`, optional `reason` | Device acknowledges a previously received `command` frame. |

## Server→client frames

| `type` | Direction | Behavior |
|---|---|---|
| `registered` | to one device | Response to `register`; carries `session_token`, `management_server_url`, `default_config`. |
| `config_changed` | to one device | New `DeviceConfig` to apply locally. Includes `config_version` for the device to ack via next `heartbeat`. |
| `command` | to one device | One of `CommandVerb` (reboot, restart_voice, restart_manager, reset_config, factory_reset, mute, unmute, identify) plus optional `args`. |
| `ota_apply` | to one device | Carries `{ version, url }` from `POST /satellite/{id}/ota/apply`. |
| `state_update` | to UI fan-out subscribers | Mirrors `GET /satellite/{id}/state` deltas — emitted on registration, status transition, config change, OTA progress, removal. The platform-neutral CLI `sat-cli watch` consumes this via the existing in-process subscription, then re-emits it on its stdout NDJSON stream. |
| `log_entry` | to UI fan-out subscribers | Same shape as the client→server `log_entry`; relays device-emitted entries to operator subscribers. |
| `barge_in` | to one device | Tell the device to stop local playback (call-scoped UI signal); MAY also be carried over the voice SCTP datachannel for lower latency. |

## Reserved subscriber endpoint (UI fan-out)

The same WS URL accepts an operator-side "subscriber" mode where the first
frame is `{type: "subscribe_device", device_id}` (or
`{type: "subscribe_fleet"}`) and subsequent traffic is server→client only.
This is **not** part of the v1 spec surface for operator surfaces — `sat-cli`
uses the REST + SSE pair (constitution III rule on operator transport).
It's documented here only because the existing implementation already
supports it for tests; it stays internal.

## Version

`management-ws.md` shares the v1.0.0 semver of `management-api.yaml` and
`cli-contract.md` (R-13). Additive frame types bump minor; removed or
re-shaped existing frames bump major and require coordinated CLI + REST
bumps.

## Non-goals

- This protocol does NOT carry voice/Opus — that is the per-session
  WebRTC PC (`/webrtc/offer`, `/webrtc/candidate`).
- This protocol does NOT carry operator log subscription — operators use
  SSE (`GET /satellite/{id}/logs?follow=true`).
- This protocol does NOT branch on which `AgentPlatform` is active. The
  platform plugin is server-side and invisible here.
