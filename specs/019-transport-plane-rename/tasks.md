---
description: "Task list for feature 019 — Internal plugin-name rename"
---

# Tasks: Internal plugin-name rename — `satellite_webrtc` → `aivg_satellite`

**Input**: Design documents from [/specs/019-transport-plane-rename/](./)
**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [quickstart.md](./quickstart.md)

**Tests**: Three new unit test files are mandatory (per plan.md "Testing" section + FR-010 in spec.md), since they are the primary guard against the silent-shadow trap this feature exists to fix.

**Organization**: Tasks are grouped by user story. Both stories are P1 — neither is "nice to have." Story 1 (US1) is the rename itself; story 2 (US2) is the conflict detector that turns today's silent-shadow trap into a loud failure.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks).
- **[Story]**: US1 or US2 for user-story tasks; absent for Setup/Foundational/Polish.
- Every task includes its target file path.

## Path Conventions

Single-project layout:
- Source: `src/aivg_core/...`
- Tests: `tests/unit/...`, `tests/fixtures/...`
- Tooling: repo root scripts under `scripts/`, deploy under `deploy/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Capture the pre-019 baseline so the wire-surface-invariance gate (SC-002) has something to diff against, and confirm the dev environment matches the constitution check's assumptions.

- [X] T001 Capture pre-019 wire-surface baseline per [quickstart.md § 4.1](./quickstart.md): run the gateway on `main` (commit `52d70ed` or later), restart, capture `/satellite/list?state=all`, `aivg --contract-version`, and the WS register exchange into `/tmp/aivg-019-baseline/pre/`. The post-019 diff harness in T023 compares against this snapshot.
- [X] T002 [P] Capture pre-019 test count: run `PYENV_VERSION=3.11.9 PYTHONPATH=src:tests pytest tests/ -q --tb=line 2>&1 | tail -3` from repo root, record the passing count as the baseline (expected: 329 from feature 017). Write the count into a comment at the top of `tests/unit/test_plugin_registration_name.py` (created in T013) so the final regression in T021 has an explicit numeric target.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add the canonical-name constant that EVERY rename site (US1) and the conflict detector (US2) will read from. Without it, callers would either embed the literal `"aivg_satellite"` (drift bug magnet) or reach across modules in ways that complicate the rename.

**⚠️ CRITICAL**: No user-story work begins until T003 lands.

- [X] T003 Add `CANONICAL_PLUGIN_NAME = "aivg_satellite"` to [src/aivg_core/platforms/hermes/setup.py](../../src/aivg_core/platforms/hermes/setup.py), immediately under the existing `LEGACY_PLUGIN_NAME = "satellite_webrtc"` constant (around line 52). Export from the module (no `_` prefix). Add a 1-line docstring explaining: "Post-019 canonical plugin-registration name. Read by the plugin entrypoint shim, the adapter class, get_chat_info, and the dev banner — one source of truth."

**Checkpoint**: Foundation ready — both user stories can proceed.

---

## Phase 3: User Story 1 — Rename happens end-to-end (Priority: P1) 🎯 MVP

**Goal**: Every internal site that today reads `satellite_webrtc` flips to read `aivg_satellite`. Gateway log lines, the dev-mode banner, the adapter class name, `get_chat_info()`'s `platform` field, and the `PlatformEntry(name=…)` argument all converge on the canonical name. A one-line back-compat alias keeps external Python importers working through one release.

**Independent Test**: per [quickstart.md § 1.1, § 1.2, § 1.3, § 5](./quickstart.md): no `satellite_webrtc` literals remain in shipping code (outside `setup.py`'s legacy constant); the entry-point shim has `name="aivg_satellite"`; the back-compat alias exists; the post-restart gateway log line emits `aivg_satellite`. Test suite stays green (US2's new tests do not yet exist; US1 brings the rename-assertion test).

### Implementation tasks for US1

The first six tasks all touch [src/aivg_core/adapter.py](../../src/aivg_core/adapter.py) — same file, so sequential. T010–T015 touch different files and may run in parallel with each other (but after T004–T009 land).

- [X] T004 [US1] Rename `class SatelliteWebRTCAdapter:` → `class AivgSatelliteAdapter:` at [src/aivg_core/adapter.py:30](../../src/aivg_core/adapter.py#L30). Update the module-level + class-level docstrings at lines 1 and 30 to use the canonical name.
- [X] T005 [US1] Add the back-compat alias `SatelliteWebRTCAdapter = AivgSatelliteAdapter` immediately after the class definition in [src/aivg_core/adapter.py](../../src/aivg_core/adapter.py). Include a 2-line docstring per [data-model.md § 3](./data-model.md#3-back-compat-alias-satellitewebrtcadapter) — name the removal release.
- [X] T006 [US1] Update the class attribute `name = "satellite_webrtc"` at [src/aivg_core/adapter.py:31](../../src/aivg_core/adapter.py#L31) to `name = CANONICAL_PLUGIN_NAME`. Add the import at the top of the file: `from .platforms.hermes.setup import CANONICAL_PLUGIN_NAME`.
- [X] T007 [US1] Update the error message string at [src/aivg_core/adapter.py:98](../../src/aivg_core/adapter.py#L98) from `f"satellite_webrtc not ready: signaling site failed to bind …"` to `f"{CANONICAL_PLUGIN_NAME} not ready: signaling site failed to bind …"`.
- [X] T008 [US1] Update the `get_chat_info` return at [src/aivg_core/adapter.py:277](../../src/aivg_core/adapter.py#L277) — change `"platform": "satellite_webrtc"` to `"platform": CANONICAL_PLUGIN_NAME`. Rationale: [research.md § R-4](./research.md#r-4-what-does-get_chat_info-return-for-the-platform-field).
- [X] T009 [US1] Update `PlatformEntry(name="satellite_webrtc", …)` at [src/aivg_core/adapter.py:295](../../src/aivg_core/adapter.py#L295) → `PlatformEntry(name=CANONICAL_PLUGIN_NAME, …)`. In the same call, update the adjacent `plugin_name="hermes_satellite_adapter"` at line 300 → `plugin_name="aivg_core"` (cosmetic per [research.md "Cross-cutting non-issues"](./research.md#cross-cutting-non-issues-recorded-for-completeness)).
- [X] T010 [P] [US1] Update [src/aivg_core/__main__.py](../../src/aivg_core/__main__.py): change `from .adapter import SatelliteWebRTCAdapter` at line 16 → `from .adapter import AivgSatelliteAdapter`; update the dev banner at line 40 `f"[dev] satellite_webrtc adapter up — management:"` to read `f"[dev] {CANONICAL_PLUGIN_NAME} adapter up — management:"`. Add the `CANONICAL_PLUGIN_NAME` import.
- [X] T011 [P] [US1] Update docstring reference in [src/aivg_core/platforms/base.py:173](../../src/aivg_core/platforms/base.py#L173): change `:class:`SatelliteWebRTCAdapter`` → `:class:`AivgSatelliteAdapter``. Cosmetic, but keeps Sphinx-style cross-references resolvable.
- [X] T012 [US1] Update the plugin entry-point shim at [src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py:53](../../src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py#L53): change `name="satellite_webrtc"` → `name="aivg_satellite"` in the `ctx.register_platform(...)` call. (Reading from a constant is acceptable but optional here; the entry-point shim is the canonical reader so a literal is also OK.) Update the module docstring at line 1 from "Plugin entry point for the satellite_webrtc platform" → "Plugin entry point for the aivg_satellite platform". This task does NOT add the conflict detector — that's T016 in US2.
- [X] T013 [P] [US1] Update [src/aivg_core/platforms/hermes/plugin_entrypoint/__init__.py:1](../../src/aivg_core/platforms/hermes/plugin_entrypoint/__init__.py#L1) docstring from "Hermes platform plugin: satellite_webrtc." → "Hermes platform plugin: aivg_satellite (formerly satellite_webrtc)."
- [X] T014 [P] [US1] Update [tests/fixtures/platforms/echo/setup.py](../../tests/fixtures/platforms/echo/setup.py): the three `self._st.plugins_dir / "satellite_webrtc"` references (lines 80, 136, 201) become `self._st.plugins_dir / "aivg_satellite"`. The echo fixture exercises the CANONICAL install path going forward; the legacy-path test exists separately in setup.py's `LEGACY_PLUGIN_NAME` cleanup logic.
- [X] T015 [P] [US1] Update [tests/unit/test_adapter_sites.py:65-73](../../tests/unit/test_adapter_sites.py#L65-L73): change the import to `from aivg_core.adapter import AivgSatelliteAdapter` AND add a sibling test that imports the back-compat alias (`from aivg_core.adapter import SatelliteWebRTCAdapter as _SWA; assert _SWA is AivgSatelliteAdapter`) so both names are exercised. Update the existing test's instantiation to use the new class name.
- [X] T016 [P] [US1] Create [tests/unit/test_plugin_registration_name.py](../../tests/unit/test_plugin_registration_name.py) with three tests:
  (1) call `register()` with a recording-fake `ctx` (a `unittest.mock.MagicMock`), assert `ctx.register_platform.call_args.kwargs["name"] == "aivg_satellite"`;
  (2) assert `AivgSatelliteAdapter.name == "aivg_satellite"`;
  (3) assert the back-compat alias `SatelliteWebRTCAdapter is AivgSatelliteAdapter` (identity, not equality).

**Checkpoint US1**: After T016, run `pytest tests/unit/test_plugin_registration_name.py tests/unit/test_adapter_sites.py -v` — all pass. Run quickstart §1.1 grep — zero matches. Story 1 is complete and independently verifiable; the rename has landed.

---

## Phase 4: User Story 2 — Conflict detector kills the silent shadow (Priority: P1)

**Goal**: When the post-019 entry-point plugin's `register()` is invoked AND a pre-rebrand bundled `satellite_webrtc/` plugin is still installed in Hermes's plugin scan path, `register()` raises `RuntimeError` with a clear operator-actionable message instead of silently letting both plugins coexist and shadow each other. This is the direct fix for the trap that consumed hours of today's deploy session.

**Independent Test**: per [quickstart.md § 6](./quickstart.md): re-inject the legacy backup directory, restart the gateway, confirm the gateway log shows a clear ERROR line naming the conflicting directory + cleanup verb, confirm `hermes plugins list` shows `aivg-satellite` with `error="<conflict text>"`, confirm OTHER Hermes platforms (irc/etc.) load normally.

### Implementation tasks for US2

- [X] T017 [US2] Add the helper `_check_no_legacy_bundled_plugin()` at module scope in [src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py](../../src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py). Signature + docstring per [data-model.md § 2](./data-model.md#2-conflict-detector-_check_no_legacy_bundled_plugin). Body: import `hermes_cli.plugins.get_plugin_manager` lazily inside the function (to avoid hard-importing hermes at AIVG import time — keeps non-Hermes contexts importable); call `discover_plugins()` if available, then `get_plugin_manager().list_plugins()`; iterate and look for any plugin where `p.get("name") == "satellite-webrtc-platform"` AND `p.get("source") == "bundled"`. On match: raise `RuntimeError` with the multi-line message described in [research.md § R-2](./research.md#r-2-what-does-register-do-when-a-conflict-is-detected) (name, directory path, cleanup verb, reason). Wrap the whole helper body in try/except for the unhappy API case ([data-model.md § 2 "Hermes plugin manager API unavailable"](./data-model.md#2-conflict-detector-_check_no_legacy_bundled_plugin) — log a warning, return None).
- [X] T018 [US2] Wire the helper into `register()` in the same file [src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py:33](../../src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py#L33): call `_check_no_legacy_bundled_plugin()` as the FIRST statement of `register()` body, BEFORE `entry = build_platform_entry()`. A raise from the helper short-circuits the whole `register()` and Hermes's plugin loader surfaces the error.
- [X] T019 [P] [US2] Create [tests/unit/test_conflict_detector.py](../../tests/unit/test_conflict_detector.py). Use `unittest.mock.patch` to replace `hermes_cli.plugins.get_plugin_manager` with a stub whose `list_plugins()` returns a controlled list including a fake `{"name": "satellite-webrtc-platform", "source": "bundled", "enabled": True, "path": "/tmp/fake/satellite_webrtc"}` row. Assert `_check_no_legacy_bundled_plugin()` raises `RuntimeError`. Assert the message contains the directory path AND the cleanup verb string AND the literal `mv` or `rm` recommendation. Two further tests: (a) plugin manager returns a plugin with name `satellite-webrtc-platform` but `source="entrypoint"` (not bundled) → no raise; (b) plugin manager returns multiple legacy plugins → raise message enumerates all of them.
- [X] T020 [P] [US2] Create [tests/unit/test_no_conflict_quiet_path.py](../../tests/unit/test_no_conflict_quiet_path.py). Patch the plugin manager to return ONLY the entry-point plugin (`{"name": "aivg-satellite", "source": "entrypoint", "enabled": True}`). Assert `_check_no_legacy_bundled_plugin()` returns `None` and DOES NOT raise. Capture stderr/log and assert ZERO WARNING-or-higher records were emitted (the detector must be silent on the common case).
- [X] T021 [P] [US2] Add one more test in [tests/unit/test_conflict_detector.py](../../tests/unit/test_conflict_detector.py) (sequential with T019's other tests since same file): patch the plugin manager to RAISE on `list_plugins()` — assert `_check_no_legacy_bundled_plugin()` logs a warning but does NOT propagate the exception (does NOT block registration). This is the "Hermes API unavailable" edge case from [data-model.md § 2](./data-model.md#2-conflict-detector-_check_no_legacy_bundled_plugin).

**Checkpoint US2**: After T021, run `pytest tests/unit/test_conflict_detector.py tests/unit/test_no_conflict_quiet_path.py -v` — all pass. Both US1 and US2 are independently complete.

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Run the full regression, the wire-surface diff harness, and live verification against the running Hermes gateway. Land the CHANGELOG entry.

- [X] T022 Run the full test suite 3 times per [quickstart.md § 3](./quickstart.md): `for i in 1 2 3; do PYENV_VERSION=3.11.9 PYTHONPATH=src:tests pytest tests/ -q --tb=line 2>&1 | tail -3; echo ---; done`. Expected: `329 + N passed, 0 failed` where `N` is the count of new tests added in T015–T021 (approximately 8–12). Zero flakes across the 3 runs.
- [X] T023 [P] Static surface check per [quickstart.md § 1.1](./quickstart.md): from repo root, run `rg --no-heading -n '"satellite_webrtc"|satellite_webrtc' src/aivg_core/ --glob '!*setup.py'`. Expected: zero matches. The single allowed remaining reference is `LEGACY_PLUGIN_NAME = "satellite_webrtc"` inside `setup.py`. If any other match is found, that file was missed by US1's rename tasks — fix and re-run.
- [X] T024 [P] Wire-surface byte-diff per [quickstart.md § 4.2, § 4.3](./quickstart.md): on the 019 branch, restart the gateway, capture `/tmp/aivg-019-baseline/post/`, then `diff -u` against `/tmp/aivg-019-baseline/pre/` from T001. Expected: zero diff on `list.json`, `contract-version.json`, and `ws-register.txt`. This is the binding constitution-II gate (SC-002).
- [X] T025 Live gateway log assertion per [quickstart.md § 5](./quickstart.md): restart Hermes, `sleep 5`, `grep -E 'aivg_satellite|satellite_webrtc' ~/.hermes/logs/gateway.log | tail -10`. Expected: lines containing `aivg_satellite` (e.g. `✓ aivg_satellite connected`); ZERO lines containing `satellite_webrtc` from the post-019 restart timestamp onward.
- [X] T026 Live conflict-detector smoke per [quickstart.md § 6.1–6.3](./quickstart.md): restore the pre-rebrand vendored plugin from `~/.hermes/backups/satellite_webrtc.pre-aivg-redeploy.*.bak`, restart the gateway, confirm the conflict-detector ERROR log line appears within 5s, confirm OTHER platforms (irc/etc.) still load. Then move the legacy directory back out, restart, confirm clean boot.
- [X] T027 Live pre-019-client compat smoke per [quickstart.md § 7.1](./quickstart.md): from `clients/electron-test/`, run `npm start`, do connect → adopt → press-and-hold PTT → release. Expected: full voice turn completes; renderer shows `adoption: adopted ✓`; ZERO renderer-side changes were required.
- [X] T028 Add CHANGELOG entry per [quickstart.md § 8](./quickstart.md) to `CHANGELOG.md` at repo root. Version `0.3.1` (PATCH bump from current 0.3.0 — internal rename + safety net, no API surface change). Entry text per the quickstart template.

---

## Dependencies & Story Completion Order

```text
Phase 1 Setup (T001, T002)
   │
   ▼
Phase 2 Foundational (T003 — CANONICAL_PLUGIN_NAME constant)
   │
   ├──▶ Phase 3 US1: Rename (T004–T016)
   │       │
   │       └──▶ Phase 4 US2: Conflict detector (T017–T021)
   │
   └──▶ Phase 4 US2: ... can also start in parallel after T003
        (US2 references CANONICAL_PLUGIN_NAME via the entry-point
         shim, but is otherwise independent of US1's rename sites)
            │
            ▼
        Phase 5 Polish (T022–T028) — runs after BOTH US1 and US2 land
```

- **US2 is independent of US1.** The conflict detector lives in `plugin_entrypoint/adapter.py` and queries the Hermes plugin manager. It does not read `CANONICAL_PLUGIN_NAME` directly (it checks for the LEGACY plugin's manifest name `"satellite-webrtc-platform"`). Strictly, US2 could ship before US1 if needed — but US1 is the headline deliverable, so the natural shipping order is US1 → US2.
- **Polish phase (T022–T028) waits for both stories.** The regression runs and the live smokes assume both the rename and the conflict detector are in place.

---

## Parallel Execution Examples

### Within Phase 3 (US1)

After the sequential adapter.py edits (T004 → T005 → T006 → T007 → T008 → T009) land, the rest of US1 can run in parallel:

```text
T010 [P] (__main__.py)
T011 [P] (platforms/base.py docstring)
T013 [P] (plugin_entrypoint/__init__.py)
T014 [P] (echo fixture)
T015 [P] (test_adapter_sites.py)
T016 [P] (test_plugin_registration_name.py — new file)
```

`T012` (plugin_entrypoint/adapter.py:53) is the same file as T017–T018 in US2, so don't parallelize it with US2 tasks. Land T012 before US2 starts so US2's edits don't conflict on the same file.

### Within Phase 4 (US2)

```text
T017 (helper)       ┐
                    ├─ sequential (same file: plugin_entrypoint/adapter.py)
T018 (wire-up)      ┘

T019 [P] (test_conflict_detector.py — new file)
T020 [P] (test_no_conflict_quiet_path.py — new file)
T021 [P] (test_conflict_detector.py — additional case; sequential with T019)
```

### Within Phase 5 (Polish)

```text
T023 [P] (static surface check)
T024 [P] (wire-surface byte-diff)
T026 (live conflict-detector smoke — needs gateway access)
T027 (live electron-test compat — needs gateway access)

T022 (full pytest suite) — sequential, mutates test working directory
T025 (live gateway log assertion) — sequential, requires gateway restart
T028 (CHANGELOG entry) — sequential, mutates a single repo-root file
```

T026 and T027 both require an interactive gateway and the electron-test, so they're sequential against each other in practice (one operator can only watch one app at a time).

---

## Implementation Strategy

### MVP (delivers user-visible value on its own)

**US1 alone is the MVP.** Land T001–T016 plus T022 (full regression) and T025 (live log assertion). At that point:

- Gateway log lines emit `aivg_satellite` (the operator-facing rename has happened).
- All 329+ existing tests still pass.
- No wire-surface change (SC-002 satisfied — operators on the existing legacy plugin path notice nothing).
- A pre-019 vendored bundled plugin would still silently shadow the entry-point plugin — but no MORE silently than it does today on `main`, since today the shadowing wasn't even possible to detect from the AIVG side.

US1 alone is a complete, ship-ready release.

### Incremental — add US2 (safety net)

Land T017–T021 plus T026 (live conflict-detector smoke) afterward. At that point:

- The silent-shadow trap that consumed hours of today's deploy session can no longer happen — the entry-point plugin's `register()` refuses to register when the legacy bundled plugin is also installed, with a clear operator-actionable error.
- Every existing operator with a pre-019 install gets a loud failure on first post-019 boot instead of a silent shadow. The error tells them exactly what to do.

US1 + US2 = the full feature.

### Final — Polish

T023, T024, T027, T028 round out the verification suite + CHANGELOG. These are not optional — they're the binding gates the constitution check assumes ran. Specifically, T024 (wire-surface byte-diff) is the literal SC-002 gate, and T023 (static surface check) is the literal SC-001 gate.

---

## Test Count Target

- **Pre-019 baseline**: 329 passing (from feature 017's closeout).
- **New tests added by 019**:
  - test_plugin_registration_name.py: 3 tests (T016)
  - test_conflict_detector.py: 4 tests (T019 + T021)
  - test_no_conflict_quiet_path.py: 1 test (T020)
  - test_adapter_sites.py: +2 sibling tests for back-compat alias + new class name (T015)
- **Target post-019**: `329 + 10 = 339` passing, 0 failing, 3-run flake-free per T022.

---

## Out-of-Scope Reminders

To make the implementation auditable against the clarification-driven scope reduction, these explicitly remain UNCHANGED by 019 and are NOT covered by any task:

- REST routes under `/satellite/*` (no rename, no aliases)
- WebSocket paths `/satellite/ws` (no rename, no aliases)
- `~/.hermes/config.yaml` `satellite:` config block (no migration, no rename)
- Environment variables `SATELLITE_ALLOWED_USERS` / `SATELLITE_ALLOW_ALL_USERS` (no rename, no deprecation)
- Contract version `1.1.0` (no bump; `aivg --contract-version` output bytes invariant)
- `@aivg/sat-sdk` TypeScript SDK (no release; stays at 0.1.4)
- The `aivg-satellite` PyPI entry-point manifest name (unchanged — operators do NOT edit `plugins.enabled:`)
- ESPHome native API transport (port 6053; unaffected)
- `Platform.LOCAL` enum value used in `SessionSource` (unchanged)
- `AgentPlatform`, `MediaTransport`, `SetupCapability` Protocol surfaces (unchanged)

Any task that creeps into this territory is a scope violation against [spec.md § Clarifications](./spec.md#clarifications) and MUST be split into a separate feature.
