# Feature Specification: Internal plugin-name rename — `satellite_webrtc` → `aivg_satellite`

**Feature Branch**: `019-transport-plane-rename`  
**Created**: 2026-05-21  
**Status**: Draft  
**Input**: User description: "rename satellite_webrtc → aivg_satellite end-to-end. Cover: Hermes plugin registration name, REST paths /satellite/* → /aivg/* with one-release deprecation aliases for SDK compat, config block satellite: → aivg: with migration shim in aivg setup, env vars SATELLITE_* → AIVG_*. Bump @aivg/sat-sdk to read the new paths (0.2.0 major). Constitution-neutral (additive aliasing during the transition window)."

## Clarifications

### Session 2026-05-21

- Q: What's the rename scope? → A: Option A — rename ONLY the internal
  Hermes plugin-registration name (`satellite_webrtc` → `aivg_satellite`).
  KEEP REST paths `/satellite/*`, the `satellite:` config block, and the
  `SATELLITE_*` env vars unchanged: "satellite" is the correct domain
  noun for the resource being managed (the device IS a satellite), not
  a pre-rebrand product-brand prefix. The original sweeping rename
  proposal would have made `/satellite/list` become `/aivg/list`
  ("list the AIVGs") which is meaningless. Scope reduction removes
  the need for deprecation aliases, migration shims, contract-version
  bumps, @aivg/sat-sdk 0.2.0 major release, and the migration
  document. Feature collapses to a small internal rename plus a
  load-time conflict detector that addresses the pre-019 vendored-plugin
  trap we hit during today's deploy.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Gateway logs reflect the brand and the multi-transport reality (Priority: P1)

An operator inspecting their gateway log today sees lines like
`✓ satellite_webrtc connected` — a string that is misleading on two
counts. First, it has no brand prefix, so it doesn't read as
AIVG-owned (it predates feature 012's rebrand). Second, the `_webrtc`
suffix has been wrong since feature 017 added the ESPHome native API
as an additive transport under the same plugin: the plugin handles
both WebRTC and ESPHome traffic, not just WebRTC. After 019, the
same log line reads `✓ aivg_satellite connected` — brand-prefixed
and transport-neutral.

**Why this priority**: This is the entire feature. The internal
plugin registration name is the only surface 019 changes, and the
gateway log is the operator's primary contact with that name. If
the log line still says `satellite_webrtc` after 019, the rename
has not happened.

**Independent Test**: Take a post-019 AIVG install. Restart the
gateway. Inspect `~/.hermes/logs/gateway.log` for the plugin-
connect line. The line MUST contain `aivg_satellite` and MUST NOT
contain `satellite_webrtc`. Run `hermes plugins list` and confirm
no row shows `satellite_webrtc` as the platform name. The wire
surfaces (REST `/satellite/*`, config `satellite:` block, env vars
`SATELLITE_*`) MUST be byte-identical to pre-019.

**Acceptance Scenarios**:

1. **Given** a post-019 AIVG install with the `aivg-satellite`
   entry-point plugin enabled, **When** the operator restarts the
   Hermes gateway, **Then** the gateway log's plugin-connect line
   names `aivg_satellite` (NOT `satellite_webrtc`).
2. **Given** a post-019 gateway running normally, **When** an
   unchanged pre-019 @aivg/sat-sdk 0.1.4 client connects via
   `/satellite/ws`, **Then** the connection completes a full
   register → adopt → voice-turn flow with wire frames
   byte-identical to those produced by the pre-019 gateway.
3. **Given** a post-019 gateway with the same `satellite:` config
   block, the same `SATELLITE_ALLOWED_USERS` env var, and the same
   `/satellite/*` REST routes the operator used before the upgrade,
   **When** the operator runs their existing scripts /
   monitoring / `aivg list` / device-firmware traffic against the
   gateway, **Then** zero behavior changes are observed — every
   wire surface is byte-equivalent to pre-019.

---

### User Story 2 — Pre-019 vendored plugin and post-019 entry-point plugin can't silently coexist (Priority: P1)

The trap we hit during today's local deploy: a vendored bundled
plugin from feature 003 (`~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`)
was still present on disk. Hermes loaded it automatically (bundled
platforms auto-load with no opt-in). The post-rebrand entry-point
plugin was also discovered, but disabled until we added it to
`plugins.enabled`. After we enabled the entry-point plugin, BOTH
were eligible to load — and the bundled-plugin version (running
older code without `adoption_state` in the wire) was the one
actually serving port 8643, while the entry-point plugin was
nominally "loaded too." This silent shadow lasted hours and caused
the SDK to print `adoption: undefined` until we explicitly moved
the vendored directory out of the scan path.

After 019, the post-019 entry-point plugin's `register()` MUST
detect this coexistence and refuse to register, with an error
message that names the exact directory to remove. The operator
gets a clear "you need to clean up the old plugin" message
instead of a hours-long silent shadow.

**Why this priority**: P1 because every existing operator with a
pre-019 install has the vendored plugin sitting on disk. Without
this detector, every single one of them hits the same silent shadow
on first post-019 boot. Without the detector, the rename is worse
than the status quo — at least today's `satellite_webrtc` is the
ONLY name; after a sloppy rename, two names exist and the wrong
one might win.

**Independent Test**: On a host that has both:
(a) a pre-019 vendored plugin at
`~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`,
(b) the post-019 `aivg-satellite` entry-point plugin enabled in
`plugins.enabled`,

1. Restart the Hermes gateway.
2. The gateway log MUST contain a clear error from the post-019
   plugin's `register()` naming the conflicting directory and the
   recommended cleanup (`mv` or `rm`).
3. Either the gateway refuses to start, OR only the bundled
   plugin loads — but never both silently. The exact choice is a
   plan-phase decision; the binding behavior is "no silent
   coexistence."
4. Once the operator moves the vendored directory out of the scan
   path and restarts, the gateway loads cleanly with only the
   `aivg_satellite` entry-point plugin.

**Acceptance Scenarios**:

1. **Given** both the pre-019 vendored bundled plugin and the
   post-019 entry-point plugin are installed and enabled,
   **When** the gateway starts, **Then** the operator sees a
   clearly-formatted error message in the gateway log naming the
   vendored directory and the cleanup verb, BEFORE the gateway
   reaches a "ready" state.
2. **Given** the operator follows the error message's cleanup
   instruction (moves or removes the vendored directory),
   **When** they restart the gateway, **Then** the gateway loads
   the entry-point plugin cleanly, the conflict error no longer
   fires, and the plugin-connect log line reads `aivg_satellite`.
3. **Given** ONLY the post-019 entry-point plugin is installed
   (no vendored directory present), **When** the gateway starts,
   **Then** zero conflict-detection logging fires (the detector
   stays silent on the common case; it's not a warning storm).

---

### Edge Cases

- **`@aivg/sat-sdk` 0.1.x continues unchanged.** 019 makes no SDK
  release. The SDK reads `/satellite/*` paths today and continues
  to do so post-019 because those paths are unchanged.
- **ESPHome voice satellite traffic unchanged.** Feature 017's
  ESPHome native API transport (port 6053, `aioesphomeapi`
  framing) carries through 019 with zero change. The plugin
  internal-name rename has no effect on its wire format.
- **`plugins.enabled:` config block unchanged.** Operators who
  already have `aivg-satellite` in their `plugins.enabled` list
  (post-feature-013 installs) do nothing. The PyPI entry-point
  manifest name is `aivg-satellite` both before and after 019;
  only the `ctx.register_platform(name=…)` value changes.
- **`hermes plugins list` row still reads as expected.** The row
  shown in `hermes plugins list` keys off the manifest name
  (`aivg-satellite`), which is unchanged. The internal name
  change is visible only in the Hermes gateway log lines and the
  Hermes platform-registry's internal dict.
- **Contract version unchanged.** 019 ships at contract version
  `1.1.0` (current) because no wire surface changes. No
  `--contract-version` output diff.
- **Pre-019 `~/.aivg/state.json` records, OTA manifests,
  per-device API key files** — none reference the plugin
  registration name. All carry forward verbatim.
- **REST list / state response shapes unchanged.** `/satellite/list`
  continues to return the v1.1.0 schema (`adoption_state`, `name`,
  `transport`, `ota_state`, etc.) after the post-deploy fixes we
  landed today.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The Hermes platform-plugin registration name passed
  to `ctx.register_platform(name=…)` MUST change from
  `satellite_webrtc` to `aivg_satellite` in
  `aivg_core.platforms.hermes.plugin_entrypoint`.
- **FR-002**: Gateway log lines that today emit `satellite_webrtc`
  (e.g., `✓ satellite_webrtc connected`,
  `Connecting to satellite_webrtc...`, shutdown lines) MUST emit
  `aivg_satellite` instead, post-019.
- **FR-003**: The internal Python class
  `SatelliteWebRTCAdapter` (today the `name` attribute is
  `"satellite_webrtc"`) MAY be renamed to `AivgSatelliteAdapter`
  for symmetry; if renamed, all callers within `aivg_core` MUST
  be updated atomically. (Internal-only; not a wire change.)
- **FR-004**: The post-019 entry-point plugin's `register()` MUST
  detect the presence of a pre-019 vendored bundled plugin under
  the Hermes plugin scan path (e.g.,
  `~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`
  with its own `plugin.yaml`), and MUST refuse to register with a
  clear error naming the offending directory and the recommended
  cleanup action.
- **FR-005**: The PyPI entry-point manifest name `aivg-satellite`
  is UNCHANGED. The string operators type into their
  `plugins.enabled:` list stays the same.
- **FR-006**: The REST paths under `/satellite/*` (including
  `/satellite/ws`, `/satellite/register`, `/satellite/list`,
  `/satellite/{id}/state`, `/satellite/{id}/adopt`,
  `/satellite/{id}/config`, `/satellite/{id}/ota/*`,
  `/satellite/{id}/command`, `/satellite/{id}/logs`,
  `/satellite/logs`) are UNCHANGED post-019. Operators, devices,
  and SDKs see no path-level diff.
- **FR-007**: The `~/.hermes/config.yaml` `satellite:` block
  format and key names are UNCHANGED. Operator-customized config
  values carry through 019 untouched.
- **FR-008**: The env vars `SATELLITE_ALLOWED_USERS` and
  `SATELLITE_ALLOW_ALL_USERS` are UNCHANGED. Operators who set
  them today continue to do so post-019.
- **FR-009**: The gateway contract version stays at `1.1.0`
  (no wire-surface bump). `aivg --contract-version` output is
  byte-identical pre/post 019.
- **FR-010**: ALL 329+ pre-019 tests MUST continue to pass
  without modification. A small new test set MUST be added to
  cover the post-019 plugin-name change (gateway log assertion)
  and the conflict-detector (FR-004).
- **FR-011**: The AIVG constitution (v2.0.1) remains unchanged.
  Principles I (thin satellite), II (four-plane contract), III
  (separate control/voice connections), IV (reuse the upstream
  agent platform), and V (research-backed decisions) are all
  unaffected — this rename touches a single internal Python
  string and one error path.

### Key Entities

- **Plugin Registration Name**: the string value passed to
  Hermes's `ctx.register_platform(name=…)` API. Today
  `"satellite_webrtc"`. Post-019: `"aivg_satellite"`. The
  identifier Hermes uses internally to key its platform-adapter
  dict and to emit gateway log lines.
- **Vendored Bundled Plugin (legacy)**: a pre-rebrand directory
  under `~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`
  containing a `plugin.yaml` declaring kind=platform. Hermes's
  bundled-platform auto-load policy means this directory is
  loaded regardless of `plugins.enabled`. Conflict-detector
  scope.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Post-019 gateway log emits `aivg_satellite` in every
  line where pre-019 logs emitted `satellite_webrtc`. Verified by
  greping `~/.hermes/logs/gateway.log` after a clean restart.
- **SC-002**: Pre-019 wire surfaces (REST `/satellite/*` schema +
  status codes, WS frames on `/satellite/ws`, config `satellite:`
  block key names, env var names `SATELLITE_*`,
  `aivg --contract-version` output) are byte-identical to their
  pre-019 form. Verified by a diff harness comparing pre-019 vs.
  post-019 captures over the same scripted client flow.
- **SC-003**: On a host with BOTH the pre-019 vendored bundled
  plugin AND the post-019 entry-point plugin enabled, the
  conflict detector fires with a clear error within 5 seconds of
  gateway start, naming the vendored directory and the cleanup
  verb. Operator following the named cleanup verb produces a
  clean post-019 boot on the next restart.
- **SC-004**: Test suite passes at 329+N (where N is the count
  of new tests added for the plugin-name change and the conflict
  detector) for 3 consecutive runs with no flakes.
- **SC-005**: Zero pre-019 satellite clients (electron-test
  0.1.4, Home Assistant Voice PE, M5Stack Atom Echo, third-party
  custom clients) require any change to continue working
  against the post-019 gateway. Verified by running each
  unchanged client through its standard register → adopt → voice-turn
  flow.

## Assumptions

- **Class rename is opt-in.** Renaming
  `SatelliteWebRTCAdapter` → `AivgSatelliteAdapter` is purely
  internal cosmetics. The plan phase decides whether to do it in
  019 or defer to a later cleanup. Either choice satisfies the
  user-visible criteria above.
- **CHANGELOG entry is one line.** 019 ships as a maintenance
  release with a one-line CHANGELOG entry along the lines of
  "Renamed the Hermes plugin internal registration name from
  `satellite_webrtc` to `aivg_satellite`; gateway log lines
  now reflect the new name. No wire-surface change."
- **No SDK release.** `@aivg/sat-sdk` stays at 0.1.4 (the
  post-fix release we shipped today). No 0.2.0 cut.
- **No migration verb.** 019 does NOT add `aivg setup --migrate-…`
  or any analog. Nothing to migrate.
- **No deprecation warnings.** Nothing is being deprecated. No
  warning machinery added.
- **Conflict-detector implementation site.** The detector lives
  in the post-019 entry-point plugin's `register()` (or a helper
  it calls), not in Hermes core. AIVG owns this code path and
  can ship it without coordinating with the Hermes-agent
  release cycle.
- **Detector failure mode**: "refuse to register" is the
  conservative choice. The exact mechanism (raise from
  `register()`, return without calling
  `ctx.register_platform`, mark the platform as disabled) is a
  plan-phase decision; the binding behavior is "no silent
  coexistence."
- **PyPI release ordering vs. feature 018.** This feature can
  ship before OR after 018's first PyPI release. If before:
  the first PyPI release carries the canonical internal name.
  If after: a 0.3.1 or 0.4.0 patch/minor bump on PyPI ships the
  rename. The wire surface is unchanged either way, so the
  ordering is a release-management call, not a correctness one.
- **No constitution amendment.** Wire surfaces unchanged.
  Principle II ("Generic Four-Plane Contract") binding unchanged.
- **ESPHome / OpenClaw plugins unaffected.** ESPHome's wire is
  upstream-defined. OpenClaw is a stub; whenever implemented it
  uses the post-019 canonical naming pattern.
