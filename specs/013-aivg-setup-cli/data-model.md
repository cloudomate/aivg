# Data Model: `aivg setup`

**Feature**: `013-aivg-setup-cli` · **Plan**: [plan.md](./plan.md) ·
**Date**: 2026-05-20

This feature is a CLI subcommand + plugin-layer interface; the "data
model" here is the **types crossing the boundaries**:

1. The `SetupCapability` Protocol every plugin implements.
2. Its companion dataclasses (`DetectResult`, `SetupOptions`,
   `SetupPhase`, `InstallResult`, `UninstallResult`).
3. The on-disk backup format under `~/.aivg/installs/`.
4. The lock-file shape at `~/.aivg/setup.lock`.

No new runtime entities (no new dataclass added to `aivg_core.models`).

## 1. `SetupCapability` Protocol

Lives at `src/aivg_core/platforms/base.py` next to the existing
`AgentPlatform` Protocol. A plugin can implement zero, one, or both —
runtime-only plugins skip `SetupCapability`; deploy-aware plugins
implement it.

```python
from typing import Protocol, runtime_checkable


@runtime_checkable
class SetupCapability(Protocol):
    name: str       # stable identifier, e.g. "hermes" — matches the plugin folder
    label: str      # human display name, e.g. "Hermes Agent"

    def detect(self) -> DetectResult: ...
    def preflight(self, opts: SetupOptions) -> PreflightReport: ...
    def install(self, opts: SetupOptions) -> InstallResult: ...
    def uninstall(self, opts: SetupOptions) -> UninstallResult: ...

    # Optional: only the Hermes plugin needs this in v1.
    def parity_check(self, opts: SetupOptions, *, phrase: str) -> ParityCheckResult: ...
    def rollback(self, opts: SetupOptions, *, backup_dir: Path) -> RollbackResult: ...
```

### Discovery

`aivg_cli/setup.py` resolves the active `SetupCapability` via
`aivg_core.platforms.base.PluginRegistry.load_setup_capability(name)`
— a new sibling to `load_platform()`. The loader:

1. Imports `aivg_core.platforms.<name>`.
2. Looks for `SETUP = HermesSetupCapability()` (or equivalent) at
   the module's top level.
3. If absent: raises `RuntimeError("setup_not_supported_for_platform")`
   — the CLI maps this to `error.code = setup_not_supported_for_platform`.

A plugin without runtime support (no `PLATFORM` attribute) but with
install support (has `SETUP`) is permitted; runtime and setup are
independent capabilities.

## 2. Companion dataclasses

```python
@dataclass
class DetectResult:
    is_installed: bool
    paths: dict[str, str] = field(default_factory=dict)   # e.g. {"venv": "~/.hermes/.../venv", "config": "~/.hermes/config.yaml"}
    version: str | None = None
    reasons: list[str] = field(default_factory=list)      # bullets for the operator/agent


@dataclass
class SetupOptions:
    yes: bool = False
    force: bool = False
    legacy_hermes: bool = False
    no_tune: bool = False
    json_mode: bool = False
    extra: dict[str, Any] = field(default_factory=dict)   # plugin-specific overrides (e.g. --parity-phrase)


@dataclass
class SetupPhase:
    name: str           # one of: detecting | preflight | confirming | backup | vendoring |
                        # config_writing | installing_deps | restarting_gateway | post_verifying |
                        # uninstall_vendor | uninstall_config | uninstall_restart | done | failed
    status: str         # started | ok | skipped | failed
    detail: dict[str, Any] | None = None


@dataclass
class PreflightReport:
    ok: bool                            # are all checks green?
    intended_changes: list[str]         # one bullet per file/config the install would touch
    blockers: list[str]                 # failure-blocking checks (venv missing, perms, etc.)
    warnings: list[str]                 # non-blocking notes (e.g. "config block already present")


@dataclass
class InstallResult:
    ok: bool
    phases: list[SetupPhase]
    backup_dir: Path | None
    rollback_command: str | None
    failure_phase: str | None
    failure_reason: str | None


@dataclass
class UninstallResult:
    ok: bool
    phases: list[SetupPhase]
    removed: list[str]                  # filesystem paths actually removed
    config_changes: list[str]           # config block edits applied
    failure_reason: str | None


@dataclass
class ParityCheckResult:                # used by the legacy `parity-check.sh` wrapper
    ok: bool
    expected: str
    observed: str
    notes: list[str]


@dataclass
class RollbackResult:
    ok: bool
    restored_files: list[str]
    new_backup_dir: Path                # backup-of-the-rollback (always created)
```

### Phase set (closed)

Every `aivg setup` invocation emits envelopes drawn from this fixed
set; clients can rely on it:

```text
detecting
  → preflight
  → confirming (skipped under --yes)
  → vendoring
  → config_writing
  → installing_deps
  → restarting_gateway
  → post_verifying
  → done | failed

uninstall_*   variant set (preflight → confirming → backup → uninstall_vendor
              → uninstall_config → uninstall_restart → post_verifying → done | failed)

parity_check  (single phase; ok|failed only)
rollback      (preflight → restoring → restarting_gateway → post_verifying → done | failed)
```

## 3. On-disk backup format

`~/.aivg/installs/<platform>/<UTC-timestamp>/`:

```text
manifest.json:
  {
    "feature": "013-aivg-setup-cli",
    "mode": "install" | "uninstall" | "rollback",
    "platform": "hermes",
    "started_at": 1779263327.5,
    "finished_at": 1779263428.1,
    "opts": { "yes": true, "force": false, "legacy_hermes": false, "no_tune": false },
    "result": "ok" | "failed",
    "failure_phase": null
  }

pre_state.json:
  {
    "config_file": "~/.hermes/config.yaml",
    "config_sha256": "ab12...",
    "plugin_dirs": {
      "google_chat": "<sha256-of-tarball>",
      "irc": "<sha256-of-tarball>",
      ...
    },
    "aivg_install_marker_present": false
  }

config.yaml.before:
  <verbatim copy of the config at install time>

phases.ndjson:
  <one SetupPhase JSON per line, chronological>

failure_reason.txt:
  <free-text; present only on failure>
```

### Backup retention

- AIVG **never deletes** a backup folder. Operator owns cleanup.
- The folder name is the `YYYYMMDDTHHMMSSZ` UTC timestamp — sortable;
  no collisions.
- Successful uninstall produces its own backup folder (under
  `~/.aivg/installs/<platform>/<ts>/` with `mode: "uninstall"`).

## 4. Lock-file format

`~/.aivg/setup.lock` — held exclusively (`flock LOCK_EX | LOCK_NB`)
for the duration of any `aivg setup` invocation. Its content is
metadata for diagnostics:

```json
{
  "pid": 49371,
  "argv": ["aivg", "setup", "--yes"],
  "started_at": 1779263327.5,
  "host": "yashs-mbp"
}
```

Content is rewritten on every acquire. Stale content from a crashed
process is harmless because the OS releases the `flock`; the next
invocation acquires fresh.

## 5. Validation summary

| Rule | Where enforced | Test |
|---|---|---|
| `SetupCapability` Protocol satisfied | `PluginRegistry.load_setup_capability` (structural `isinstance` check) | `tests/contract/test_setup_cli.py` |
| Detection precedence (explicit > probe > error) | `aivg_cli/setup.py` | `tests/contract/test_setup_cli.py` (multi-detect → 409) |
| Lock held during mutation | `aivg_cli/setup.py` | `tests/integration/test_setup_lock.py` |
| Backup created BEFORE first mutation | `HermesSetupCapability.install` | `tests/integration/test_setup_fault_injection.py` |
| Uninstall byte-equivalent to pre-install | sha256-walk in `uninstall.post_verify` | `tests/integration/test_setup_lifecycle.py` (SC-003) |
| Preflight is read-only | filesystem diff before/after | `tests/integration/test_setup_lifecycle.py` (SC-002) |
| New `error.code` in closed set | match against [contracts/setup-cli-contract.md](./contracts/setup-cli-contract.md) | extension to `tests/unit/test_cli_help_contract.py` |
| `aivg --contract-version == "1.0.0"` | unchanged | `tests/contract/test_rebrand_invariants.py` |
