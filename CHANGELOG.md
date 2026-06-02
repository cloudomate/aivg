# Changelog

## [Unreleased] — Feature 021: gRPC satellite transport

Adds a **gRPC bidirectional-streaming transport** for native satellites as an
additive sibling under `aivg_core.transports.grpc/` (mirrors the feature-017
ESPHome transport pattern). Off by default; WebRTC stays for browser
satellites and existing native deployments — transport is chosen by capability
negotiation, no flag-day.

### Added

- **gRPC audio plane** (`aivg.satellite.v1.Audio`). One bidi `Audio.Stream`
  per voice session: mic PCM up; synthesized audio + streaming transcripts +
  turn events down on the same stream. Reuses the canonical `Session` /
  `AgentPlatform` seam verbatim — no ICE/DTLS/SCTP to stall (closes the
  "stuck connecting" failure class). Reconnect opens a fresh stream rather
  than renegotiating a peer connection.
- **gRPC management plane** (`aivg.satellite.v1.Management`, opt-in via
  `transports.grpc.management_over_grpc`). A native satellite can run its whole
  lifecycle — register/adopt, heartbeat, state, control — over gRPC without the
  `/satellite/ws` WebSocket. Kept as a separate long-lived service from
  `Audio.Stream`; reuses `ManagementService` and its broadcast fan-out verbatim
  (identical control semantics).
- **Capability-based transport negotiation.** Satellites advertise
  `transport_capabilities`; the gateway selects the best mutually-supported
  transport (prefers gRPC for native, WebRTC for browser) with no `device_type`
  branching. Operators can pin a transport; an unsatisfiable pin is a clear
  error. Browser/legacy WebRTC and ESPHome satellites are unaffected.
- **Canonical wire contract** at `proto/aivg/satellite/v1/{audio,management}.proto`
  (single source of truth, vendored by the `aivg-devices` C++ client);
  checked-in Python stubs via `scripts/gen_proto.sh`. Server reflection enabled
  for `grpcurl` diagnosability.
- New runtime deps: `grpcio`, `grpcio-reflection`, `protobuf` (`grpcio-tools`
  for codegen, dev only).

### Changed

- **Wire-contract envelope bumped `0.2.0` → `0.3.0`** (additive minor): the
  build now advertises a third transport (`grpc`) alongside `webrtc` +
  `esphome_api`. Existing `0.2.0` WebRTC/ESPHome clients are unaffected. The
  `@aivg/sat-sdk` (TypeScript) bump to match is a separate, coordinated SDK
  release.

### Notes

- **Deferred:** Opus downstream encoding (PCM is the working default; Opus
  selection degrades to PCM until an encoder lands) and full mTLS cert plumbing
  (insecure-LAN works; mTLS refuses to silently downgrade). Defaulting native
  satellites to gRPC is gated on a ≥7-day real-hardware soak (Constitution V).

## [0.2.2] — 2026-06-01 — WebRTC renegotiate after gateway restart + TTS text filter

Small follow-on to `0.2.1`. No wire-contract changes; drop-in.

### Fixed

- **WebRTC voice plane doesn't survive a gateway restart.** When the
  management WS reconnects after a non-clean close, the C++ SDK now
  tears down the dead `PeerConnection`, emits
  `VoiceSessionResult{reason="gateway_reconnected"}`, and rebuilds the
  voice session with the same audio callbacks under a per-Satellite
  mutex (`vs_mu`). Internal `ControlPlane::Callbacks::on_reconnected`
  fires only on real reconnects (skips the first connect). Opt-out via
  `AIVG_SAT_DISABLE_WEBRTC_RENEGOTIATE=1` for lab benches that prefer
  manual recovery. Closes upstream bug 5.

### Added

- **TTS markdown + emoji filter.** New
  `aivg_core.webrtc.tts_text_filter` strips markdown (fenced/inline
  code, images, links, bare URLs, headers, blockquotes, bullets,
  numbered lists, strikethrough, bold/italic, tables, HTML tags) +
  Unicode emoji (faces, symbols, transport, flags, ZWJ sequences) +
  ASCII smileys (`:)`, `:-(`, `;P`, `<3`, `^_^`, …) from agent replies
  before TTS synthesis, so Piper/Coqui don't literally pronounce
  punctuation or emit 0-frame audio for unrenderable codepoints.
  Idempotent; applied as a belt-and-suspenders pass after Hermes's own
  `_strip_markdown_for_tts`. Configurable via
  `satellite.tts_text_filter: bool` (default `true`); per-host override
  via `AIVG_DISABLE_TTS_TEXT_FILTER=1`. Revises the spec-009 "no emoji
  handling" decision based on field experience.

## [0.2.1] — 2026-06-01 — Bug fixes

Patch release on top of the `0.2.0` PyPI baseline.

### Fixed

- **`aivg setup` PyPI bootstrap.** `PIP_PACKAGE_NAME` is now `aivg`
  (matching the actual PyPI distribution, not `aivg-core`);
  `_find_repo_root` anchors on `name = "aivg"`; and when no local
  source tree is found it falls back to `pip install aivg`, so
  `pip install aivg && aivg setup` bootstraps end-to-end.
- **`aivg logs <id>` markup crash.** Rich markup in
  `source`/`device_id`/`message` is now escaped, so log lines
  containing `[/]` or `[bold]` no longer raise `MarkupError`.
- **`/satellite/{id}/logs` tail query.** `LogSink.query` accepts
  `tail`; the snapshot handler whitelists/coerces query params (drops
  unknown ones, parses `since`/`tail` numerically) and scopes by the
  path `{id}` as `device_id`.

### Changed

- **`aivg list --state` help text** clarifies that `pending` only
  populates with `auto_adopt_on_register: false` (or after a factory
  reset), so default deployments don't surprise operators with empty
  results.
- **Root CLI help text** shortened to a plain one-liner ("manage voice
  satellites and fleets from the command line").

## [0.2.0] — 2026-05-21 — Feature 018: First public PyPI release

This is the FIRST publicly-versioned release of AIVG on PyPI. Every
prior version listed under "Pre-publication history" below was
internal — never visible outside the repo. `0.2.0` is the public
baseline; every future release evolves the version semver-cleanly
from here.

### Install

```bash
pip install aivg
# or, into an existing Hermes venv (the canonical path):
uv pip install --python ~/.hermes/hermes-agent/venv/bin/python aivg
```

### Added (in this PyPI release)

- **PyPI distribution as `aivg`.** Replaces the old "clone the repo,
  run `pip install -e .`" workflow with the standard Python
  packaging path. Wheel size 149 KB, pure-Python (`py3-none-any`).
  PyPI listing: <https://pypi.org/project/aivg/0.2.0/>.
- **Complete `pyproject.toml` metadata** (per Spec 018 R-3):
  `license = "MIT"`, `readme`, `authors`, `maintainers`, `keywords`,
  twelve PyPI classifiers, and `[project.urls]` populating the PyPI
  sidebar with Repository / Issues / Changelog / Documentation links.
- **`LICENSE` file at repo root** (MIT, matching
  `sdks/typescript/LICENSE`). Required by FR-009; previously absent.
- **GitHub Actions CI release workflow** at `.github/workflows/release.yml`.
  Triggered on `vX.Y.Z` tag push: builds via `uv build`, uploads to
  TestPyPI via Trusted Publishing OIDC, smoke-installs in a clean
  venv, promotes the SAME artifact bytes to real PyPI. No long-lived
  PyPI tokens anywhere.
- **Two new test files** in the regular pytest suite:
  `tests/contract/test_pypi_metadata.py` (8 tests — guards every
  required PyPI metadata field; runs in <0.5s) and
  `tests/integration/test_install_from_built_wheel.py` (3 tests —
  builds the wheel, installs into a throwaway venv, confirms
  `aivg --version` works end-to-end). Test count 294 → 302.

### Changed (Spec 018 Clarifications Q1, Q2, Q3)

- **PyPI distribution name**: `aivg-core` (pre-PyPI placeholder)
  → `aivg` (canonical short name; matches the CLI binary and the
  product brand). Python module name `aivg_core` is UNCHANGED —
  common Python pattern (`pyyaml` installs `yaml`, `beautifulsoup4`
  installs `bs4`).
- **Package version**: every pre-018 version (`0.1.0` → `0.3.1`)
  treated as internal pre-publication history; first PyPI release
  is `0.2.0` (the public baseline). Listed below.
- **Wire-contract version** (`aivg --contract-version` JSON field):
  `1.1.0` (pre-PyPI, set by feature 017's ESPHome bump) → `0.2.0`
  (public baseline; matches the package version at the release
  boundary). The two axes will naturally diverge over time
  (package bumps every release, wire bumps only on wire-shape
  changes); single number is the starting alignment only.
- **`@aivg/sat-sdk` bumps to `0.2.0`** (MAJOR per 0.x semver
  convention, coordinated with this release). The SDK's source
  `CONTRACT_VERSION` constant is now `"0.2.0"`; consumers must
  bump their pin from `^0.1.x` to `^0.2.0` to talk to a post-018
  gateway. See [sdks/typescript/CHANGELOG.md](sdks/typescript/CHANGELOG.md).
- README PyPI-rendered intro block, leading with `pip install aivg`
  and the "install into the Hermes venv, NOT a fresh venv" gotcha
  (caught us on 2026-05-21).

### Compatibility

- **`@aivg/sat-sdk@0.1.x` clients** talking to a post-018 gateway:
  incompatible (SDK sends `"1.0.0"` in register frame; gateway
  emits `"0.2.0"`). Bump SDK to `0.2.0`.
- **Pre-018 ESPHome devices** flashed against the pre-018 gateway:
  the wire format (REST paths, WS frames, config keys, env vars) is
  byte-identical to pre-018 — only the `contract_version` envelope
  string changed. Devices that ignore that field continue to work
  unchanged; devices that check it need a re-flash with the new
  string. None in production (per Spec Clarification Q2 rationale).

---

## Pre-publication history (internal versions; never on PyPI)

Every version below this header is internal-only. The 0.3.x sequence
was bumped during pre-publication development; we never published
those numbers to PyPI. Public versioning starts at 0.2.0 above.

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
