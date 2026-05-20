# Follow-up: remove the AIVG compat shims (next release)

**Source**: feature 012 task T043, [quickstart.md](./quickstart.md#removing-the-compat-shims-next-release).
**Owner**: next feature after 012.

The AIVG rebrand kept four compat shims alive for one release. They go
together in a single follow-up PR:

| Surface | Shim location | Removal |
|---|---|---|
| Legacy Python package `satellite_core` | `src/satellite_core/__init__.py` + sub-`__init__.py` files under `platforms/`, `webrtc/`, `management/`, `platforms/hermes/` | Delete `src/satellite_core/` entirely. |
| Legacy Python package `sat_cli` | `src/sat_cli/__init__.py` + `src/sat_cli/cli.py` | Delete `src/sat_cli/` entirely. |
| Two-hop legacy package `hermes_satellite_adapter` | `src/hermes_satellite_adapter/__init__.py` | Delete `src/hermes_satellite_adapter/` entirely. |
| Legacy binary `sat-cli` | `[project.scripts]` entry in `pyproject.toml` + `sat_cli.cli:legacy_app` | Remove the `sat-cli = …` line; remove `sat_cli` from `packages.find.include`. |
| `satellite-core` distribution metapackage | (not yet published; if published, mark as `obsoletes` or unpublish) | Coordinate with the PyPI release. |

After deletion, the rebrand-lint allow-list trims:

```diff
- src/satellite_core/__init__.py
- src/sat_cli/__init__.py
- src/sat_cli/cli.py
- src/hermes_satellite_adapter/__init__.py
```

The two test files
(`tests/unit/test_compat_shim.py`,
`tests/unit/test_persistence_migration.py`) stay — they continue to
verify that no consumer accidentally re-introduces the old import
paths.

## Verification

1. `pytest -q` → green (the shim-only tests get deleted or repurposed;
   everything else stays green).
2. `python -c "import satellite_core"` → `ImportError`. Same for
   `sat_cli` and `hermes_satellite_adapter`.
3. `which sat-cli` → not found (the script entry is gone).

## Sequencing constraints

- Land this PR **at least one release after** feature 012 ships. The
  whole point of the shim window is to give external consumers a
  chance to migrate; collapsing the window defeats it.
- The legacy `~/.satellite/` data-dir migration (atomic) is **kept**
  beyond shim removal — it's a one-shot first-run helper, harmless to
  retain.

## Constitution check

Removing the shims does not change any Principle. No amendment needed.
