# Contract: Management Plane (`:8643`)

Served by the adapter's management aiohttp site. Device-agnostic (constitution
II): identical for `rpi`/`esp32`/`browser`. Security deferred (no auth) — out
of scope per spec Assumptions. Source of truth: design Appendix A.

## REST — Registration & lifecycle

```
POST /satellite/register
  req : { device_id, device_type, capabilities, firmware_version, ip_address }
  res : 200 { session_token, management_server_url, default_config }
  note: client calls on boot; registry upserts ConnectedClient → online

GET  /satellite/list
  res : 200 [ { device_id, device_type, status, last_seen,
                firmware_version, active_routing_mode, webrtc_state } ]

GET  /satellite/{id}/state    res: 200 <SatelliteState>  | 404
DELETE /satellite/{id}        res: 204  (removed; may re-register)
```

## REST — Configuration

```
GET  /satellite/{id}/config          res: 200 <running SatelliteConfig>
POST /satellite/{id}/config          req: <partial config> → 200 <applied config>
GET  /satellite/{id}/config/schema   res: 200 <JSON Schema>
```

## SSE — Logs

```
GET /satellite/{id}/logs ?since=&level=&source=vad|wakeword|asr|tts|webrtc|system
GET /satellite/logs       ?device_id=        (aggregate)
  res: text/event-stream of LogEntry
```

## Commands & OTA

```
POST /satellite/{id}/command
  req: { command: reboot|restart_voice|restart_manager|reset_config|factory_reset }
  res: 200 { accepted, scheduled_at }
POST /satellite/{id}/ota/check   res: { update_available, latest_version, changelog_url }
POST /satellite/{id}/ota/apply   req:{version,url} res:{ started_at, estimated_duration }
GET  /satellite/{id}/ota/manifest res:{ version,url,sha256,signature,changelog }
```

(OTA endpoints exist in the contract for all devices; `browser` has no OTA.)

## Control WebSocket — `WS /satellite/ws` (always-on)

The §2.1 control plane. Up even with no active call (presence, config push,
"start a call", logs, OTA). Auto-reconnect w/ exponential backoff. Durable
control MUST NOT move to a WebRTC data channel (constitution III).

```
client → server : register, heartbeat (state snapshot every heartbeat_interval),
                   subscribe_device, unsubscribe_device, device_command,
                   log_entry, ota_progress
server → client : state_update, log_entry, config_changed,
                   command_response, ota_progress
```

## Conformance tests (contract/)

- Register upserts client to `online`; `/list` reflects it.
- Missed heartbeats flip `status → offline`; re-register restores `online`.
- `POST /config` returns applied config and pushes `config_changed` on WS.
- Logs SSE filters by `level`/`source`/`device_id`.
- WS stays connected and serves messages with **no active voice session**
  (SC-006 / constitution III).
