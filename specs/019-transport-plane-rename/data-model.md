# Phase 1 — Data Model

**Feature**: 019-transport-plane-rename · **Date**: 2026-05-21

Feature 019 is an internal-identifier rename plus a load-time
guard. It introduces no new persistent records, no new wire
fields, no new public types. The "data" being modeled is the set
of in-process Python identifiers that carry the plugin's name and
the shape of the conflict-detection helper.

---

## 1. Plugin Registration Name (string identifier)

### Source of truth

A pair of module-level constants in
`src/aivg_core/platforms/hermes/setup.py`:

```python
LEGACY_PLUGIN_NAME    = "satellite_webrtc"   # pre-rebrand; kept for
                                              # feature 013's setup CLI
                                              # cleanup logic (already
                                              # present today)
CANONICAL_PLUGIN_NAME = "aivg_satellite"     # post-019; new in this
                                              # feature
```

`LEGACY_PLUGIN_NAME` exists today (feature 013 uses it in setup
preflight / install / uninstall paths). 019 ADDS the
`CANONICAL_PLUGIN_NAME` sibling. Both are exported from the
module so any caller can import the one it needs.

### Callers (post-019)

| Caller (file:line) | Reads | Purpose |
| --- | --- | --- |
| `aivg_core/adapter.py:31` (`SatelliteWebRTCAdapter.name` → `AivgSatelliteAdapter.name`) | `CANONICAL_PLUGIN_NAME` | Class attribute returned by the adapter's `.name` accessor |
| `aivg_core/adapter.py:277` (`get_chat_info` `platform:` field) | `CANONICAL_PLUGIN_NAME` | Display string returned to Hermes for chat metadata |
| `aivg_core/adapter.py:295` (`PlatformEntry(name=…)`) | `CANONICAL_PLUGIN_NAME` | Hermes platform-registry key |
| `aivg_core/platforms/hermes/plugin_entrypoint/adapter.py:53` (`ctx.register_platform(name=…)`) | `CANONICAL_PLUGIN_NAME` | The actual registration call into Hermes |
| `aivg_core/__main__.py:40` (dev banner) | `CANONICAL_PLUGIN_NAME` | Operator-visible string when running adapter in dev mode |
| `aivg_core/adapter.py:98` (startup error message) | `CANONICAL_PLUGIN_NAME` | Substring of error raised when signaling site fails to bind |
| `aivg_core/platforms/hermes/setup.py` (existing setup paths) | `LEGACY_PLUGIN_NAME` (unchanged) | Detect + clean up pre-rebrand vendored directory |
| `tests/fixtures/platforms/echo/setup.py` (plugin_target dirs) | `CANONICAL_PLUGIN_NAME` | Echo platform fixture installs into the canonical path going forward |

### Invariants

- All callers in the same module-call group MUST read the same
  constant. If a caller refers to `"aivg_satellite"` as an inline
  literal AND another reads `CANONICAL_PLUGIN_NAME`, refactoring
  the canonical name later silently breaks the literal. The
  tasks-phase implementation MAY refactor the four `adapter.py`
  sites to import from `setup.py` directly; the binding
  invariant is "one source of truth, eight consumers."
- `LEGACY_PLUGIN_NAME` MUST NOT be removed in 019. Feature 013's
  setup CLI uses it to recognize pre-rebrand installs for
  cleanup; removing it breaks that recognition.
- `CANONICAL_PLUGIN_NAME` MUST equal the entry-point manifest
  name's snake-case form (`aivg-satellite` → `aivg_satellite`).
  This is the convention Hermes operators expect (the bundled
  IRC plugin's manifest is `irc` and registers as `irc`).

### State transitions

The constant values are immutable once the module is imported.
There is no runtime state machine. The "transition" being
modeled is the one-shot rename from `satellite_webrtc` to
`aivg_satellite` across the codebase, which is a compile-time
edit, not a runtime behavior.

---

## 2. Conflict Detector (`_check_no_legacy_bundled_plugin`)

A new helper function inside
`src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py`.
Called from `register()` BEFORE
`ctx.register_platform(name=CANONICAL_PLUGIN_NAME, …)` and ONLY
on the success path of that call.

### Signature

```python
def _check_no_legacy_bundled_plugin() -> None:
    """Raise RuntimeError if a pre-rebrand satellite_webrtc bundled
    plugin is also loaded by Hermes.

    Reads the already-loaded plugin manifest list via the Hermes
    plugin manager API. Looks for a plugin whose manifest name is
    the pre-rebrand `satellite-webrtc-platform` (i.e., the value of
    `name:` in the legacy plugin.yaml) AND whose source is
    `bundled`. If found, raises with a message naming the
    conflicting directory path and the cleanup verb.

    Honors Constitution Principle IV by consuming Hermes's own
    plugin discovery; never re-walks the filesystem.

    Raises:
        RuntimeError: with the operator-actionable cleanup message.
    """
```

### Inputs

- No formal parameters. Internally calls
  `hermes_cli.plugins.get_plugin_manager().list_plugins()`.
- Module-level constant: the legacy manifest name to scan for
  (`"satellite-webrtc-platform"` — the value of the `name:` field
  in the pre-rebrand `plugin.yaml`, distinct from
  `LEGACY_PLUGIN_NAME` which is the directory + registration name).

### Outputs / side effects

- Returns `None` on the clean path.
- Raises `RuntimeError` on the conflict path. The error message
  carries:
  - The conflicting plugin's manifest name (always
    `satellite-webrtc-platform` for a true conflict).
  - The expected directory path (best-effort, from the plugin
    manager's `path` field if it exposes one — fall back to a
    generic `~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`).
  - The cleanup verb (recommended: `mv <path> ~/.hermes/backups/`).
  - One-line explanation of why both can't coexist (port-binding
    conflict + silent-shadow risk).

### Failure semantics

- The exception propagates out of `register()`. Hermes's plugin
  loader catches it, logs it, and the satellite platform fails
  to load. Other Hermes platforms (IRC / Telegram / Discord /
  etc.) continue loading normally — this is critical, the
  conflict-detector failure must not take down unrelated
  platforms.
- The operator sees the failure in two places: the gateway log
  (with the full error message) and `hermes plugins list`
  (which shows the plugin as `enabled=True, error="<exception text>"`).

### Edge cases

- **Hermes plugin manager API unavailable / raises**: catch the
  exception, log a warning, and proceed with registration. The
  conservative choice — a broken detector should not block the
  rename's primary outcome. Documented in the function's
  docstring.
- **Legacy plugin's manifest manually renamed**: if an operator
  has edited the bundled `plugin.yaml` to call itself something
  other than `satellite-webrtc-platform`, the detector won't see
  it. This is acceptable — the bundled plugin still wouldn't
  collide with `aivg_satellite` on the registration name, so
  there's no two-plugins-bound-to-same-port shadow to detect.
- **Multiple legacy plugins (somehow)**: the detector enumerates
  all matches and includes every conflicting directory in the
  error message.

### Test fixtures

`tests/unit/test_conflict_detector.py` uses a fake plugin manager
object with `list_plugins() -> list[dict]` returning controlled
shapes. No real Hermes plugin scan is performed in the unit
tests.

---

## 3. Back-compat alias (`SatelliteWebRTCAdapter`)

A one-line module-scope assignment in `aivg_core/adapter.py`,
immediately after the `class AivgSatelliteAdapter:` definition:

```python
SatelliteWebRTCAdapter = AivgSatelliteAdapter
"""Back-compat alias for external importers (one-release window).

Slated for removal in the release following 019. Internal callers
MUST use the new name.
"""
```

### Why a separate "data model" entry

Because this alias is THE backwards-compat surface for the
rename. Anyone with an existing
`from aivg_core.adapter import SatelliteWebRTCAdapter` import
keeps working without modification. The alias's existence,
intent, and lifetime are part of 019's contract with downstream
consumers.

### Invariants

- The alias is `=` (a name binding), not a subclass. Subclassing
  would introduce a divergent class identity (`isinstance(x, SatelliteWebRTCAdapter) != isinstance(x, AivgSatelliteAdapter)` for subclass instances), defeating the
  zero-divergence promise.
- The alias is exported from the same module as the canonical
  name (`aivg_core.adapter`). It is NOT a separate compat module.
- The docstring names the removal release explicitly so the
  CHANGELOG and the alias agree.

---

## Out of scope (positive enumeration)

To make the "no wire change" promise auditable, 019 explicitly
does NOT add, remove, or modify any of:

- REST endpoints under `/satellite/*` or `/aivg/*`
- WebSocket frame shapes on `/satellite/ws`
- Config block keys, nesting, or defaults under `satellite:` in
  `~/.hermes/config.yaml`
- Environment variable names beginning with `SATELLITE_` or
  `AIVG_`
- Contract version envelope (`aivg --contract-version` output)
- `Platform.LOCAL` enum value used in `SessionSource`
- `AgentPlatform`, `MediaTransport`, or `SetupCapability`
  Protocol surfaces
- Persistent state in `~/.aivg/state.json`, OTA manifests, or
  per-device API key files
- ESPHome native API transport surface (feature 017's port 6053,
  proto wire format)
- The `@aivg/sat-sdk` TypeScript SDK (no version bump, no source
  edits)
- The `@aivg/sat-sdk` CHANGELOG (no entry for 019)

This enumeration is the literal data model of "what didn't
change," and the quickstart's diff-harness verifies it.
