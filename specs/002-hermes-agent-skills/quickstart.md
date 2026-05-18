# Quickstart: Import & Use the Hermes Agent Skill

## Import (one deliberate command)

```bash
scripts/import-hermes-skill.sh 98db898c0bd4df0b09a5830b6a18a069c771e67c
```

This fetches the upstream `SKILL.md` at the pinned commit (read-only), writes
`.claude/skills/hermes-agent/SKILL.md` verbatim, (re)writes
`.claude/skills/hermes-agent/PROVENANCE.md`, and prints the byte-identity
result. With no arg it uses the pinned commit recorded in `PROVENANCE.md`.

Manual equivalent:

```bash
mkdir -p .claude/skills/hermes-agent
gh api 'repos/NousResearch/hermes-agent/contents/skills/autonomous-ai-agents/hermes-agent/SKILL.md?ref=98db898c0bd4df0b09a5830b6a18a069c771e67c' \
  --jq '.content' | base64 -d > .claude/skills/hermes-agent/SKILL.md
```

## Verify (SC-004 / FR-003)

```bash
# Local content SHA must equal the upstream git blob SHA at the pinned commit.
EXPECT=3a610642f85cbd20da8f2c5fe4932c5e7f3edd23
GOT=$(git hash-object .claude/skills/hermes-agent/SKILL.md)
[ "$GOT" = "$EXPECT" ] && echo "BYTE-IDENTICAL: yes" || echo "MISMATCH ($GOT)"
```

(`git hash-object` reproduces GitHub's blob SHA, so this is an exact upstream
match check.)

## Confirm discovery (FR-002)

In a Claude Code session in this repo, the `hermes-agent` skill should appear
in the available skills list (its upstream frontmatter already provides
`name`/`description`). If it does not appear, that is a discovery conflict to
escalate — do NOT edit `SKILL.md` to force it (FR-003).

## Use it (with the safety guardrail — FR-005)

Ask the assistant to do an adapter task via the skill, e.g. "use the
hermes-agent skill to enable the satellite platform / inspect voice & STT/TTS
config." The assistant follows the skill's documented procedure. Before any
step that **mutates or reaches the Hermes host**, it pauses for explicit
confirmation; read-only inspection proceeds freely. The skill never runs
itself (FR-007).

## Failure behaviour (FR-006 / SC-006)

If GitHub is unreachable, the import exits non-zero, writes nothing, and says
so. It never substitutes guessed skill content.

## Re-import later (FR-008)

Re-running the helper with a newer commit is the *only* way the vendored copy
changes — it is deliberate and rewrites provenance. Nothing auto-syncs; a stale
copy is visible by comparing `PROVENANCE.md` against upstream.
