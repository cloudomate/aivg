# Provenance — `hermes-agent` skill (vendored copy)

`SKILL.md` in this directory is a **verbatim, point-in-time copy** of an
upstream Hermes Agent skill. It is intentionally byte-identical to upstream and
MUST NOT be hand-edited (see spec FR-003 / SC-004). This provenance file is a
**sibling**, never merged into `SKILL.md`.

| Field | Value |
|-------|-------|
| source_repo | `github.com/NousResearch/hermes-agent` |
| source_path | `skills/autonomous-ai-agents/hermes-agent/SKILL.md` |
| pinned_commit | `98db898c0bd4df0b09a5830b6a18a069c771e67c` |
| upstream_commit_date | `2026-05-08` |
| blob_sha | `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23` |
| copied_on | `2026-05-18` |
| upstream_skill | `hermes-agent` v2.1.0 — "Configure, extend, or contribute to Hermes Agent." |
| license | MIT (per upstream frontmatter) |

**Point-in-time, not auto-synced.** Upstream may move on; this copy does not.
Staleness is intentionally visible by comparing this file to upstream. To
deliberately re-import a newer revision:

```bash
scripts/import-hermes-skill.sh <commit-sha>      # or no arg → re-pin current
```

Verify this copy still matches what is recorded here:

```bash
git hash-object .claude/skills/hermes-agent/SKILL.md
# must equal blob_sha above: 3a610642f85cbd20da8f2c5fe4932c5e7f3edd23
```

Using this skill against a live Hermes host: any step that mutates or reaches
the host requires explicit confirmation (spec FR-005); read-only inspection is
free. The skill is reference guidance and never runs itself (FR-007). Importing
it changes nothing on any host and nothing in the satellite runtime (FR-009).
