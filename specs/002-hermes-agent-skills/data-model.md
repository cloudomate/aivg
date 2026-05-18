# Phase 1 Data Model: Hermes Agent Skill Import

No runtime data. The "model" is two static repo files and their relationship.

## Entity: Vendored Hermes Skill

| Field | Value / Rule |
|-------|--------------|
| Location | `.claude/skills/hermes-agent/SKILL.md` |
| Content | **Byte-identical** to upstream blob (FR-003 / SC-004) |
| Identity | upstream blob SHA `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23` |
| Frontmatter (from upstream) | `name: hermes-agent`, `description: "Configure, extend, or contribute to Hermes Agent."`, `version: 2.1.0`, `license: MIT` |
| Mutability | Never hand-edited; only replaced wholesale by a deliberate re-import (FR-008) |

## Entity: Provenance Note

Sibling file `.claude/skills/hermes-agent/PROVENANCE.md` (separate so it never
alters the verbatim skill).

| Field | Value |
|-------|-------|
| `source_repo` | `github.com/NousResearch/hermes-agent` |
| `source_path` | `skills/autonomous-ai-agents/hermes-agent/SKILL.md` |
| `pinned_commit` | `98db898c0bd4df0b09a5830b6a18a069c771e67c` |
| `upstream_commit_date` | `2026-05-08` |
| `blob_sha` | `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23` |
| `copied_on` | date the import ran |
| `license` | MIT (per upstream frontmatter) |
| `note` | Point-in-time copy; not auto-synced. Re-import via `scripts/import-hermes-skill.sh`. |

## Relationship & invariant

`SKILL.md` ↔ `PROVENANCE.md` are 1:1 and must stay consistent: the
`blob_sha`/`pinned_commit` in `PROVENANCE.md` MUST match the bytes in
`SKILL.md`. The byte-identity test (vendored file vs upstream blob at
`pinned_commit`) is the enforcing check (SC-004).

## State transitions

```
(absent) --import--> vendored@commitA
vendored@commitA --deliberate re-import--> vendored@commitB   (PROVENANCE rewritten)
upstream changes with NO re-import  --> stays vendored@commitA (intended; staleness
                                         is visible via PROVENANCE, not auto-fixed)
upstream unreachable at import time --> import FAILS, no file written (FR-006)
```

## Non-entities

The Hermes build/host, the agent, and STT/TTS are out of scope here — this
feature only places a reference document; acting on it is the assistant's
later, confirmation-gated use (FR-005), not modeled as data.
