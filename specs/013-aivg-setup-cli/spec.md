# Feature Specification: `aivg setup` — Platform-Agnostic CLI Deploy

**Feature Branch**: `013-aivg-setup-cli`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "ship an aivg setup / aivg deploy CLI
subcommand that detects the installed agent platform and installs the
satellite plugin via that platform's plugin-registration convention;
deprecate the deploy/*.sh shell scripts; add a setup capability to
per-platform skills so the agent can do it conversationally"

## Overview

Today, installing the AIVG satellite system onto a host means running a
bash script — `deploy/deploy-local.sh` for the same machine or
`deploy/deploy-to-hermes.sh` for SSH-to-Hermes. Both scripts predate
constitution v2.0.0 / Principle IV (agent-platform-agnostic) and are
Hermes-coupled by design: they hard-code `~/.hermes/hermes-agent/`, the
Hermes plugin layout, the `satellite:` config-block format, the Hermes
gateway restart command. After the AIVG rebrand (feature 012) they also
no longer import-resolve, because they `cp -R` the old
`hermes_satellite_adapter/` path that has been removed.

This feature replaces them with an **operator-facing CLI subcommand**
— `aivg setup` (and `aivg deploy` as an alias for clarity in scripted
contexts) — that:

1. **Detects** which agent platform is installed on the host (Hermes
   today; OpenClaw planned; future ones extensible).
2. **Installs** the AIVG satellite plugin into that platform using
   that platform's own plugin-registration convention — implemented
   inside the per-platform plugin module (`aivg_core/platforms/
   <name>/setup.py`), keeping all platform-specific knowledge behind
   the existing plugin seam (constitution v2.0.0 Principle IV).
3. **Adds a `setup` capability to per-platform agent skills** so the
   user can say *"install the AIVG satellite into Hermes"* in chat
   and the agent runs `aivg setup` under the hood with the same
   confirmation discipline destructive verbs already use.
4. **Deprecates** the four `deploy/*.sh` scripts and the
   `deploy/plugin/` plugin shim folder — kept for one release as
   thin wrappers that forward to `aivg setup --legacy-hermes`, then
   removed in the release after.

The CLI subcommand is the canonical operator entry point; the agent
skill wraps the CLI (same pattern as every other `aivg` capability —
constitution IV, feature 011 clarification). Other agent platforms
plug in the same way: a new `platforms/<name>/setup.py` and a sibling
skill folder — no new bash, no `deploy/*.sh` to maintain per platform.

## Clarifications

### Session 2026-05-20

(none yet — Phase 0 / specification only.)

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Operator installs AIVG into Hermes with one command (Priority: P1)

An operator on a host that already has Hermes Agent installed runs
`aivg setup`. The CLI detects the Hermes install, summarizes what it
will do, asks for confirmation (interactive) OR proceeds under
`--yes`, vendors the plugin into the Hermes plugins directory, adds an
`aivg:` (or `satellite:`) block to `~/.hermes/config.yaml`, installs
any missing Python deps into the Hermes venv, restarts the Hermes
gateway, and post-verifies that the management plane is listening.

**Why this priority**: This is the headline capability. Without it the
operator-facing deploy story is "run a broken shell script"; with it
the satellite system is one command away from a working voice loop on
the host.

**Independent Test**: On a host with Hermes Agent installed, run
`aivg setup --yes` and confirm:
1. Hermes plugin directory contains the new plugin module.
2. `~/.hermes/config.yaml` has the new config block.
3. Hermes gateway restarts and is responding on `8643`/`8644`.
4. `aivg list` against `localhost:8643` returns a (possibly empty) fleet.

**Acceptance Scenarios**:

1. **Given** a Hermes Agent install at the standard location and no
   pre-existing AIVG plugin, **When** the operator runs
   `aivg setup --yes`, **Then** the plugin is vendored, config is
   updated, the gateway restarts, and post-verify confirms the
   management plane is listening.
2. **Given** an AIVG plugin is already vendored on the host, **When**
   `aivg setup --yes` runs, **Then** it detects the existing install
   and re-vendors idempotently (no duplicate config block, no
   gateway-restart-loop, no destructive overwrite without an explicit
   `--force` flag).
3. **Given** the operator runs `aivg setup` without `--yes`, **When**
   the confirmation prompt appears, **Then** the operator sees a
   one-screen summary of every file/config change that will be made,
   and answering "no" leaves the host untouched.
4. **Given** the operator runs `aivg setup --preflight`, **When**
   executed, **Then** the command runs every detection + dependency
   check read-only, prints what *would* happen, and exits without
   touching the host.

---

### User Story 2 — Operator uninstalls cleanly (Priority: P2)

An operator runs `aivg setup --uninstall`. The CLI removes the
vendored plugin, removes the AIVG config block, restarts the gateway,
and post-verifies the platform is back to its pre-AIVG state — the
inverse of US1.

**Why this priority**: Reversibility is the operator-trust contract.
A platform-agnostic install isn't credible without a platform-agnostic
uninstall. P2 because US1 alone delivers value; uninstall is the
safety net.

**Independent Test**: After US1, run `aivg setup --uninstall --yes`
and confirm:
1. Plugin directory no longer contains the AIVG plugin.
2. Config block is removed from `~/.hermes/config.yaml` (other config
   sections unchanged).
3. Gateway restarts and returns to its pre-AIVG behavior (other
   pre-existing platform plugins still load).

**Acceptance Scenarios**:

1. **Given** a host with AIVG installed (US1 completed), **When**
   `aivg setup --uninstall --yes` runs, **Then** every artifact US1
   created is removed, and pre-existing platform plugins listed before
   install are unchanged.
2. **Given** an uninstall is invoked, **When** the configured backup
   from install time exists, **Then** the operator is offered a
   rollback to that backup as the recommended path; on `--yes` the
   uninstall proceeds without rollback.

---

### User Story 3 — Agent installs AIVG conversationally (Priority: P2)

The user says to a Hermes-platform agent: *"install the AIVG satellite
system on this machine."* The agent uses its `satellite-management`
skill's new `setup` capability, asks the user to confirm the host-
mutating action in chat, then shells out to `aivg setup --yes` on the
operator's behalf. The agent reports each step's outcome from the
NDJSON progress stream.

**Why this priority**: Closes the conversational install loop — the
skill becomes a full operator surface, not just a configure/OTA tool.
P2 because the CLI alone (US1/US2) is sufficient for a CI/automation
operator; the conversational shape is for the chat-driven operator.

**Independent Test**: Drive the skill via the Hermes agent (or test
runner) with the install intent; verify the agent (a) asks for
confirmation before running, (b) calls `aivg setup --json --yes`, and
(c) reports the final outcome from the envelope.

**Acceptance Scenarios**:

1. **Given** the user asks the agent to install AIVG, **When** the
   agent reaches the destructive step, **Then** it pauses, asks the
   user to confirm in chat, and only then runs `aivg setup --json --yes`.
2. **Given** the install fails midway, **When** `aivg setup` exits
   non-zero, **Then** the agent reports the specific failure step +
   reason from the NDJSON output (not just "command failed").
3. **Given** the user says "no" to the in-chat confirmation, **When**
   the agent receives that, **Then** the agent does NOT add `--yes`,
   and the install does not run.

---

### User Story 4 — Setup works for a new agent platform without new bash (Priority: P3)

A new agent platform (e.g. OpenClaw) ships its plugin module at
`aivg_core/platforms/openclaw/`. To make `aivg setup` install AIVG
into OpenClaw, the platform author adds a `setup.py` next to the
plugin module implementing the same interface as the Hermes plugin's
`setup.py`. No `deploy/openclaw-deploy.sh` script is needed; no
changes to the satellite core; no new top-level entries.

**Why this priority**: This is the architectural payoff. The whole
point of the v2.0.0 plugin seam is that adding a platform is a
plugin-author task, not a core-team task. P3 because OpenClaw itself
is a future feature; what this story proves is the seam survives the
deploy layer too.

**Independent Test**: Write a fake-platform `setup.py` (similar to the
existing `tests/fixtures/platforms/echo/`); set `platform: echo` in a
test config; run `aivg setup --preflight --platform echo`; assert
the right detection logic fires and **no Hermes-plugin module is
imported**.

**Acceptance Scenarios**:

1. **Given** a host with two plugins available, **When** the operator
   passes `--platform openclaw`, **Then** the OpenClaw plugin's
   `setup.py` runs; the Hermes plugin's `setup.py` does not.
2. **Given** detection finds no installed agent platform on the host,
   **When** `aivg setup` runs, **Then** the CLI surfaces a specific
   error (`no_platform_detected`) listing the platforms it looked for
   + how to install them; does not silently fall back to any
   particular default.

---

### User Story 5 — Legacy `deploy/*.sh` users keep working for one release (Priority: P3)

Anyone who scripted `bash deploy/deploy-local.sh` gets a one-release
window: the scripts become thin wrappers that emit a one-line stderr
deprecation notice and forward to `aivg setup --legacy-hermes [--yes]`.
The release after this one removes the shell scripts entirely.

**Why this priority**: Same compat-window discipline feature 011
applied to package renames and feature 012 applied to the binary name.
P3 because the scripts are already broken post-rebrand; if no external
consumer depends on them today, the compat window might collapse to
zero.

**Independent Test**: Run `bash deploy/deploy-local.sh --preflight`;
confirm (a) one stderr deprecation notice mentioning `aivg setup`,
(b) the underlying `aivg setup --preflight` runs and prints what it
would do, (c) exit code is preserved.

**Acceptance Scenarios**:

1. **Given** the user runs `bash deploy/deploy-local.sh --preflight`,
   **When** executed, **Then** stderr contains one deprecation notice
   pointing at `aivg setup`, and the underlying preflight runs to
   completion with the same exit code.
2. **Given** the next release ships, **When** `deploy/deploy-local.sh`
   no longer exists, **Then** the CHANGELOG entry for that release
   names the removal and the migration command.

---

### Edge Cases

- **Hermes not installed** at the standard location → CLI surfaces
  `no_platform_detected` with the searched locations listed.
- **Hermes installed but the venv is broken / missing required deps**
  → preflight reports the gap; `setup --yes` either installs the
  missing deps (with explicit operator consent) or refuses cleanly.
- **Mid-install failure** (e.g. config-write partial, gateway restart
  hangs) → the install must be rollback-safe via the backup
  captured at the start; the CLI offers the rollback command in the
  failure message.
- **Multiple installed platforms** (e.g. Hermes AND OpenClaw on the
  same host) → `aivg setup` with no `--platform` flag prompts the
  operator to choose; under `--json` without `--platform` returns
  `error.code = multiple_platforms_detected` so an agent can ask
  the user explicitly.
- **`aivg setup` run from inside an existing AIVG install** (e.g.
  the operator already ran it) → detects the prior install via a
  state file or marker, treats as a no-op re-vendor unless
  `--force`.
- **Concurrent invocation** — two `aivg setup` processes against the
  same host → second instance detects a lock file (or running peer)
  and refuses.
- **Config file already contains an `aivg:` / `satellite:` block from
  manual edits** → preflight surfaces the existing block; on
  install, the CLI never overwrites a hand-edited block silently —
  it either skips with a note or refuses pending `--force-config`.
- **Non-Hermes plugin with no `setup.py`** → the plugin loads at
  runtime but `aivg setup` for that platform fails with
  `setup_not_supported_for_platform` and a pointer at the plugin's
  README.

## Requirements *(mandatory)*

### Functional Requirements

**CLI surface**

- **FR-001**: The system MUST provide an `aivg setup` subcommand on
  the existing `aivg` CLI that performs the host-side install of the
  AIVG satellite plugin into the active agent platform. `aivg deploy`
  MUST be accepted as a synonym for `aivg setup` (no behavior
  difference; clarity-of-intent alias).
- **FR-002**: `aivg setup` MUST support these mutually-exclusive
  modes:
  * `--preflight` — read-only checks, no mutation; prints the
    detection summary + a deterministic list of every change that
    *would* be made.
  * default (no mode flag) — install; mutates the host after
    operator confirmation OR `--yes`.
  * `--uninstall` — remove an existing AIVG plugin install; same
    confirmation gate as install.
- **FR-003**: `aivg setup` MUST emit machine-readable progress in
  NDJSON form under `--json` (one envelope per phase: `detecting`,
  `preflight`, `confirming`, `vendoring`, `config_writing`,
  `installing_deps`, `restarting_gateway`, `post_verifying`,
  `done`/`failed`). The envelope shape matches the existing CLI
  v1 envelope (`{ok, data, error, v=1}`).

**Platform detection**

- **FR-004**: The system MUST detect installed agent platforms on the
  host without importing any platform-specific Python code at the CLI
  layer. Detection MUST live inside each platform's plugin module
  (e.g. `aivg_core/platforms/hermes/setup.py::detect()`), so adding a
  new platform is a plugin-author task only.
- **FR-005**: With no `--platform` flag, the CLI MUST iterate the
  enabled plugins, call each `detect()`, and pick the platform that
  reports `is_installed=True`. If multiple report installed, the CLI
  MUST refuse with a specific `multiple_platforms_detected` error
  (interactive: prompt; `--json`: error envelope).
- **FR-006**: With `--platform <name>`, the CLI MUST use only that
  plugin and surface a specific error if it is not installed.

**Per-platform install logic (plugin seam)**

- **FR-007**: Each agent-platform plugin that supports install MUST
  expose a documented `setup.py` (or equivalent) with at least:
  `detect() → DetectResult`, `preflight() → PreflightReport`,
  `install(opts) → InstallResult`, `uninstall(opts) → UninstallResult`.
  Constitution v2.0.0 Principle IV: every platform-specific concept
  (config-block format, plugin directory layout, gateway-restart
  command, dependency installer) lives behind this interface.
- **FR-008**: The Hermes plugin MUST implement this interface and
  replace the Hermes-specific behavior currently in
  `deploy/deploy-local.sh`/`deploy-to-hermes.sh`/`deploy/plugin/`
  (vendor + config block + aiortc install + `hermes gateway restart`
  + post-verify), with the same safety contract (backup-first,
  idempotent, rollback-safe).
- **FR-009**: A plugin that does not support setup MUST be detectable
  but invokable for setup MUST return `setup_not_supported_for_platform`
  with a pointer at the plugin's README (e.g. OpenClaw stub in v1).

**Safety + reversibility**

- **FR-010**: Every host-mutating step MUST be preceded by an explicit
  operator confirmation, either interactively (the destructive-action
  prompt feature 011 introduced) OR via `--yes` under `--json`. Under
  `--json` without `--yes`, the CLI MUST refuse the action with
  `error.code = bad_input` (same safety net as `aivg device command
  factory-reset`, FR-019 from feature 011).
- **FR-011**: Every install MUST capture a host-state backup (config-
  file backup, list of pre-existing plugins, any modified state)
  BEFORE any mutation, in a per-install timestamped folder under
  the AIVG state directory. The backup MUST be referenced in the
  install summary so the operator can revert with a documented
  command.
- **FR-012**: `aivg setup --uninstall` MUST be the inverse of install:
  remove the same files, restore the config block to its pre-install
  state from the backup. Uninstall MUST leave **pre-existing
  platform plugins** on the host untouched (the "we don't remove
  what we didn't add" rule).
- **FR-013**: Concurrent `aivg setup` invocations against the same
  host MUST be prevented (lock file or equivalent); the second
  invocation refuses with a specific error pointing at the running
  one.

**Per-platform agent skill**

- **FR-014**: The Hermes-platform agent skill at
  `skills/hermes-agent/SKILL.md` MUST gain a documented `setup`
  capability that:
  * Asks the user to confirm the host-mutating action in chat.
  * Shells `aivg setup --json --yes` only after the user confirms.
  * Reports each NDJSON envelope to the user as progress.
  * On failure, reports the specific failed phase + reason from the
    envelope, not just "command failed".
- **FR-015**: Every per-platform skill that ships with AIVG (Hermes
  v1; OpenClaw planned) MUST follow the same `setup` capability
  shape; the skill is the conversational wrapper, the CLI is the
  single execution surface.

**Deprecation of `deploy/*.sh`**

- **FR-016**: The four scripts `deploy/deploy-local.sh`,
  `deploy/deploy-to-hermes.sh`, `deploy/parity-check.sh`,
  `deploy/rollback.sh` MUST be replaced (for one release window)
  with thin wrappers that:
  * Emit a one-line stderr deprecation notice naming `aivg setup`.
  * Forward to `aivg setup --legacy-hermes [--yes] [--preflight] [--uninstall]`,
    mapping the legacy flags to the new CLI's flags.
  * Preserve the legacy exit code.
- **FR-017**: The `deploy/plugin/` subdirectory (Hermes-side plugin
  shim) MUST migrate into the Hermes plugin module
  (`aivg_core/platforms/hermes/`) — specifically into a new
  `plugin_entrypoint.py` (or equivalent) that the Hermes plugin's
  `setup.install()` vendors. After the migration, the old
  `deploy/plugin/` is empty (or contains only a stub forwarding
  README).
- **FR-018**: The release after this one MUST remove the
  `deploy/*.sh` wrappers entirely. This feature ships a follow-up
  tracking doc (e.g.
  `specs/013-aivg-setup-cli/followup-deploy-shell-removal.md`) so the
  removal is queued.

**Operator-side guarantees + contract invariants**

- **FR-019**: `aivg --contract-version` MUST remain `1.0.0`. Adding
  `aivg setup` is additive to the CLI surface — no command rename,
  no flag rename, no exit-code-meaning change (same v1 contract
  discipline that features 011 and 012 followed).
- **FR-020**: New `error.code` values added by `aivg setup` MUST
  appear in the closed set documented in
  `contracts/cli-contract.md`. At minimum these are added by this
  feature: `no_platform_detected`, `multiple_platforms_detected`,
  `setup_not_supported_for_platform`, `setup_lock_held`,
  `setup_partial_failure`. New `error.code` additions are minor
  bumps (additive); removing/renaming is a major bump.

### Key Entities

- **PlatformSetup module**: the per-platform interface
  (`detect / preflight / install / uninstall`) every plugin that
  supports CLI deploy implements. Lives next to the plugin's
  runtime module (`aivg_core/platforms/<name>/setup.py`).
- **InstallBackup**: the timestamped folder under the AIVG state dir
  containing every artifact captured before the first mutation, used
  for rollback.
- **InstallSummary / NDJSON progress event**: one envelope per phase
  of an install/uninstall (matches the existing CLI v1 envelope),
  consumed by the per-platform skill to report progress.
- **DeprecatedShellScript**: the four `deploy/*.sh` files retained
  for one release as deprecation-warned forwarders to `aivg setup`.
- **PlatformDetectionResult**: `{is_installed: bool, paths: dict,
  version: str|null, reasons: list[str]}` per platform; the CLI
  aggregates these to decide which plugin to use.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: An operator with Hermes Agent already installed can run
  `aivg setup --yes` and have a working AIVG satellite management
  plane (`aivg list` returns a non-error response from
  `localhost:8643`) in under **2 minutes** end-to-end on a typical
  developer laptop.
- **SC-002**: `aivg setup --preflight` is **read-only** in 100% of
  invocations — verified by a CI integration test that diffs the
  host's filesystem before/after and asserts zero changes.
- **SC-003**: `aivg setup --uninstall` cleanly removes everything an
  install created **and nothing else**, verified by the same diff:
  after `setup` + `uninstall`, the host is byte-equivalent to its
  pre-install state (modulo the install/uninstall log entries and
  any pre-existing-platform-plugin state that itself logged).
- **SC-004**: Adding a new agent platform (proven via the
  `tests/fixtures/platforms/echo/` fixture) requires **zero changes
  to the satellite core or the `aivg setup` CLI** — only the new
  plugin's `setup.py`. Verified by a test that adds the echo
  platform's setup module and exercises detect/preflight/install
  via the same CLI invocation that handles Hermes.
- **SC-005**: A Hermes-platform agent driven by the
  `satellite-management` skill can install AIVG end-to-end from a
  chat prompt with **exactly one user confirmation in chat** and
  **zero CLI prompts** (the skill always invokes `aivg setup --json
  --yes` after the user confirms).
- **SC-006**: Legacy `deploy/*.sh` invocations succeed for one
  release with one stderr deprecation notice per invocation and
  preserved exit codes — verified by a test that runs each script's
  `--preflight` mode and asserts the notice + exit code.
- **SC-007**: The CLI contract version reported by
  `aivg --contract-version` stays at **`1.0.0`** through this
  feature's ship — no contract bump, only additive surface (FR-019).
- **SC-008**: Concurrent invocations of `aivg setup` against the
  same host result in exactly one mutation; the second invocation
  refuses with `error.code = setup_lock_held` and a pointer at the
  running peer — verified by a parallel-subprocess test.
- **SC-009**: A failed install (induced by killing the gateway-
  restart step) leaves the host in a recoverable state: the
  pre-install backup is intact, the operator can invoke a documented
  rollback command, and post-rollback the host is byte-equivalent
  to its pre-install state — verified by a fault-injection test.
- **SC-010**: A repo-wide grep for `deploy-local.sh` /
  `deploy-to-hermes.sh` finds them only in (a) the wrapper scripts
  themselves, (b) the CHANGELOG entry deprecating them, (c) the
  follow-up doc tracking their removal. No new code references the
  old paths (rebrand-lint analog, enforced via the existing
  `test_no_legacy_branding.py` mechanism extended with a few extra
  patterns).

## Assumptions

- The active agent platform on the host is installed via that
  platform's own installer (e.g. Hermes via its documented install
  flow). AIVG does NOT install the agent platform; it installs the
  AIVG plugin INTO an agent platform that's already there.
- A BLE-capable host is NOT a prerequisite for `aivg setup` (BLE is
  only the onboarding path from feature 011; deploy is unrelated).
- The operator running `aivg setup` has write access to the agent
  platform's plugin directory and config file. Permission failures
  surface as `error.code = permission_denied` with the path that
  failed.
- `aivg setup` does not need to be SSH-aware in v1 — the legacy
  `deploy-to-hermes.sh` script's SSH path is folded into the local
  Hermes plugin's setup module for now; remote deploy (SSH/cloud)
  is a future feature (separate flag set, separate spec).
- Compat-shim window for `deploy/*.sh` is **one release** — same
  policy features 011 (package shims) and 012 (binary shim)
  followed.
- The `aivg setup` summary screen and the NDJSON progress envelopes
  are stable contracts; downstream agents/scripts can parse the
  envelopes. The exact wording of the human-mode prompt is not.

## Dependencies

- The `aivg` CLI from features 011 and 012 (the Typer entry point
  + the v1 JSON envelope contract).
- The `AgentPlatform` plugin seam from constitution v2.0.0 (feature
  011 Phase 2) — `aivg setup` reuses it for plugin discovery and
  per-platform dispatch.
- The Hermes plugin at `aivg_core/platforms/hermes/` — gains a new
  `setup.py` module that absorbs the Hermes-specific logic currently
  in the shell scripts.
- The Hermes agent skill at `skills/hermes-agent/SKILL.md` — gains a
  new `setup` capability example.

## Out of Scope

- **Remote deploy (SSH/cloud)** — the legacy `deploy-to-hermes.sh`
  SSH path is consolidated into the local Hermes setup module for
  v1; a separate future feature handles SSH/cloud install.
- **Installing the agent platform itself** — `aivg setup` installs
  the AIVG plugin INTO an agent platform that is already installed,
  not the platform.
- **Repository directory rename** (`hermes-voice/` → `aivg/`) —
  tracked separately in
  `specs/012-aivg-branding/followup-repo-rename.md` and partially
  done already (the GitHub remote was renamed); the in-repo dir
  rename is not gated by this feature.
- **Removing the `deploy/*.sh` scripts immediately** — they stay for
  one release as deprecation-warned forwarders (FR-016, FR-018).
- **OpenClaw platform implementation** — the seam this feature
  exercises proves OpenClaw will plug in cleanly once it lands;
  shipping OpenClaw itself is a separate feature.
- **The runtime `AgentPlatform` rewire** — the voice loop in
  `webrtc/session.py` still imports `HermesBridge` directly (feature
  011 T019 partial, future feature 014). `aivg setup` is the deploy-
  time rewire, not the runtime rewire; they're independent.