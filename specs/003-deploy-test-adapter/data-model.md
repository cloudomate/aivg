# Phase 1 Data Model: Deploy & Live-Test

Operational entities (no application DB). These track the deployment and the
live-test result so rollback and pass/fail are deterministic.

## Entity: Deployment

| Field | Notes |
|-------|-------|
| `deploy_id` | timestamp/id of this deployment attempt |
| `adapter_version` | git SHA of the vendored 001 package deployed |
| `host` | target (`ssh hermes`) |
| `plugin_path` | `…/hermes-agent/plugins/platforms/satellite_webrtc/` |
| `config_backup_ref` | path of the `config.yaml.bak.<ts>` taken before change |
| `state` | `preflight` → `confirmed` → `applied` → `verified` \| `failed` \| `rolled_back` |
| `mutations` | ordered list of host changes made (for precise rollback) |

**Invariant**: no transition past `confirmed` without an explicit operator
confirmation (FR-004); `config_backup_ref` MUST exist before `applied`
(FR-003).

## Entity: Gateway State Backup

| Field | Notes |
|-------|-------|
| `config_yaml_backup` | byte copy of `~/.hermes/config.yaml` pre-change |
| `plugin_absent` | record that the plugin dir did not exist pre-deploy (so rollback removes it) |
| `pre_existing_platforms` | list captured pre-deploy for the regression check |
| `taken_at` | timestamp |

Rollback target: restoring `config_yaml_backup` + removing the plugin dir MUST
reproduce `pre_existing_platforms` behaviour exactly (SC-005/SC-006).

## Entity: Electron Test Client

| Field | Notes |
|-------|-------|
| `device_id` | e.g. `electron-test-1` |
| `mgmt_url` / `webrtc_url` | SSH-forwarded host ports (8643/8644) |
| `mic_permission` | granted/denied (denied ⇒ test cannot pass, edge case) |
| `mode` | `push_to_talk` (v1) |
| `echo_strategy` | `browser_aec3` (Chromium AEC) |

## Entity: Live Test Session

| Field | Notes |
|-------|-------|
| `session_id` | from the deployed adapter registry |
| `state_timeline` | idle→listening→thinking→speaking→… transitions observed |
| `eos_to_reply_ms` | measured end-of-speech → start-of-spoken-reply (SC-002) |
| `barge_in_stop_ms` | measured if barge-in exercised (SC-003) |
| `provider_used` | the gateway's actual STT/TTS providers (parity, SC-004) |
| `logs_ref` | per-session log location on the gateway |

## Entity: Test Result

| Field | Notes |
|-------|-------|
| `result` | `pass` \| `fail` |
| `eos_to_reply_ms` | recorded latency |
| `regression_check` | `0 regressions` required (SC-005) |
| `notes` | failure cause / observations |
| `deploy_id` | links result to the Deployment under test |

## State transitions (deployment lifecycle)

```
preflight --ok--> (await confirm) --confirm--> backup --> apply -->
  verify --pass--> verified --(test)--> Test Result
  verify --fail--> rollback --> rolled_back
apply --interrupted--> {prior state restorable via backup | flagged rollback-required}  (FR-006)
verified --rollback requested--> rolled_back   (restore backup + remove plugin)
```

## Non-entities

The Hermes gateway, agent, STT/TTS providers, and feature 001's adapter
internals are reused, not modeled here. The vendored `hermes-agent` skill
(feature 002) MAY drive/validate config but is not data owned by this feature.
