# Contract: `SetupCapability` — per-platform install interface

**Feature**: `013-aivg-setup-cli` · **Plan**: [../plan.md](../plan.md) ·
**Version**: 1.0.0

`SetupCapability` is the **deploy-layer** sibling of the runtime
`AgentPlatform` Protocol from feature 011. A plugin can implement
either, neither, or both:

| Plugin capability | Implements |
|---|---|
| Runtime only (the voice loop talks to this plugin) | `AgentPlatform` |
| Setup only (`aivg setup` can install AIVG into this platform; runtime is somebody else's problem) | `SetupCapability` |
| Both (the canonical case — Hermes is here) | both |

## Where it lives

```text
aivg_core/platforms/
├── base.py                      # holds the Protocol + companion dataclasses (data-model.md §2)
├── hermes/
│   ├── __init__.py              # `PLATFORM` (runtime) AND `SETUP` (this contract)
│   ├── bridge.py                # runtime
│   ├── setup.py                 # `HermesSetupCapability` — absorbs deploy/*.sh logic
│   └── plugin_entrypoint/       # what `install()` vendors into the Hermes plugins/ dir
│       ├── __init__.py
│       ├── adapter.py
│       └── plugin.yaml
└── openclaw/
    ├── __init__.py              # `PLATFORM` stub; no `SETUP` (returns setup_not_supported_for_platform)
    └── setup.py                 # optional; stub raising NotImplementedError
```

## The Protocol

```python
from typing import Protocol, runtime_checkable
from pathlib import Path


@runtime_checkable
class SetupCapability(Protocol):
    name: str            # plugin id; matches the folder name
    label: str           # human display

    # Detection — read-only; called before any mutation.
    def detect(self) -> DetectResult: ...

    # Preflight — read-only; lists the intended changes + blockers.
    def preflight(self, opts: SetupOptions) -> PreflightReport: ...

    # Install — mutating. MUST emit one SetupPhase per significant
    # action (consumed by the CLI as NDJSON under --json). MUST be
    # rollback-safe: if any phase fails, the operator can invoke
    # `aivg setup --restore-backup <backup_dir>` to revert.
    def install(self, opts: SetupOptions) -> InstallResult: ...

    # Uninstall — mutating; the inverse of install. MUST leave
    # pre-existing platform plugins (logged in pre_state.json) intact.
    def uninstall(self, opts: SetupOptions) -> UninstallResult: ...

    # OPTIONAL methods (Hermes in v1):
    def parity_check(self, opts: SetupOptions, *, phrase: str) -> ParityCheckResult: ...
    def rollback(self, opts: SetupOptions, *, backup_dir: Path) -> RollbackResult: ...
```

## Plugin rules (binding)

1. **No global side effects on import**. Importing
   `aivg_core.platforms.hermes.setup` MUST NOT touch the filesystem,
   start a subprocess, or modify any host state. All mutation happens
   inside the four methods, only when the CLI calls them with
   `opts.yes=True` (or the user has confirmed interactively).
2. **`detect()` is read-only and idempotent**. May be called many
   times per session (preflight + install both call it). Returns
   `DetectResult` (see data-model.md §2).
3. **`preflight()` is read-only and complete**. Its
   `intended_changes` list MUST enumerate every host-side change
   `install()` would make — so an operator/agent reading the
   preflight envelope sees exactly what's about to happen.
4. **`install()` MUST capture a backup BEFORE any mutating phase**.
   The first phase emitted is `backup` (status=started, then
   status=ok with `backup_dir`); subsequent phases reference that
   directory in their `detail`. (FR-011 / SC-009.)
5. **Phase names are drawn from the closed set** in
   data-model.md §2 → "Phase set". A plugin may emit additional
   `detail` per phase but MUST NOT invent new phase names — clients
   key off the set.
6. **`uninstall()` removes only what `install()` created** —
   referencing the per-install backup's `pre_state.json` to
   distinguish AIVG artifacts from pre-existing platform state
   (FR-012 / SC-003).
7. **Errors are typed**. A method raises one of the documented
   `error.code` values (R-11) wrapped as `SetupError(code,
   message)`; the CLI catches and maps to the JSON envelope. Naked
   exceptions surface as `setup_partial_failure`.

## Plugin marker file

After a successful `install()`, the plugin MUST write a marker
inside the vendored plugin folder so a re-run of `aivg setup`
detects the prior install (R-10):

```text
<platform-plugin-dir>/satellite_webrtc/.aivg-install-marker.json
{
  "feature": "013-aivg-setup-cli",
  "installed_at": 1779263428.1,
  "installed_by_aivg_version": "0.3.0",
  "backup_dir": "~/.aivg/installs/hermes/20260520T210000Z",
  "platform": "hermes"
}
```

The marker is a vendoring concern; the satellite plugin source itself
ignores it.

## Versioning

This contract shares the v1.0.0 semver of the feature-011
`agent-platform.md` contract. Adding methods to `SetupCapability` is
minor (existing plugins that don't implement the new method continue
to work — they're optional methods); removing methods is major.
