# Feature Specification: AIVG Rebrand — Hermes Voice → AI Voice Gateway

**Feature Branch**: `012-aivg-branding`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "producr has been renamed to aivg (ai voice gateway) change the branding"

## Overview

The product previously named **"Hermes Voice"** (or "Hermes Voice Satellite")
is renamed to **AIVG — AI Voice Gateway**. This rename completes the
agent-platform-agnostic stance ratified in constitution v2.0.0 (feature 011):
AIVG is the product, and **Hermes** is one of several supported agent-platform
plugins (the v1 canonical one). Other plugins planned: OpenClaw, and future
ones.

This is a **branding + naming hygiene feature**, not a new capability. It
delivers a coordinated rename across every place the old name appears, with
**compat shims** kept for one release so external consumers can migrate
without breakage. The depth of the rename is **full** (clarification
2026-05-20): visible text, CLI binary, Python packages, and the data
directory all rename together; the **repo directory itself is intentionally
out of scope** (a separate concern with its own GitHub / clone-URL
implications).

Anywhere `Hermes` legitimately refers to **the agent-platform plugin**
(`platforms/hermes/`, `~/.hermes/config.yaml` which the plugin reads,
`skills/hermes-agent/` which is the Hermes-platform agent skill),
**Hermes stays**. Anywhere `Hermes` was a shorthand for **the product**, it
becomes **AIVG**.

## Clarifications

### Session 2026-05-20

- Q: How deep should the AIVG rename go? → A: **Full rename** — visible
  text + tagline + CLI binary (`sat-cli` → `aivg`) + Python packages
  (`satellite_core` → `aivg_core`, `sat_cli` → `aivg_cli`) + data
  directory (`~/.satellite/` → `~/.aivg/`). Compat shims (deprecation-
  warned) for one release. Repo directory is **not** renamed in this
  feature.
- Q: Does `Hermes` keep its role under the new branding? → A: **Hermes
  = v1 agent-platform plugin** (constitution v2.0.0 Principle IV
  stance). The plugin folder, the plugin's reuse of `~/.hermes/config.
  yaml`/`.env`/logs, and the per-platform `skills/hermes-agent/` skill
  all stay. **Every other "Hermes Voice"/"Hermes voice satellite"
  prose mention is rewritten** to AIVG-on-Hermes phrasing (e.g.
  "AIVG, running its Hermes plugin").

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A new reader recognizes the product as AIVG (Priority: P1)

A developer arrives at the repository — via the README, a docs page, a spec,
the constitution, or `--help` output — and within the first screenful sees
the product identified as **AIVG (AI Voice Gateway)**. Hermes appears only
as the name of an agent-platform plugin, not as the name of the product.

**Why this priority**: The whole point of the rebrand is recognition. If a
new reader still calls it "Hermes Voice" after reading any one entry
point, the rebrand failed.

**Independent Test**: Open each top-level entry point (README, root docs,
constitution, latest feature spec, `aivg --help`, the Hermes-agent skill
description). For each, confirm the product is identified as AIVG within
the first paragraph/screen and that "Hermes" appears only when discussing
the plugin.

**Acceptance Scenarios**:

1. **Given** the repo's README and root docs, **When** opened, **Then**
   the product name "AIVG (AI Voice Gateway)" appears in the first
   heading/paragraph and "Hermes" appears only in contexts that
   explicitly scope it to the agent-platform plugin.
2. **Given** the constitution, **When** opened, **Then** the title reads
   "AIVG Constitution" (or equivalent AIVG-first phrasing) and the
   project codename note records the rename from "Hermes Voice".
3. **Given** the CLI, **When** the operator runs `aivg --help` or
   `aivg --version`, **Then** the tagline and help describe AIVG.
4. **Given** the Hermes-platform agent skill, **When** read, **Then**
   the skill describes itself as the **Hermes plugin for AIVG**, not
   as "Hermes Voice's skill".
5. **Given** any spec under `specs/` (including all historical features
   001–011), **When** opened, **Then** product-level "Hermes Voice"
   references are rewritten to AIVG; plugin-level Hermes references
   are preserved with their scope explicit.

---

### User Story 2 — Existing code keeps working through compat shims (Priority: P1)

An external consumer who imports `satellite_core` or runs `sat-cli`
continues to work for one release after the rename, with a clear
deprecation warning telling them to migrate. The same applies to anything
written to `~/.satellite/` and to the old pyproject project name.

**Why this priority**: A rename that silently breaks downstream users is
worse than no rename. The compat window is the safety net.

**Independent Test**: From a fresh shell after the rename ships, run
`from satellite_core import models`, run `sat-cli --version`, and read
`~/.satellite/state.json`. Each works, each emits one
`DeprecationWarning` pointing to the new name, and the new name works
equivalently.

**Acceptance Scenarios**:

1. **Given** an existing script that does `import satellite_core`,
   **When** it runs after the rename, **Then** it succeeds and prints
   one `DeprecationWarning` naming `aivg_core` as the new location.
2. **Given** an existing CLI invocation `sat-cli list`, **When** run,
   **Then** it works identically to `aivg list` and emits a deprecation
   notice on stderr (without contaminating `--json` stdout).
3. **Given** an existing `~/.satellite/state.json` on disk, **When**
   the rebranded gateway starts, **Then** it reads the old path and
   migrates the contents to `~/.aivg/state.json` atomically.
4. **Given** an existing `pyproject.toml` referencing
   `satellite-core`, **When** another package depends on it, **Then**
   the new `aivg-core` distribution provides the same import surface
   via the shim.
5. **Given** the next release after the compat window, **When** the
   shims are removed, **Then** consumers on the old names get a
   clear, actionable error pointing at the new names.

---

### User Story 3 — A new operator-facing surface lands on AIVG (Priority: P2)

When the operator runs anything new (the binary, an agent skill, the
contract files, error messages, exit-code docs), the product appears as
AIVG. The error envelope, exit-code mapping, and `--json` `data` shape do
NOT change — the rebrand is **a visible-text-only contract change** at the
operator surface.

**Why this priority**: Operators rely on the closed `error.code` and exit-
code sets; those MUST NOT shift during a rebrand. Only labels do.

**Independent Test**: Diff the v1.0.0 contract files (REST `info.title`,
CLI tagline, agent-skill name/description) against the post-rebrand set;
confirm that **operation IDs, schemas, error codes, exit codes, and JSON
envelope shape are byte-identical** while **titles/descriptions/taglines
are updated**.

**Acceptance Scenarios**:

1. **Given** `contracts/management-api.yaml`, **When** opened, **Then**
   `info.title` is "AIVG Satellite Management API"; every
   `operationId`, schema, status code, and `error` enum is unchanged.
2. **Given** `contracts/cli-contract.md`, **When** read, **Then** the
   binary name is `aivg`; the documented closed `error.code` set, the
   JSON envelope shape, and exit codes are unchanged.
3. **Given** `aivg --json --version`, **When** run, **Then** the
   envelope still has shape `{ok, data, error, v}`; `data.version`
   reports an AIVG version; `data.contract_version` is unchanged
   (1.0.0).

---

### User Story 4 — Constitution amendment records the rename (Priority: P2)

The constitution is amended to reflect the new product name, with a Sync
Impact Report bullet recording the rename. No principle is removed or
redefined; this is a **PATCH** version bump (cosmetic + clarification).
The Hardware/Workflow/Governance language updates to AIVG where it
referred to the project, and to "Hermes plugin" / "agent-platform plugin"
where it referred to the upstream.

**Why this priority**: Governance source-of-truth must reflect the
canonical name; otherwise specs/plans/agents disagree on what to call
the thing.

**Independent Test**: Read the constitution top-to-bottom; verify the
title, the Sync Impact Report's latest entry, the project-codename
note, and every prose mention align with AIVG-as-product / Hermes-as-
plugin.

**Acceptance Scenarios**:

1. **Given** `.specify/memory/constitution.md`, **When** opened,
   **Then** the title is AIVG-first; the Sync Impact Report records
   the rename and a PATCH version bump (v2.0.0 → v2.0.1) with
   rationale "Branding rebrand — Hermes Voice → AIVG (AI Voice
   Gateway); no principle changes".
2. **Given** Principles I–V, **When** read, **Then** their normative
   content is **unchanged**; only "Hermes Voice"/"the product"
   phrasing updates to AIVG; Hermes-as-plugin references stay.

---

### User Story 5 — Tooling and CI find no stragglers (Priority: P3)

After the rebrand ships, a project-wide grep for the obsolete product
name (`"Hermes Voice"`, `"hermes-voice"` as a product label, `"Hermes
voice"`) returns zero hits **outside** allowed exempt locations
(historical commit messages, the compat shim modules, archived feature
quickstarts marked as historical).

**Why this priority**: A repeated rebrand a year later is much harder
than catching stragglers now.

**Independent Test**: A scripted scan listing all matches with an
allow-list passes empty.

**Acceptance Scenarios**:

1. **Given** a documented allow-list of paths (compat shims, historical
   archives), **When** the rebrand scan runs, **Then** zero
   non-allowed matches are reported.
2. **Given** a CI lint job (added in this feature), **When** a new
   change re-introduces the obsolete product name outside the allow-
   list, **Then** the job fails with a clear pointer.

---

### Edge Cases

- **Concurrent migration on first run**: if both `~/.satellite/state.
  json` and `~/.aivg/state.json` exist, the newer file wins; the older
  is renamed with a `.pre-aivg-rebrand.bak` suffix rather than deleted.
- **Old CLI piped into JSON consumer**: `sat-cli`'s deprecation notice
  goes to **stderr**, never to stdout, so `--json` consumers stay clean.
- **`pip install` of the old name**: the old distribution name resolves
  to a metapackage that depends on the new one and emits the
  `DeprecationWarning` on import.
- **Constitution version semantics**: this is a PATCH bump (no
  principle change). If the rebrand accidentally rephrases a normative
  rule, that's a MINOR/MAJOR bump and the spec rejects the change.
- **Agent skill installation paths**: the Hermes-platform skill stays
  at `skills/hermes-agent/` and installs to `~/.hermes/skills/...`;
  only product-level names in its description change. The skill's
  `name:` frontmatter stays `satellite-management` (the capability,
  not the product).
- **Historical feature quickstarts (001–011)**: prose product-name
  mentions are updated; **commit messages and the implementation
  history are NOT rewritten** (the spec must not require rewriting
  git history).
- **Misspelling protection**: a CI lint catches "Hermes Voice"
  reintroductions; a non-CI checklist catches `AIVoiceGateway` (no
  space) and `aivg-voice-gateway` (redundant) variants in new copy.

## Requirements *(mandatory)*

### Functional Requirements

**Product identity**

- **FR-001**: The product MUST be identified as **AIVG (AI Voice Gateway)**
  in every operator-facing or developer-facing entry point: README, root
  docs, constitution, every feature spec/plan, CLI help/tagline/version
  output, agent-skill description, and the REST API contract title.
- **FR-002**: Where `Hermes` referred to the product, the text MUST be
  rewritten to AIVG. Where `Hermes` refers to the agent-platform plugin
  (per constitution v2.0.0 Principle IV), the term Hermes MUST stay,
  with the plugin scope made explicit on first use in each document.

**Compat shims**

- **FR-003**: The legacy Python package `satellite_core` MUST remain
  importable for one release, re-exporting from the new `aivg_core`
  package and emitting one `DeprecationWarning` per process pointing
  to the new import path.
- **FR-004**: The legacy CLI binary `sat-cli` MUST continue to be
  available for one release, dispatching to the new `aivg` binary and
  printing a one-line deprecation notice on **stderr** (never stdout,
  so JSON consumers stay clean).
- **FR-005**: A `~/.satellite/state.json` (and any `~/.satellite/
  firmware/`) present at first run of the rebranded gateway MUST be
  migrated to `~/.aivg/` atomically; the old file MUST be left in
  place with a `.pre-aivg-rebrand.bak` suffix, never deleted.
- **FR-006**: The legacy distribution name `satellite-core` MUST
  install (as a metapackage depending on `aivg-core`) for one release;
  removing it after the window MUST surface a clear, actionable error.

**Operator-surface invariants (no contract drift)**

- **FR-007**: The rebrand MUST NOT change any documented
  `operationId`, REST request/response schema, status code, or HTTP
  route in `contracts/management-api.yaml`. Only `info.title`,
  `info.description`, tag titles, and other purely-descriptive text
  change.
- **FR-008**: The rebrand MUST NOT change the CLI's JSON envelope
  shape (`{ok, data, error, v}`), the closed `error.code` set, exit
  codes, or any `data.*` field name. Only the binary name, tagline,
  and help prose change.
- **FR-009**: The Hermes-platform agent skill's `name:` frontmatter
  (which Hermes uses to install the skill) MUST NOT change; only
  description, examples, and prose update.

**Constitution amendment**

- **FR-010**: The constitution MUST be amended with a Sync Impact
  Report bullet recording the rebrand and a PATCH version bump (e.g.
  v2.0.0 → v2.0.1). Principles I–V MUST keep the normative content
  byte-equivalent (modulo product-name replacements that do not
  change rule meaning).

**Hygiene & ongoing enforcement**

- **FR-011**: A documented **rebrand allow-list** MUST specify which
  files may keep the obsolete product name (compat shims; historical
  commit messages; archived feature quickstart files marked
  ARCHIVED).
- **FR-012**: A lint check (CI-runnable; works locally) MUST scan
  the working tree for the obsolete product-name strings and fail
  when a non-allow-listed file contains them. The lint MUST run as
  part of the project's standard test invocation.

**Coordinated identifier renames**

- **FR-013**: The new Python package names MUST be `aivg_core` and
  `aivg_cli`; the new CLI binary MUST be `aivg`; the new data
  directory MUST be `~/.aivg/`. Every internal reference (docs,
  specs, plan, contracts, tasks) MUST use the new names.
- **FR-014**: Hermes-as-plugin identifiers MUST NOT change:
  `platforms/hermes/`, `skills/hermes-agent/`, and the plugin's reuse
  of `~/.hermes/config.yaml`, `~/.hermes/.env`,
  `~/.hermes/logs/gateway.log`. The plugin's identifier is `hermes`
  (lowercase).

### Key Entities

- **AIVG (the product)**: the umbrella name for the satellite voice
  system and its management plane and CLI. Replaces the prior product
  codename "Hermes Voice".
- **Hermes (an agent-platform plugin)**: one of several plugins AIVG
  supports under constitution v2.0.0 Principle IV. Owns its
  `~/.hermes/` data; v1 canonical plugin.
- **Compat shim**: a thin, deprecation-warned forwarder kept for one
  release so external consumers can migrate without breakage. Applies
  to: the `satellite_core` Python package, the `sat-cli` binary, the
  `satellite-core` distribution name, and the `~/.satellite/` data
  directory.
- **Rebrand allow-list**: a documented set of paths where the obsolete
  product name may persist (compat shims, historical commit messages,
  archived quickstarts).
- **Lint check**: a project-standard scan that fails when the obsolete
  product name re-enters outside the allow-list.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A new reader landing on README, the constitution, the
  latest feature spec, or `aivg --help` correctly identifies the
  product as AIVG within the first 30 seconds in 100% of cases.
- **SC-002**: After the rebrand ships, 100% of obsolete product-name
  occurrences in the working tree are either resolved or live in the
  documented allow-list — the lint check (FR-012) exits 0.
- **SC-003**: Zero documented `operationId`s, REST schemas, HTTP
  routes, CLI exit codes, CLI `error.code` values, or `data.*` field
  names change in this feature (contract-diff = 0 substantive).
- **SC-004**: External consumers on the old names (`satellite_core`
  import, `sat-cli` binary, `~/.satellite/` data dir, `satellite-core`
  distribution) keep working for at least one release after the
  rename, each producing exactly one `DeprecationWarning` (or
  equivalent stderr notice) per process.
- **SC-005**: An existing `~/.satellite/state.json` on disk is
  preserved (renamed to `.pre-aivg-rebrand.bak`, never deleted) and
  the equivalent `~/.aivg/state.json` is created with identical
  content in 100% of migrations.
- **SC-006**: Constitution version bumps from v2.0.0 → v2.0.1 with a
  Sync Impact Report bullet that names the rebrand; no Principle
  text gains or loses normative meaning.
- **SC-007**: The Hermes-plugin folder (`platforms/hermes/`), the
  Hermes-platform agent skill (`skills/hermes-agent/`), and the
  plugin's reuse of `~/.hermes/` configuration paths remain
  unchanged.
- **SC-008**: Repeated rebrand work is prevented — the CI lint (FR-
  012) catches a re-introduction of the obsolete product name within
  one PR.

## Assumptions

- The **repository directory itself** (`hermes-voice/`) is **not**
  renamed in this feature. Renaming the directory triggers external
  clone-URL changes (GitHub remote rename, README badges, deployment
  paths) and is its own separate piece of work; tracked but
  out-of-scope here.
- Git **history is not rewritten**; commit messages and historical
  branch names retain their original "Hermes Voice" mentions.
- The constitution amendment is a **PATCH** bump (cosmetic /
  product-name only). If, during the rebrand, anyone proposes a
  normative principle change, that's a separate amendment and
  blocks the spec.
- Compat shims live for **one release** — the next feature after
  this one MAY remove them (tracked under a follow-up task, not done
  in this feature).
- The Hermes-platform agent skill's `name:` field
  (`satellite-management`) is a capability identifier and does NOT
  encode the product name — so it does not change.
- The CLI's `--contract-version` (currently `1.0.0`) does NOT change:
  this rebrand is not a contract change (FR-007/FR-008).
- AIVG expands to "AI Voice Gateway" — this expansion is documented
  on first mention in each top-level doc, then the acronym alone is
  used.

## Dependencies

- The rebrand depends on constitution v2.0.0 already being in place
  (feature 011), which established `Hermes` as a plugin name rather
  than the product name.
- The Python packages, CLI binary, and data directory being renamed
  here are the ones introduced/renamed in feature 011 — this feature
  is a coordinated second pass over the same surface, no new
  capability.
- No external dependencies (no UI, no third-party SDK changes).
