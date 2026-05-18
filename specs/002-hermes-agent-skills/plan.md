# Implementation Plan: Hermes Agent Skill Import for the Adapter Workbench

**Branch**: `002-hermes-agent-skills` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/002-hermes-agent-skills/spec.md`

## Summary

Vendor a single file — the upstream `SKILL.md` from
`NousResearch/hermes-agent` at `skills/autonomous-ai-agents/hermes-agent/` —
verbatim into this repo's `.claude/skills/hermes-agent/` so the assistant
working here can use Hermes's own documented configuration/self-improvement
procedure while building and validating feature `001`. A sibling provenance
file records the source repo/path/commit so the point-in-time copy is
auditable. No discovery, catalog, scoping, sync, or drift system (removed in
clarification). Build-time tooling only — does not touch the satellite runtime.

Upstream verified read-only via `gh api`:

- Path: `skills/autonomous-ai-agents/hermes-agent/SKILL.md` (exists, 45,630 B)
- Skill: `name: hermes-agent`, v2.1.0, MIT, desc "Configure, extend, or
  contribute to Hermes Agent."
- Pinned commit: `98db898c0bd4df0b09a5830b6a18a069c771e67c` (2026-05-08)
- Blob SHA: `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23`

## Technical Context

**Language/Version**: N/A — no code. Markdown asset vendoring + a small,
optional re-import shell helper.
**Primary Dependencies**: `gh` CLI (or `curl`) for a read-only fetch of the
upstream file at a pinned commit; `git` for committing the vendored copy.
**Storage**: Two static files in the repo: the verbatim skill and a provenance
sidecar. No runtime storage.
**Testing**: A byte-identity check (vendored file vs upstream blob at the
pinned commit) and a frontmatter-loadability check (Claude Code skill
discovery sees `name`/`description`).
**Target Platform**: This repository / the developer's Claude Code session.
**Project Type**: Single repo; documentation/skill asset (no application code).
**Performance Goals**: N/A (one-time copy; SC-005 is a workflow-efficiency
outcome, not a runtime metric).
**Constraints**: FR-003 verbatim copy (no edits, incl. upstream frontmatter &
license line); FR-005 host-mutating steps need explicit confirmation when the
skill is later *used*; FR-006 fail loudly if upstream unreachable; FR-008 no
auto-sync; FR-009 no satellite-runtime impact.
**Scale/Scope**: Exactly one file imported; one provenance sidecar; one
optional re-import helper. Nothing else.

**Resolved (no NEEDS CLARIFICATION):** sourcing model, destination, file scope,
and safety posture were all fixed in the spec's Clarifications session
(2026-05-18). Upstream existence/commit verified in Phase 0.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The constitution governs the **voice satellite runtime**. This feature is
build-time tooling; it is checked for non-interference and posture, not as a
runtime component.

| # | Principle | Relevance | Status |
|---|-----------|-----------|--------|
| I | Thin Satellite, Gateway-Owned Intelligence | Feature ships nothing into the satellite/adapter runtime (FR-009) | ✅ PASS (no impact) |
| II | Generic Four-Plane Contract | Not a device/contract change | ✅ N/A |
| III | Separate Control and Voice Connections | No connection/transport change | ✅ N/A |
| IV | Reuse Hermes, Don't Rebuild | This feature *is* "reuse Hermes": it imports Hermes's own skill rather than authoring a bespoke one | ✅ PASS (reinforces) |
| V | Research-Backed, Verify Before Relying | Upstream verified at a pinned commit before vendoring; host-mutating use gated by confirmation (FR-005); fail-loud if source unreachable (FR-006) | ✅ PASS (reinforces) |

**Result: PASS, no violations.** Complexity Tracking not required.

## Project Structure

### Documentation (this feature)

```text
specs/002-hermes-agent-skills/
├── plan.md  research.md  data-model.md  quickstart.md
├── contracts/skill-placement.md   # destination layout + provenance + verbatim contract
└── tasks.md                       # /speckit-tasks output (not created here)
```

### Repository assets (created by this feature)

```text
.claude/skills/hermes-agent/
├── SKILL.md           # VERBATIM upstream copy (FR-001/003) — byte-identical
└── PROVENANCE.md      # source repo + path + pinned commit + blob SHA + copy date (FR-004)

scripts/
└── import-hermes-skill.sh   # optional, deliberate re-import helper (FR-008):
                              #   read-only fetch at an explicit commit →
                              #   overwrite SKILL.md → rewrite PROVENANCE.md →
                              #   print byte-identity result. Never auto-runs.
```

**Structure Decision**: Place the skill at `.claude/skills/hermes-agent/SKILL.md`
so Claude Code auto-discovers it (clarification Q2). The provenance is a
**sibling file**, never edited into `SKILL.md`, to keep the copy byte-identical
to upstream (FR-003 / SC-004). The re-import helper exists only to make FR-008's
"deliberate, explicit re-import" easy and auditable; it performs no host
mutation and is not wired to run automatically.

## Complexity Tracking

> Not applicable — Constitution Check passed with no violations.
