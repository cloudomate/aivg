# Quickstart: `aivg setup`

**Feature**: `013-aivg-setup-cli` · **Plan**: [plan.md](./plan.md) ·
**Status**: design — describes the operator experience once the plan
ships. Until tasks land, `aivg setup` does not exist.

## Operator flow — first install on a Hermes host

```bash
# 1. Read-only check; nothing is mutated.
aivg setup --preflight

# Output (human mode): summary of intended changes + any blockers.
# Output (--json):     NDJSON phase envelopes ending with `phase: done`
#                      carrying intended_changes + blockers + warnings.

# 2. Interactive install (CLI prompts for confirmation; type the
#    platform label or 'yes' to proceed).
aivg setup

# 3. Same thing, scripted (no prompt; CI-friendly).
aivg setup --yes

# 4. Force a re-install over an existing AIVG marker (idempotency
#    override; creates a fresh backup folder).
aivg setup --yes --force
```

After step 2/3/4, the operator has:

* The plugin vendored under
  `~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`
  (Hermes example; OpenClaw will vendor into its own analog).
* An `aivg:` block in `~/.hermes/config.yaml` (sentinel comment
  marks the block as AIVG-owned).
* `aiortc` installed in the Hermes venv if it was missing.
* The Hermes gateway restarted and verified listening on
  `8643`/`8644`.
* A backup of the pre-install state at
  `~/.aivg/installs/hermes/<YYYYMMDDTHHMMSSZ>/` — referenced in the
  terminal `done` envelope.

## Operator flow — uninstall

```bash
# Read-only: what would be removed?
aivg setup --preflight --uninstall

# Mutating; same confirmation discipline.
aivg setup --uninstall --yes

# After this, the host is byte-equivalent to its pre-install state
# (modulo the install/uninstall log entries themselves), and the
# pre-existing platform plugins are untouched.
```

## Operator flow — rollback after a partial-failure install

```bash
# A failed install emits an error envelope like:
# {"ok":false, "error":{"code":"setup_partial_failure",
#  "message":"vendoring ok; config_writing failed; rollback: aivg setup --restore-backup ~/.aivg/installs/hermes/20260520T210000Z",
#  "phase":"config_writing"}, "v":1}

# Restore the host to its pre-install state.
aivg setup --restore-backup ~/.aivg/installs/hermes/20260520T210000Z --yes
```

## Operator flow — explicit platform selection

```bash
# Force the Hermes plugin even if openclaw also reports installed
# (useful when both are present on the same host).
aivg setup --platform hermes --yes

# Inverse: install into OpenClaw (returns setup_not_supported_for_platform
# in v1 because the OpenClaw plugin is a stub).
aivg setup --platform openclaw
```

## Legacy `deploy/*.sh` users — one-release compat

```bash
# The old scripts still work; they emit a stderr deprecation notice
# and forward to `aivg setup --legacy-hermes`. The release after this
# one removes them entirely.
bash deploy/deploy-local.sh --preflight
# DEPRECATED: deploy/deploy-local.sh is replaced by `aivg setup`...
# ...preflight runs identically to `aivg setup --preflight`.

bash deploy/deploy-local.sh --yes
# Same as `aivg setup --legacy-hermes --yes`.
```

## Hermes agent (chat-driven)

User: *"install the AIVG satellite into Hermes."*

Agent flow (drives `aivg setup` per US3, R-9):

1. Runs `aivg setup --json --preflight`, reports the intended
   changes to the user.
2. Asks the user in chat: "Confirm by typing 'yes' to proceed."
3. After explicit user consent, runs
   `aivg setup --json --yes`, reports each NDJSON phase envelope as
   "Vendoring plugin... ok. Restarting gateway... ok. Done.
   Backup at ~/.aivg/installs/hermes/20260520T210000Z."
4. On failure, surfaces the specific `phase` + `error.message` from
   the terminal envelope, including the documented rollback
   command.

## Adding a new platform — what a plugin author does

```text
aivg_core/platforms/openclaw/
├── __init__.py              # (existing) exposes PLATFORM stub
└── setup.py                 # NEW — implements SetupCapability for OpenClaw
```

That's the whole change. The CLI, the agent skill, the contract docs,
and the test fixtures stay the same. Adding OpenClaw setup is a
plugin-author task; no satellite-core PR is needed.

## What's deliberately not in v1

- **Remote/SSH deploy** — `aivg setup` is local-host-only in v1.
  The legacy `deploy-to-hermes.sh` SSH path is folded into the
  local Hermes plugin's setup so existing scripts work; a new
  feature handles real SSH/cloud install.
- **Installing the agent platform itself** — `aivg setup` installs
  AIVG INTO an installed Hermes/OpenClaw, not the platform.
- **Service-supervisor management** — `aivg setup` invokes the
  platform's existing restart command; doesn't install systemd
  units, launchd plists, etc.
- **The runtime `AgentPlatform` rewire** — feature 011 T019 / future
  feature 014. `aivg setup` is the **deploy-layer** Principle IV
  realization; the runtime-layer rewire is separate.
