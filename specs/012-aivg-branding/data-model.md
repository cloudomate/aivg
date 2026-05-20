# Data Model: AIVG Rebrand

**Feature**: `012-aivg-branding` · **Plan**: [plan.md](./plan.md) ·
**Date**: 2026-05-20

This is a **rename feature**; the "data model" here is the **mapping
table** of what changes and what stays. No new runtime entities.

## 1. Rename map

### Python packages

| Old (feature 011) | New (feature 012) | Compat shim window |
|---|---|---|
| `hermes_satellite_adapter` | (already a shim → `satellite_core`) | carried over; now two-hop |
| `satellite_core` | `aivg_core` | one release |
| `sat_cli` | `aivg_cli` | one release |

### CLI

| Old | New |
|---|---|
| `sat-cli` (binary) | `aivg` |
| `sat-cli --help` tagline | `aivg --help` tagline ("AIVG management CLI") |

### Distribution & build

| Old | New |
|---|---|
| `[project].name = "satellite-core"` | `"aivg-core"` |
| `[project.scripts] sat-cli` | `aivg` (primary) + `sat-cli` (legacy alias) |
| `[project].description` | "AIVG — AI Voice Gateway: …" |

### Data directory

| Old | New |
|---|---|
| `~/.satellite/config.yaml` | `~/.aivg/config.yaml` |
| `~/.satellite/state.json` | `~/.aivg/state.json` |
| `~/.satellite/firmware/<type>/manifest.json` | `~/.aivg/firmware/<type>/manifest.json` |
| (legacy file post-migration) | `~/.satellite/state.json.pre-aivg-rebrand.bak` |

### REST / docs contracts

| Field | Old | New |
|---|---|---|
| `management-api.yaml` `info.title` | "Hermes Satellite Management API" | "AIVG Satellite Management API" |
| `management-api.yaml` `info.description` | mentions Hermes Voice | rewritten to AIVG |
| `cli-contract.md` H1 | "`sat-cli` — …" | "`aivg` — Satellite Management CLI" |
| `management-ws.md` H1 | mentions Hermes voice | rewritten to AIVG |
| All `operationId` values | — | UNCHANGED |
| All schema names / fields | — | UNCHANGED |
| All `error.code` values | — | UNCHANGED |
| Exit codes | — | UNCHANGED |
| `--contract-version` output | `1.0.0` | `1.0.0` UNCHANGED |

### Constitution

| Field | Old | New |
|---|---|---|
| Title | "Hermes Voice Satellite Constitution" | "AIVG Constitution" |
| Project codename preface | "Project codename: 'Hermes Voice' (historical)…" | "Project codename: AIVG (AI Voice Gateway). Formerly 'Hermes Voice' through feature 011." |
| Sync Impact Report | — | new bullet: v2.0.0 → v2.0.1, PATCH, "Branding rebrand only" |
| Footer | "Version: 2.0.0" | "Version: 2.0.1" |
| Principle I–V body | — | UNCHANGED (modulo product-name strings) |
| Hardware & Platform Constraints | — | UNCHANGED |
| Development Workflow & Quality Gates | — | UNCHANGED |
| Governance | "Hermes Voice satellite system" | "AIVG satellite system" |

## 2. Frozen identifiers (Hermes-plugin scope)

Constitution v2.0.0 Principle IV: `Hermes` is the v1 agent-platform
plugin. The following names identify the plugin, not the product —
the rebrand **does not touch them**.

| Identifier | What it is |
|---|---|
| `aivg_core/platforms/hermes/` | the Hermes-plugin folder (under the renamed package) |
| `aivg_core/platforms/hermes/bridge.py` | the plugin's bridge to the Hermes runtime |
| `aivg_core/platforms/hermes/__init__.py` `PLATFORM.name = "hermes"` | the plugin's stable id |
| `skills/hermes-agent/` | the Hermes-platform agent skill |
| `skills/hermes-agent/SKILL.md` `name: satellite-management` | capability id (NOT product id) |
| `~/.hermes/config.yaml` | Hermes-runtime config, read by the Hermes plugin |
| `~/.hermes/.env` | Hermes-runtime secrets |
| `~/.hermes/logs/gateway.log` | Hermes-runtime log destination |
| `~/.hermes/skills/` | Hermes-runtime skill install path |

## 3. Compat-shim semantics

| Shim | What it does | When it goes away |
|---|---|---|
| `src/satellite_core/__init__.py` | re-exports `aivg_core.*`, emits one `DeprecationWarning` per process | Next release after this one |
| `src/sat_cli/__init__.py` + `cli.py::legacy_app` | dispatches `sat-cli` → `aivg`, stderr deprecation notice | Next release |
| `src/hermes_satellite_adapter/__init__.py` | (already two-hop now via `satellite_core` → `aivg_core`) | Next release (carried over from feature 011) |
| `[project.scripts] sat-cli` | console-script entry → `sat_cli.cli:legacy_app` | Next release |
| `satellite-core` distribution metapackage | depends-on `aivg-core` | Next release |

## 4. The rebrand allow-list (R-4)

Documented in `docs/rebrand-allow-list.md`; the lint reads it. Seed
contents:

```text
# Rebrand allow-list — paths where "Hermes Voice" may persist.
# One gitignore-style pattern per line; whole-line `#` is a comment.

# The rebrand spec itself (it documents what's being renamed).
specs/012-aivg-branding/**

# The lint scanner + its companion test.
tests/unit/test_no_legacy_branding.py
tests/unit/test_compat_shim.py

# The compat shims (they reference both names by design).
src/satellite_core/__init__.py
src/sat_cli/__init__.py
src/sat_cli/cli.py
src/hermes_satellite_adapter/__init__.py

# The dedicated rebrand doc.
docs/rebrand-allow-list.md
```

Historical specs (001–011) are NOT in the allow-list — they get the
product-name sweep (R-6). Their identifier mentions (e.g.
`hermes_satellite_adapter`) are not product names so the lint
doesn't catch them; they stay as-is for archaeology.

## 5. Validation summary (cross-cutting)

| Rule | Where enforced | Test |
|---|---|---|
| One DeprecationWarning per process per shim | `satellite_core.__init__`, `sat_cli.__init__` | `tests/unit/test_compat_shim.py` |
| `sat-cli` legacy emits on stderr never stdout | `sat_cli.cli:legacy_app` | `tests/unit/test_compat_shim.py` |
| Existing `~/.satellite/state.json` migrates atomically + `.pre-aivg-rebrand.bak` left | `aivg_core.persistence.migrate_legacy_data_dir` | `tests/unit/test_persistence_migration.py` |
| Zero `operationId` / schema / exit-code drift | `contracts/management-api.yaml`, `cli-contract.md` | byte-diff CI step in tasks; companion in `contracts/rebrand-invariants.md` |
| Constitution Principles I–V byte-equivalent modulo product name | `.specify/memory/constitution.md` | byte-diff CI step in tasks |
| Working tree contains no obsolete product-name strings outside allow-list | repo-wide scan | `tests/unit/test_no_legacy_branding.py` (FR-012) |
| Hermes-plugin identifiers untouched | every file under `aivg_core/platforms/hermes/`, `skills/hermes-agent/` | byte-diff vs feature-011 HEAD; companion table in this doc |
