# Phase 0 Research: Hermes Agent Skill Import

All Technical Context items resolved; spec Clarifications (2026-05-18) removed
the previously-open scope/source/destination/safety unknowns. Phase 0 work was
to **verify the upstream source read-only** before vendoring (constitution V).

## Upstream verification (read-only, `gh api`, 2026-05-18)

- **Decision**: Source is `NousResearch/hermes-agent`, path
  `skills/autonomous-ai-agents/hermes-agent/SKILL.md`, pinned at commit
  `98db898c0bd4df0b09a5830b6a18a069c771e67c` (committed 2026-05-08,
  "feat(skills): declare platforms frontmatter for all 79 undeclared built-in
  skills"). File blob SHA `3a610642f85cbd20da8f2c5fe4932c5e7f3edd23`, 45,630
  bytes.
- **Rationale**: Pinning to an explicit commit makes the copy a verifiable
  point-in-time artifact (SC-004, FR-004) and lets the byte-identity test be
  deterministic. `main` moves; a SHA does not.
- **Alternatives considered**: Track `main` head (rejected — non-reproducible,
  reintroduces drift the clarification removed). Source from the running
  `ssh hermes` host's on-disk skills (rejected — the user explicitly pointed at
  the public GitHub path; GitHub is the canonical published source and needs no
  host access to import).

## D1 — Verbatim copy + separate provenance

- **Decision**: `SKILL.md` is written byte-for-byte from the upstream blob;
  provenance lives in a **sibling** `PROVENANCE.md`, never merged into
  `SKILL.md`.
- **Rationale**: FR-003 / SC-004 require the imported file to be byte-identical
  to upstream; any inline header or edit would break the identity test and the
  "faithful copy" guarantee. A sidecar satisfies FR-004 without touching the
  file.
- **Alternatives considered**: Prepend an HTML-comment provenance header
  (rejected — mutates the file, fails byte-identity); Git commit message only
  (rejected — not discoverable next to the file, weaker for SC-007).

## D2 — Fetch mechanism

- **Decision**: `gh api repos/.../contents/<path>?ref=<commit>` (base64 →
  decode) for both verification and the optional re-import helper; `curl`
  raw.githubusercontent.com at the pinned commit as a no-`gh` fallback.
- **Rationale**: `gh` is available here, gives the blob + SHA for the identity
  check in one call, and works unauthenticated on a public repo.
- **Alternatives considered**: `git clone --filter` / sparse checkout
  (rejected — heavyweight for one file); scraping the HTML tree page (rejected
  — unreliable, as Phase 0's WebFetch showed).

## D3 — Claude Code skill discovery compatibility

- **Decision**: Place at `.claude/skills/hermes-agent/SKILL.md`. The upstream
  frontmatter already provides `name: hermes-agent` and a `description`, which
  is what Claude Code skill discovery needs; extra upstream keys (`version`,
  `author`, `license`, `platforms`, `metadata`) are additional and expected to
  be ignored by the loader.
- **Rationale**: Satisfies clarification Q2 ("immediately invocable here") with
  zero edits to the file (preserves FR-003).
- **Risk / validation**: If the loader rejected unknown frontmatter keys the
  skill would not appear. Mitigation: a Phase-1 quickstart check confirms the
  skill is listed/discoverable after import; if (and only if) discovery
  required frontmatter changes, that is a spec conflict (FR-003 vs
  discoverability) to escalate — not silently patch. Not expected (Claude Code
  tolerates extra frontmatter keys).

## D4 — Re-import is deliberate, never automatic

- **Decision**: Ship `scripts/import-hermes-skill.sh <commit>` that re-fetches,
  overwrites `SKILL.md`, rewrites `PROVENANCE.md`, and prints the byte-identity
  result. It is run by hand; nothing schedules or hooks it.
- **Rationale**: FR-008 — re-import must be explicit; no auto-sync/drift system
  (clarification Q1). The helper just makes the deliberate action repeatable
  and auditable.
- **Alternatives considered**: A git hook / CI job to track upstream (rejected
  — that is the auto-sync the clarification explicitly removed).

## D5 — Safety posture on use (unchanged from spec)

- **Decision**: Importing the file changes nothing on any host. When the
  assistant later *uses* the skill, any step that mutates or reaches the Hermes
  host requires explicit confirmation (FR-005); read-only steps are free.
- **Rationale**: Consistent with the project's outward-action posture (host-key
  episode, feature 001 T045) and constitution V. The skill is reference
  guidance, not an autorun (FR-007).

**No NEEDS CLARIFICATION remain.**
