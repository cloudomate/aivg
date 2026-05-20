# Contract: AIVG Rebrand Invariants

**Feature**: `012-aivg-branding` · **Plan**: [../plan.md](../plan.md) ·
**Version**: 1.0.0

The AIVG rebrand is a **labels-only** change at every external surface.
This document is the contract that names exactly what MUST NOT change so
that existing scripts, agents, and integrations keep working.

## 1. REST API (`contracts/management-api.yaml`)

| Field | Before | After |
|---|---|---|
| `openapi` | `3.1.0` | `3.1.0` |
| `info.version` | `1.0.0` | `1.0.0` |
| `info.title` | "Hermes Satellite Management API" | "**AIVG** Satellite Management API" |
| `info.description` | mentions Hermes Voice | rewritten to AIVG (prose only) |
| `tags[*]` | `[registry, adoption, …]` | UNCHANGED |
| Every `paths.*` route | UNCHANGED | UNCHANGED |
| Every `operationId` | UNCHANGED | UNCHANGED |
| Every request/response schema name | UNCHANGED | UNCHANGED |
| Every schema field name | UNCHANGED | UNCHANGED |
| Every `enum` value (incl. `error` enum) | UNCHANGED | UNCHANGED |
| Every HTTP status code per operation | UNCHANGED | UNCHANGED |

**Verification**: a scripted diff that strips `info.title`/
`info.description` from both copies MUST produce zero substantive
differences. Wired as a CI step in `tasks.md`.

## 2. CLI contract (`contracts/cli-contract.md`)

| Field | Before | After |
|---|---|---|
| Document H1 | "`sat-cli` — Satellite Management CLI" | "`aivg` — Satellite Management CLI" |
| Body prose mentioning `sat-cli` as the binary | "`sat-cli`" | "`aivg`" |
| Body prose mentioning `sat-cli` as a legacy compat alias | (n/a) | "`sat-cli` (legacy alias for `aivg`; one-release window)" |
| `--contract-version` output | `1.0.0` | `1.0.0` |
| JSON envelope shape | `{ok, data, error, v=1}` | UNCHANGED |
| Closed `error.code` set | listed in cli-contract.md | UNCHANGED |
| Exit-code table (0/1/2/3/4/5/64+) | listed | UNCHANGED |
| Every command name | `list`, `device get`, `logs`, `fleet logs`, `watch`, `onboard` | UNCHANGED |
| Every documented flag | UNCHANGED | UNCHANGED |
| `data.*` field names inside any envelope | UNCHANGED | UNCHANGED |

**Verification**: a scripted diff stripping the H1 + body
`sat-cli`→`aivg` substitution MUST produce zero substantive
differences.

## 3. Device WS contract (`contracts/management-ws.md`)

| Field | Before | After |
|---|---|---|
| Document H1 / preamble | mentions Hermes voice | rewritten to AIVG (prose only) |
| Every frame `type` | UNCHANGED | UNCHANGED |
| Every required field per frame | UNCHANGED | UNCHANGED |
| Version | `1.0.0` | `1.0.0` |

## 4. AgentPlatform contract (`contracts/agent-platform.md`)

| Field | Before | After |
|---|---|---|
| Document preamble | mentions `satellite_core` package | rewritten to `aivg_core` |
| Plugin folder path mentioned | `satellite_core/platforms/<name>/` | `aivg_core/platforms/<name>/` |
| `Protocol` method names + signatures | UNCHANGED | UNCHANGED |
| `PLATFORM` exposure rule | UNCHANGED | UNCHANGED |
| Hermes-plugin's `PLATFORM.name = "hermes"` | UNCHANGED | UNCHANGED |
| OpenClaw plugin stub's `PLATFORM.name = "openclaw"` | UNCHANGED | UNCHANGED |

## 5. Constitution

| Field | Before (v2.0.0) | After (v2.0.1) |
|---|---|---|
| Title | "Hermes Voice Satellite Constitution" | "AIVG Constitution" |
| Project-codename preface | "Project codename: 'Hermes Voice' (historical)…" | "Project codename: AIVG (AI Voice Gateway). Formerly 'Hermes Voice' through feature 011." |
| Principles I–V body | — | **UNCHANGED** modulo product-name strings (FR-010 / SC-006) |
| Hardware & Platform Constraints | — | UNCHANGED |
| Development Workflow & Quality Gates | — | UNCHANGED |
| Governance section | "Hermes Voice satellite system" | "AIVG satellite system" |
| Footer Version | `2.0.0` | `2.0.1` |
| Sync Impact Report | — | gains one entry: v2.0.0→v2.0.1 PATCH "Branding rebrand only" |

**Verification**: scripted diff per Principle that normalizes "Hermes
Voice" ↔ "AIVG" replacements before comparing MUST produce zero
substantive differences. Wired in tasks.

## 6. Hermes-plugin identifiers (frozen)

Per FR-014 + data-model.md §2, these names are **byte-equivalent**
before/after the rebrand:

| Path / identifier |
|---|
| `aivg_core/platforms/hermes/` (every file) |
| `skills/hermes-agent/` (every file's *non-prose* contents) |
| `~/.hermes/config.yaml` |
| `~/.hermes/.env` |
| `~/.hermes/logs/gateway.log` |
| `~/.hermes/skills/` |
| `PLATFORM.name = "hermes"` |
| `name: satellite-management` (in `skills/hermes-agent/SKILL.md` frontmatter) |

The skill's body prose may mention "AIVG" instead of "Hermes Voice"
where it described the product; that's a prose change, not an
identifier change. The frontmatter `name:` is the identifier — it
stays.

## 7. Operator-side guarantees (combined view)

For any existing script or agent integration:

| Integration | Still works for one release? |
|---|---|
| `from satellite_core import X` | YES (DeprecationWarning) |
| `from sat_cli.cli import app` | YES (DeprecationWarning) |
| Subprocess `sat-cli ... --json` | YES (stderr-only deprecation notice; stdout JSON unchanged) |
| HTTP `POST /satellite/{id}/adopt` request/response | YES — byte-identical contract |
| Hermes agent skill invoking `sat-cli`-paths | YES — skill examples updated to `aivg`, but old `sat-cli` calls still work |
| Existing `~/.satellite/state.json` on disk | YES — migrated on first start |
| `pip install satellite-core` | YES (metapackage → `aivg-core`) |

A consumer that does **NONE** of: read deprecation warnings, parse a
binary name, watch the data-dir path — sees **no functional change**.
That is the binding invariant of this feature.

## 8. Versioning

This contract document follows the same v1.0.0 semver as
`management-api.yaml` / `cli-contract.md` / `agent-platform.md`. The
rebrand does NOT bump those contracts (label-only change). A future
contract change that crosses surfaces requires a coordinated bump
across all four.
