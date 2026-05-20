# Changelog

## Unreleased — Note on deploy/*.sh after the rebrand

The shell-script deploy infrastructure (`deploy/deploy-local.sh`,
`deploy/deploy-to-hermes.sh`, `deploy/parity-check.sh`,
`deploy/rollback.sh`, `deploy/plugin/`) is **broken by the AIVG
rebrand and not fixed in feature 012** — by design. The scripts
predate constitution v2.0.0 / Principle IV and are Hermes-hardcoded;
patching them to point at `aivg_core` would perpetuate the wrong
layer. The replacement — a CLI-based `aivg setup` that detects the
active agent platform and dispatches to platform-specific install
logic inside the plugin seam — is recorded as the next feature in
[specs/012-aivg-branding/followup-cli-deploy.md](specs/012-aivg-branding/followup-cli-deploy.md).

In-process smoke (`python -m aivg_core --dev-fake-bridge` +
`aivg list / device get / logs --follow`) remains the working local-
test path for AIVG-side work that doesn't need a real upstream
agent-platform gateway.

## Unreleased — AIVG compat-shim removal (feature 012 Phase 9)

User-requested early closure of the compat-shim window opened by the
AIVG rebrand. The "one release after" guideline in the rebrand spec was
explicitly waived — there were no external consumers depending on the
legacy import paths or the `sat-cli` binary, so the window collapses.

### Removed

* Python package `satellite_core` — `ImportError` now.
* Python package `sat_cli` — `ImportError` now.
* Python package `hermes_satellite_adapter` (two-hop shim from
  feature 011) — `ImportError` now.
* CLI binary `sat-cli` — the `[project.scripts]` entry is gone; the
  `aivg` binary is the only entry point.
* `tests/unit/test_compat_shim.py` — its premise (the shims exist) no
  longer holds.
* The three compat-shim `DeprecationWarning` filters from
  `pyproject.toml` `filterwarnings`.
* The compat-shim entries from `docs/rebrand-allow-list.md`.

### Retained

* `aivg_core.persistence.migrate_legacy_data_dir()` — the one-shot
  `~/.satellite/` → `~/.aivg/` first-run migration helper stays.
  It's harmless to keep and still helps any operator who has a legacy
  data directory on disk.
* `tests/unit/test_persistence_migration.py` — verifies the migration
  helper above.
* The Hermes-plugin's gateway-side registration name
  (`plugin_name="hermes_satellite_adapter"` in
  `aivg_core/adapter.py`) — that's an externally-known identifier to
  the upstream Hermes gateway plugin registry, **not** a Python
  import. Renaming it would break the Hermes integration; it stays.

### Tests at this checkpoint

188 passed + 1 xpassed (was 193 before Phase 9; net drop of 5 from
the deleted `test_compat_shim.py`).

### Smoke verification

```
python -c "import satellite_core"          → ModuleNotFoundError
python -c "import sat_cli"                 → ModuleNotFoundError
python -c "import hermes_satellite_adapter" → ModuleNotFoundError
python -m aivg_cli.cli --json --version    → {"ok":true,"data":{"version":"0.2.0","contract_version":"1.0.0"},…}
```

`--contract-version` is still `1.0.0`. Removing the shims is **not** a
contract bump (FR-007/FR-008 still hold byte-for-byte).

## Unreleased — AIVG rebrand (feature 012)

**Product renamed**: Hermes Voice → **AIVG (AI Voice Gateway)**.
Hermes remains the v1 agent-platform plugin (constitution v2.0.0
Principle IV); the rebrand only retitles the *product*. Constitution
PATCH-amended to **v2.0.1** with byte-equivalent Principle text.

### Renamed identifiers

| Was | Now |
|---|---|
| Python package `satellite_core` | `aivg_core` |
| Python package `sat_cli` | `aivg_cli` |
| CLI binary `sat-cli` | `aivg` |
| Data dir `~/.satellite/` | `~/.aivg/` |
| pyproject `[project].name` `satellite-core` | `aivg-core` |
| REST `info.title` "Hermes Satellite Management API" | "AIVG Satellite Management API" |

### Compat shims (one release)

- `import satellite_core` still works (one `DeprecationWarning` per
  process, pointing at `aivg_core`).
- `import sat_cli` still works (one `DeprecationWarning` per process,
  pointing at `aivg_cli`).
- `import hermes_satellite_adapter` still works (two-hop shim from
  feature 011, refreshed to point directly at `aivg_core`).
- The `sat-cli` binary still works (stderr-only deprecation notice;
  stdout JSON envelope is byte-equivalent to `aivg`).
- An existing `~/.satellite/state.json` is **atomically migrated** to
  `~/.aivg/state.json` on first run of the rebranded gateway; the old
  file is renamed to `~/.satellite/state.json.pre-aivg-rebrand.bak`
  (never deleted, so you have a rollback rope). Same pattern for the
  per-device-type `firmware/.../manifest.json` subtree.

### Zero substantive contract drift

- Every REST `operationId`, schema, status code, route — **unchanged**.
- Every CLI command, flag, exit code, `error.code` value, JSON envelope
  field — **unchanged**.
- `aivg --contract-version` → `1.0.0` (unchanged).
- The Hermes plugin (`aivg_core/platforms/hermes/`,
  `skills/hermes-agent/`, plugin reuse of `~/.hermes/config.yaml` and
  `~/.hermes/.env`) — **unchanged**.

Verified by `tests/contract/test_rebrand_invariants.py` (T028) and
`tests/unit/test_constitution_principles_byte_equiv.py` (T034).

### Operator references

- New: [`docs/aivg-data-dir.md`](docs/aivg-data-dir.md) — AIVG data
  directory layout + first-run migration semantics.
- New: [`docs/rebrand-allow-list.md`](docs/rebrand-allow-list.md) — the
  rebrand-lint allow-list.
- Quickstart: [`specs/012-aivg-branding/quickstart.md`](specs/012-aivg-branding/quickstart.md)
  — "Hermes vs AIVG — when to use which" table; post-pull contributor
  checklist; CLI / data-dir migration paths.

### Removal schedule

The compat shims (Python packages + binary + distribution metapackage)
are scheduled for removal in the release after feature 012. See
[`specs/012-aivg-branding/followup-shim-removal.md`](specs/012-aivg-branding/followup-shim-removal.md).

The repo directory itself stays `hermes-voice/` in this feature; see
[`specs/012-aivg-branding/followup-repo-rename.md`](specs/012-aivg-branding/followup-repo-rename.md)
for the planned external-clone-URL rename.

---

## v0.2.0 — feature 011 (satellite management; constitution v2.0.0)

Earlier work landed in commits c05ff2d / 7141477. See
[`specs/011-satellite-management/`](specs/011-satellite-management/).
