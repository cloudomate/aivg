# Changelog

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
