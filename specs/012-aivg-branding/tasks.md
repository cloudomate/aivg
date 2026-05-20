---
description: "Task list for feature 012-aivg-branding"
---

# Tasks: AIVG Rebrand — Hermes Voice → AI Voice Gateway

**Input**: Design documents from [/specs/012-aivg-branding/](.)
**Constitution**: v2.0.0 → **v2.0.1** in this feature (PATCH bump)
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Tests**: included — three new unit tests are explicit FR/SC requirements
(`test_no_legacy_branding.py` per FR-012, `test_compat_shim.py` per
FR-003/FR-004/SC-004, `test_persistence_migration.py` per
FR-005/SC-005).
**Organization**: tasks are grouped by user story (US1–US5). Phase 1
(Setup) and Phase 2 (Foundational) block all stories.

## Format: `[ID] [P?] [Story?] Description with file path`

## Path conventions

Single-repo Python project (existing). New homes:
`src/aivg_core/` (formerly `satellite_core/`) and `src/aivg_cli/`
(formerly `sat_cli/`). The Hermes-plugin folder
`platforms/hermes/` and `skills/hermes-agent/` are **frozen** — the
rebrand does not touch them beyond prose mentions of "Hermes Voice"
inside their docs.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: prepare the new package skeletons and the rebrand
allow-list. No behavior change yet — every test should still pass at
the checkpoint.

- [X] T001 Create the new package directories with empty `__init__.py`: `src/aivg_core/`, `src/aivg_cli/`. The new homes are siblings of the existing `src/satellite_core/` and `src/sat_cli/` (which become shims in Phase 2).
- [X] T002 [P] Create the rebrand allow-list documentation at `docs/rebrand-allow-list.md` with the seed contents from [research.md R-4](./research.md) — patterns are gitignore-style globs, one per line; whole-line `#` is a comment.
- [X] T003 [P] Add `docs/aivg-data-dir.md` documenting `~/.aivg/config.yaml`, `~/.aivg/state.json`, `~/.aivg/firmware/<device_type>/manifest.json`, and the first-run migration semantics (R-3). Cross-link from `docs/satellite-data-dir.md` (which gets a "renamed in feature 012" header note).
- [X] T004 Update [pyproject.toml](pyproject.toml): rename `[project].name` to `aivg-core`; update `[project].description` to "AIVG — AI Voice Gateway: …"; replace `[project.scripts] sat-cli` with `aivg = "aivg_cli.cli:app"` AND keep `sat-cli = "sat_cli.cli:legacy_app"` (one-release alias); add `aivg_core*` and `aivg_cli*` to `[tool.setuptools.packages.find].include`; extend `filterwarnings` to also ignore the new `aivg_core` and `aivg_cli` shim DeprecationWarnings during tests.
- [X] T005 [P] Refresh the existing migration table in [specs/011-satellite-management/plan.md](specs/011-satellite-management/plan.md#structure-decision) — add a one-line note "(superseded in feature 012 by aivg_core / aivg_cli; old paths are compat shims)" pointing at this feature.

**Checkpoint**: new package dirs exist (empty); pyproject knows about them; allow-list doc exists. No code moved yet, no tests broken.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: move every existing source file to its new home, install
the compat shims, and add the data-dir migration. After this phase the
project builds and **every existing test passes via the shims** — the
prose sweep and the lint follow in Phase 3+.

- [X] T006 `git mv src/satellite_core/*` → `src/aivg_core/` (preserving the `platforms/hermes/`, `platforms/openclaw/`, `webrtc/`, `management/` subtrees verbatim) and rename intra-package references inside the moved files from `satellite_core` → `aivg_core` (Python imports, docstring file paths, `# AgentPlatform-coupling-TODO` markers stay).
- [X] T007 `git mv src/sat_cli/*` → `src/aivg_cli/`. Update `src/aivg_cli/cli.py`'s tagline to "AIVG management CLI — platform-neutral (feature 011, constitution v2.0.0)" and intra-package imports from `sat_cli` → `aivg_cli`. Imports of `satellite_core.*` inside `aivg_cli` change to `aivg_core.*`.
- [X] T008 Add the data-dir migration function in `src/aivg_core/persistence.py`: `migrate_legacy_data_dir(*, src=Path("~/.satellite").expanduser(), dst=Path("~/.aivg").expanduser()) -> bool` per [research.md R-3](./research.md#r-3) — atomic write of `dst/state.json`, then `os.replace(src/state.json, src/state.json.pre-aivg-rebrand.bak)`; idempotent; the `firmware/` subtree migrates via the same pattern.
- [X] T009 Wire the migration: call `migrate_legacy_data_dir()` once from `aivg_core.management.service.ManagementService.__init__` (or from `aivg_core.adapter.SatelliteWebRTCAdapter.__init__`, whichever fires first on gateway startup) BEFORE any read of `~/.aivg/state.json`. Guard with a process-level sentinel so it never runs twice in the same process.
- [X] T010 Replace `src/satellite_core/__init__.py` with the **cached-DeprecationWarning shim** per [research.md R-1](./research.md#r-1): `sys.__dict__["_aivg_satellite_core_shim_warned"]` sentinel + `from aivg_core import *` + explicit submodule re-imports (`models`, `registry`, `logsink`, `config`, `persistence`, `turnlatency`, `management`, `webrtc`, `platforms`, `adapter`). Add `src/satellite_core/<every_subpackage>/__init__.py` shims if any tests import submodules directly.
- [X] T011 Replace `src/sat_cli/__init__.py` with a cached-DeprecationWarning shim re-exporting from `aivg_cli`. Create `src/sat_cli/cli.py` with a `legacy_app()` function: writes one stderr line `"sat-cli is renamed to aivg (feature 012, AIVG rebrand). The legacy binary still works for this release."` (cached via `sys.__dict__`), then `aivg_cli.cli.app()`. The `[project.scripts] sat-cli` entry from T004 points here.
- [X] T012 Update the existing `src/hermes_satellite_adapter/__init__.py` two-hop shim from feature 011: change its `from satellite_core import …` to `from aivg_core import …` and refresh its `DeprecationWarning` text to mention the AIVG rebrand. Same `sys.__dict__` sentinel pattern. The shim now points two hops forward (`hermes_satellite_adapter → aivg_core`).
- [X] T013 Run the full test suite (`PYTHONPATH=src pytest -q`) to confirm Phase 2 is import-clean: every existing test passes via the shims; the shim DeprecationWarnings are silenced by the pyproject `filterwarnings` from T004.
- [X] T014 [P] Bulk-update test import paths from `satellite_core.*` → `aivg_core.*` and `sat_cli.*` → `aivg_cli.*` across `tests/**/*.py` (the shims would keep them working, but the canonical state of tests must point at the new names). Use `sed -i.bak` then delete the backups, same pattern as the feature 011 rename (T005 there).
- [X] T015 Run the full test suite again to confirm direct imports work — should be 170+ passing.

**Checkpoint**: code lives at the new paths; old paths are silent (cached-warned) compat shims; data-dir migration is wired; tests pass on the new imports.

---

## Phase 3: User Story 1 — Product identity (Priority: P1) 🎯 MVP

**Goal**: a fresh reader sees the product as AIVG within the first screen of any entry point. Pure prose sweep — no code behavior changes.

**Independent Test**: open the README (when added), root docs, constitution, the latest spec, and `aivg --help`; the product is identified as AIVG in the first paragraph/screen of each.

### Tests

- [X] T016 [P] [US1] Smoke test: `PYTHONPATH=src python -m aivg_cli.cli --json --version` returns an envelope whose `data.version` matches the new package version; `data.contract_version` is `1.0.0` (unchanged); the rendered `--help` tagline contains "AIVG" not "satellite_webrtc"/"Hermes Voice". Add as `tests/unit/test_cli_tagline.py`.

### Implementation (prose sweep)

- [X] T017 [US1] Create `README.md` at the repo root with AIVG-first framing (product name, what it does, the satellite-management CLI quickstart, link to the latest plan). If a README already exists, rewrite the top-of-file product paragraph.
- [X] T018 [P] [US1] Update [src/aivg_cli/cli.py](src/aivg_cli/cli.py) tagline + every Typer `help=` string that mentions the product to AIVG (commands: root `_root` callback, `list`, `device get`, `logs`, `fleet logs`, `watch`, `onboard`). Do NOT change command names or flag names (FR-008).
- [X] T019 [P] [US1] Update [skills/hermes-agent/SKILL.md](skills/hermes-agent/SKILL.md) `description` frontmatter and body prose so the skill describes itself as "the Hermes plugin for AIVG"; do NOT change the `name:` frontmatter (it is `satellite-management`, a capability id — FR-009). Refresh [skills/hermes-agent/README.md](skills/hermes-agent/README.md) similarly.
- [X] T020 [P] [US1] Update [skills/openclaw/README.md](skills/openclaw/README.md) preamble to "Planned OpenClaw plugin for AIVG (constitution v2.0.0 Principle IV)".
- [X] T021 [P] [US1] Sweep prose mentions of "Hermes Voice"/"Hermes Voice Satellite"/"Hermes voice" → "AIVG" across `docs/*.md` (excluding the rebrand allow-list — see `docs/rebrand-allow-list.md`). Specifically: `docs/generic-voice-satellite-design.md` (Hermes-plugin-section retains the Hermes name; product-name prose at the top updates to AIVG), and refresh `docs/satellite-data-dir.md` with a header note pointing at the new `docs/aivg-data-dir.md`.
- [X] T022 [P] [US1] Sweep prose mentions in historical specs `specs/001-...` through `specs/011-satellite-management/` (excluding their `tasks.md` which is historical implementation log). Strategy per [research.md R-6](./research.md#r-6): rewrite product-name prose; LEAVE identifier strings (`hermes_satellite_adapter`, `satellite_core`, `sat_cli`) intact because they document the state-at-the-time. Files to touch (from the Phase 0 survey): `specs/005-aiortc-media-transport/quickstart.md`, `specs/006-streaming-tts/quickstart.md`, `specs/007-live-agent-streaming/quickstart.md`, `specs/008-agent-delta-streaming/quickstart.md`, `specs/009-tts-text-normalization/{quickstart,research,spec}.md`, `specs/010-voice-turn-latency/quickstart.md`, `specs/011-satellite-management/{plan.md,contracts/management-api.yaml}`.
- [X] T023 [P] [US1] Update [clients/electron-test/README.md](clients/electron-test/README.md) — replace "Hermes Voice" prose mentions with "AIVG".
- [X] T024 [P] [US1] Update [deploy/plugin/plugin.yaml](deploy/plugin/plugin.yaml) — rewrite the `description` / label fields to AIVG; `name` / identifier keys stay because they are configuration ids, not display names.

**Checkpoint**: every entry point identifies the product as AIVG within the first screen; identifier strings unchanged; Hermes-plugin names untouched.

---

## Phase 4: User Story 2 — Compat shims keep existing consumers working (Priority: P1)

**Goal**: external consumers on the old names (`satellite_core` import, `sat-cli` binary, `~/.satellite/` data dir) keep working for one release, each producing exactly one `DeprecationWarning` per process.

**Independent Test**: a fresh shell after the rebrand: `python -c 'from satellite_core import models'` succeeds with one warning; `sat-cli --version` works with a stderr notice; an existing `~/.satellite/state.json` is preserved and `~/.aivg/state.json` matches.

### Tests

- [X] T025 [P] [US2] Create `tests/unit/test_compat_shim.py` with cases (in addition to T013/T015 already exercising the shims): (a) `import satellite_core` emits exactly one `DeprecationWarning` per process (re-importing in the same process emits nothing); (b) the warning's message names `aivg_core` as the new path; (c) `import sat_cli` does the same for `aivg_cli`; (d) running `sat_cli.cli.legacy_app()` writes one line to **stderr** that mentions `aivg`, and stdout from a subsequent `--version` is byte-equivalent to running `aivg_cli.cli.app(['--json','--version'])` (proves the JSON envelope on stdout is unchanged); (e) `from hermes_satellite_adapter import models` still resolves (two-hop shim).
- [X] T026 [P] [US2] Create `tests/unit/test_persistence_migration.py` covering [research.md R-3](./research.md#r-3): seed a temp dir with `tmp/.satellite/state.json` containing one adopted client; call `migrate_legacy_data_dir(src=tmp/.satellite, dst=tmp/.aivg)`; assert `tmp/.aivg/state.json` exists with identical content; assert `tmp/.satellite/state.json.pre-aivg-rebrand.bak` exists; assert calling the function again is idempotent (no-op when `dst` is newer). Also cover: no `src/state.json` → no-op; conflicting `src` and `dst` (newer `dst` wins; older `src` still gets renamed to `.bak`).

### Implementation

> Phase 2 already added the shims (T010, T011, T012). This phase is the test wrapper proving they behave correctly. If the tests fail, the fix lands in the shim implementations, not new code.

**Checkpoint**: compat-shim tests green; one DeprecationWarning per process; stderr-only deprecation for `sat-cli`; data-dir migration atomic and idempotent.

---

## Phase 5: User Story 3 — Zero substantive contract drift (Priority: P2)

**Goal**: every documented `operationId`, schema, status code, route, CLI exit code, `error.code`, JSON envelope field, and `--contract-version` value is byte-identical before and after the rebrand. Labels only change.

**Independent Test**: a scripted diff (added in T028 below) that strips `info.title` / H1 / tagline substitutions reports zero substantive differences vs the feature-011 versions of `contracts/management-api.yaml`, `cli-contract.md`, `management-ws.md`, `agent-platform.md`.

### Tests / verification

- [X] T027 [P] [US3] Update [specs/011-satellite-management/contracts/management-api.yaml](specs/011-satellite-management/contracts/management-api.yaml): `info.title` "Hermes Satellite Management API" → "AIVG Satellite Management API"; rewrite the prose in `info.description` to AIVG. **Do not touch any `operationId`, schema name, schema field, enum value, route, or status code** (FR-007 / SC-003).
- [X] T028 [P] [US3] Add a contract-drift verification step in `tests/contract/test_rebrand_invariants.py`: load both `contracts/management-api.yaml` and parse it with PyYAML; walk every `paths.*` → assert each `operationId` matches the closed set from `data-model.md` §1 (the set is the post-rebrand list, which equals the pre-rebrand list); walk every `components.schemas.*` → assert each schema name matches; walk every `error` enum → assert every value is one of the documented closed set. Failing this test means the rebrand silently dropped or renamed a contract field.
- [X] T029 [P] [US3] Update [specs/011-satellite-management/contracts/cli-contract.md](specs/011-satellite-management/contracts/cli-contract.md): H1 / binary references "`sat-cli`" → "`aivg`"; add a section "Legacy binary alias" describing the `sat-cli` compat alias and its stderr deprecation. **Do not change the JSON envelope shape, the closed `error.code` set, exit codes, command names, or flags** (FR-008).
- [X] T030 [P] [US3] Update [specs/011-satellite-management/contracts/management-ws.md](specs/011-satellite-management/contracts/management-ws.md): preamble prose updates to AIVG; every frame `type`, every required field, every direction-of-travel claim stays byte-equivalent.
- [X] T031 [P] [US3] Update [specs/011-satellite-management/contracts/agent-platform.md](specs/011-satellite-management/contracts/agent-platform.md): the package-path mentions `satellite_core/platforms/...` → `aivg_core/platforms/...`; the Protocol method names + signatures stay verbatim; the OpenClaw stub + Hermes plugin's `PLATFORM.name` values stay verbatim.

**Checkpoint**: every contract document has been re-titled and prose-updated; the byte-equivalence test green; aivg's `--contract-version` still reports `1.0.0`.

---

## Phase 6: User Story 4 — Constitution PATCH amendment (Priority: P2)

**Goal**: constitution amended from v2.0.0 → v2.0.1; title is AIVG-first; Sync Impact Report records the rebrand; Principles I–V keep normative content byte-equivalent (modulo product-name strings).

**Independent Test**: open the constitution top-to-bottom and verify title + preface + Sync Impact Report entry + footer version; the scripted Principle-text byte-diff (T034 below) reports zero substantive differences.

### Implementation

- [X] T032 [US4] Amend [.specify/memory/constitution.md](.specify/memory/constitution.md): rewrite the title to "AIVG Constitution"; rewrite the project-codename preface to "*Project codename: AIVG (AI Voice Gateway). Formerly 'Hermes Voice' through feature 011.*"; sweep prose mentions of "Hermes Voice" / "Hermes Voice satellite" → "AIVG"; preserve every Hermes-as-plugin reference verbatim (these appear in Principle IV's rule text and the rationale).
- [X] T033 [US4] Prepend a new Sync Impact Report entry at the top of [.specify/memory/constitution.md](.specify/memory/constitution.md) recording: version change `2.0.0 → 2.0.1`; bump rationale "PATCH. Branding rebrand only (Hermes Voice → AIVG (AI Voice Gateway)). No principle text gains or loses normative meaning. Hermes remains the v1 agent-platform plugin per v2.0.0 Principle IV."; templates/artifacts status table noting which files in the repo updated alongside the amendment.
- [X] T034 [US4] Add `tests/unit/test_constitution_principles_byte_equiv.py`: load the post-amendment constitution; for each Principle I–V section, normalize by replacing every "AIVG" with a sentinel `__PRODUCT__` and every "Hermes Voice" or "hermes voice" with the same sentinel; load the **pre-amendment** Principle text from a fixture (the verbatim Principle bodies copied into `tests/fixtures/constitution_v2_0_0_principles.md`) with the same normalization; assert the two are byte-equivalent. Failing this test means the PATCH amendment accidentally drifted normative content — that's a separate amendment, not part of this feature.
- [X] T035 [US4] Update the constitution footer "Version: 2.0.0 | Last Amended: 2026-05-20" → "Version: 2.0.1 | Last Amended: 2026-05-20" (same date if the amendment happens today; otherwise the actual date).

**Checkpoint**: constitution v2.0.1 in place; Sync Impact Report records the rebrand; byte-equivalence test green.

---

## Phase 7: User Story 5 — Lint catches reintroductions (Priority: P3)

**Goal**: a CI-runnable lint scans the working tree for the obsolete product name and fails on any non-allow-listed hit.

**Independent Test**: with the lint installed and the allow-list seeded, the working tree post-rebrand passes `pytest tests/unit/test_no_legacy_branding.py`. Manually re-introduce "Hermes Voice" into a non-allow-listed file, re-run, and the test fails with a clear pointer.

### Implementation

- [X] T036 [P] [US5] Create `tests/unit/test_no_legacy_branding.py` per [research.md R-4](./research.md#r-4): reads `docs/rebrand-allow-list.md`, walks the repo's tracked text files (`.md`, `.py`, `.toml`, `.yaml`, `.yml`, `.cfg`), and asserts no obsolete-product-name regex matches a non-allow-listed file outside a comment line. The regex is `r"\bHermes Voice\b|\bhermes voice\b"`. Skip lines whose leading non-whitespace is `#` (allow file-top historical notes).
- [X] T037 [P] [US5] Validate the allow-list (`docs/rebrand-allow-list.md`) against the repo's actual paths in `tests/unit/test_no_legacy_branding.py`: every pattern in the allow-list MUST resolve to at least one file; orphaned patterns fail loudly (catches typos when allow-list entries are added prematurely).
- [X] T038 [US5] Confirm the lint passes by running it locally: `PYTHONPATH=src pytest tests/unit/test_no_legacy_branding.py -v`. If anything fails outside the allow-list, add the file to the allow-list (legitimate historical reference) or rewrite the prose (forgotten sweep). Iterate until green.

**Checkpoint**: the lint is green; any future PR that re-introduces the obsolete product name fails the standard test invocation.

---

## Phase 8: Polish & Cross-Cutting Concerns

- [X] T039 Run the full test suite one final time and capture the count baseline: `PYTHONPATH=src pytest -q`. Expected: ≥170 passed + 1 xpassed, plus the net-new tests from this feature (T016 / T025 / T026 / T028 / T034 / T036). Record the number at the bottom of this tasks.md.
- [X] T040 [P] Re-evaluate the Constitution Check from [plan.md](./plan.md#constitution-check) against the shipped code under v2.0.1. All five principles must still PASS. Record the result at the bottom of this file.
- [X] T041 [P] Smoke-test the CLI end-to-end: `PYTHONPATH=src python -m aivg_cli.cli --json --version` → envelope has `data.contract_version == "1.0.0"` AND `data.version` reports an AIVG-aware version. Repeat with `python -m sat_cli.cli --json --version` (legacy alias) and confirm the same stdout JSON envelope plus one stderr line mentioning `aivg`.
- [X] T042 [P] Add a brief CHANGELOG entry (or equivalent repo-top release note file) mentioning the AIVG rebrand, the compat-shim window of one release, and a pointer at `docs/aivg-data-dir.md` and the Hermes-vs-AIVG quickstart table.
- [X] T043 [P] Track the compat-shim removal as a follow-up task for the next feature: write `specs/012-aivg-branding/followup-shim-removal.md` listing the four shim removal steps from [quickstart.md](./quickstart.md#removing-the-compat-shims-next-release).
- [X] T044 (Deferred — track only.) Repo-directory rename `hermes-voice/` → `aivg/` is **not** done in this feature (spec Assumption). Record it as a noted follow-up in `specs/012-aivg-branding/followup-repo-rename.md` with the external-clone-URL implications listed.

---

## Dependencies (story completion order)

```text
Phase 1 (Setup, T001–T005)
        │
        ▼
Phase 2 (Foundational, T006–T015)   ◄── git mv + shims + persistence migration; ALL stories block on this
        │
        ├──► Phase 3 (US1 — MVP product-identity sweep, T016–T024)
        │
        ├──► Phase 4 (US2 — compat-shim tests, T025–T026)
        │
        ├──► Phase 5 (US3 — contract no-drift, T027–T031)
        │
        ├──► Phase 6 (US4 — constitution PATCH, T032–T035)
        │
        ├──► Phase 7 (US5 — lint + allow-list, T036–T038)
        │
        ▼
Phase 8 (Polish, T039–T044)
```

**One PR end-to-end** is the recommended rollout per [research.md R-8](./research.md#r-8). Splitting introduces a window where the lint either doesn't exist (US5 not landed) or fails noisily (US1 not landed). Phase 2 is the binding prerequisite; everything from Phase 3 onward is largely parallelizable across pairs of contributors.

## Parallel-execution examples

**Within Phase 1**: T002, T003, T005 are `[P]` (different files).

**Within Phase 2**: T006/T007 are sequential (separate `git mv`s of overlapping import paths); T010/T011/T012 are sequential (each new shim depends on the previous); T014 is `[P]`-after-T013 because it touches only test files.

**Within Phase 3 (US1)**: T018–T024 are all `[P]` — different files; the prose sweep can fan out to up to six pairs of eyes.

**Within Phase 5 (US3)**: T027/T029/T030/T031 are all `[P]` — four different contract files. T028 sequences after T027 because it parses the YAML T027 just edited.

**Across stories**: Phases 3, 4, 5, 6, 7 can run in parallel once Phase 2 is done; their tests don't share files. Phase 8 sequences last.

## Implementation strategy

1. **Phase 1 + Phase 2** as the first half of the PR — purely mechanical (`git mv` + shims). Reviewers can sanity-check the new package skeleton without combing prose changes.
2. **Phase 3** (US1 — product-identity sweep) is the bulk of the prose churn. Driven by the lint (Phase 7) — write the lint FIRST locally, then iterate prose sweeps until the lint stays green.
3. **Phase 5** (US3 — contract no-drift) is the binding invariant of the feature. Phase 5's test (T028) is the single failing-line that proves you accidentally drifted a contract; treat it as a merge gate.
4. **Phase 6** (US4 — constitution PATCH) sequences last among the stories because Principle text quoting needs the AIVG renames stable.
5. **Phase 7** (US5 — lint) is the safety net that catches any miss in Phases 3 and 6.
6. **Phase 8** is the close-out — full test sweep + smoke tests + follow-up tracking.

## Format validation

All tasks above follow `- [ ] T### [P?] [Story?] Description with file path`:

- ✅ Checkbox: every line begins `- [ ]`.
- ✅ Task ID: T001 → T044 sequential.
- ✅ [P] marker: present on parallelizable tasks only.
- ✅ [Story] label: present on US1–US5 tasks only (T016–T038); absent on Setup (T001–T005), Foundational (T006–T015), Polish (T039–T044).
- ✅ Description includes a concrete file path or directory for every implementation task.

**Total task count**: 44 (Setup 5 · Foundational 10 · US1 9 · US2 2 · US3 5 · US4 4 · US5 3 · Polish 6).
