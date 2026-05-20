---
description: "Task list for feature 011-satellite-management"
---

# Tasks: Satellite Management — Onboard, Configure & OTA

**Input**: Design documents from [/specs/011-satellite-management/](.)
**Constitution**: v2.0.0 (Principle IV — Reuse the Upstream Agent Platform)
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Tests**: included — the plan calls out three test tiers
(`tests/contract/`, `tests/integration/`, `tests/unit/`) and the
constitution v2.0.0 binding gate (`test_no_platform_branching.py`,
`test_agent_platform_seam.py`).
**Organization**: tasks are grouped by user story (US1–US5). Setup +
Foundational phases block all stories; each story phase is independently
testable.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: parallelizable (different files, no incomplete deps)
- **[Story]**: required on user-story tasks only

## Path conventions

Single-repo Python project. Source under `src/`, tests under `tests/`,
skills under `skills/`. New CLI binary `sat-cli` lives in `src/sat_cli/`.
The rename target package is `satellite_core` (from
`hermes_satellite_adapter`).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: rename the existing package, scaffold the new packages and
skill folders, wire the build.

- [X] T001 Add new package directories: `src/satellite_core/`, `src/satellite_core/management/`, `src/satellite_core/platforms/`, `src/satellite_core/platforms/hermes/`, `src/satellite_core/platforms/openclaw/`, `src/satellite_core/webrtc/`, `src/sat_cli/`, `src/sat_cli/onboard/`, `skills/hermes-agent/`, `skills/openclaw/` (empty `__init__.py` in each Python dir).
- [X] T002 Move existing files to their new paths per the migration table in [plan.md](./plan.md#structure-decision): `src/hermes_satellite_adapter/adapter.py` → `src/satellite_core/adapter.py`; `config.py`, `models.py`, `registry.py`, `logsink.py` → `src/satellite_core/`; `signaling.py`, `session.py`, `media.py`, `streamasm.py` → `src/satellite_core/webrtc/`; `management.py` → `src/satellite_core/management/service.py` + `management/app.py` (split); `hermes_bridge.py` + `textseg.py` → `src/satellite_core/platforms/hermes/`; `turnlatency.py` → `src/satellite_core/turnlatency.py`. Update all intra-package imports.
- [X] T003 Write `src/hermes_satellite_adapter/__init__.py` as a compatibility shim that re-exports the moved symbols from `satellite_core` with a `DeprecationWarning("hermes_satellite_adapter is renamed to satellite_core; remove this import path after the 011 migration completes")`.
- [X] T004 [P] Update `pyproject.toml`: rename `[project].name` to `satellite-core`, add `sat_cli` to `[tool.setuptools.packages.find]`, add `[project.scripts] sat-cli = "sat_cli.cli:app"`, add new deps `typer>=0.12`, `httpx>=0.27`, `bleak>=0.22`, `rich`, `aiohttp-sse`. Keep `aiortc` and `aiohttp`.
- [X] T005 [P] Update all `tests/**/*.py` import paths from `hermes_satellite_adapter...` → `satellite_core...` and `satellite_core.platforms.hermes...` for the Hermes bridge. Don't change test logic.
- [X] T006 [P] Create `~/.satellite/` directory convention: write `docs/satellite-data-dir.md` documenting `~/.satellite/config.yaml`, `~/.satellite/state.json`, `~/.satellite/firmware/<device_type>/manifest.json`. (Documentation only; the dir is created at runtime.)
- [X] T007 [P] Configure `ruff` + `black` for the new packages (already in `[tool.ruff]` / `[tool.black]` — extend `target-version` checks; no new config files).

**Checkpoint**: package rename + scaffolding done; existing tests pass against new import paths via the compat shim. No new endpoints yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: install the v2.0.0 plugin seam, the platform-neutrality
gates, persistence, and the model additions everything else depends on.
**No user story work can begin until this phase is complete.**

- [X] T008 Create the `AgentPlatform` Python `Protocol` in `src/satellite_core/platforms/base.py` matching the interface in [contracts/agent-platform.md](./contracts/agent-platform.md): `name`, `startup`, `transcribe`, `agent_step`, `synthesize`, `endpoint`, `shutdown`. Include `PluginRegistry.load(name) -> AgentPlatform`.
- [X] T009 Wrap the moved Hermes bridge code (`src/satellite_core/platforms/hermes/bridge.py`) in a module-level `PLATFORM: AgentPlatform = HermesAgentPlatform()` in `src/satellite_core/platforms/hermes/__init__.py`. The class implements the six methods by delegating to the existing bridge functions; no behavior change.
- [X] T010 Create the OpenClaw stub at `src/satellite_core/platforms/openclaw/__init__.py`: `class OpenClawAgentPlatform` whose methods all `raise NotImplementedError("OpenClaw plugin: planned for a future feature")`; `PLATFORM: AgentPlatform = OpenClawAgentPlatform(); PLATFORM.name = "openclaw"`. Add `skills/openclaw/README.md` saying the plugin is a stub.
- [~] T011 [P] Extend `src/satellite_core/config.py` to read `~/.satellite/config.yaml` `platform: <name>` and load the plugin via `PluginRegistry.load(name)`. Unknown name → fatal startup error with a clear message. Default `~/.satellite/config.yaml` shipped at `docs/sample-satellite-config.yaml`.
- [X] T012 Add new model classes/enums in `src/satellite_core/models.py` per [data-model.md](./data-model.md): `AdoptionState` enum, `PendingDevice` dataclass, `OtaState` enum, `OtaJob` dataclass, `OtaManifest` dataclass, `CommandVerb` enum, `CommandRequest`/`CommandResponse` dataclasses, `RegistrySnapshot` dataclass. Extend `ConnectedClient` with `name`, `adoption_state`, `config_version`, `config_updated_at`, `ota_state`, `ota_version`, `ota_job_id`.
- [X] T013 Add `Registry._pending: dict[str, PendingDevice]` in `src/satellite_core/registry.py`; promote-on-adopt method; demote-on-`factory_reset=true` register; bump `config_version` on every `update_config()`; enforce `device_id` uniqueness across pending ∪ adopted.
- [X] T014 Create `src/satellite_core/persistence.py` with atomic JSON dump/load of `RegistrySnapshot` to `~/.satellite/state.json` (tmp+rename). Single `asyncio.Lock`. Hook into `Registry` so every mutating method writes after committing in-memory.
- [X] T015 [P] Create `tests/unit/test_no_platform_branching.py` — static check (AST-walk `src/satellite_core/` excluding `platforms/`) for any `import satellite_core.platforms.<concrete>` or string `platform_name == "hermes"`/`"openclaw"`. **This is the constitution v2.0.0 binding gate.** Failing this test blocks the merge.
- [X] T016 [P] Create `tests/unit/test_agent_platform_contract.py` — asserts each plugin module under `satellite_core.platforms.<name>` exposes `PLATFORM: AgentPlatform`; asserts `PLATFORM.name == "<name>"`; asserts the Protocol's required methods exist; uses `typing.get_type_hints` to assert signatures match.
- [ ] T017 [P] Create `tests/integration/test_agent_platform_seam.py` — add a fake `EchoPlatform` under `tests/fixtures/platforms/echo/__init__.py`, set `platform: echo` in a test config, run the full register → voice-turn loop via the adapter, and `assert not any(m.startswith("satellite_core.platforms.hermes") for m in sys.modules)`. Binding gate for v2.0.0 Principle IV.
- [X] T018 [P] Create `tests/unit/test_persistence.py` — round-trip dump/load; partial-write atomicity (kill mid-write → file is either old or new, never corrupted); schema_version unknown → empty start.
- [ ] T019 Update [src/hermes_satellite_adapter/__main__.py](src/hermes_satellite_adapter/__main__.py) (in its new path `src/satellite_core/__main__.py`) so the adapter loads the active platform via `config.load_platform()` instead of importing `hermes_bridge` directly. **First call site that goes through the seam.**

**Checkpoint**: rename + plugin seam shipped; existing voice loop still works (via the Hermes plugin); neutrality gates green. No new operator-facing endpoints yet.

---

## Phase 3: User Story 1 — Fleet visibility (Priority: P1) 🎯 MVP

**Goal**: an operator can answer "is the fleet working, and which device needs attention?" via `sat-cli` (and via the Hermes agent skill that wraps it), with live updates without re-invocation.

**Independent Test**: with one registered device, `sat-cli list --json` reports it; `sat-cli watch` reflects an offline transition within one heartbeat without re-running; `sat-cli logs <device> --follow` streams entries live.

### Tests (contract + unit)

- [X] T020 [P] [US1] Add `tests/contract/test_list_state_logs.py` extensions: validate `GET /satellite/list` accepts `?state={all,adopted,pending}` and returns `DeviceSummary[]` matching [contracts/management-api.yaml](./contracts/management-api.yaml).
- [X] T021 [P] [US1] Add `tests/contract/test_log_sse.py`: `GET /satellite/{id}/logs?follow=true` responds `text/event-stream`; one `data:` line per LogEntry; filters `level`/`source` honored; reconnect `Last-Event-Id` resumes.
- [X] T022 [P] [US1] Add `tests/unit/test_cli_json_output.py`: shape of `sat-cli list --json` matches the envelope in [contracts/cli-contract.md](./contracts/cli-contract.md) (`ok`, `data`, `error`, `v`); golden-file the v1 schema for `list`, `device get`, `logs`, `watch`.
- [~] T023 [P] [US1] Add `tests/integration/test_watch_ndjson.py`: spin up a fake gateway emitting two state changes, run `sat-cli watch --json` as a subprocess, assert two NDJSON lines arrive with the right `event` shape and ordering.

### Implementation

- [X] T024 [US1] Extend `ManagementService.list_clients()` in `src/satellite_core/management/service.py` to accept `state: Literal["all","adopted","pending"]` (default `all`) and merge `Registry._pending` records with adopted; map output to `DeviceSummary`.
- [X] T025 [US1] Add `?state=` query handling in the aiohttp wiring at `src/satellite_core/management/app.py` for `GET /satellite/list`.
- [X] T026 [US1] Add `src/satellite_core/management/log_sse.py` — an SSE iterator over `LogSink`'s existing in-memory ring + a live subscription. Honors `since`, `level`, `source`, `device_id` filters; emits each `LogEntry` as `data: {json}\n\n`; sends `id:` headers so `Last-Event-Id` resumes.
- [X] T027 [US1] Wire SSE into `app.py`: `GET /satellite/{id}/logs?follow=true` and `GET /satellite/logs?follow=true` switch to the SSE iterator when `follow=true`, else return the existing JSON array.
- [X] T028 [US1] Create `src/sat_cli/cli.py` Typer app skeleton with the global flags from [cli-contract.md](./contracts/cli-contract.md): `--gateway`, `--json`, `--yes`, `--timeout`, `--verbose`, `--no-color`. Add `--version` and `--contract-version`.
- [X] T029 [US1] Create `src/sat_cli/rest_client.py` — `httpx.AsyncClient` wrapper with timeout, base URL from `--gateway`, error mapping (network → `gateway_unreachable`, 4xx/5xx → typed envelope).
- [X] T030 [US1] Create `src/sat_cli/output.py` — Rich human formatters + the v1 JSON envelope writer (`emit_ok`, `emit_error`); NDJSON helper for streaming commands.
- [X] T031 [US1] [P] Create `src/sat_cli/exit_codes.py` constants matching [cli-contract.md](./contracts/cli-contract.md) and a `map_error_to_exit_code(code: str) -> int` helper.
- [X] T032 [US1] Implement `sat-cli list` (+ `--state` flag) in `src/sat_cli/cli.py` calling `GET /satellite/list`; human mode = Rich table with status dots + STT/TTS/Wake health chips; JSON mode = envelope-wrapped `DeviceSummary[]`.
- [X] T033 [US1] Implement `sat-cli device get DEVICE_ID` calling `GET /satellite/{id}/state`.
- [X] T034 [US1] Implement `sat-cli logs DEVICE_ID [--follow] [--level] [--source] [--since]` in `src/sat_cli/stream.py` + a thin command in `cli.py`. Follow mode iterates the SSE stream via `httpx` and emits one NDJSON envelope per LogEntry.
- [X] T035 [US1] Implement `sat-cli fleet logs [--follow] [--device] [--level] [--source]` against `GET /satellite/logs`.
- [X] T036 [US1] Implement `sat-cli watch [--device]` consuming the existing in-process state subscription via SSE (or a thin REST poll fallback) and emitting one NDJSON envelope per `state_update`.
- [X] T037 [P] [US1] Write `skills/hermes-agent/SKILL.md` (Hermes skill schema mirroring `.claude/skills/hermes-agent/SKILL.md`) — body is "list, watch, logs" examples that all shell out to `sat-cli --json ...`. Write `skills/hermes-agent/README.md` documenting install path `~/.hermes/skills/satellite-management/`.

**Checkpoint MVP**: an operator can see the fleet, drill into a device, watch the fleet live, and tail logs — both via `sat-cli` and via the Hermes agent skill that wraps it. The plugin seam is in use end-to-end.

---

## Phase 4: User Story 2 — Onboard a new satellite (Priority: P1)

**Goal**: from a BLE-capable host, the operator runs `sat-cli onboard` to bring a factory-state device into the fleet via Improv-over-BLE → REST register → adopt → default config.

**Independent Test**: a factory-state device + a host with `sat-cli` ends at a named, default-configured fleet member, with no keyboard ever on the device, within 5 minutes. Failures produce specific exit codes (4 for BLE/Improv, 1 for limit).

### Tests

- [ ] T038 [P] [US2] Add `tests/contract/test_adopt.py`: `POST /satellite/{id}/adopt` requires `name`; returns 404 for unknown id; returns 409 `already_adopted` for already-adopted; returns 409 `device_limit_reached` at limit.
- [ ] T039 [P] [US2] Add `tests/integration/test_adoption_flow.py`: register → pending shows up in `list?state=pending` → adopt promotes → re-register without `factory_reset` keeps adopted → re-register with `factory_reset=true` demotes back to pending (R-7). Persistence file matches in-memory state at every step.
- [ ] T040 [P] [US2] Add `tests/integration/test_device_limit.py`: register 11 devices with `device_limit=10`, adopt 10, the 11th adopt returns 409 `device_limit_reached`; pending count is unrestricted (R-12).
- [ ] T041 [P] [US2] Add `tests/unit/test_improv_ble.py`: against a mock BLE peripheral, the Improv-Wifi GATT framing (state, error, RPC command, RPC result) is correct; failure paths produce specific `error.code` values (`ble_unavailable`, `improv_timeout`, `wifi_join_failed`).
- [ ] T042 [P] [US2] Add `tests/integration/test_cli_roundtrip.py`: `sat-cli list` then `sat-cli onboard` (BLE mocked) → device adopted → `sat-cli device get` returns the same state. All under `--json`.

### Implementation

- [ ] T043 [US2] Extend `Registry` (`src/satellite_core/registry.py`): `register(...)` stores in `_pending` for first-time ids and refreshes `last_seen` for adopted ids; `register(factory_reset=True)` removes from `_clients` and re-adds to `_pending`.
- [ ] T044 [US2] Add `ManagementService.adopt(device_id, name, config_overrides)` in `src/satellite_core/management/service.py`: returns `404` if not pending, `409 already_adopted` if already adopted, `409 device_limit_reached` if `len(_clients) >= cfg.device_limit`. On success, promote, persist (T014), broadcast `config_changed` over WS, return `DeviceState`.
- [ ] T045 [US2] Create `src/satellite_core/management/adopt.py` (thin module owning the adopt logic; service.py delegates to it) for clarity and to keep service.py < 500 LOC.
- [ ] T046 [US2] Wire `POST /satellite/{id}/adopt` and `DELETE /satellite/{id}` (already exists; extend to clean up persistence) in `src/satellite_core/management/app.py`.
- [ ] T047 [US2] Add the `factory_reset` field to the `RegisterRequest` handling in `service.register()`; default `False`; when `True` and the device is currently adopted, call `Registry.demote_to_pending()`.
- [ ] T048 [US2] Add `satellite.device_limit` (default 10) to `SatelliteAdapterConfig` in `src/satellite_core/config.py`.
- [ ] T049 [US2] Create `src/sat_cli/onboard/improv_ble.py` — `bleak`-based BLE central; speaks the Improv-Wifi GATT service (state, error, RPC command, RPC result UUIDs); functions `scan(timeout)`, `connect(addr)`, `send_credentials(ssid, password, gateway_hint)`, `wait_for_wifi_join(timeout)`. Specific errors for `ble_unavailable`, `improv_timeout`, `wifi_join_failed`.
- [ ] T050 [US2] Create `src/sat_cli/onboard/flow.py` orchestrating: BLE scan → connect → send_credentials → wait_for_wifi_join → poll `GET /satellite/list?state=pending` for the new device id (timeout 90 s) → `POST /satellite/{id}/adopt { name }`. Map every failure to a typed `error.code` + exit code (4 for BLE/Improv, 1 for limit, 3 for gateway, 2 for offline, 0 for success).
- [ ] T051 [US2] Implement `sat-cli onboard --ssid --password [--gateway] [--name] [--scan-timeout] [--register-timeout]` in `src/sat_cli/cli.py` calling `onboard.flow.run(...)` and streaming progress (under `--json`, one NDJSON envelope per phase: `scanning`, `connecting`, `sending_credentials`, `wifi_join`, `awaiting_register`, `adopted`).
- [ ] T052 [P] [US2] Extend `skills/hermes-agent/SKILL.md` with an "onboard" example (operator says "onboard a new satellite called bedroom" → skill shells `sat-cli onboard ...`).

**Checkpoint**: onboarding works end-to-end from CLI and agent skill; tests prove failures surface specific reasons; persistence survives a gateway restart mid-flow (pending devices are repopulated by the next register).

---

## Phase 5: User Story 3 — Configure a satellite (Priority: P2)

**Goal**: operators tune speaker volume, mic gain, wake word + sensitivity, TTS voice, VAD, LED-ring behavior from `sat-cli`/skill; changes apply on the device within 5 s and survive reboot; concurrent writes converge deterministically.

**Independent Test**: from CLI: write a setting, observe the device adopt it, reboot, observe survival. From the skill: same. Concurrent writes via CLI + a second writer don't corrupt the file (R-11).

### Tests

- [ ] T053 [P] [US3] Add `tests/contract/test_config.py`: `POST /satellite/{id}/config` with no `If-Match` = last-writer-wins, bumps `config_version`; with stale `If-Match` returns 409; offline device returns 503 `device_offline` unless `?queue=true`; `GET /config/schema` returns a JSON Schema object.
- [ ] T054 [P] [US3] Add `tests/integration/test_concurrent_config.py`: two concurrent writers (CLI subprocess + direct REST), neither sees corruption; final running config matches one of the two writes and `config_version` increased by 2.
- [ ] T055 [P] [US3] Extend `tests/unit/test_cli_json_output.py` golden files for `device config get/set/schema`.

### Implementation

- [ ] T056 [US3] Extend `ManagementService.post_config()` in `src/satellite_core/management/service.py` to honor optional `If-Match: <config_version>` (raise 409 on mismatch), bump `config_version`, set `config_updated_at`, persist via T014, broadcast `config_changed { version, config }` on the device WS.
- [ ] T057 [US3] Add `GET /satellite/{id}/config/schema` handler in `src/satellite_core/management/app.py` returning a JSON Schema. The schema is device-type-shaped (the same shape for now — extend later per `device_type` only inside `models.py`, never in the dashboard, constitution II).
- [ ] T058 [US3] Implement `device_offline` refusal in `post_config()`: if `client.status != ONLINE` and `?queue=true` is absent → 503 with `error.code = device_offline`; with `?queue=true` → enqueue on `Registry._pending_writes` and apply on next `register/heartbeat`.
- [ ] T059 [US3] Implement `sat-cli device config get DEVICE_ID` in `src/sat_cli/cli.py`.
- [ ] T060 [US3] Implement `sat-cli device config set DEVICE_ID [--field key=value]... [--from-file PATH] [--if-match N] [--queue]`. JSON envelope on output; map 409 → exit 1 / `error.code = config_conflict`.
- [ ] T061 [US3] Implement `sat-cli device config schema DEVICE_ID`.
- [ ] T062 [P] [US3] Extend `skills/hermes-agent/SKILL.md` with examples for "set kitchen wake word to hey jarvis" and "show the bedroom config" → both shell `sat-cli ...`.

**Checkpoint**: live configuration round-trips through all surfaces; concurrent writes are deterministic; offline writes either refuse cleanly or queue.

---

## Phase 6: User Story 4 — OTA updates (Priority: P2)

**Goal**: operators check + apply firmware updates per device, with supervised progress and safe failure (rollback); browser explicitly excluded.

**Independent Test**: on an older firmware version, `sat-cli ota check`/`apply --follow` reports progress to `success`; simulate flash failure and the device returns to working firmware with a specific failure reason. Browser device returns `browser_not_ota_eligible`.

### Tests

- [ ] T063 [P] [US4] Add `tests/contract/test_ota.py`: `/ota/check`, `/ota/apply`, `/ota/status`, `/ota/manifest` match [contracts/management-api.yaml](./contracts/management-api.yaml); browser device returns 409 `browser_not_ota_eligible` on every OTA endpoint.
- [ ] T064 [P] [US4] Add `tests/integration/test_ota_rollback.py`: happy path (success); device reports `failed` → exit 5 + `error.code = ota_failed`; device reports `rolled_back` → exit 5 + `error.code = rolled_back`; OTA progress flows through the SSE log stream as `source="ota"`.
- [ ] T065 [P] [US4] Add `tests/unit/test_ota_manifest.py`: `sha256` 64-hex-lowercase enforced; `device_type == "browser"` rejected at load.

### Implementation

- [ ] T066 [US4] Create `src/satellite_core/management/ota.py` — `OtaService.load_manifest(device_type)`, `.check(device_id)`, `.apply(device_id, version) -> OtaJob`. Manifests loaded from `~/.satellite/firmware/<device_type>/manifest.json`. Browser device → raise `BrowserNotOtaEligible`.
- [ ] T067 [US4] Wire `POST /satellite/{id}/ota/check`, `POST /satellite/{id}/ota/apply`, `POST /satellite/{id}/ota/status` (device-reported), `GET /satellite/{id}/ota/manifest` in `src/satellite_core/management/app.py`. `apply` emits an `ota_apply { version, url }` frame on the device WS.
- [ ] T068 [US4] Emit OTA progress events into `LogSink` with `source="ota"` and structured `metadata` (state, pct, version) on every device-side `ota_status` post; the existing SSE log stream (T026) carries them.
- [ ] T069 [US4] Implement `sat-cli ota check DEVICE_ID` and `sat-cli ota manifest DEVICE_ID` in `src/sat_cli/cli.py`.
- [ ] T070 [US4] Implement `sat-cli ota apply DEVICE_ID VERSION [--follow]` — without `--follow`, returns the `OtaJob`; with `--follow`, opens the SSE log stream filtered to `source=ota` and emits one NDJSON envelope per progress event; exits on terminal `result`. Maps `failed`/`rolled_back` to exit 5.
- [ ] T071 [P] [US4] Extend `skills/hermes-agent/SKILL.md` with "update bedroom to the latest firmware and tell me when it's done" → `sat-cli ota apply --follow --json`.

**Checkpoint**: OTA flows are observable per device, browser-exempt is enforced, failures are surfaced cleanly.

---

## Phase 7: User Story 5 — Operate & diagnose (Priority: P3)

**Goal**: command verbs (reboot/restart/mute/unmute/identify/reset_config/factory_reset), unpair, log filtering, and an interactive-confirm gate on destructive actions.

**Independent Test**: identify-LED on a real device flashes; factory_reset requires confirmation and (after success) the device re-registers as pending; `sat-cli logs` filters work.

### Tests

- [ ] T072 [P] [US5] Add `tests/contract/test_command.py` parametrized across the closed `CommandVerb` enum: 202 on accepted, 400 on unknown verb, 503 on offline.
- [ ] T073 [P] [US5] Add `tests/integration/test_destructive_confirm.py`: `sat-cli device command DEVICE_ID factory-reset` without `-y` prompts (simulated stdin) and aborts on "no"; with `-y` proceeds; after success, the device re-registers as pending.
- [ ] T074 [P] [US5] Add `tests/unit/test_cli_help_contract.py`: every command has `--help`, every flag in [cli-contract.md](./contracts/cli-contract.md) is present, contract version reported correctly.

### Implementation

- [ ] T075 [US5] Add `Registry.send_command(device_id, verb, args)` and `ManagementService.command(device_id, body)` in `src/satellite_core/management/{service.py,command.py}`: validates against `CommandVerb` enum, returns 400 on unknown, 503 on offline, otherwise sends the `command` frame on the device WS and returns 202 `CommandResponse`.
- [ ] T076 [US5] Wire `POST /satellite/{id}/command` (already declared in OpenAPI; ensure handler is registered) in `src/satellite_core/management/app.py`.
- [ ] T077 [US5] Implement `sat-cli device command DEVICE_ID VERB [--args JSON]` in `src/sat_cli/cli.py`. Destructive verbs (`factory-reset`) require an interactive confirmation prompt unless `--yes` is passed; under `--json --yes` proceed without prompting; under `--json` without `--yes` for a destructive verb → exit 1 with `error.code = bad_input` and a message.
- [ ] T078 [US5] Implement `sat-cli device delete DEVICE_ID` (calling `DELETE /satellite/{id}`) with the same destructive-confirm gate.
- [ ] T079 [P] [US5] Extend `tests/integration/test_cli_roundtrip.py` (or add a sibling) to exercise `device command identify` and assert a `command_ack` arrives on the device WS subscription.
- [ ] T080 [P] [US5] Extend `skills/hermes-agent/SKILL.md` with "identify the kitchen satellite" and "factory-reset bedroom" (skill must ask the user to confirm factory-reset before running `sat-cli ... factory-reset -y`).

**Checkpoint**: full command surface available; destructive confirmation enforced at the client (CLI/skill), per FR-019.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T081 Delete `src/hermes_satellite_adapter/__init__.py` compatibility shim and any remaining `hermes_satellite_adapter/*` files. Confirm no test or import path references the old name. (Last step — only after every other phase ships.)
- [ ] T082 [P] Write `docs/cli-cheatsheet.md` summarizing every `sat-cli` command + its envelope shape, linking to `contracts/cli-contract.md`.
- [ ] T083 [P] Add `docs/migration-from-hermes_satellite_adapter.md` for anyone outside this repo who depended on the old package name.
- [ ] T084 [P] Update `docs/generic-voice-satellite-design.md` with a top-of-file note: "Under constitution v2.0.0 this document specifies the **Hermes plugin**. The satellite system is platform-agnostic; see `specs/011-satellite-management/contracts/agent-platform.md`."
- [ ] T085 Re-run the constitution check from [plan.md](./plan.md#constitution-check) against the shipped code (all five principles) and record the result at the bottom of this tasks.md as "Post-implementation constitution check: PASS" before closing the feature.
- [ ] T086 [P] Performance check: `sat-cli list --json` on a synthetic 10-device fleet returns ≤500 ms; `sat-cli watch` reflects an offline transition within heartbeat (default 30 s). Record numbers in `specs/011-satellite-management/perf-notes.md`.
- [ ] T087 [P] Update CHANGELOG / repo-root README to mention `satellite-core` + `sat-cli` and the v2.0.0 constitution amendment.
- [ ] T088 [P] (Deferred — track only.) Stub `clients/satellite_ui/` placeholder README pointing at FR-009 as future P3 work; do not implement.

---

## Dependencies (story completion order)

```text
Phase 1 (Setup, T001–T007)
        │
        ▼
Phase 2 (Foundational, T008–T019)  ◄── all user stories block on this
        │
        ├──► Phase 3 (US1 — MVP, T020–T037)
        │
        ├──► Phase 4 (US2, T038–T052)     [needs US1's Registry + CLI base]
        │
        ├──► Phase 5 (US3, T053–T062)     [needs US1's CLI base]
        │
        ├──► Phase 6 (US4, T063–T071)     [needs US1's CLI base + SSE log stream]
        │
        ├──► Phase 7 (US5, T072–T080)     [needs US1's CLI base]
        │
        ▼
Phase 8 (Polish, T081–T088)        ◄── after at least US1+US2 ship
```

US1 (MVP) is the only phase truly blocking everything; US2–US5 can ship in any order after the foundational phase. US3/US4/US5 depend on US1's CLI scaffolding (cli.py, rest_client.py, output.py, exit_codes.py) but not on each other.

## Parallel-execution examples

**Within Phase 1**: T004 / T005 / T006 / T007 are `[P]` — different files, no shared state.

**Within Phase 2**: T015 / T016 / T017 / T018 are `[P]` — independent test modules. T008 → T009 → T010 (plugin seam) sequential.

**Within Phase 3 (US1)**: T020 / T021 / T022 / T023 (all tests) `[P]`; T031 `[P]`; T037 `[P]`. Implementation tasks T024–T036 each touch distinct files but share a logical sequence.

**Across stories**: once Phase 2 is done, two implementers can pair on US2 and US3 in parallel — different REST endpoints, different CLI subcommands, no shared mutable state beyond the registry which is already locked.

## Implementation strategy

1. **Land Phase 1 + Phase 2 first** as a single PR — the rename + plugin seam is mechanical but invasive; reviewing it standalone is much easier than reviewing it tangled with new endpoints.
2. **MVP = US1 (Phase 3)** — read-only fleet visibility via `sat-cli` + Hermes skill. Ship it. This independently proves the seam, the SSE pipe, the JSON envelope, and the skill→CLI contract.
3. **Then US2 (onboarding)** — the headline capability; once landed, the fleet can actually grow.
4. **US3 → US4 → US5** can each be one PR; they don't block each other.
5. **Phase 8** is the close-out — only after every story ships can the compat shim be removed (T081). The constitution re-check (T085) is the merge gate for the whole feature.

## Format validation

All tasks above follow `- [ ] T### [P?] [Story?] Description with file path`:

- ✅ Checkbox: every line begins `- [ ]`.
- ✅ Task ID: T001 → T088 sequential.
- ✅ [P] marker: present on parallelizable tasks only.
- ✅ [Story] label: present on US1–US5 tasks only (T020–T080); absent on Setup (T001–T007), Foundational (T008–T019), Polish (T081–T088).
- ✅ Description includes a concrete file path or directory for every implementation task.

**Total task count**: 88 (Setup 7 · Foundational 12 · US1 18 · US2 15 · US3 10 · US4 9 · US5 9 · Polish 8).
