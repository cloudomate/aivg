---
description: "Task list for Hermes Agent Skill Import"
---

# Tasks: Hermes Agent Skill Import for the Adapter Workbench

**Input**: Design documents from `/specs/002-hermes-agent-skills/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Conformance test tasks ARE included — the placement contract
explicitly enumerates them (byte-identity, provenance, discovery, fail-loud,
non-interference). They are shell/asset checks, not a code test suite.

**Organization**: By user story (US1 P1 · US2 P2 · US3 P2). This is a
single-file vendoring feature, so Foundational delivers the shared artifact and
each story phase adds its story-specific verification.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: parallelizable (different files, no incomplete deps)
- Paths: skill → `.claude/skills/hermes-agent/`, helper → `scripts/`

---

## Phase 1: Setup

- [X] T001 Create directories `.claude/skills/hermes-agent/` and `scripts/` in the repo root
- [X] T002 [P] Confirm `gh` CLI is available and can read the public repo unauthenticated: `gh api repos/NousResearch/hermes-agent --jq .full_name`

**Checkpoint**: Destination dirs exist; fetch mechanism works

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Produce the shared artifact every user story depends on. No story
work can begin until the skill is imported and verified.

**⚠️ CRITICAL**: Blocks US1/US2/US3

- [X] T003 Fetch upstream `SKILL.md` verbatim at the pinned commit and write it to `.claude/skills/hermes-agent/SKILL.md`: `gh api 'repos/NousResearch/hermes-agent/contents/skills/autonomous-ai-agents/hermes-agent/SKILL.md?ref=98db898c0bd4df0b09a5830b6a18a069c771e67c' --jq .content | base64 -d > .claude/skills/hermes-agent/SKILL.md` (FR-001/FR-003)
- [X] T004 Byte-identity test: assert `git hash-object .claude/skills/hermes-agent/SKILL.md` == `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23` (upstream blob at the pinned commit); fail the import if not (FR-003 / SC-004)
- [X] T005 [P] Write `.claude/skills/hermes-agent/PROVENANCE.md` with source_repo, source_path, pinned_commit `98db898c0bd4df0b09a5830b6a18a069c771e67c`, upstream_commit_date `2026-05-08`, blob_sha `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23`, copied_on (today), license MIT, and the "point-in-time, not auto-synced" note (FR-004 / data-model.md)
- [X] T006 Implement `scripts/import-hermes-skill.sh [commit]` per contracts/skill-placement.md: read-only fetch at the given/pinned commit → overwrite SKILL.md → rewrite PROVENANCE.md → print `BYTE-IDENTICAL: yes/no`; exit non-zero and write nothing if the fetch fails; never auto-run (FR-006/FR-008)
- [X] T007 [P] Make `scripts/import-hermes-skill.sh` executable (`chmod +x`)

**Checkpoint**: Verbatim skill + provenance vendored; deliberate re-import helper ready

---

## Phase 3: User Story 1 - Configure the Hermes gateway via the imported skill (Priority: P1) 🎯 MVP

**Goal**: The assistant can drive an adapter gateway-config task by following
the imported skill instead of improvised commands.

**Independent Test**: In a Claude Code session in this repo, ask the assistant
to use the `hermes-agent` skill for one concrete config inspection/change for
feature 001; it follows the skill's procedure and cites it.

- [X] T008 [US1] Verify Claude Code discovers the `hermes-agent` skill from `.claude/skills/hermes-agent/SKILL.md` (appears in the available-skills list via its upstream `name`/`description` frontmatter) (FR-002). If discovery requires editing the file → STOP and escalate the FR-003 vs discovery conflict; do not patch SKILL.md
- [X] T009 [US1] Dry-run validation: ask the assistant to perform one read-only adapter gateway-config inspection *through the skill*; confirm zero improvised host commands and that any host-mutating step would pause for explicit confirmation (FR-005 / SC-001 / SC-003)

**Checkpoint**: MVP — skill is discoverable and usable for adapter configuration

---

## Phase 4: User Story 2 - Validate the adapter via the imported skill (Priority: P2)

**Goal**: The assistant can run an adapter validation by following the skill's
self-check guidance and report pass/fail.

**Independent Test**: Ask the assistant to validate adapter STT/TTS/config
against the real Hermes using the skill's check procedure; it reports pass/fail.

- [X] T010 [US2] Confirm the imported `SKILL.md` contains usable
  validation/health/troubleshooting guidance for the gateway/voice path
  (inspection only); record which sections feature 001 T045 can rely on
- [X] T011 [US2] Dry-run: ask the assistant to perform one read-only adapter
  validation step via the skill; confirm pass/fail reporting and the
  confirmation guardrail on any host-reaching action (SC-002 / SC-003)

**Checkpoint**: US1 + US2 usable from the imported skill

---

## Phase 5: User Story 3 - Review the imported skill before relying on it (Priority: P2)

**Goal**: A developer can audit exactly what was vendored and its origin.

**Independent Test**: Open the two files; confirm `SKILL.md` is verbatim
upstream and `PROVENANCE.md` states repo/path/commit/blob/date in <1 min.

- [X] T012 [US3] Verify `PROVENANCE.md` is complete and self-consistent: its `blob_sha`/`pinned_commit` match the actual `SKILL.md` bytes (re-run the T004 hash check against the recorded SHA) (SC-004 / SC-007)
- [X] T013 [P] [US3] Add a one-line pointer in the project README / `.claude/skills/hermes-agent/PROVENANCE.md` so a reviewer finds the source and "point-in-time, re-import via scripts/import-hermes-skill.sh" note quickly (SC-007)

**Checkpoint**: All three stories independently verifiable

---

## Phase 6: Polish & Cross-Cutting

- [X] T014 [P] Fail-loud test: run the import helper against an unreachable/bogus ref; assert non-zero exit, no file written/overwritten, clear message, no fabricated content (FR-006 / SC-006)
- [X] T015 [P] Non-interference check: confirm the import changes nothing outside `.claude/skills/hermes-agent/` and `scripts/` — `git status` touches only those paths; `src/` and feature 001 tests unaffected (FR-009)
- [X] T016 Run `quickstart.md` end-to-end and confirm every listed check passes

---

## Dependencies & Execution Order

- **Setup (P1)** → **Foundational (P2)** produces the artifact and BLOCKS all stories
- **US1/US2/US3** depend only on Foundational; independently verifiable after it
- **Polish (P6)** after the stories
- Within Foundational: T003 → T004 (verify) before T006 (helper wraps the same logic); T005/T007 [P]

## Parallel Opportunities

- T002 ∥ T001-followup; T005 ∥ T007; T013 ∥ T012; T014 ∥ T015
- US1/US2/US3 verification phases can run together once Foundational is done

## Implementation Strategy

**MVP = Phase 1 + Phase 2 + Phase 3 (US1)**: skill vendored verbatim, provenance
recorded, discoverable, and usable for adapter configuration with the
confirmation guardrail. US2/US3 add validation-use and auditability; Polish adds
fail-loud + non-interference assurances. Entire feature is reversible
(`git revert` / delete two files).

## Notes

- FR-003/SC-004 is the hard invariant: `SKILL.md` byte-identical to upstream;
  provenance is a SIBLING file, never inlined.
- Constitution: build-time tooling only (FR-009); reinforces IV (reuse Hermes)
  and V (verified upstream at a pinned commit before vendoring).
- No code/test suite; tasks are asset + shell-check tasks. Commit after
  Foundational and after each story.
