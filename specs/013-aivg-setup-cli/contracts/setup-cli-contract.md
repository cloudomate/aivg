# Contract: `aivg setup` — CLI surface

**Feature**: `013-aivg-setup-cli` · **Plan**: [../plan.md](../plan.md) ·
**Version**: 1.0.0 (additive to the feature 011 / 012 CLI contract;
no `aivg --contract-version` bump)

`aivg setup` is the platform-agnostic host-install operator surface.
Its **JSON envelope** and **exit-code semantics** are byte-equivalent
to the existing CLI contract (cli-contract.md from feature 011) — this
contract only documents the **additive surface**.

## Subcommand tree

```text
aivg setup [--platform NAME]
           [--preflight | --uninstall | --restore-backup PATH | --parity-check]
           [--yes] [--force] [--legacy-hermes] [--no-tune]
           [--phrase PHRASE]               # only with --parity-check

aivg deploy  # exact synonym for `aivg setup` (FR-001)
```

### Flags

| Flag | Meaning | Mutually exclusive with |
|---|---|---|
| `--platform NAME` | Force a specific plugin (e.g. `hermes`, `openclaw`). Without it the CLI probes. | — |
| `--preflight` | Read-only mode. Run detection + preflight; emit "intended changes" envelope; **do not mutate**. | `--uninstall`, `--restore-backup`, `--parity-check` |
| `--uninstall` | Remove an existing AIVG install (the inverse of default install). | `--preflight`, `--restore-backup`, `--parity-check` |
| `--restore-backup PATH` | Replay the pre-state captured at `PATH` (a `~/.aivg/installs/.../` folder). | `--preflight`, `--uninstall`, `--parity-check` |
| `--parity-check` | Compare a Hermes-spoken phrase against what the operator typed (legacy `parity-check.sh` analog). Requires `--phrase`. | `--preflight`, `--uninstall`, `--restore-backup` |
| `--yes` / `-y` | Skip the destructive-action confirmation prompt. Required under `--json` for any mutating operation. | — |
| `--force` | Re-run install over an existing AIVG marker; overwrite hand-edited config blocks. | — |
| `--legacy-hermes` | Apply Hermes-specific legacy tuning (`stt.local.model medium→small`, `voice.silence_duration 3.0→1.2`). Set automatically when invoked via the deprecation-warned wrappers; new operators should set it explicitly only if they want feature-010-deployed defaults. | — |
| `--no-tune` | Inverse of `--legacy-hermes` in the legacy script — explicitly skip the Hermes tuning step (default behavior under fresh `aivg setup`). | `--legacy-hermes` |
| `--phrase PHRASE` | Required when `--parity-check`. The phrase the operator spoke into the satellite. | — |

## Phases (NDJSON envelope under `--json`)

Every invocation emits zero or more **phase envelopes** on stdout
(one per `SetupPhase` start AND terminal transition), then exactly
one **terminal envelope** (`phase=done` or `phase=failed`).

### Phase set per mode

| Mode | Phase order |
|---|---|
| default install | `detecting` → `preflight` → `confirming` → `backup` → `vendoring` → `config_writing` → `installing_deps` → `restarting_gateway` → `post_verifying` → `done` \| `failed` |
| `--preflight` | `detecting` → `preflight` → `done` \| `failed` (no `confirming`; no mutation phases) |
| `--uninstall` | `detecting` → `preflight` → `confirming` → `backup` → `uninstall_vendor` → `uninstall_config` → `uninstall_restart` → `post_verifying` → `done` \| `failed` |
| `--restore-backup PATH` | `preflight` → `confirming` → `restoring` → `restarting_gateway` → `post_verifying` → `done` \| `failed` |
| `--parity-check` | `parity_check` → `done` \| `failed` |

### Envelope shape

Reuses the v1 envelope from the feature-011 CLI contract:

```json
{"ok":true,"data":{"phase":"<name>","status":"<started|ok|skipped|failed>","detail":{...}},"error":null,"v":1}
```

On terminal failure:

```json
{"ok":false,"data":null,"error":{"code":"<closed-set>","message":"...","phase":"<failed-phase>"},"v":1}
```

### Terminal `done` envelope (install / uninstall / rollback)

```json
{"ok":true,"data":{
  "phase":"done",
  "platform":"hermes",
  "backup_dir":"~/.aivg/installs/hermes/20260520T210000Z",
  "rollback_command":"aivg setup --restore-backup ~/.aivg/installs/hermes/20260520T210000Z"
},"error":null,"v":1}
```

### Terminal `done` envelope (preflight)

```json
{"ok":true,"data":{
  "phase":"done",
  "platform":"hermes",
  "intended_changes":[
    "vendor plugin to ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/",
    "add aivg: block to ~/.hermes/config.yaml",
    "install aiortc into ~/.hermes/hermes-agent/venv/",
    "restart Hermes gateway"
  ],
  "blockers":[],
  "warnings":["satellite: config block already present (will be re-written under --force)"]
},"error":null,"v":1}
```

## Closed `error.code` set (added by this feature)

Joining the feature-011 closed set. Adding new codes is a minor bump
of this contract; removing or renaming is a major bump.

| Code | Trigger | Exit code |
|---|---|---|
| `no_platform_detected` | Every shipped plugin's `detect()` returned `is_installed=False` | `1` |
| `multiple_platforms_detected` | More than one plugin reports installed; operator must `--platform <name>` | `1` |
| `setup_not_supported_for_platform` | Plugin has no `SetupCapability` (e.g. OpenClaw stub) | `1` |
| `setup_lock_held` | Another `aivg setup` is already running on this host | `1` |
| `setup_partial_failure` | Install failed after at least one mutating phase succeeded; backup intact; rollback command in `error.message` | `5` |
| `permission_denied` | Path the install needs to write is not writable | `1` |
| `host_state_drifted` | `--force` not passed AND a marker/config the install expected is missing or different | `1` |

## Exit codes (no change to feature-011 mapping)

`0` ok · `1` user-input / state-drift / unknown / limit / lock-held · `2` device offline (unused by setup) · `3` gateway unreachable (rare; surfaces if `post_verifying` can't reach the management plane) · `4` BLE/Improv (unused by setup) · `5` `setup_partial_failure` and similar terminal failures with operator follow-up.

## Help / version expectations

- `aivg setup --help` documents every flag listed above with stable
  wording (the help text is part of the contract insofar as flag
  names are stable through v1.x).
- `aivg --version` and `aivg --contract-version` are **unchanged** —
  this feature is additive (FR-019, SC-007).

## Non-goals

- **No remote-host install** in v1 — `aivg setup` only operates on
  the local host. (Out of scope §1.) Future feature for SSH/cloud.
- **No agent-platform install** — `aivg setup` installs the AIVG
  plugin INTO an already-installed agent platform; it does not
  install Hermes/OpenClaw itself.
- **No service-supervisor management** — `aivg setup` invokes the
  platform's own restart command; it does not install systemd
  units, launchd plists, or analogous.

## Versioning

This contract shares the v1.0.0 semver of the feature-011 cli-contract.
A breaking change here is a coordinated CLI-contract bump. Adding new
flags / new `error.code` values is minor (additive).
