# Follow-up: replace `deploy/*.sh` with `aivg setup` (CLI-based, platform-detecting)

**Status**: deferred — proposal recorded; no spec/plan/code yet. Surfaced
during feature-012 post-implementation testing when the existing
`deploy/deploy-local.sh` script was discovered to be broken by the
AIVG rebrand AND structurally Hermes-coupled.
**Owner**: a future feature 013 (or whatever number is next when this
work starts).

## The problem the existing scripts have

`deploy/deploy-local.sh`, `deploy/deploy-to-hermes.sh`,
`deploy/parity-check.sh`, `deploy/rollback.sh`, and the `deploy/plugin/`
shims were written in feature 003 — before constitution v2.0.0 made the
satellite system agent-platform-agnostic. They:

* Live at the **repository top level**, parallel to (not inside) the
  `aivg_core/platforms/` plugin seam.
* Hard-code the Hermes layout: `~/.hermes/hermes-agent/`,
  `~/.hermes/config.yaml`, the `satellite:` block format, the
  `stt.local.model medium → small` tuning, the `streaming.transport:
  auto` config patch, the `hermes gateway restart` command.
* Reference the pre-feature-011 package name `hermes_satellite_adapter`
  in the `cp -R` step and in `deploy/plugin/adapter.py`'s imports — so
  after the feature-011 rename to `satellite_core` and the feature-012
  rename to `aivg_core`, the scripts no longer work.
* Have **no analog for OpenClaw** (or any future agent-platform plugin):
  adding a second supported platform would require a parallel set of
  shell scripts — the exact "per-platform special case in the gateway"
  anti-pattern Principle II forbids, mirrored into the deploy layer.

The right shape is a CLI subcommand that detects the platform and
dispatches to platform-specific install logic that lives **inside**
the plugin seam.

## The proposed shape

```text
pip install aivg               # ships the CLI + every shipped platforms/* plugin
aivg setup                     # detects + installs into the active platform
aivg setup --platform hermes   # explicit platform override
aivg setup --via-skill         # hand off to the agent so the install runs
                               # conversationally via the per-platform skill
aivg setup --preflight         # read-only checks; no mutation
aivg setup --uninstall         # vendor removal + config revert
```

**Detection** lives in `aivg_cli/setup.py` (probes `~/.hermes/hermes-
agent/`, `~/.openclaw/`, env vars, etc.). It picks a platform; **every
platform-specific install step** then lives in
`aivg_core/platforms/<platform>/setup.py` — the same per-platform module
boundary the runtime uses. Example:

```text
aivg_core/platforms/hermes/setup.py
  install(host_paths)   # vendor the plugin, patch config.yaml, install aiortc, restart
  uninstall(host_paths) # the reverse
  preflight(host_paths) # read-only
  via_skill_invocation(host_paths)  # delegate to the Hermes-platform skill
```

The Hermes-platform skill at `skills/hermes-agent/SKILL.md` gains an
example: when the user says "install the AIVG satellite plugin",
the skill shells `aivg setup --platform hermes`. Same shape any other
platform's skill would use.

## What this replaces (and what stays)

Removed (one release after feature 013 lands):

* `deploy/deploy-local.sh`
* `deploy/deploy-to-hermes.sh`
* `deploy/parity-check.sh`
* `deploy/rollback.sh`
* `deploy/plugin/__init__.py`, `adapter.py`, `plugin.yaml` — the
  Hermes-side plugin wrapper. Its logic moves into
  `aivg_core/platforms/hermes/plugin_entrypoint.py`.

Kept:

* The constitution-I post-verify (the "no embedded engines outside the
  bridge" check) — moves into a platform-agnostic test fixture or a
  `aivg setup` post-step.
* The Hermes-platform skill (`skills/hermes-agent/`) — gets a `setup`
  capability documented.
* The historical feature-003 specs — they're archaeology, left intact.

## Decisions worth pinning in the feature-013 spec

1. **Detection precedence** — env var override > `--platform` flag >
   filesystem probe. Conflict surfaces a clear error rather than
   guessing.
2. **Pip distribution mechanics** — does `pip install aivg` package
   the plugin assets, or does `aivg setup` rsync them from the
   installed `aivg_core/` location? (Likely the latter — keeps the
   shim minimal.)
3. **`--via-skill` semantics** — when does the skill drive the install
   itself (calls `aivg setup` under the hood) vs. when does the CLI
   call the skill? Probably "skill is a thin wrapper; CLI does the
   work" — same shape as the existing satellite-management skill.
4. **Backward-compat for `deploy-local.sh`** — one release as a thin
   stub forwarding to `aivg setup --legacy-hermes`, then deletion?
   Or just deletion with a CHANGELOG migration note? (No external
   consumers depend on the shell scripts as far as we know — same
   logic as the Phase-9 shim removal in feature 012.)
5. **Per-platform tuning lives where?** — feature 010's `stt.local.
   model` and `streaming.transport: auto` tweaks are Hermes-specific
   *deploy* concerns, not Hermes-runtime concerns. They belong in
   `aivg_core/platforms/hermes/setup.py`, not in the satellite core.

## Why not now

The user opted to ship features 011/012 first and revisit. Reasonable —
features 011/012 already shipped a substantial AIVG-rebrand effort and
the in-process smoke proved the management plane + CLI works without
the shell scripts being in play. The CLI-deploy work is genuinely a
separate feature with its own design surface (detection, pip
distribution, skill handoff).

## What to do today

1. **Do NOT patch `deploy/*.sh`** — fixing the bash to use `aivg_core`
   would perpetuate the wrong layer. Leave the scripts broken; the
   broken state is a useful forcing-function reminder.
2. **Do NOT run `deploy/*.sh`** for the foreseeable future — they
   won't work post-rebrand and patching them is the deferred work
   above.
3. **In-process smoke** (`python -m aivg_core --dev-fake-bridge` +
   `aivg list / device get / logs follow`) remains the working local-
   test path for AIVG-side work that doesn't need a real Hermes
   gateway.
4. When ready for the real-host loop, open feature 013 with the
   spec sketch above.
