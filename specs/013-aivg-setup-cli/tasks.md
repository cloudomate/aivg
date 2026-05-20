---
description: "Task list for feature 013-aivg-setup-cli"
---

# Tasks: `aivg setup` — Platform-Agnostic CLI Deploy

**Input**: Design documents from [/specs/013-aivg-setup-cli/](.)
**Constitution**: v2.0.1 (no amendment in this feature)
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Tests**: included — the plan explicitly calls out six new test
files (T028, T037, T044, T055, T060) and extensions to two existing
ones (`test_cli_help_contract.py`, `test_no_legacy_branding.py`). The
binding gates are SC-002 (preflight is byte-equivalent read-only),
SC-003 (uninstall is byte-equivalent reverse), SC-007 (contract
version stays `1.0.0`), SC-008 (lock prevents concurrent
mutation), SC-009 (fault-injected install is recoverable).
**Organization**: tasks grouped by user story (US1–US5). Phase 1
(Setup) and Phase 2 (Foundational) block all stories.

## Format: `[ID] [P?] [Story?] Description with file path`

## Path conventions

Single-repo Python project. New files only inside the established
package directories (`src/aivg_core/`, `src/aivg_cli/`,
`tests/`, `skills/`). The four `deploy/*.sh` scripts shrink to
~10-line bash wrappers; their Python equivalent lives at
`src/aivg_core/platforms/hermes/setup.py`. No new top-level
directories.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: lay the deploy-layer companion to the existing
`AgentPlatform` plugin seam. No CLI surface change yet.

- [X] T001 Add the `SetupCapability` `Protocol` + companion dataclasses (`DetectResult`, `SetupOptions`, `SetupPhase`, `PreflightReport`, `InstallResult`, `UninstallResult`, `ParityCheckResult`, `RollbackResult`) per [data-model.md §1–2](./data-model.md) to `src/aivg_core/platforms/base.py` next to the existing `AgentPlatform`. Make `SetupCapability` `@runtime_checkable`. The closed set of phase names lives in this file as a `PHASE_NAMES: frozenset[str]` so tests can assert against it.
- [X] T002 Add `PluginRegistry.load_setup_capability(name) → SetupCapability` to `src/aivg_core/platforms/base.py`: import `aivg_core.platforms.<name>` lazily; look for module attribute `SETUP`; if absent raise `RuntimeError("setup_not_supported_for_platform")`; if present + `isinstance(SETUP, SetupCapability)` fails, raise the same error with a specific message.
- [X] T003 [P] Extend `src/aivg_core/persistence.py` with `~/.aivg/installs/<platform>/<UTC-ts>/` backup-folder helpers per [data-model.md §3](./data-model.md): `new_install_backup(platform, mode) → Path`, `record_pre_state(backup_dir, config_path, plugin_dirs)`, `append_phase(backup_dir, phase: SetupPhase)`, `finalize_backup(backup_dir, result)`. All atomic via `tmp + os.replace`.
- [X] T004 [P] Extend `src/aivg_core/persistence.py` with `flock`-based lock helpers per [data-model.md §4](./data-model.md): `acquire_setup_lock() → ContextManager` (non-blocking; raises `SetupLockHeld(running_pid, argv, started_at)` on contention); lock file at `~/.aivg/setup.lock`; metadata rewritten on every acquire. Single-host scope; multi-host out of scope per spec.
- [X] T005 [P] Add closed-set constants for the new `error.code` values to `src/aivg_cli/exit_codes.py` (matching [contracts/setup-cli-contract.md](./contracts/setup-cli-contract.md)): `NO_PLATFORM_DETECTED`, `MULTIPLE_PLATFORMS_DETECTED`, `SETUP_NOT_SUPPORTED_FOR_PLATFORM`, `SETUP_LOCK_HELD`, `SETUP_PARTIAL_FAILURE`, `PERMISSION_DENIED`, `HOST_STATE_DRIFTED`. Update `map_error_to_exit_code()` so `setup_partial_failure` → 5 and the rest → 1.

**Checkpoint**: Protocol + dataclasses + persistence helpers + exit-code map landed; nothing user-visible yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: scaffold the `aivg setup` Typer command tree and the
preflight/dispatch logic shared by every user story.

- [X] T006 Create `src/aivg_cli/setup.py` with the Typer command skeleton: `setup_app = typer.Typer()` (or a single `@app.command("setup")` function) and a `@app.command("deploy")` alias (FR-001). Wire global flags from [contracts/setup-cli-contract.md](./contracts/setup-cli-contract.md): `--platform`, `--preflight`, `--uninstall`, `--restore-backup`, `--parity-check`, `--yes`, `--force`, `--legacy-hermes`, `--no-tune`, `--phrase`. Reject mutually-exclusive combos with `error.code = bad_input`.
- [X] T007 [P] Add `aivg setup` + `aivg deploy` to the Typer hierarchy in `src/aivg_cli/cli.py` (`app.add_typer(setup_app, name="setup")` and an alias). Help text mirrors the contract.
- [X] T008 Implement platform-detection precedence in `src/aivg_cli/setup.py::_resolve_platform(opts) → SetupCapability` per [research.md R-2](./research.md#r-2): explicit `--platform` wins; else probe every shipped plugin's `detect()` in alphabetical order; multi-detect → `error.code = multiple_platforms_detected`; zero-detect → `no_platform_detected`. The function MUST NOT import a concrete plugin — only `aivg_core.platforms.base.PluginRegistry`.
- [X] T009 Implement the NDJSON phase emitter in `src/aivg_cli/setup.py::_emit_phase(name, status, detail=None)` matching [contracts/setup-cli-contract.md "Phases"](./contracts/setup-cli-contract.md). One envelope per `started` transition + one per terminal (`ok|skipped|failed`). Reuses `aivg_cli.output.emit_ndjson`; no new envelope shape.
- [X] T010 Implement the destructive-confirm gate in `src/aivg_cli/setup.py::_confirm_or_bail(opts, summary_text) → bool` reusing the `_confirm_destructive_or_bail` helper from `cli.py` (feature 011 FR-019). Under `--yes`: pass; under `--json` without `--yes`: emit `error.code = bad_input` envelope and return False; interactive: prompt with the preflight summary.
- [X] T011 Wire the lock-acquire + emit-on-contention flow at the entry of every mutating mode (`install` / `--uninstall` / `--restore-backup`). Use the context manager from T004; on `SetupLockHeld` emit `error.code = setup_lock_held` with the running PID + argv from the lock file, exit code 1.
- [X] T012 Update [contracts/cli-contract.md](specs/011-satellite-management/contracts/cli-contract.md) to add the seven new `error.code` values (R-11) to the documented closed set + the `aivg setup` / `aivg deploy` commands to the command list. Bump that contract's MINOR version (the closed-set additions are additive). `aivg --contract-version` value stays `1.0.0` (the file's `--contract-version` field is unchanged).

**Checkpoint**: `aivg setup --help` renders correctly; `aivg setup --preflight` without any plugins implementing setup returns `setup_not_supported_for_platform`; concurrent dummy invocations refuse on the lock.

---

## Phase 3: User Story 1 — Operator installs AIVG into Hermes (Priority: P1) 🎯 MVP

**Goal**: an operator on a Hermes-installed host runs `aivg setup --yes` and ends with a working management plane on `localhost:8643`.

**Independent Test**: SC-001 — fresh Hermes-installed host, `aivg setup --yes` succeeds end-to-end in < 2 min; `aivg list` returns a non-error response after.

### Tests (US1)

- [X] T013 [P] [US1] Add `tests/contract/test_setup_cli.py`: typer-help contract (every flag from setup-cli-contract.md is present), `--preflight` is read-only (filesystem diff = 0), mutually-exclusive flags reject with `error.code=bad_input`, default install requires confirmation or `--yes`.
- [X] T014 [P] [US1] Add `tests/integration/test_setup_lifecycle.py::test_preflight_is_byte_equivalent_readonly` — drive `aivg setup --preflight` against the fake `echo` platform fixture (added in T046); sha256-walk the host's relevant paths before/after; assert no change. **Binding gate for SC-002.**
- [X] T015 [P] [US1] Add `tests/integration/test_setup_lifecycle.py::test_install_emits_full_phase_sequence` — under `--json --yes`, the install run emits exactly the documented phase set (`detecting → preflight → confirming(skipped) → backup → vendoring → config_writing → installing_deps → restarting_gateway → post_verifying → done`); each envelope matches the v1 shape `{ok,data,error,v=1}`.

### Implementation (US1)

- [X] T016 [US1] Create `src/aivg_core/platforms/hermes/setup.py::HermesSetupCapability` implementing the four core `SetupCapability` methods. Module-level `SETUP = HermesSetupCapability()`.
- [X] T017 [US1] Implement `HermesSetupCapability.detect()` per [research.md R-2](./research.md#r-2): probe `~/.hermes/hermes-agent/` (overridable via `HERMES_HOME` env), capture `paths.venv`, `paths.plugins_dir`, `paths.config`, parse Hermes version from `<venv>/pyvenv.cfg` or equivalent. Return `DetectResult(is_installed, paths, version, reasons)`.
- [X] T018 [US1] Implement `HermesSetupCapability.preflight(opts)` — read-only: confirm venv has `aiohttp+av`; detect missing `aiortc`; list pre-existing plugin dirs; check write permissions on `~/.hermes/config.yaml` and `<plugins_dir>`; check for an existing AIVG marker (idempotent re-install scenario, R-10). Return `PreflightReport(ok, intended_changes, blockers, warnings)`.
- [X] T019 [US1] Move `deploy/plugin/__init__.py`, `deploy/plugin/adapter.py`, `deploy/plugin/plugin.yaml` into `src/aivg_core/platforms/hermes/plugin_entrypoint/` (the new home for the Hermes-side plugin shim). Update the entrypoint's import line `from .hermes_satellite_adapter.adapter import build_platform_entry` (currently broken post-feature-012) to the new path (e.g. `from aivg_core.adapter import build_platform_entry`).
- [X] T020 [US1] Implement `HermesSetupCapability.install(opts)` per [research.md R-5/R-8](./research.md#r-5-backup-format--timestamped-folder-under-aivginstalls): emit phases in the documented order. Per phase: (a) **backup** — `persistence.new_install_backup` + `record_pre_state`; (b) **vendoring** — `shutil.copytree(plugin_entrypoint, plugins_dir/satellite_webrtc, dirs_exist_ok=True)` + write the `.aivg-install-marker.json` marker file (R-10); (c) **config_writing** — read `~/.hermes/config.yaml`, append or upsert the `aivg:`/`satellite:` block with a sentinel comment `# managed by aivg setup` (idempotent: don't re-add if marker present); (d) **installing_deps** — `subprocess.run([venv_pip, "install", "aiortc"])` only if `aiortc` missing; (e) **restarting_gateway** — `subprocess.run(["hermes", "gateway", "restart"])` with fallback `start`/`status`; (f) **post_verifying** — `lsof -nP -iTCP -sTCP:LISTEN | grep -E ':(8643|8644)\b'` loop for up to 30 s.
- [X] T021 [US1] Implement `HermesSetupCapability.install` legacy tuning path: when `opts.legacy_hermes=True` and `not opts.no_tune`, apply the feature-010 tweaks (`stt.local.model: medium → small`; `voice.silence_duration: 3.0 → 1.2`) to the Hermes config; idempotent. Document in a `# legacy-hermes tuning` comment in the config.
- [X] T022 [US1] Wire `_resolve_platform` (T008) + `_emit_phase` (T009) + `_confirm_or_bail` (T010) into `aivg setup` default-mode handler in `src/aivg_cli/setup.py`: call `platform.detect()` → `platform.preflight(opts)` → confirm → `platform.install(opts)`. Map every `SetupError` raised by the plugin onto the JSON envelope (`error.code` + `phase` from the failing `SetupPhase`).
- [X] T023 [US1] On terminal `done`, write the marker `.aivg-install-marker.json` (R-10) inside the vendored plugin dir; emit the final NDJSON envelope including `backup_dir` and `rollback_command`.
- [X] T024 [P] [US1] Extend `tests/unit/test_cli_help_contract.py`: assert `setup`, `deploy` are in the root command list; `aivg setup --help` lists every flag from [setup-cli-contract.md](./contracts/setup-cli-contract.md).

**Checkpoint**: an operator with Hermes Agent installed can run `aivg setup --yes` and end up with a vendored plugin + config block + restarted gateway + post-verify green. Integration tests for the full lifecycle live under the `echo` fixture (US4) for portability.

---

## Phase 4: User Story 2 — Operator uninstalls cleanly (Priority: P2)

**Goal**: `aivg setup --uninstall` is the byte-equivalent inverse of US1 (SC-003).

**Independent Test**: SC-003 — after US1 + uninstall, the host is byte-equivalent to its pre-install state (modulo the install/uninstall log entries).

### Tests (US2)

- [ ] T025 [P] [US2] Add `tests/integration/test_setup_lifecycle.py::test_uninstall_is_byte_equivalent_reverse` — sha256-walk before US1 install; install; uninstall; sha256-walk again; assert byte-equivalence modulo the install/uninstall log entries (allow-list the `~/.aivg/installs/...` paths). **Binding gate for SC-003.**
- [ ] T026 [P] [US2] Add `tests/integration/test_setup_lifecycle.py::test_uninstall_leaves_preexisting_plugins_intact` — seed the host with two fake plugin dirs *before* install; install AIVG; uninstall; assert the two pre-existing plugin dirs are still present byte-equivalent.

### Implementation (US2)

- [ ] T027 [US2] Implement `HermesSetupCapability.uninstall(opts)` per [data-model.md §1](./data-model.md): emit phases `detecting → preflight → confirming → backup → uninstall_vendor → uninstall_config → uninstall_restart → post_verifying → done`. (a) backup: same as install (record pre-uninstall state); (b) uninstall_vendor: `shutil.rmtree(plugins_dir/satellite_webrtc)`; (c) uninstall_config: remove the `aivg:`/`satellite:` block (identified by the `# managed by aivg setup` sentinel); preserve any other config edits; (d) uninstall_restart: same as install's restart phase.
- [ ] T028 [US2] Wire `aivg setup --uninstall` handler in `src/aivg_cli/setup.py`: dispatch to `platform.uninstall(opts)`. Same confirm-gate as install.
- [ ] T029 [US2] Implement `aivg setup --restore-backup PATH` handler — reads `<PATH>/pre_state.json` + `<PATH>/config.yaml.before`, calls the plugin's `rollback(opts, backup_dir=PATH)` method. Creates a fresh backup folder (backup-of-the-rollback) per R-5.
- [ ] T030 [US2] Implement `HermesSetupCapability.rollback(opts, *, backup_dir)`: restore `<backup_dir>/config.yaml.before` to `<paths.config>` atomically (tmp+rename); remove any plugin dirs not in `<backup_dir>/pre_state.json::plugin_dirs`; restart the gateway; post-verify. Returns `RollbackResult`.

**Checkpoint**: uninstall + restore-backup work end-to-end via the fake `echo` platform; sha256 diff before/after is empty.

---

## Phase 5: User Story 3 — Agent installs AIVG conversationally (Priority: P2)

**Goal**: a Hermes-platform agent drives `aivg setup` from chat with exactly one user confirmation in chat and zero CLI prompts (SC-005).

**Independent Test**: SC-005 — drive the skill via a test runner; assert the agent (a) calls `aivg setup --json --preflight` first, (b) asks the user for confirmation in chat, (c) on user "yes" calls `aivg setup --json --yes`, (d) reports each phase envelope.

### Tests (US3)

- [ ] T031 [P] [US3] Add `tests/integration/test_setup_skill_protocol.py` — simulates an agent driving the skill: feed the install-intent prompt; assert the agent's call sequence matches the documented protocol (preflight first, in-chat confirmation, then `--yes`). Uses a stub that records the subprocess calls without actually invoking `aivg setup`.

### Implementation (US3)

- [ ] T032 [US3] Extend `skills/hermes-agent/SKILL.md` with a new section "6. Setup / Install (US3)" documenting the protocol from [research.md R-9](./research.md#r-9): the agent always runs `aivg setup --json --preflight` first, reports the intended changes to the user, asks for explicit chat confirmation, then runs `aivg setup --json --yes` (or `--legacy-hermes --yes` if the user explicitly invokes via the legacy script flow), reports each phase envelope, surfaces the backup + rollback command on completion/failure.
- [ ] T033 [P] [US3] Extend `skills/openclaw/README.md` with a note that the `setup` capability returns `setup_not_supported_for_platform` in v1 (a `SetupCapability` is implementable for OpenClaw in a future feature; until then the skill should report the error code clearly rather than hide it).

**Checkpoint**: the Hermes-platform agent has a working chat protocol for install; the integration test asserts the call sequence.

---

## Phase 6: User Story 4 — Setup works for a new platform without new bash (Priority: P3)

**Goal**: SC-004 — adding a new agent platform requires zero changes to the satellite core or `aivg setup` CLI. Only a new `platforms/<name>/setup.py`.

**Independent Test**: SC-004 — add a fake `echo` `SetupCapability` under `tests/fixtures/platforms/echo/`; assert `aivg setup --platform echo --yes` runs install/uninstall against it using the same code paths the Hermes plugin uses.

### Tests (US4)

- [ ] T034 [P] [US4] Extend the existing `tests/fixtures/platforms/echo/` with a `setup.py` module exposing `SETUP = EchoSetupCapability()` — an in-memory `SetupCapability` that "installs" by writing files into a tmp directory (no host mutation). Used by every US1/US2 integration test so they don't actually mutate `~/.hermes/`.
- [ ] T035 [P] [US4] Add `tests/integration/test_setup_seam.py` — drives `aivg setup --platform echo --yes` against the fake plugin; asserts (a) the `SetupCapability` Protocol gate accepts it, (b) the install phases emit in the documented order, (c) no Hermes-plugin module is imported during the run (`sys.modules` assertion, mirroring the feature 011 T017 seam test). **Binding gate for SC-004.**
- [ ] T036 [P] [US4] Add `tests/unit/test_setup_no_platform_branching.py` — AST-walk `src/aivg_cli/setup.py`; assert no `import aivg_core.platforms.<concrete>` (only `aivg_core.platforms.base`). Same regex/marker rule as the feature 011 `test_no_platform_branching.py`.

### Implementation (US4)

- [ ] T037 [US4] Confirm `src/aivg_cli/setup.py` references only `aivg_core.platforms.base.PluginRegistry` for plugin discovery (no concrete-plugin imports). If T036 fails, refactor to satisfy.
- [ ] T038 [US4] Add a documented "How to add a new platform's setup capability" section to [contracts/platform-setup.md](./contracts/platform-setup.md) (already drafted; verify the example matches what T034's `EchoSetupCapability` actually does — keep them in lock-step).

**Checkpoint**: a plugin author writes one `setup.py` and gets full `aivg setup` support — proven by the `echo` fixture round-trip.

---

## Phase 7: User Story 5 — Legacy `deploy/*.sh` users keep working for one release (Priority: P3)

**Goal**: SC-006 — every legacy invocation succeeds with one stderr deprecation notice + preserved exit code.

**Independent Test**: SC-006 — run each of the four `deploy/*.sh --preflight`; assert exactly one stderr notice + correct exit code.

### Tests (US5)

- [ ] T039 [P] [US5] Add `tests/unit/test_legacy_deploy_wrapper.py` — for each of the four wrappers (`deploy-local.sh`, `deploy-to-hermes.sh`, `parity-check.sh`, `rollback.sh`): run via `subprocess` with `--preflight`; assert (a) stderr contains exactly one occurrence of "DEPRECATED" + "aivg setup"; (b) stdout matches what `aivg setup --legacy-hermes --preflight` (or equivalent) emits; (c) exit code is preserved (read from the underlying CLI).
- [ ] T040 [P] [US5] Extend `tests/unit/test_no_legacy_branding.py` (the rebrand lint from feature 012): add a new regex pass that catches `deploy-local.sh` / `deploy-to-hermes.sh` references in non-allow-listed paths. Allow-list the four wrapper scripts themselves + the CHANGELOG entry + the follow-up doc.

### Implementation (US5)

- [ ] T041 [US5] Replace `deploy/deploy-local.sh` with the ~10-line bash wrapper from [research.md R-7](./research.md#r-7): one stderr deprecation notice + `exec aivg setup --legacy-hermes [...args mapped...]`. Map `--preflight` → `--preflight`; `--yes` → `--yes`; `--no-tune` → `--no-tune`.
- [ ] T042 [P] [US5] Same wrapper shape for `deploy/deploy-to-hermes.sh` — for v1, SSH is out of scope; the wrapper either refuses with a clear message + pointer at the follow-up doc, OR forwards to `aivg setup --legacy-hermes` for local-only mode (decide in tasks: refuse is cleaner since the script can't reach a remote host anymore).
- [ ] T043 [P] [US5] Same wrapper shape for `deploy/parity-check.sh` → `exec aivg setup --parity-check --legacy-hermes --phrase "$@"`.
- [ ] T044 [P] [US5] Same wrapper shape for `deploy/rollback.sh` → `exec aivg setup --restore-backup "$(cat ~/.aivg/installs/.../last_backup_local)"` (find the latest backup) `--legacy-hermes`.
- [ ] T045 [US5] Add `deploy/plugin/README.md` stub explaining the contents moved to `src/aivg_core/platforms/hermes/plugin_entrypoint/` in feature 013, with a pointer. Keep the old files in `deploy/plugin/` deleted (`git rm`) — they were moved by T019.
- [ ] T046 [P] [US5] Update [CHANGELOG.md](CHANGELOG.md) with a new top-of-file entry: "Feature 013: `aivg setup` lands; `deploy/*.sh` deprecated for one release; `deploy/plugin/` contents moved to `aivg_core/platforms/hermes/plugin_entrypoint/`."

**Checkpoint**: every legacy invocation works for one release; the rebrand lint catches new references.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T047 [P] Implement `HermesSetupCapability.parity_check(opts, *, phrase)` — reuse the legacy `parity-check.sh` semantics (compare a Hermes-spoken phrase to operator-typed; surface diff). Wire `aivg setup --parity-check --phrase "..."` in setup.py. Single-phase emission (`parity_check → done|failed`).
- [ ] T048 [P] Add a fault-injection integration test `tests/integration/test_setup_fault_injection.py` — induce a failure mid-install (e.g. `restarting_gateway` fails); assert (a) the backup folder is fully populated; (b) `aivg setup --restore-backup <dir> --yes` restores byte-equivalence; (c) the error envelope's `error.message` contains the documented rollback command. **Binding gate for SC-009.**
- [ ] T049 [P] Add a concurrency-safety integration test `tests/integration/test_setup_lock.py` — spawn two parallel `aivg setup --json --yes` subprocesses against the `echo` fixture; assert one acquires the lock, one refuses with `error.code = setup_lock_held`, the lock file's content names the running PID. **Binding gate for SC-008.**
- [ ] T050 [P] Add `aivg setup --version`/`--contract-version` smoke test — these MUST still return `1.0.0` after this feature. Extend `tests/unit/test_cli_tagline.py`. **Binding gate for SC-007.**
- [ ] T051 [P] Add `tests/contract/test_rebrand_invariants.py::test_setup_error_codes_in_closed_set` — load [contracts/setup-cli-contract.md](./contracts/setup-cli-contract.md), parse the documented `error.code` table, assert `sat_cli.exit_codes._ERROR_CODE_TO_EXIT` contains every entry. Drift here means a code was emitted but not documented.
- [ ] T052 [P] Track the next-release shell-script removal: write `specs/013-aivg-setup-cli/followup-deploy-shell-removal.md` — same shape as feature 012's followup-shim-removal.md; lists the four wrappers + `deploy/plugin/` for removal in the release after.
- [ ] T053 Re-run the full constitution check (every v2.0.1 principle): assert no Principle prose touched; assert the lint, contract-drift, and no-platform-branching tests all stay green. Record the result at the bottom of this tasks.md as "Post-implementation constitution check: PASS" before closing.
- [ ] T054 Final smoke test: on a Hermes-installed host, run `aivg setup --preflight` (read-only) and capture the output; run `aivg setup --yes` and capture the run; run `aivg setup --uninstall --yes` and capture the restore. Save the three outputs to `specs/013-aivg-setup-cli/smoke-outputs/` (gitignored) for the operator's manual review.
- [ ] T055 [P] Update [README.md](README.md) with a one-line update to the Quickstart pointing at `aivg setup` (replaces the implicit "manual install" path), and update [docs/aivg-data-dir.md](docs/aivg-data-dir.md) to mention `~/.aivg/installs/` and `~/.aivg/setup.lock` as new sibling files of `state.json`.

---

## Dependencies (story completion order)

```text
Phase 1 (Setup, T001–T005)
        │
        ▼
Phase 2 (Foundational, T006–T012)   ◄── all stories block on this
        │
        ├──► Phase 3 (US1 — MVP install, T013–T024)
        │        │
        │        ▼
        ├──► Phase 4 (US2 — uninstall + restore-backup, T025–T030)   [needs US1's install + marker file]
        │
        ├──► Phase 5 (US3 — agent skill, T031–T033)                  [needs US1 CLI]
        │
        ├──► Phase 6 (US4 — new-platform fixture, T034–T038)         [parallel after Phase 2]
        │
        ├──► Phase 7 (US5 — legacy script wrappers, T039–T046)       [needs US1 install path]
        │
        ▼
Phase 8 (Polish, T047–T055)
```

US1 (MVP) is the only phase truly blocking everything; US2/US3/US4/US5 can ship in parallel after US1 lands. US4 (new-platform fixture) is genuinely independent — it can land anytime after Phase 2.

## Parallel-execution examples

**Within Phase 1**: T003/T004/T005 `[P]` — different files.

**Within Phase 2**: T007 `[P]` after T006 (different files). T012 is a documentation-only update; it can land in parallel with T006–T011 once the surface decisions are stable.

**Within Phase 3 (US1)**: T013/T014/T015 (tests) `[P]`. T024 `[P]`. T016→T017→T018→T020 sequential (each phase builds on the previous). T019 `[P]` (file move). T021 `[P]` (legacy tuning is a separate code path).

**Within Phase 4 (US2)**: T025/T026 `[P]`. T027 must land before T028 (handler dispatches to method). T029→T030 sequential.

**Within Phase 5 (US3)**: T031 `[P]`. T032/T033 `[P]` (different files).

**Within Phase 6 (US4)**: T034/T035/T036 `[P]`. T037/T038 `[P]`.

**Within Phase 7 (US5)**: T041/T042/T043/T044 sequential (all touch `deploy/`, but each is one file — `[P]` is also fine since they're separate files). T039/T040 `[P]`. T045/T046 `[P]`.

**Within Phase 8**: T047/T048/T049/T050/T051/T052/T055 all `[P]`.

**Across stories**: once Phase 2 is done, two implementers can pair on US1 and US4 in parallel — different files, different code paths. US2 needs to wait for US1's marker file to exist; US3/US5 wait for US1's CLI surface; US6 (Polish) waits for everything.

## Implementation strategy

1. **Land Phase 1 + Phase 2 first** as one PR — the Protocol + dataclasses + lock/backup helpers + the Typer scaffolding. No user-visible surface change yet; the existing tests stay green; new tests are scaffolding.
2. **Phase 3 (US1)** is the MVP — once it ships, an operator with Hermes installed has a working install path. Phase 3 absorbs the most logic from the legacy bash; it's also the densest test surface (SC-001, SC-002, plus the v1 envelope contract).
3. **Phase 4 (US2)** sequences right after US1 since it depends on US1's marker file + backup folder structure; ship them together if possible.
4. **Phase 6 (US4)** is the architectural payoff — it's the seam test that proves the design holds. Land it any time after Phase 2; doesn't depend on US1.
5. **Phase 5 (US3) + Phase 7 (US5)** can ship together or apart depending on operator urgency. The agent skill (US3) requires only US1's CLI to be present; the legacy wrappers (US5) need US1's install path complete.
6. **Phase 8 (Polish)** is the close-out — fault-injection (SC-009), concurrency (SC-008), parity-check, the contract-version-stays-1.0.0 guard, the rebrand-lint extension, the next-release-removal tracker, the final constitution re-check.

## Format validation

All 55 tasks above follow `- [ ] T### [P?] [Story?] Description with file path`:

- ✅ Checkbox: every line begins `- [ ]`.
- ✅ Task ID: T001 → T055 sequential.
- ✅ [P] marker: present on parallelizable tasks only.
- ✅ [Story] label: present on US1–US5 tasks only (T013–T046); absent on Setup (T001–T005), Foundational (T006–T012), Polish (T047–T055).
- ✅ Description includes a concrete file path or directory for every implementation task.

**Total task count**: 55 (Setup 5 · Foundational 7 · US1 12 · US2 6 · US3 3 · US4 5 · US5 8 · Polish 9).
