# Implementation Plan: `aivg setup` — Platform-Agnostic CLI Deploy

**Branch**: `013-aivg-setup-cli` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/013-aivg-setup-cli/spec.md`
**Constitution**: v2.0.1 (no amendment in this feature)

## Summary

Replace the four host-coupling shell scripts at `deploy/*.sh` with a
single Typer subcommand on the existing CLI: `aivg setup` (alias `aivg
deploy`). The CLI detects the installed agent platform on the host
and dispatches install/uninstall/preflight to that platform's plugin
module — keeping every Hermes-specific (or future OpenClaw-specific)
deploy detail behind the constitution-v2.0.0 `AgentPlatform` seam.
The Hermes plugin gets a new `setup.py` module that absorbs the four
shell scripts' logic verbatim (backup-first, idempotent, rollback-
safe, post-verify). The Hermes-platform agent skill gets a `setup`
capability that shells through the same CLI with the same destructive-
action confirmation discipline the rest of the skill already follows.

The four shell scripts stay for one release as **thin
deprecation-warned forwarders** to `aivg setup --legacy-hermes [...]`
(same compat pattern features 011 and 012 used). The
`deploy/plugin/{__init__.py, adapter.py, plugin.yaml}` Hermes-side
shim folder moves under `aivg_core/platforms/hermes/plugin_entrypoint/`
so it travels with the plugin and `aivg setup` vendors the contents.

The whole feature is **additive to the CLI surface**:
`aivg --contract-version` remains `1.0.0`; every new `error.code` is
documented in the closed set; the existing JSON envelope shape is
unchanged.

## Technical Context

**Language/Version**: Python 3.11 (existing).

**Primary Dependencies**: no new runtime deps. All install logic uses
stdlib (`pathlib`, `shutil`, `subprocess`, `os`, `tempfile`, `fcntl`
for the lock file, `tomllib` for any TOML reads, `yaml` already in the
project for `~/.hermes/config.yaml` patching). The agent platform's
package installer (e.g. `uv` for Hermes) is invoked via `subprocess`
exactly as the existing shell scripts do.

**Storage**: `~/.aivg/state.json` (feature 011 persistence) is
unchanged; this feature adds:

- `~/.aivg/installs/<platform>/<timestamp>/` — per-install backup
  folder (config-file copy, list of pre-existing plugins, capture of
  modified files). One directory per install attempt; never
  overwritten; operator-visible rollback referent.
- `~/.aivg/setup.lock` — a flock-based mutex file held for the
  duration of an install/uninstall; second invocation refuses with
  `setup_lock_held`.

**Testing**: pytest (existing). New tests:

- `tests/contract/test_setup_cli.py` — Typer command shape; flag/help
  contract.
- `tests/integration/test_setup_lifecycle.py` — preflight is byte-
  equivalent read-only; install + uninstall is byte-equivalent on
  the host (SC-002, SC-003) — driven against a fake platform under
  `tests/fixtures/platforms/echo/setup.py`.
- `tests/integration/test_setup_lock.py` — concurrent invocations
  refuse with `setup_lock_held` (SC-008).
- `tests/integration/test_setup_fault_injection.py` — kill the
  gateway-restart step; backup is intact; documented rollback path
  restores byte-equivalence (SC-009).
- `tests/unit/test_legacy_deploy_wrapper.py` — each of the four
  `deploy/*.sh` wrappers emits one stderr deprecation notice and
  preserves the exit code (SC-006).
- Extension to `tests/unit/test_cli_help_contract.py` — `aivg setup`
  + `aivg deploy` synonyms; the new closed-set `error.code` values
  documented.
- Extension to `tests/unit/test_no_legacy_branding.py` /
  `tests/contract/test_rebrand_invariants.py` — no new code
  references `deploy-local.sh` / `deploy-to-hermes.sh` outside the
  wrappers themselves (SC-010).

**Target Platform**: macOS or Linux. The current shell scripts work
on both; the Python port inherits the same coverage.

**Project Type**: Single Python repo; CLI + per-platform plugin
extension. Same shape as features 011 and 012.

**Performance Goals**:

- `aivg setup --yes` end-to-end ≤ **2 minutes** on a typical
  developer laptop with Hermes already installed (SC-001).
- `aivg setup --preflight` returns in ≤ **5 seconds** (read-only;
  filesystem + venv probes only).

**Constraints**:

- **`aivg --contract-version` MUST stay `1.0.0`** (FR-019 / SC-007).
  This feature is additive at the CLI surface; the binding-gate test
  `tests/contract/test_rebrand_invariants.py` enforces this.
- **No platform-specific imports outside `aivg_core/platforms/`**
  (constitution v2.0.0 Principle IV). `aivg_cli/setup.py` reaches
  platforms only through `aivg_core.platforms.base.PluginRegistry`.
- **Destructive-confirm discipline** (feature 011 FR-019): every
  host-mutating step requires either an interactive prompt or
  `--yes`. Under `--json` without `--yes`, the CLI refuses with
  `error.code = bad_input`.
- **One-release compat window** for the four `deploy/*.sh` scripts.
  The release after this one removes them entirely (tracked in a
  follow-up doc, T-LATE in tasks.md).
- **Backups never deleted automatically.** Operator owns cleanup of
  `~/.aivg/installs/<platform>/<timestamp>/` directories. AIVG only
  appends; never prunes.

**Scale/Scope**: Single-host install. Multi-host (SSH) deploy is
**out of scope** for v1 (Out of Scope §6 in spec); the legacy
`deploy-to-hermes.sh` SSH path is collapsed into the local Hermes
plugin setup for this feature and tracked as a future feature.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against **v2.0.1** (the active version after feature 012).
**Status: PASS, no violations.**

| Principle | Check | Status |
|---|---|---|
| I. Thin Satellite | `aivg setup` is a deploy-time CLI subcommand; touches no STT/TTS/agent engine; tests/unit/test_no_embedded_engines.py is unaffected. | ✅ PASS |
| II. Generic Four-Plane Contract | The CLI subcommand is platform-neutral; per-platform install logic dispatched via the plugin seam. No `device_type` branching introduced. | ✅ PASS |
| III. Separate Control/Voice Connections | Unchanged. `aivg setup` doesn't touch the runtime control or voice planes. | ✅ PASS |
| IV. Reuse Upstream Agent Platform (v2.0.0) | **The feature operationalizes Principle IV in the deploy layer.** Every Hermes-specific detail (plugin-dir layout, config-block format, `hermes gateway restart`, aiortc install) lives in `aivg_core/platforms/hermes/setup.py`. A new platform = a new `platforms/<name>/setup.py`, no top-level changes. | ✅ PASS |
| V. Research-Backed | Each design decision in Phase 0 cites a binding constraint: detection precedence (FR-005/6), lock-file mechanics (SC-008), backup format (FR-011, SC-009), legacy-wrapper shape (FR-016, SC-006). | ✅ PASS |

No violations → **Complexity Tracking table empty.**

## Project Structure

### Documentation (this feature)

```text
specs/013-aivg-setup-cli/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── setup-cli-contract.md     # `aivg setup` flags / phases / error codes / exit codes
│   └── platform-setup.md         # PlatformSetup Protocol every plugin's setup.py implements
├── checklists/
│   └── requirements.md
└── tasks.md                       # /speckit-tasks output (NOT created here)
```

### Source code touchpoints

```text
hermes-voice/
├── src/
│   ├── aivg_cli/
│   │   ├── cli.py                          # add `aivg setup` + `aivg deploy` alias Typer command
│   │   └── setup.py                        # NEW — Typer subcommand impl; reads PluginRegistry; no platform imports
│   └── aivg_core/
│       ├── platforms/
│       │   ├── base.py                     # extend: SetupCapability Protocol + DetectResult / PreflightReport / InstallResult dataclasses
│       │   ├── hermes/
│       │   │   ├── __init__.py
│       │   │   ├── bridge.py
│       │   │   └── setup.py                # NEW — Hermes-specific install logic absorbed from deploy/*.sh
│       │   │   └── plugin_entrypoint/      # NEW — contents moved from deploy/plugin/
│       │   │       ├── __init__.py
│       │   │       ├── adapter.py
│       │   │       └── plugin.yaml
│       │   └── openclaw/
│       │       └── setup.py                # NEW — stub raising setup_not_supported_for_platform
│       └── persistence.py                  # extend: ~/.aivg/installs/<platform>/<timestamp>/ helpers + lock file
├── deploy/
│   ├── deploy-local.sh                     # → thin wrapper: stderr notice + `aivg setup --legacy-hermes`
│   ├── deploy-to-hermes.sh                 # → thin wrapper
│   ├── parity-check.sh                     # → thin wrapper
│   ├── rollback.sh                         # → thin wrapper
│   └── plugin/                             # the contents move to aivg_core/platforms/hermes/plugin_entrypoint/;
│                                            # deploy/plugin/ becomes a README stub pointing at the new location
├── skills/
│   ├── hermes-agent/SKILL.md               # add a "Setup" example section
│   └── openclaw/README.md                  # note: setup not implemented; lookup error.code
└── tests/
    ├── contract/test_setup_cli.py          # NEW
    ├── integration/test_setup_lifecycle.py # NEW
    ├── integration/test_setup_lock.py      # NEW
    ├── integration/test_setup_fault_injection.py # NEW
    ├── unit/test_legacy_deploy_wrapper.py  # NEW
    ├── unit/test_cli_help_contract.py      # extend (4 lines)
    └── fixtures/platforms/echo/setup.py    # NEW — proves SC-004 (new platform = no core change)
```

**Structure Decision**: the existing two-package layout
(`aivg_core` + `aivg_cli`) is preserved verbatim — this feature
adds files only inside the established directories. The four
`deploy/*.sh` scripts shrink to deprecation-warned bash wrappers
(each ≈10 lines); the `deploy/plugin/` Python shim moves under the
Hermes plugin so it travels with whatever the plugin vendors.

The `SetupCapability` Protocol is added to `aivg_core/platforms/
base.py` next to the existing `AgentPlatform` Protocol — they're
companions, not the same thing: a plugin can be runtime-only
(implements `AgentPlatform`) or runtime + deploy-aware (implements
both). The CLI loads only `SetupCapability` for `aivg setup`, never
the runtime `AgentPlatform` — keeping the deploy path light.

## Complexity Tracking

> No constitution violations → no complexity to justify.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
