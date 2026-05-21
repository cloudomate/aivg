# Phase 0 Research: `aivg setup` — Platform-Agnostic CLI Deploy

**Feature**: `013-aivg-setup-cli` · **Plan**: [plan.md](./plan.md) ·
**Spec**: [spec.md](./spec.md) · **Date**: 2026-05-20

Each item below states a decision, its rationale (tied to a binding
rule from the spec / constitution / prior features), and the
alternatives considered. No `NEEDS CLARIFICATION` markers remain after
this phase.

---

## R-1. CLI shape — `aivg setup` Typer subcommand, `aivg deploy` alias

**Decision**: Add one Typer command tree under the existing `aivg`
binary:

```text
aivg setup [--platform NAME] [--preflight | --uninstall]
           [--yes] [--force] [--legacy-hermes] [--json]
aivg deploy   # synonym for `aivg setup` (FR-001)
```

Implementation lives in a new `src/aivg_cli/setup.py` module imported
by `src/aivg_cli/cli.py`. The new module **never imports any concrete
platform plugin**; all platform-specific work goes through
`aivg_core.platforms.base.PluginRegistry`.

**Rationale**:

- One subcommand tree keeps the surface flat (no `aivg setup install
  --extra-flag X`); operators see the same usage shape as `aivg
  device command`.
- `aivg deploy` as a synonym (FR-001) reads naturally in scripts
  without forcing a single canonical verb. They map to the same
  function; help text for both points at `aivg setup`.
- The flat mode set (`--preflight | --uninstall | default`) is
  mutually exclusive — Typer enforces it, so an operator can't
  accidentally combine `--preflight` with `--uninstall`.

**Alternatives considered**:

- `aivg setup install / uninstall / preflight` (three subcommands)
  — more nouns, more help screens; no clarity win.
- Hide `--uninstall` under a separate `aivg uninstall` top-level —
  splits the safety story (backup folder is keyed by install run;
  uninstall and install belong together).

---

## R-2. Detection precedence — explicit flag > probe > error

**Decision**: With `--platform <name>`, the CLI uses only that
plugin and surfaces a specific error if `detect()` returns
`is_installed=False`. With no flag, the CLI calls
`detect()` on every shipped plugin in alphabetical order and picks
the platform that reports `is_installed=True`. If multiple plugins
report installed, the CLI refuses (interactive: prompt; `--json`:
`error.code = multiple_platforms_detected`).

**Rationale**:

- Explicit-over-implicit: operator intent wins over heuristic.
- Alphabetical iteration is deterministic and easy to debug. The
  precedence inside `detect()` is each plugin's concern.
- Refusing on ambiguous detection (rather than silently picking
  "hermes" because it's the default) avoids the silent-wrong-host
  failure mode.

**Alternatives considered**:

- Always default to Hermes if multiple detected — surprises any
  future user who installs both.
- Read an env var as a tiebreaker — same problem, layered.
- Probe-then-confirm (interactive in both single-platform and multi-
  platform cases) — annoying when the detection is unambiguous.

---

## R-3. `SetupCapability` Protocol — shape + location

**Decision**: Add a `SetupCapability` Python `Protocol` (PEP-544)
next to the existing `AgentPlatform` Protocol in
`aivg_core/platforms/base.py`. It declares:

```python
class SetupCapability(Protocol):
    name: str            # "hermes" / "openclaw" / ...
    label: str           # "Hermes Agent" / "OpenClaw" (human display)

    def detect(self) -> DetectResult: ...
    def preflight(self, opts: SetupOptions) -> PreflightReport: ...
    def install(self, opts: SetupOptions) -> InstallResult: ...
    def uninstall(self, opts: SetupOptions) -> UninstallResult: ...
```

Companion dataclasses (also in `base.py`):

```python
@dataclass
class DetectResult:
    is_installed: bool
    paths: dict[str, str]      # platform-meaningful paths (venv, config, plugin dir)
    version: str | None
    reasons: list[str]         # human-readable bullets

@dataclass
class SetupOptions:
    yes: bool                  # operator already confirmed
    force: bool                # overwrite hand-edited config etc.
    legacy_hermes: bool        # invoked via deploy-local.sh wrapper

@dataclass
class SetupPhase:
    name: str                  # "detecting" | "preflight" | "vendoring" | ...
    status: str                # "started" | "ok" | "skipped" | "failed"
    detail: dict | None

@dataclass
class InstallResult:
    ok: bool
    phases: list[SetupPhase]
    backup_dir: Path
    rollback_command: str | None
    failure_reason: str | None
```

**Rationale**:

- Same `Protocol` style as `AgentPlatform` (R-15 in feature 011) —
  structural typing means a plugin author doesn't subclass; just
  expose the named methods.
- Phases as first-class objects (not just log strings) means the
  CLI's NDJSON envelope and the agent skill's progress report share
  the same data structure (FR-003 / SC-005).
- `SetupOptions` carries cross-cutting flags the CLI parses once,
  so platforms don't re-parse argv.

**Alternatives considered**:

- Subclass-required ABC — more boilerplate; structural typing
  achieves the same gate via `runtime_checkable`.
- One mega-method `setup(action: str, opts)` — loses type-safety on
  the per-action return shapes.

---

## R-4. Lock file mechanics — `flock` on `~/.aivg/setup.lock`

**Decision**: Single-host mutex via Python `fcntl.flock` (LOCK_EX |
LOCK_NB) on `~/.aivg/setup.lock`. The lock file's content records
the PID + start timestamp + invocation argv (for diagnostics). On
contention, the second invocation refuses with `error.code =
setup_lock_held` and a pointer at the lock file (and the running
PID).

```python
# Sketch
LOCK_PATH = Path("~/.aivg/setup.lock").expanduser()
with open(LOCK_PATH, "w+") as f:
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # → setup_lock_held envelope
        ...
    else:
        f.write(json.dumps({"pid": os.getpid(), "argv": sys.argv, "started_at": time.time()}))
        f.flush()
        try:
            ...
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
```

The lock file is removed at successful end-of-run (clean
`flock(UN)`); if the process is killed, the OS releases the lock so
the file stays but the next invocation can re-acquire (stale lock-
file content is overwritten on re-acquire).

**Rationale**:

- `flock` is stdlib + works on macOS + Linux. Atomic and OS-managed
  so we don't roll our own "is the PID alive?" check.
- Single-host scope is the v1 scope — multi-host SSH deploy is out
  of scope (spec §Out of Scope §1). No distributed lock needed.

**Alternatives considered**:

- Filesystem `mkdir` lock — works but doesn't auto-release on
  crash.
- SQLite advisory lock — overkill; introduces a dep just for
  mutex.
- No lock at all — operator can footgun themselves; SC-008 requires
  the gate.

---

## R-5. Backup format — timestamped folder under `~/.aivg/installs/`

**Decision**: Every install/uninstall run creates a fresh folder at
`~/.aivg/installs/<platform>/<YYYYMMDDTHHMMSSZ>/`. Folder contents:

```text
~/.aivg/installs/hermes/20260520T210000Z/
├── manifest.json          # mode (install/uninstall), opts, started_at, finished_at
├── pre_state.json         # list of pre-existing plugin dirs + their sha256s; sha256 of config.yaml
├── config.yaml.before     # full copy of ~/.hermes/config.yaml at start
├── phases.ndjson          # one line per SetupPhase emitted (chronological)
└── failure_reason.txt     # present only on failure
```

Rollback command surfaced to the operator (and embedded in the
failure-mode envelope):

```bash
aivg setup --restore-backup ~/.aivg/installs/hermes/20260520T210000Z
```

The restore reads `pre_state.json` + `config.yaml.before`, restores
the config, removes any plugin dirs that were not in
`pre_state.json`, and emits its own (smaller) backup folder under
the same convention (a backup-of-the-rollback).

**Rationale**:

- Timestamped folders never overwrite — operator has full
  audit trail.
- Storing per-file sha256s lets uninstall be byte-equivalent (SC-003)
  rather than rely on "remove these names" (which would falsely
  remove an operator-replaced file).
- Backups never deleted by AIVG — that's an operator decision
  (Constraints in plan.md).

**Alternatives considered**:

- Single rolling backup directory — destroys audit trail.
- Compress-on-write (tar.gz) — saves disk but complicates the
  rollback command. Optional v2.
- Git-track the backup — pollutes the operator's repo state; not
  every host has git; backups belong outside the source tree.

---

## R-6. NDJSON phase envelopes — exact shape

**Decision**: Under `--json`, every `aivg setup` invocation emits one
NDJSON envelope per `SetupPhase` transition (`started` → terminal
`ok` / `skipped` / `failed`). The envelope wraps `SetupPhase` in the
existing v1 envelope from feature 011:

```json
{"ok":true,"data":{"phase":"detecting","status":"started"},"error":null,"v":1}
{"ok":true,"data":{"phase":"detecting","status":"ok","detail":{"platform":"hermes","paths":{"venv":"~/.hermes/.../venv"}}},"error":null,"v":1}
{"ok":true,"data":{"phase":"preflight","status":"started"},"error":null,"v":1}
{"ok":true,"data":{"phase":"preflight","status":"ok","detail":{"changes":[...]}},"error":null,"v":1}
{"ok":true,"data":{"phase":"confirming","status":"skipped","detail":{"reason":"--yes passed"}},"error":null,"v":1}
{"ok":true,"data":{"phase":"vendoring","status":"started"},"error":null,"v":1}
...
{"ok":true,"data":{"phase":"done","backup_dir":"~/.aivg/installs/hermes/20260520T210000Z"},"error":null,"v":1}
```

On failure, the last line carries the error envelope shape:

```json
{"ok":false,"data":null,"error":{"code":"<closed_set>","message":"...","phase":"restarting_gateway"},"v":1}
```

**Rationale**:

- The agent skill's progress reporting (FR-014) needs phase-by-
  phase granularity. One envelope per phase × `started/terminal`
  transition is the smallest shape that lets the skill say
  "vendoring complete; restarting gateway".
- Reusing the v1 envelope means no contract bump (FR-019) and
  zero new shape for downstream parsers to learn.
- `phase` in the error envelope's `error` field (not just at the
  top level) means an agent that only logs `error` still gets the
  failed-step name.

**Alternatives considered**:

- One envelope per phase transition (`SetupPhase.status` changes) —
  same shape; redundant given we already emit started/terminal.
- Separate `progress` stream + final `result` envelope — two shapes
  to parse; rejected per "one envelope per output unit" v1 rule.

---

## R-7. Legacy `deploy/*.sh` — bash wrapper shape

**Decision**: Each of the four scripts shrinks to ~10 lines:

```bash
#!/usr/bin/env bash
# Legacy wrapper — deprecated in feature 013. Forwards to `aivg setup`.
# Removed entirely in the release after this one (see
# specs/013-aivg-setup-cli/followup-deploy-shell-removal.md).
set -euo pipefail
printf >&2 'DEPRECATED: %s is replaced by `aivg setup` (feature 013).\n' "$0"
printf >&2 '  This wrapper forwards to: aivg setup --legacy-hermes %s\n' "$*"

case "$0" in
  *deploy-local.sh)      MODE=install ;;
  *deploy-to-hermes.sh)  MODE=install ;;  # SSH path folded into local Hermes setup for v1
  *parity-check.sh)      MODE=parity ;;   # parity gets a `aivg setup --parity-check` flag
  *rollback.sh)          MODE=rollback ;;
esac
case "${1:-}" in
  --preflight)           shift; exec aivg setup --legacy-hermes --preflight "$@" ;;
  --yes)                 shift; exec aivg setup --legacy-hermes --yes "$@" ;;
  *)                     exec aivg setup --legacy-hermes "$@" ;;
esac
```

The `--legacy-hermes` flag tells the Hermes plugin's `setup.py` to:

- Skip the "no platform detected" failure path (assume Hermes; the
  script was Hermes-specific by name).
- Apply the legacy tuning step (`stt.local.model medium→small`,
  `voice.silence_duration 3.0→1.2`) for parity with the old
  script's behavior (Hermes-platform-specific deploy concern;
  matches feature 010's tweaks).
- Preserve the legacy script's exit codes.

**Rationale**:

- One bash shim per script keeps any operator's existing
  invocation working — wrapper preserves argv, exit code, stderr
  notice.
- `--legacy-hermes` is the explicit opt-in for the script's
  Hermes-specific tuning steps; new operators using `aivg setup`
  directly don't get those auto-applied.
- The wrappers themselves count as the only files in the repo that
  may reference `deploy-local.sh`/`deploy-to-hermes.sh` post-feature
  (SC-010 / FR-018).

**Alternatives considered**:

- Hard-delete the scripts now — breaks anyone scripting bash
  against them; one-release window costs ~40 lines of bash.
- Wrapper-as-Python — same effect but adds Python startup
  overhead vs. immediate-exec.

---

## R-8. Hermes `setup.py` — what the four scripts collapse to

**Decision**: `aivg_core/platforms/hermes/setup.py` exposes
`HermesSetupCapability` implementing the four `SetupCapability`
methods. Each absorbs a slice of the existing bash:

| Script | What lands where in `HermesSetupCapability` |
|---|---|
| `deploy-local.sh::preflight` | `.preflight()` — venv check, list pre-existing plugin dirs, find Hermes config |
| `deploy-local.sh::backup` + `vendor` + `add satellite block` + `restart` + `postverify` | `.install()` — split into phases (`backup`, `vendoring`, `config_writing`, `installing_deps`, `restarting_gateway`, `post_verifying`) emitting NDJSON envelopes per R-6 |
| `deploy-local.sh::--no-tune` gate | `SetupOptions.no_tune` boolean from a `--no-tune` CLI flag |
| `deploy-to-hermes.sh` SSH path | Folded into `.install()` with an `SetupOptions.target=<host>` (out of scope for v1; tracked) |
| `parity-check.sh` | `.parity_check()` — a fifth method on `SetupCapability`; surfaced as `aivg setup --parity-check` |
| `rollback.sh` | `.rollback()` — but rollback in v1 is `aivg setup --restore-backup <dir>`, so `rollback.sh` wrapper invokes that |

The Hermes-specific tuning lines (`stt.local.model medium→small`,
`voice.silence_duration 3.0→1.2`) are gated behind
`opts.legacy_hermes=True` so a fresh `aivg setup` operator chooses
their own defaults via the Hermes config (constitution IV — these
are *platform* tuning, not satellite tuning, and live in the plugin).

**Rationale**:

- Direct port — minimal new logic; reduces regression risk.
- Each phase becomes one NDJSON envelope, which the agent skill can
  surface line-by-line.
- The legacy tuning becoming opt-in (vs. default) lets new
  operators see the un-tuned defaults; the wrapper preserves
  legacy-tuned behavior for existing scripts.

**Alternatives considered**:

- Rewrite the bash semantics from scratch in Python — risks
  behavioral drift; the bash is well-tested in feature 010 deploys.
- Keep the bash and have the Python `setup.install()` shell out to
  it — defeats the platform-agnostic goal; reverts to "Python
  calls bash"; constitution-IV fails.

---

## R-9. Per-platform skill `setup` capability — wrapper pattern

**Decision**: Add a new section to `skills/hermes-agent/SKILL.md`
("Setup / install (US3)") and to the analogous OpenClaw skill
(`skills/openclaw/README.md`, noting that OpenClaw doesn't yet have
the underlying plugin support). The Hermes-skill section documents
the protocol:

1. The user expresses install intent ("install the AIVG satellite
   into Hermes", "set up the satellite on this machine", etc).
2. The agent **always** runs `aivg setup --json --preflight` first
   to surface what's about to change.
3. The agent reports the preflight phases to the user and **asks
   for explicit confirmation in chat** ("type 'yes' to proceed").
4. After the user confirms, the agent runs `aivg setup --json
   --yes` and reports each NDJSON envelope's `phase` to the user.
5. On terminal `done`, the agent confirms success and points at
   the backup folder. On terminal `failed`, the agent reports the
   specific failed phase + the documented rollback command from
   the error envelope.

**Rationale**:

- Same shape as the `factory-reset` skill protocol (feature 011
  US5/T080) — chat-side confirmation, CLI-side `--yes`.
- Preflight-before-install is the agent-side analog of the CLI's
  interactive confirmation prompt — the user sees what's about to
  change before consenting.

**Alternatives considered**:

- Agent does install in one shot (`aivg setup --json --yes`) without
  preflight — works but the user doesn't see what's about to
  change; defeats the agent-driven transparency.
- Agent invokes `aivg setup` without `--json` and parses prose —
  fragile.

---

## R-10. Idempotency — re-running install is a no-op-with-summary

**Decision**: `aivg setup` checks for an existing AIVG install by
looking for an "AIVG install marker" inside the Hermes plugins
directory (specifically, a sentinel file
`plugins/platforms/satellite_webrtc/.aivg-install-marker.json`
written by `HermesSetupCapability.install()`). If found, the install
flow:

1. Reports `phase: detecting_prior_install` with the marker's
   contents (timestamp of the prior install, which backup folder
   captured the pre-state).
2. Switches to "idempotent re-vendor" mode: refreshes the plugin
   files (rsync), but **does not** add a second config block, does
   not re-install deps that are already present.
3. On `--force`, ignores the marker and re-runs the full install
   sequence (and creates a fresh backup folder).

**Rationale**:

- Operators frequently re-run install scripts; the failure mode of
  "duplicate config block, gateway restart fails" is exactly what
  the existing bash protected against and the Python port must
  too.
- The marker file is the deterministic, in-band signal — not a
  search through the host for "does this look like AIVG?".

**Alternatives considered**:

- Always re-run everything from scratch — fast but destructive on
  hand-edited config blocks.
- Refuse re-install entirely without `--force` — annoying for the
  common case of "I bumped the AIVG version and want to update".

---

## R-11. Closed `error.code` set — what `aivg setup` adds (FR-020)

**Decision**: Add these to the documented closed set in
`contracts/cli-contract.md`:

| Code | When |
|---|---|
| `no_platform_detected` | `detect()` returned `is_installed=False` for every shipped plugin |
| `multiple_platforms_detected` | More than one plugin's `detect()` returned `is_installed=True`; operator must `--platform <name>` |
| `setup_not_supported_for_platform` | Plugin has no `SetupCapability` (e.g. OpenClaw stub in v1) |
| `setup_lock_held` | `flock` contended; another `aivg setup` running on this host |
| `setup_partial_failure` | Install failed after at least one mutating phase succeeded; backup is intact; rollback command in `error.message` |
| `permission_denied` | Path the install needs to write is not writable by the caller |
| `host_state_drifted` | `--force` not passed AND a marker/config the install expected to find is missing or different (e.g. operator hand-edited the config block) |

Exit codes (extending feature 011 / cli-contract.md):

- `setup_lock_held` → 1 (treat as a "try again" user-input error)
- `setup_partial_failure` → 5 (terminal failure with operator
  follow-up)
- `host_state_drifted` → 1
- `no_platform_detected` → 1
- `permission_denied` → 1
- `setup_not_supported_for_platform` → 1

**Rationale**: each code maps to a unique operator action; collapsing
any pair to a single code (e.g. `no_platform_detected` and
`multiple_platforms_detected` both as `bad_input`) loses the
distinction the agent needs to ask the right follow-up question.

---

## R-12. Constitution alignment — re-check vs v2.0.1

**Decision**: No principle is touched. The feature is the **deploy-
layer realization** of Principle IV — the constitution amendment in
feature 012 widened "Reuse Hermes" to "Reuse the upstream agent
platform"; this feature operationalizes that at the install path.
Every per-platform install detail lives behind the existing plugin
seam. No constitution change in feature 013.

**Verification**: `tests/unit/test_constitution_principles_byte_equiv.py`
(feature 012 T034) stays green; this feature adds no Principle prose
edits.

---

## Open questions deferred to `/speckit-tasks`

None at the spec/plan level. Two implementation-detail items belong
to `/speckit-tasks`:

- Whether `aivg setup --parity-check` ships in v1 (the existing
  `deploy/parity-check.sh` invokes `parity-check.sh "<phrase>"` —
  exact flag shape decided in tasks).
- Whether the rollback flow gets its own subcommand (`aivg setup
  --restore-backup <dir>`) or lives under a sibling
  (`aivg setup rollback <dir>`). Both work; the spec / plan let
  tasks pick the ergonomics.
