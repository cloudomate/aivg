# Contract: Skill Placement & Provenance

The only "interface" this feature exposes: where the vendored skill lives, what
guarantees hold, and how a deliberate re-import behaves.

## Placement contract

```
.claude/skills/hermes-agent/
├── SKILL.md        # verbatim upstream copy
└── PROVENANCE.md   # provenance sidecar (NOT part of the skill content)
```

- `SKILL.md` MUST be byte-identical to the upstream blob at the pinned commit
  (FR-001/FR-003 / SC-004). No header, no reformat, no frontmatter edit.
- `PROVENANCE.md` MUST exist alongside it with: `source_repo`, `source_path`,
  `pinned_commit`, `upstream_commit_date`, `blob_sha`, `copied_on`, `license`
  (FR-004 / SC-007).
- Claude Code MUST be able to discover the skill from this path (the upstream
  frontmatter already supplies `name` + `description`) (FR-002).

## Import behaviour contract (`scripts/import-hermes-skill.sh [commit]`)

| Condition | Required behaviour |
|-----------|--------------------|
| Upstream reachable | Fetch the file at the given (default: pinned) commit read-only; overwrite `SKILL.md`; rewrite `PROVENANCE.md`; print `BYTE-IDENTICAL: yes/no` vs the upstream blob SHA |
| Upstream unreachable | Exit non-zero, write nothing, print a clear failure — NO guessed/fabricated content (FR-006 / SC-006) |
| Re-run later | Only when invoked by hand; never scheduled/hooked/auto-run (FR-008 / FR-007) |
| Host side | The import itself performs ZERO host mutation; it only reads GitHub and writes two repo files |

## Use-time contract (when the assistant later acts on the skill)

- Any step the skill prescribes that mutates or reaches the Hermes host MUST be
  surfaced for explicit confirmation before execution; read-only/inspection
  steps may proceed (FR-005 / SC-003).
- The skill is reference guidance only; it does not execute itself (FR-007).
- Acting on the skill MUST NOT modify the satellite/adapter runtime (FR-009).

## Conformance checks (→ tasks/tests)

- `T:` `SKILL.md` SHA equals upstream blob `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23`
  at commit `98db898c0bd4df0b09a5830b6a18a069c771e67c` (byte-identity, SC-004).
- `T:` `PROVENANCE.md` contains all required fields and they match the file.
- `T:` Claude Code lists/discovers the `hermes-agent` skill after import (FR-002).
- `T:` Import helper exits non-zero and writes nothing when the fetch fails
  (FR-006) — simulated with an unreachable ref.
- `T:` No file outside `.claude/skills/hermes-agent/` + `scripts/` is changed
  by the import (FR-009 non-interference).
