# Changelog

## [0.3.1] — 2026-05-21 — Feature 019: internal plugin-name rename

PATCH release. Renames the internal Hermes plugin registration name
from `satellite_webrtc` to `aivg_satellite` and adds a load-time
conflict detector that refuses to register when a pre-rebrand
vendored `satellite_webrtc/` bundled plugin is also present.

**No wire-surface change.** REST paths under `/satellite/*`,
the `satellite:` config block, the `SATELLITE_*` env vars, the
contract version (`1.1.0`), and the `aivg --contract-version`
envelope are byte-identical to pre-019. The narrowed scope is
deliberate — "satellite" is the correct domain noun for the
resource being managed (the device IS a satellite); only the
brand prefix and the `_webrtc` suffix on the internal name
needed fixing (`_webrtc` became misleading the moment feature
017 added the ESPHome transport under the same plugin).

### Changed

* Hermes platform-plugin registration name `satellite_webrtc` →
  `aivg_satellite`. Gateway log lines now carry the new name
  (`✓ aivg_satellite connected`).
* `aivg_core.adapter.SatelliteWebRTCAdapter` class renamed to
  `AivgSatelliteAdapter`. The old name remains importable as a
  back-compat alias for one release (slated for removal in the
  release after 0.3.1).
* `get_chat_info()` `platform:` field returns `"aivg_satellite"`
  (was `"satellite_webrtc"`). Display-only field; not a
  persistence key.
* `PlatformEntry` `plugin_name` field updated from
  `"hermes_satellite_adapter"` to `"aivg_core"` (cosmetic).

### Added

* The post-019 plugin entry-point's `register()` detects a
  pre-rebrand vendored `satellite-webrtc-platform` bundled plugin
  still installed under `~/.hermes/hermes-agent/plugins/platforms/`
  and refuses to register, with a clear multi-line error naming
  the conflicting directory and the cleanup verb. Eliminates the
  silent-shadow trap that consumed hours of the 2026-05-21 deploy
  session (two plugins binding to the same management/signaling
  ports, the bundled one silently winning, the entry-point one
  loaded-but-inert).
* New `CANONICAL_PLUGIN_NAME` constant in
  `aivg_core.platforms.hermes.setup` (sibling to the existing
  `LEGACY_PLUGIN_NAME`). Single source of truth that all four
  renamed sites read from.

### Tests

* +9 new tests: `tests/unit/test_plugin_registration_name.py` (3),
  `tests/unit/test_conflict_detector.py` (4),
  `tests/unit/test_no_conflict_quiet_path.py` (1),
  `tests/unit/test_adapter_sites.py` (+1 back-compat alias check).
  Unit + contract suite: 285 → 294 passing.

### Verification

* Wire-surface byte-diff harness against pre-019 baseline: zero
  diff on `contract-version.json`, `/satellite/list?state=all`
  schema, and `/satellite/ws` register-reply schema (only
  runtime state — timestamps + transient session state —
  differs).
* Live conflict-detector smoke: re-injected backup, restarted
  gateway, observed `Failed to load plugin 'aivg-satellite': …`
  with the directory path and `mv` cleanup verb in the message.
  Other Hermes platforms unaffected. Cleanup + restart yields
  clean `✓ aivg_satellite connected` boot.
* Pre-019 client compatibility: unchanged @aivg/sat-sdk 0.1.4
  electron-test client kept registering, adopting, and
  voice-turning continuously across all post-019 gateway
  restarts — no client-side change required.

## Unreleased — Feature 011 US3 + US4 + US5 (configure / OTA / commands)

Closes the remaining work in feature 011: every command the CLI
contract documents now exists in the implementation. The management
plane is feature-complete for the v1 operator surface.

### Added

* `POST /satellite/{id}/config` now honors optimistic concurrency via
  the `If-Match: <config_version>` header and offline-write queueing
  via `?queue=true`. Returns `(status, payload)` shape: 200 apply,
  202 queued, 409 stale, 503 offline, 404 unknown device.
* `GET /satellite/{id}/config/schema` — JSON Schema for the editable
  config fields (constitution II: same shape for every device type).
* `aivg device config get / set / schema` — Typer subcommands.
  `set --field key=value` is repeatable (JSON-parsed values), supports
  `--from-file PATH`, `--if-match N`, `--queue`.
* `aivg_core/management/ota.py` — `OtaService` with manifest loader
  (`~/.aivg/firmware/<device_type>/manifest.json`), `check / apply /
  status_report / manifest_response`. Browser-not-eligible enforced.
  OTA progress relayed through `LogSink` with `source="ota"` so the
  existing SSE log stream carries it.
* `POST /satellite/{id}/ota/check`, `/ota/apply`, `/ota/status`,
  `GET /satellite/{id}/ota/manifest` — REST endpoints.
* `aivg ota check / apply / manifest` — Typer subcommands with
  `--follow` on apply (NDJSON progress until terminal `result`).
* `aivg device command <verb> [--args JSON]` — closed CommandVerb
  enum (`reboot`, `restart-voice`, `restart-manager`, `reset-config`,
  `factory-reset`, `mute`, `unmute`, `identify`); destructive verbs
  require interactive confirmation OR `--yes` under `--json`.
* `aivg device delete` — same destructive-confirm gate.
* `SatelliteAdapterConfig.platform: str = "hermes"` field (T011 closed):
  the satellite config's top-level `platform:` key wins; selects the
  agent-platform plugin loaded via `PluginRegistry.load(name)`.
* `tests/fixtures/platforms/echo/` — fake EchoAgentPlatform; proves
  the plugin seam works against a third-party plugin without importing
  Hermes (T017 closed; constitution v2.0.0 IV binding gate).

### Tests at this checkpoint

252 passed + 1 xpassed (was 188 + 1 at the start of this turn; +64
net-new tests across US3 / US4 / US5 / partial closures). The
pre-existing flaky `test_sc005_ten_plus_concurrent_sessions` may
surface intermittently under load — not a regression.

### Changed (in-process API)

* `ManagementService.post_config` returns `(status, payload)` —
  previously returned a bare dict. The legacy unit test was updated.
* `ManagementService.command` returns `(status, payload)` — previously
  returned `{accepted, scheduled_at}` directly. Accepts the legacy
  bare-string shape as a back-compat shim; new callers should pass a
  `{command, args?}` body dict.
* `ManagementService.config_schema` now returns a JSON Schema document
  (was `{fields: [...]}`).

`aivg --contract-version` remains **1.0.0** — these additions are
purely **additive** to the CLI surface (FR-008 invariant intact).

### Carried-forward partial that remains

* T023 (subprocess `aivg watch --json` NDJSON test) — written then
  removed because the subprocess buffering / timing turned out too
  fragile for a reliable assertion; the in-process watch logic is
  covered by the existing tests. Tracked as still-partial in
  `specs/011-satellite-management/tasks.md`.
* T019 (rewire `webrtc/session.py` + `signaling.py` off
  `HermesBridge` and onto the `AgentPlatform` Protocol) — the
  `# AgentPlatform-coupling-TODO` markers remain in those files; the
  lint exempts them. Closing this is a separate refactor not blocking
  the v1 operator surface.

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
