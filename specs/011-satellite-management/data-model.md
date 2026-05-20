# Data Model: Satellite Management

**Feature**: `011-satellite-management` · **Plan**: [plan.md](./plan.md) ·
**Date**: 2026-05-20

This document specifies entities, fields, relationships, validation rules,
and lifecycle transitions for this feature. It **extends** (does not
replace) the existing models in
[src/hermes_satellite_adapter/models.py](src/hermes_satellite_adapter/models.py)
(design Appendix B), which this feature renames to
`src/satellite_core/models.py` per the constitution v2.0.0 plan
restructure. All models are stdlib `@dataclass` + `Enum` per R-4.

## 1. Existing models (carried in, summary only)

These are already implemented and consumed unchanged:

- `ClientStatus` (online | offline | connecting | error)
- `SessionState` (idle | listening | thinking | speaking | error)
- `EchoStrategy` (hardware_xmos | software_speex | half_duplex | browser_aec3)
- `LogLevel`, `LogSource` (debug/info/warn/error · vad/wakeword/asr/tts/webrtc/system/ota)
- `SatelliteConfig` — wake_word, wake_word_engine, vad_threshold, vad_mode,
  routing_mode, input_volume, output_volume, echo_strategy, webrtc_enabled,
  log_level, heartbeat_interval
- `ConnectedClient` — device_id, device_type, status, last_seen,
  firmware_version, ip_address, connection_type, config
- `VoiceSession`, `LogEntry`

## 2. New / extended entities

### 2.1 `AdoptionState` (new enum)

```text
AdoptionState = pending | adopted
```

- `pending`: device has registered but not yet claimed/named by an operator.
- `adopted`: an operator has called `POST /satellite/{id}/adopt` with a name.

Lifecycle transitions (per R-7):

```text
[absent] --register--> pending --adopt(name)--> adopted
adopted --DELETE /satellite/{id}--> [absent]
adopted --register(factory_reset=true)--> pending     (R-7)
```

`pending` devices live only in memory and are repopulated by the device's
next register. `adopted` devices are persisted to `~/.satellite/state.json`
(R-5).

### 2.2 `PendingDevice` (new)

In-memory record for a registered-but-not-yet-adopted device. Lives in
`Registry._pending: dict[str, PendingDevice]`.

```text
PendingDevice
  device_id: str            # stable id reported by the device (NVS / hardware)
  device_type: str          # rpi | esp32 | browser
  firmware_version: str
  ip_address: str
  first_seen: float         # epoch
  last_seen: float          # epoch — updated on re-register heartbeats while pending
```

Validation:

- `device_id` non-empty; unique across `_pending` ∪ `_clients`.
- `device_type` ∈ {`rpi`, `esp32`, `browser`}. Unknown values are rejected.
- A `device_id` cannot be both `pending` and `adopted` at the same time.

### 2.3 `ConnectedClient` (extended)

Existing record gains:

```text
+ name: str | None              # human-set during adopt; required once adopted
+ adoption_state: AdoptionState # always 'adopted' for entries in _clients
+ config_version: int           # monotonic, bumped on every POST /config (R-11)
+ config_updated_at: float
+ ota_state: str                # idle | checking | downloading | flashing | rebooting | failed | rolled_back
+ ota_version: str | None
+ ota_job_id: str | None
```

Validation:

- `name` MUST be set and non-empty for `adopted` rows.
- `config_version` strictly increases.
- `ota_state` matches `OtaState` (below).

### 2.4 `OtaState` (new enum)

```text
OtaState = idle | checking | downloading | flashing | rebooting | failed | rolled_back
```

Per-device state. The supervised happy path: `idle → checking → downloading
→ flashing → rebooting → idle` (re-register on new version observed).
Failure path: `flashing → failed` or `rebooting → rolled_back`. The
gateway records device-reported transitions; it does not infer them.

### 2.5 `OtaJob` (new)

In-memory while active; emitted as `log_entry` rows with `source="ota"` for
durable record (R-6, R-3).

```text
OtaJob
  job_id: str               # uuid4 — surfaced by /ota/apply, consumed by CLI follow
  device_id: str
  target_version: str
  state: OtaState           # mirrors ConnectedClient.ota_state
  started_at: float
  ended_at: float | None
  result: "success" | "rolled_back" | "failed" | None
  failure_reason: str | None
```

State transitions: writable only by the management plane in response to
device-reported `POST /satellite/{id}/ota/status { state, version, result?,
reason? }` events.

### 2.6 `OtaManifest` (new)

Static, loaded from `~/.satellite/firmware/<device_type>/manifest.json` (R-6).

```text
OtaManifest
  device_type: str          # rpi | esp32     (NOT browser — see invariant below)
  version: str              # semver
  url: str                  # http(s) URL or file:// served by /ota/manifest
  sha256: str               # hex, lowercase, 64 chars
  signature: str | None     # optional firmware signature (verified device-side)
  changelog: str            # markdown
```

Invariant: a manifest with `device_type == "browser"` MUST be rejected at
load time. Asserted in `tests/contract/test_ota.py` and
`tests/unit/test_no_embedded_engines.py`-adjacent constitution gate.

### 2.7 `CommandVerb` (new enum)

```text
CommandVerb = reboot | restart_voice | restart_manager | reset_config
            | factory_reset | mute | unmute | identify
```

Fixed enum. Anything else is rejected at the REST layer with `400`. The
client (CLI/skill) is responsible for confirming destructive verbs
(`factory_reset`) before sending — the server does not prompt (R-14).

### 2.8 `CommandRequest` / `CommandResponse` (new)

```text
CommandRequest   { command: CommandVerb,  args?: dict[str, Any] }
CommandResponse  { accepted: bool, scheduled_at: float, reason?: str }
```

`args` is reserved for command-specific payloads (e.g. `identify` could
take `duration_s`). Unknown args are ignored, not rejected (additive
contract evolution per R-13).

### 2.9 `RegistrySnapshot` (persistence record, R-5)

Atomic JSON written to `~/.satellite/state.json`:

```text
RegistrySnapshot
  schema_version: int = 1
  saved_at: float
  clients: list[ConnectedClient.to_dict()]    # adopted only — pending are not persisted
  device_limit: int                            # snapshot of the configured limit at write time
```

Read on `ManagementService.__init__`; if the file is missing or
`schema_version` is unknown, the registry starts empty and the next adopt
writes a fresh snapshot.

## 3. Relationships

```text
SatelliteAdapterConfig
   │ defines defaults & limits
   ▼
Registry ────────► PendingDevice       (in-memory only)
   │                    │
   │   adopt()          │
   ▼                    ▼
ConnectedClient ◄── promoted on /adopt
   │ has-a
   ├─► SatelliteConfig  (versioned, persisted in RegistrySnapshot)
   ├─► VoiceSession*    (zero-or-one active; existing model, unchanged)
   └─► OtaJob*          (zero-or-one active)

OtaService ─loads─► OtaManifest        (per device_type, from ~/.satellite/firmware/)

LogSink (existing) ─emits─► LogEntry   (consumed by /logs and OTA progress)
```

`*` cardinality means "at most one active".

## 4. Validation rules summary (cross-cutting)

| Rule | Where enforced | Test |
|---|---|---|
| `device_id` unique across pending + adopted | `Registry.register / adopt` | `tests/integration/test_adoption_flow.py` |
| `device_type ∈ {rpi, esp32, browser}` | OpenAPI + `Registry` | `tests/contract/test_register.py` |
| browser devices reject any `/ota/*` call | `ota.py` dispatch + endpoint guard | `tests/contract/test_ota.py` |
| `name` required for adopted clients | `Registry.adopt` | `tests/contract/test_adopt.py` |
| `config_version` strictly increases | `ManagementService.post_config` | `tests/integration/test_concurrent_config.py` |
| device-limit only applies at `adopt`, not `register` | `ManagementService.adopt` | `tests/integration/test_device_limit.py` |
| factory_reset re-registers as pending | `Registry.register(factory_reset=True)` | `tests/integration/test_adoption_flow.py` |
| `CommandVerb` enum closed | OpenAPI + `Registry.command` | `tests/contract/test_command.py` |
| OTA manifest sha256 64-hex lowercase | `OtaService.load_manifest` | `tests/unit/test_ota_manifest.py` |

## 5. Persistence behavior

- **Write trigger**: any of `adopt`, `delete`, `post_config`,
  `ota_state` transition to a terminal state.
- **Atomicity**: write to `~/.satellite/state.json.tmp`, `os.replace()`.
- **Concurrency**: one `asyncio.Lock` in `persistence.py`; writes are
  serialized within the gateway process. Multi-process gateway is out of
  scope (Hermes runs as one process per host).
- **Schema migration**: `schema_version` field reserved; v1 is the only
  current value. Unknown versions → empty start (no destructive migration).

## 6. What this model deliberately does NOT include

- No table of devices by user/tenant — single-tenant LAN deployment (spec
  Assumptions / constitution governance).
- No audit log of commands beyond the standard `LogEntry` ring — commands
  show up as `LogEntry { source="system", level="INFO", message="command:
  <verb> by <surface>" }`, reused, not re-modeled.
- No CRDT / vector clocks — last-writer-wins with `config_version` is the
  R-11 decision.
