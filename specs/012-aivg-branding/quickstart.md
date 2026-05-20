# Quickstart: AIVG Rebrand

**Feature**: `012-aivg-branding` · **Plan**: [plan.md](./plan.md) ·
**Status**: design — describes the contributor experience *after* this
feature ships.

## After pulling — what changed for a contributor

```bash
git pull
pip install -e .   # picks up the renamed entry point
which aivg         # new binary
which sat-cli      # still works for one release (DeprecationWarning on stderr)
```

### Imports

```python
# Preferred (after this feature):
from aivg_core import models, registry
from aivg_cli.cli import app

# Still works for one release (with one DeprecationWarning per process):
from satellite_core import models, registry
from sat_cli.cli import app

# Two-hop legacy (kept from feature 011):
from hermes_satellite_adapter import models  # warns once, forwards through both shims
```

### CLI

```bash
aivg --version            # JSON envelope: {"data":{"version":"…","contract_version":"1.0.0"}, …}
aivg list
aivg device get kitchen
aivg logs kitchen --follow
aivg onboard --ssid "MyWiFi" --password "..." --name "bedroom"

# Old binary still works (one release):
sat-cli list              # stderr: "sat-cli is renamed to aivg…"; stdout: same JSON / human output
```

### Data directory

```bash
~/.aivg/config.yaml                          # new home (was ~/.satellite/config.yaml)
~/.aivg/state.json                           # adopted-device registry
~/.aivg/firmware/<device_type>/manifest.json

# Legacy left in place if you had one:
~/.satellite/state.json.pre-aivg-rebrand.bak  # preserved, not deleted
```

The first time the rebranded gateway starts on a machine that had a
`~/.satellite/` directory, it atomically migrates the contents and
renames the old files with the `.pre-aivg-rebrand.bak` suffix.
Subsequent starts are idempotent: the migration only fires if the new
location is empty or older than the old.

## What stays the same (the binding invariant)

- Every REST `operationId`, schema, status code, route.
- Every CLI command name, flag, exit code.
- The closed `error.code` set.
- The JSON envelope `{ok, data, error, v=1}` shape.
- `aivg --contract-version` → `1.0.0` (no change from `sat-cli`).
- The Hermes plugin: `aivg_core/platforms/hermes/`,
  `skills/hermes-agent/`, `~/.hermes/config.yaml` reads.
- Constitution Principles I–V (rewordings allowed, no normative
  changes).

If you're writing automation that talks to the gateway or scripts the
CLI in JSON mode, you can keep doing exactly what you were doing — the
only thing to update is the binary name (eventually) and any imports.

## Hermes vs AIVG — when to use which

| Use this | When you mean |
|---|---|
| **AIVG** | the product, the repo, the codebase, the system as a whole |
| **Hermes** | the v1 agent-platform plugin (one of several AIVG supports) |
| **`aivg`** | the operator CLI binary |
| **`sat-cli`** | (legacy) the same binary, one release of compat |
| **`aivg_core`** | the platform-neutral Python package |
| **`aivg_core/platforms/hermes/`** | the Hermes-plugin's Python code |
| **`~/.aivg/`** | AIVG's operator data |
| **`~/.hermes/`** | the Hermes plugin's data (read-through, not owned by AIVG) |

## Adding a documentation reference to the old name

If you genuinely need to reference "Hermes Voice" in a new doc (e.g. a
follow-up release note explaining the rename), add the file path to
`docs/rebrand-allow-list.md` first; the lint
(`tests/unit/test_no_legacy_branding.py`) catches new references that
aren't on the list.

## Running the rebrand lint locally

```bash
pytest tests/unit/test_no_legacy_branding.py
```

It runs as part of the full `pytest` invocation, so a regular test
loop catches reintroductions.

## Removing the compat shims (next release)

Tracked under feature 012 Phase 8 polish (see tasks.md). Steps:

1. Delete `src/satellite_core/`, `src/sat_cli/`, the
   `hermes_satellite_adapter/` two-hop shim.
2. Remove the `sat-cli` entry from `pyproject.toml`'s
   `[project.scripts]`.
3. Remove the `satellite-core` metapackage publish.
4. Re-run the lint; expected to stay green (compat-shim allow-list
   entries become dead-code removals).
