# Feature Specification: Hermes Agent Skill Import for the Adapter Workbench

**Feature Branch**: `002-hermes-agent-skills`
**Created**: 2026-05-18
**Status**: Draft
**Input**: User description: "since we are building on hermes i want current claude to have hermes agent skills -- this is native skills used by hermes to configure or self improve by doing this we will be able to effectively design and test hermes gateway adapter we are building for our project"

## Overview

While building the realtime voice platform adapter (feature `001`), the
development assistant repeatedly needs to do the things Hermes already knows how
to do to itself: configure the gateway, inspect platform adapters, check
voice/STT/TTS settings, and validate a running build. Hermes publishes a native
agent skill for this kind of self-configuration / self-improvement.

This feature **vendors a copy of that published Hermes skill into this project**
so the assistant working here can use it directly. It is a plain import — not a
discovery/catalog/sync system. Source:
`https://github.com/NousResearch/hermes-agent/tree/main/skills/autonomous-ai-agents/hermes-agent`
(the `SKILL.md` at that path).

This is **build-time developer tooling that supports building feature 001**. It
is not part of the shipped satellite runtime and does not change the
satellite/adapter behaviour or the project constitution's thin-satellite
guarantees.

## Clarifications

### Session 2026-05-18

- Q: Scope & sourcing model — manage skills off the running host, or just copy? → A: Vendor (copy) the skill files as static project assets; drop the discover/catalog/active-scope/refresh/drift requirements entirely.
- Q: Destination so "current Claude" has the skill? → A: Into `.claude/skills/` in this repo (Claude Code auto-discovers; immediately invocable).
- Q: Exactly which files to copy? → A: Only `SKILL.md` from the given path, nothing else.
- Q: Safety posture when the skill is used? → A: Keep — any host-mutating/outward action the skill drives still requires explicit confirmation; read-only is free.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Configure the Hermes gateway for the adapter using the imported skill (Priority: P1)

The assistant, while implementing/validating the adapter, follows the imported
Hermes skill's documented procedure to perform a gateway configuration task
(for example: enable the satellite platform, set or inspect the `satellite:` /
voice / STT / TTS configuration) instead of improvising host commands.

**Why this priority**: This is the core value — it is the difference between
"guess at the Hermes API" (which already produced three reconstruction bugs in
feature 001) and "follow Hermes's own documented procedure." Without it the
feature delivers nothing.

**Independent Test**: Ask the assistant to perform one concrete gateway
configuration change for the adapter; confirm it follows the imported skill's
procedure (and cites it) rather than freehand commands.

**Acceptance Scenarios**:

1. **Given** the skill has been imported into `.claude/skills/`, **When** the
   assistant needs a gateway configuration change for the adapter, **Then** it
   uses the imported skill and the change is applied via that skill's procedure.
2. **Given** the skill's procedure would perform a mutating/outward action on
   the Hermes host, **When** it is invoked, **Then** the action is presented for
   explicit confirmation before it takes effect.
3. **Given** the skill is used, **Then** its recorded source (repository, path,
   and the commit/date it was copied) is identifiable.

---

### User Story 2 - Validate the adapter against the real Hermes using the imported skill (Priority: P2)

The assistant follows the imported skill's self-check / validation guidance to
exercise and validate the adapter end-to-end against the real build — e.g.
verifying STT/TTS provider configuration and confirming a voice path works —
helping close feature 001's outstanding live-validation gap.

**Why this priority**: Turns the adapter from "verified by reconstruction" into
"validated via Hermes's own documented procedure." High value, but depends on
US1 being able to configure first, so P2.

**Independent Test**: Ask the assistant to run an adapter validation; confirm it
uses the imported skill's check procedure and reports a clear pass/fail.

**Acceptance Scenarios**:

1. **Given** the adapter is configured, **When** the assistant validates it,
   **Then** it follows the imported skill's validation guidance and reports a
   clear pass/fail.
2. **Given** the procedure surfaces a misconfiguration, **Then** the assistant
   reports that specific finding.

---

### User Story 3 - Review the imported skill before relying on it (Priority: P2)

A developer can open the imported skill in this repo and see what it does and
where it came from (source repository, path, and the commit/date copied) before
the assistant is allowed to act on its host-changing steps.

**Why this priority**: The skill can drive changes to a real Hermes host. The
developer must be able to read exactly what was vendored and its origin before
relying on it; the core loop can still run with the confirmation guardrail, so
P2.

**Independent Test**: Open the imported skill file in the repo; confirm its
content is the verbatim upstream `SKILL.md` and that a recorded provenance note
states the source repo/path/commit-or-date.

**Acceptance Scenarios**:

1. **Given** the skill was imported, **When** the developer inspects it,
   **Then** the file is the unmodified upstream `SKILL.md` and a provenance note
   states repository, path, and copied commit/date.
2. **Given** the developer has not authorized a host change the skill would
   make, **When** that step is reached, **Then** it is withheld and surfaced,
   not performed.

### Edge Cases

- The upstream source is unreachable at import time → the import is reported as
  failed; no fabricated or guessed skill content is substituted.
- The skill's procedure requires a host change the developer has not authorized
  → the action is withheld and surfaced, not performed.
- The imported skill references Hermes behaviour that differs from the running
  build → the discrepancy is surfaced when it arises (no automatic drift system
  is in scope; the imported copy is point-in-time and explicitly so).
- The upstream `SKILL.md` is updated later → out of scope to auto-track; a fresh
  import is a deliberate, separate action (provenance makes staleness visible).
- The skill describes multiple procedures, some irrelevant to the adapter →
  the assistant uses only the procedure relevant to the task at hand.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST copy `SKILL.md` verbatim from
  `github.com/NousResearch/hermes-agent` at
  `skills/autonomous-ai-agents/hermes-agent/` into this project's
  `.claude/skills/` so the assistant in this repo can discover and use it.
- **FR-002**: The imported skill MUST be usable by the assistant in this
  project without the assistant reimplementing the skill's procedure by hand.
- **FR-003**: The imported file MUST be the unmodified upstream content (a
  faithful copy, not a paraphrase or rewrite).
- **FR-004**: The system MUST record the skill's provenance — source
  repository, source path, and the upstream commit or copy date — alongside the
  imported file so its origin and point-in-time nature are auditable.
- **FR-005**: The system MUST require explicit confirmation before any
  skill-driven action that mutates or reaches the Hermes host; read-only or
  inspection steps MAY proceed without confirmation.
- **FR-006**: If the upstream source cannot be retrieved at import time, the
  system MUST report the import as failed and MUST NOT substitute guessed or
  fabricated skill content.
- **FR-007**: The imported skill MUST NOT execute on its own; it is used only
  when the assistant explicitly invokes it for a task.
- **FR-008**: Re-importing (to pick up an upstream change) MUST be a
  deliberate, explicit action; the system MUST NOT auto-sync or silently
  update the vendored copy.
- **FR-009**: This feature MUST NOT alter the shipped satellite/adapter runtime
  behaviour or weaken the project constitution's thin-satellite, reuse-Hermes,
  and verify-before-relying guarantees; it is build-time tooling only.

### Key Entities *(include if feature involves data)*

- **Vendored Hermes Skill**: The copied `SKILL.md` placed in `.claude/skills/`;
  the verbatim upstream skill the assistant uses.
- **Provenance Note**: The recorded origin — source repository, source path,
  and upstream commit or copy date — making the copy auditable and its
  point-in-time nature explicit.
- **Hermes Build**: The running Hermes the skill's procedures act upon (reused,
  not defined here; reached via the project's existing trusted access).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: The assistant can complete a defined gateway configuration task
  for the adapter end-to-end by following the imported skill, with zero
  hand-written/improvised host commands, in a single working session.
- **SC-002**: The assistant can complete a defined adapter validation against
  the real Hermes by following the imported skill and report a clear pass/fail.
- **SC-003**: 100% of skill-driven actions that mutate or reach the Hermes host
  require explicit confirmation before taking effect (no silent host changes).
- **SC-004**: The imported file is byte-for-byte identical to the upstream
  `SKILL.md`, and 100% of imports have a recorded provenance note
  (repo + path + commit/date).
- **SC-005**: Adapter configuration/validation tasks that previously required
  manual host investigation are completed at least 50% faster (fewer
  round-trips) than the reconstruction approach used in feature 001.
- **SC-006**: When the upstream source is unreachable at import time, the
  failure is reported in 100% of cases and no guessed procedure is substituted.
- **SC-007**: A developer can determine what the imported skill is and exactly
  where/when it came from in under 1 minute by inspecting the repo.

## Assumptions

- Source of truth is the public GitHub path
  `NousResearch/hermes-agent` → `skills/autonomous-ai-agents/hermes-agent/`,
  `main` branch; the specific upstream commit/date is recorded at copy time
  (point-in-time vendored copy, not a live mirror).
- Only `SKILL.md` from that path is copied — no sibling skills, no supporting
  files (per clarification).
- Destination is this repository's `.claude/skills/` so Claude Code
  auto-discovers it and it is immediately invocable by this assistant.
- Mutating/outward actions the skill drives require explicit confirmation by
  default, consistent with this project's established outward-action safety
  posture (the host-key episode, feature 001 T045) and the constitution's
  verify-before-relying principle.
- No host-side discovery, catalog, active-scope management, refresh automation,
  or version-drift detection is in scope (removed per clarification); the copy
  is deliberate and point-in-time.
- This is build-time developer tooling enabling feature 001; it does not ship
  in, or modify, the satellite runtime. Constitution principles I (thin
  satellite), IV (reuse Hermes), and V (verify before relying) are reinforced,
  not affected.
- Security/auth for reaching the Hermes host when the skill acts is out of
  scope here (reuses the project's existing, already-trusted access).
