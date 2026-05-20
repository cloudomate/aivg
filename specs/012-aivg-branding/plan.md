# Implementation Plan: AIVG Rebrand — Hermes Voice → AI Voice Gateway

**Branch**: `012-aivg-branding` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/012-aivg-branding/spec.md`
**Constitution**: v2.0.0 → **v2.0.1** in this feature (PATCH bump)

## Summary

Coordinated rename of the **product** from "Hermes Voice" to **AIVG (AI
Voice Gateway)** across visible text, Python packages, CLI binary, and
the data directory. Compat shims (`DeprecationWarning`) kept for one
release. **Zero substantive contract drift** (FR-007/FR-008/SC-003):
operationIds, REST schemas, exit codes, `error.code`, `data.*` field
names, and `--contract-version` stay identical.

`Hermes` stays where it refers to **the v1 agent-platform plugin**
(constitution v2.0.0 Principle IV): `platforms/hermes/`,
`skills/hermes-agent/`, the plugin's reuse of `~/.hermes/config.yaml`,
`~/.hermes/.env`, `~/.hermes/logs/gateway.log`. All other "Hermes Voice"
prose mentions are rewritten.

What ships:

1. **Python packages renamed**: `satellite_core` → `aivg_core`,
   `sat_cli` → `aivg_cli`. The old paths become **compat shim
   packages** that re-export and emit one `DeprecationWarning`.
2. **CLI binary renamed**: `sat-cli` → `aivg`. The old `sat-cli`
   entry-point dispatches to the new binary with a stderr deprecation
   notice (never stdout — JSON consumers stay clean).
3. **Data directory renamed**: `~/.satellite/` → `~/.aivg/`. First
   run of the rebranded gateway atomically migrates any
   `~/.satellite/state.json` (+ `firmware/`) into `~/.aivg/` and
   leaves the old file with a `.pre-aivg-rebrand.bak` suffix.
4. **Distribution name renamed**: `satellite-core` → `aivg-core`.
   A metapackage at the old name pins to the new one.
5. **Visible text rewritten** across README, docs, all specs (where
   "Hermes Voice" refers to the product), constitution, CLI tagline +
   help text, agent-skill descriptions, REST API `info.title`.
6. **Constitution PATCH amend** (v2.0.0 → v2.0.1): title becomes
   AIVG-first; Sync Impact Report records the rebrand; Principle text
   is byte-equivalent modulo product-name strings.
7. **Lint gate**: a new pytest scans the working tree for the
   obsolete product name and fails on a non-allow-listed hit (FR-012);
   runs as part of the standard `pytest` invocation.

What does **NOT** ship in this feature (per spec Assumptions):

- The **repo directory** `hermes-voice/` itself (separate clone-URL
  concern; tracked but not done here).
- Git history rewrite.
- `--contract-version` bump (still `1.0.0`).
- The Hermes agent-skill's frontmatter `name: satellite-management`
  (it's a capability id, not a product id).

## Technical Context

**Language/Version**: Python 3.11 (unchanged).

**Primary Dependencies**: no new runtime deps. The lint check is plain
stdlib (`pathlib` + `re`). Compat shims use stdlib `warnings`. Console-
script entries are existing `pyproject.toml` mechanics.

**Storage**: data directory rename + first-run migration.
`~/.satellite/state.json` → `~/.aivg/state.json` via existing
`persistence.write_snapshot` after a one-shot import that reads the old
path and writes the new (atomic via tmp+rename; the same code path the
gateway already uses). The old file is renamed in place to
`.pre-aivg-rebrand.bak`, never deleted (SC-005).

**Testing**: pytest (existing). One new file: a working-tree scanner
(`tests/unit/test_no_legacy_branding.py`) that walks the repo (excluding
the documented allow-list) and fails on any obsolete product-name match.
Existing tests are updated to import from `aivg_core` / `aivg_cli`; both
import paths work via the compat shim so the rebrand can be staged
incrementally if needed, but the final state of this feature has tests
on the new names.

**Target Platform**: same as feature 011 (operator host macOS/Linux;
gateway Linux/macOS).

**Project Type**: single Python repo; this feature is a coordinated
rename, not a new module.

**Performance Goals**: rename is a one-shot. First-run state-file
migration on a 10-device snapshot completes in <100 ms.

**Constraints**:

- **Zero substantive contract drift** (the binding rule of this
  feature): every `operationId`, REST schema, status code, route,
  CLI exit code, `error.code` value, and `data.*` field name in
  `contracts/management-api.yaml`, `contracts/cli-contract.md`, and
  `contracts/management-ws.md` MUST be byte-equivalent before/after
  (modulo `info.title`/`info.description`/tag titles).
- **Constitution PATCH discipline**: Principles I–V keep their
  normative content byte-equivalent (modulo product-name strings).
  A change to a rule's semantics during this feature is a separate
  amendment and blocks merge.
- **Hermes-plugin identifiers untouched**: `platforms/hermes/`,
  `skills/hermes-agent/`, the plugin's reuse of `~/.hermes/*`.
- One `DeprecationWarning` per process per shim (not per import); the
  shim caches a sentinel.

**Scale/Scope**:

- Touched files: ~85 (every `.py` that imports the renamed packages
  + every `.md` that mentions the old product name + ~5
  `pyproject.toml`/contract files). Counts come from the Phase 0
  survey in `research.md`.
- Constitution: 1 file, 1 PATCH amendment.
- New files: 4 (`aivg_core/`, `aivg_cli/`, `tests/unit/
  test_no_legacy_branding.py`, `docs/rebrand-allow-list.md`).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against **v2.0.0** (the version on disk at plan-write time);
this feature amends to v2.0.1.

| Principle | Check | Status |
|---|---|---|
| I. Thin Satellite | Rebrand touches no engine; constitution-I tests untouched. | ✅ PASS |
| II. Generic Four-Plane Contract | No protocol branching introduced; the rebrand is text + identifier names only. | ✅ PASS |
| III. Separate Control/Voice Connections | Unchanged. | ✅ PASS |
| IV. Reuse Upstream Agent Platform (v2.0.0) | The whole point: AIVG-as-product, Hermes-as-plugin. The rebrand operationalizes Principle IV by removing the remaining product-name conflation. Hermes-plugin identifiers preserved verbatim. | ✅ PASS |
| V. Research-Backed | The rebrand has no new technology choices; research.md documents the rename mechanics (compat-shim shape, data-dir migration, lint scanner). | ✅ PASS |

No violations → **Complexity Tracking table empty.**

## Project Structure

### Documentation (this feature)

```text
specs/012-aivg-branding/
├── plan.md                  # This file
├── research.md              # Phase 0 — rebrand mechanics
├── data-model.md            # Phase 1 — rename + allow-list tables
├── quickstart.md            # Phase 1 — what a contributor does after pull
├── contracts/
│   └── rebrand-invariants.md  # The contract-zero-drift contract
├── checklists/
│   └── requirements.md       # 16/16 (already created by /speckit-specify)
└── tasks.md                  # /speckit-tasks output (NOT created here)
```

### Source code touchpoints

```text
hermes-voice/                                   # repo dir UNCHANGED (out of scope)
├── README.md                                   # update — product name AIVG
├── CLAUDE.md                                   # already AIVG-aware via 011; minor refresh
├── pyproject.toml                              # rename: project.name + scripts + packages.find
├── .specify/memory/constitution.md             # PATCH v2.0.1
├── docs/
│   ├── satellite-data-dir.md                   # rename → aivg-data-dir.md (with header note)
│   ├── generic-voice-satellite-design.md       # text refresh: "AIVG" replaces "Hermes Voice"
│   └── rebrand-allow-list.md                   # NEW — paths exempt from the lint
├── src/
│   ├── aivg_core/                              # NEW — formerly satellite_core
│   │   ├── (mirrors current satellite_core/ exactly — `git mv`'d)
│   │   ├── platforms/hermes/                   # UNCHANGED (plugin id)
│   │   ├── platforms/openclaw/                 # UNCHANGED (plugin id)
│   │   ├── webrtc/
│   │   ├── management/
│   │   └── persistence.py                      # +migrate_legacy_data_dir()
│   ├── satellite_core/                         # NEW SHIM (was the package)
│   │   └── __init__.py                         # re-exports aivg_core + DeprecationWarning
│   ├── aivg_cli/                               # NEW — formerly sat_cli
│   │   ├── cli.py                              # tagline → "AIVG management CLI"
│   │   ├── (everything else carried over from sat_cli/)
│   │   └── onboard/
│   └── sat_cli/                                # NEW SHIM
│       ├── __init__.py                         # re-export + DeprecationWarning
│       └── cli.py                              # dispatch to aivg_cli.cli.app + stderr notice
├── skills/
│   ├── hermes-agent/                           # UNCHANGED (plugin scope)
│   │   ├── SKILL.md                            # text refresh: "AIVG, running its Hermes plugin"
│   │   └── README.md                           # text refresh
│   └── openclaw/                               # UNCHANGED
│       └── README.md
├── clients/electron-test/README.md             # text refresh
├── deploy/plugin/plugin.yaml                   # text refresh (label only)
├── tests/
│   ├── unit/
│   │   ├── test_no_legacy_branding.py          # NEW — the rebrand lint (FR-012)
│   │   ├── test_compat_shim.py                 # NEW — shims emit one DeprecationWarning
│   │   ├── test_persistence_migration.py       # NEW — ~/.satellite → ~/.aivg first-run
│   │   └── (existing tests with import-path updates)
│   └── (other tiers: import-path updates only)
└── specs/                                       # historical specs — text refresh per FR-002
    ├── 001-..-010/quickstart.md                # AIVG-aware first-mention notes
    ├── 011-satellite-management/                # ↑ ditto; identifier mentions updated
    └── 012-aivg-branding/                       # this feature
```

**Structure Decision**: **dual-package layout with compat shims**.
`src/aivg_core/` and `src/aivg_cli/` are the new homes (created with
`git mv`'d files to preserve history). The old `src/satellite_core/`
and `src/sat_cli/` directories shrink to **shim-only packages**
(`__init__.py` re-exports + `cli.py` dispatcher), each emitting one
`DeprecationWarning` per process. `pyproject.toml` adds both binary
entry points (`aivg = aivg_cli.cli:app` and the kept-for-one-release
`sat-cli = sat_cli.cli:legacy_app`). The constitution amends to
v2.0.1; the `~/.satellite/`→`~/.aivg/` migration is a one-shot
function called on gateway startup that writes the new file before
renaming the old to `.pre-aivg-rebrand.bak`.

The repo directory **stays `hermes-voice/`** (spec Assumption). The
existing `src/hermes_satellite_adapter/` compat shim from feature 011
is **retained** (it forwards to `satellite_core`, which now itself
forwards to `aivg_core` — a two-hop shim) and scheduled for deletion
together with all new shims in the same follow-up phase.

## Complexity Tracking

> No constitution violations → no complexity to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
