# Implementation Plan: Internal plugin-name rename — `satellite_webrtc` → `aivg_satellite`

**Branch**: `019-transport-plane-rename` · **Date**: 2026-05-21 · **Spec**: [spec.md](./spec.md)

## Summary

Rename the Hermes platform-plugin registration name from
`satellite_webrtc` (pre-rebrand, plus a misleading `_webrtc` suffix
after feature 017 added the ESPHome transport under the same plugin)
to `aivg_satellite`. Add a load-time conflict detector so the
post-019 entry-point plugin refuses to register silently alongside a
still-vendored pre-019 bundled `satellite_webrtc/` plugin directory
— the exact silent-shadow trap that consumed hours of today's
deploy session.

The 2026-05-21 `/speckit-clarify` session walked the original scope
back from "rename all four surfaces (plugin name + REST routes +
config block + env vars) with deprecation aliases and an
`@aivg/sat-sdk 0.2.0` major" to "plugin name only." The reasoning is
domain-vocabulary: "satellite" is the correct noun for the resource
being managed (the device IS a satellite), not a pre-rebrand brand
prefix. `/satellite/list` means "list the satellites." Renaming to
`/aivg/list` would mean "list the AIVGs," which is nonsense. The
narrower scope keeps every wire surface byte-identical to pre-019
and collapses the feature to ~25 LoC source + ~80 LoC tests.

Result: a small, low-risk maintenance change. Constitution gates all
pass without exception. No contract bump, no SDK release, no
migration verb, no deprecation warnings. The change is binary
("rename complete" / "rename incomplete") and the conflict
detector turns today's silent-failure mode into a loud one.

## Technical Context

**Language/Version**: Python 3.11+ (matches `aivg_core` baseline;
same runtime as the existing gateway).

**Primary Dependencies**:

- `hermes-agent` (already in the deployment venv) — provides the
  `ctx.register_platform(name=…)` API that 019 mutates, and the
  `hermes_cli.plugins.get_plugin_manager()` API the conflict
  detector queries.
- No new PyPI dependencies.
- No new system packages.

**Storage**: None. The plugin registration name is a runtime string,
not persisted to disk. The conflict detector reads the existing
`~/.hermes/hermes-agent/plugins/platforms/` filesystem layout via
the Hermes plugin manager's already-loaded manifest list.

**Testing**: pytest (existing harness). New tests:

- `tests/unit/test_plugin_registration_name.py` — assert the
  entry-point plugin registers under `aivg_satellite` (not
  `satellite_webrtc`) and that the gateway log line shape carries
  the new name. Pure unit-level using a stubbed `ctx`.
- `tests/unit/test_conflict_detector.py` — drive `register()` with
  a fake Hermes plugin manager that reports both the entry-point
  plugin AND a vendored bundled plugin under the legacy directory
  name; assert `register()` raises (or refuses) with the expected
  error message naming the directory + cleanup verb.
- `tests/unit/test_no_conflict_quiet_path.py` — same `register()`
  with only the entry-point plugin discovered; assert zero
  conflict logging fires (the detector stays silent on the common
  case).

**Target Platform**: Same as the existing gateway — Linux + macOS
userspace, Python 3.11+, runs anywhere `aivg_core` runs today.
No firmware or device-side code is touched.

**Project Type**: Library / service component. Edits to existing
`aivg_core` package; no new top-level modules.

**Performance Goals**:

- Conflict detector latency: < 100 ms per gateway start (single
  filesystem stat or single plugin-manager list query).
- Zero impact on steady-state gateway latency, throughput, or
  voice-turn timings — the renamed string is read once at
  `register()` time and never on the hot path.

**Constraints**:

- Wire-surface invariance: EVERY pre-019 wire surface
  (`/satellite/*` REST + WS paths, `satellite:` config block,
  `SATELLITE_*` env vars, contract version `1.1.0`,
  `aivg --contract-version` output bytes) MUST remain byte-identical
  post-019. Verified by an automated diff harness in
  `quickstart.md`.
- Constitutional Principle II: this binding is the literal text of
  Principle II's "single contract" rule. 019's narrowed scope
  exists exactly to preserve it.
- Maintainability bar: a single developer can complete the rename,
  build, run the test suite, and ship in one sitting.

**Scale/Scope**: ~25 LoC source net + ~80 LoC tests. 8 source files
touched, all rename-only edits except for the plugin entry-point's
`register()` which gains the conflict-detection helper.

## Constitution Check

Evaluated against AIVG Constitution **v2.0.1**
(`.specify/memory/constitution.md`).

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) — ✅ PASS

Feature 019 touches no STT, TTS, agent-loop, endpointing, or
provider-layer code anywhere. The only files changed are
`adapter.py`, `__main__.py`, `platforms/base.py` (docstring),
`platforms/hermes/setup.py` (constant rename), and the
`platforms/hermes/plugin_entrypoint/` shim. None of these own any
speech intelligence; they own only the plugin-registration and
adapter-wiring path. Principle I's "STT/TTS reached only through
the active platform's provider interfaces" rule is unaffected.

### II. Generic Four-Plane Contract — ✅ PASS

The four-plane contract is binding-protected by 019's scope
reduction. The control plane (REST `/satellite/*`, WS
`/satellite/ws`), voice plane (port 8644), capture/endpointing,
and playback — every wire surface across every plane stays
byte-identical to pre-019. The contract version field
(`1.1.0`) does not move. SC-002 in spec.md is the binding gate
for this: a diff-harness comparison of pre-019 vs. post-019
captures over the same scripted client flow.

### III. Separate Control and Voice Connections — ✅ PASS

No transport surface changes. The control WS continues to be
served on the management port; the voice plane continues to use
the signaling site on the WebRTC port; the ESPHome native API
transport (feature 017) continues on port 6053 unchanged. The
single-connection ESPHome deviation already justified in feature
017's Complexity Tracking carries through.

### IV. Reuse the Upstream Agent Platform, Don't Rebuild — ✅ PASS

This is the principle whose seam 019 touches. The seam itself
(`AgentPlatform` Protocol, `PluginRegistry`,
`SetupCapability`) is unchanged. The plugin-entry-point shim
(`aivg_core.platforms.hermes.plugin_entrypoint.adapter.register`)
already exists exactly to call `ctx.register_platform(name=…)`
on the Hermes platform-registry; 019 changes the `name=` argument
and adds a conflict-detection helper invoked inside the same
`register()` body. ZERO modifications to `src/aivg_core/platforms/`
*beyond* the Hermes plugin shim itself (which is the documented
integration surface), and ZERO modifications to any other
platform plugin (OpenClaw stub stays untouched).

The conflict detector queries Hermes's own `get_plugin_manager()`
API rather than re-implementing plugin discovery — directly
honors Principle IV's "reuse the platform's primitives" rule for
the discovery problem.

### V. Research-Backed, Constraint-Driven Decisions — ✅ PASS

Four ADRs in [research.md](./research.md) carry the binding
research:

- **R-1**: how the conflict detector observes the legacy plugin
  (Hermes plugin manager API vs. filesystem scan).
- **R-2**: what `register()` does on conflict (raise vs.
  no-op-with-log vs. check_fn=False).
- **R-3**: whether to rename the Python class
  `SatelliteWebRTCAdapter` → `AivgSatelliteAdapter` in addition to
  the registration name (with a back-compat alias for one
  release).
- **R-4**: what string `get_chat_info()` returns for the
  `platform` field (was `"satellite_webrtc"`).

Principle V's "load-test before declared shipped" rule applies
trivially: the change runs on the same gateway path exercised by
the 290+ existing tests; the new test set adds parity assertions
for the renamed identifier and the conflict-detection error
shape.

### Overall Gate Result

**PASS** on all five principles, no exceptions, no complexity
tracking entry needed. The clarification-driven scope reduction is
exactly what keeps every gate clean.

### Post-Design Re-Check (after Phase 1)

After producing [research.md](./research.md),
[data-model.md](./data-model.md), and
[quickstart.md](./quickstart.md), the gates are re-evaluated:

- **I. Thin Satellite** — unchanged. Phase 1 added no
  STT/TTS/agent/endpointing code.
- **II. Generic Four-Plane Contract** — strengthened. The
  quickstart's diff-harness step makes the wire-surface invariance
  a literal byte-comparison gate.
- **III. Separate Control/Voice Connections** — unchanged.
- **IV. Reuse Upstream Agent Platform** — strengthened. R-1 binds
  the conflict detector to `hermes_cli.plugins.get_plugin_manager`
  rather than a custom directory scanner, reinforcing "reuse the
  platform's primitives."
- **V. Research-Backed Decisions** — R-1, R-2, R-3, R-4 all have
  explicit rationale + rejected alternatives.

**PASS — no new violations introduced by Phase 1 design.**

## Project Structure

### Documentation (this feature)

```text
specs/019-transport-plane-rename/
├── plan.md                    # This file (/speckit-plan output)
├── research.md                # Phase 0 — 4 ADRs (R-1..R-4)
├── data-model.md              # Phase 1 — Plugin Registration Name + Conflict Detector
├── quickstart.md              # Phase 1 — verify locally + the diff-harness gate
├── contracts/                 # Phase 1 — empty (no external interfaces touched)
└── tasks.md                   # Phase 2 — generated by /speckit-tasks
```

No `contracts/` payload: 019 has no external-interface surface to
document. Every external contract (REST schema, WS frames, config
keys, env vars, contract version envelope) is invariant. The
`/contracts/` directory is left empty as a positive signal of "no
new contract."

### Source Code (repository root)

```text
src/aivg_core/
├── adapter.py                              # — rename class + literals
│                                           #   - class SatelliteWebRTCAdapter
│                                           #     → AivgSatelliteAdapter (+ alias)
│                                           #   - name = "satellite_webrtc"
│                                           #     → "aivg_satellite"
│                                           #   - line 98 error message string
│                                           #   - line 277 get_chat_info platform value
│                                           #   - line 295 PlatformEntry(name=…)
│                                           #   - line 300 plugin_name in PlatformEntry
│                                           #   - module + class docstrings
├── __main__.py                             # — import + dev banner string
├── platforms/
│   ├── base.py                             # — docstring reference (cosmetic)
│   └── hermes/
│       ├── setup.py                        # — keep LEGACY_PLUGIN_NAME constant;
│       │                                   #   add CANONICAL_PLUGIN_NAME = "aivg_satellite";
│       │                                   #   keep all setup.py behaviour unchanged
│       │                                   #   except where it logs the plugin name
│       └── plugin_entrypoint/
│           ├── __init__.py                 # — docstring
│           └── adapter.py                  # — name="satellite_webrtc"
│                                           #     → name="aivg_satellite"
│                                           #   — add conflict detector call BEFORE
│                                           #     ctx.register_platform(...)
│                                           #   — docstring
│
└── (everything else: UNCHANGED)

tests/
├── unit/
│   ├── test_plugin_registration_name.py    # NEW (asserts new name)
│   ├── test_conflict_detector.py           # NEW (asserts loud failure)
│   ├── test_no_conflict_quiet_path.py      # NEW (asserts silent success)
│   └── test_adapter_sites.py               # — update import:
│                                           #     SatelliteWebRTCAdapter
│                                           #     → AivgSatelliteAdapter
│                                           #   (back-compat alias keeps the
│                                           #   old import working — test
│                                           #   the new name explicitly)
└── fixtures/
    └── platforms/echo/setup.py             # — rename plugin_target dir from
                                                "satellite_webrtc" to
                                                "aivg_satellite" (the fixture
                                                exercises the canonical install
                                                path; legacy migration is
                                                tested separately via 013's
                                                existing LEGACY_PLUGIN_NAME
                                                paths)
```

**Structure Decision**:

The feature is **strictly internal** in source structure. No new
files in `src/`. Eight existing files touched, six of them
rename-only string edits. The only structural addition is the
conflict-detection helper inside the plugin entry-point's
`register()` and three new test files in `tests/unit/`.

1. **No new top-level modules.** A purely-internal rename should
   not create new package directories.
2. **`SatelliteWebRTCAdapter` keeps a back-compat alias** in
   `adapter.py`: `SatelliteWebRTCAdapter = AivgSatelliteAdapter`.
   This costs one line and avoids breaking any external Python
   importer (e.g., a downstream library that depends on the old
   class name). Documented in research.md R-3 as a one-release
   alias; future removal is a separate trivial PR.
3. **`LEGACY_PLUGIN_NAME` in `setup.py` is kept**, since feature
   013's setup CLI already uses it to detect and migrate the
   pre-rebrand vendored directory. 019 adds a sibling
   `CANONICAL_PLUGIN_NAME = "aivg_satellite"` for the conflict
   detector and any future cleanup logic to share.
4. **No new tests dir, no new fixtures dir.** Three new unit test
   files in the existing `tests/unit/` are sufficient — the
   change is small enough that integration-level tests would be
   redundant against the unit-level assertions plus the existing
   suite.

## Complexity Tracking

No constitutional violations. No complexity-tracking entries
needed. The clarification-driven scope reduction is exactly the
record of which alternatives were rejected:

| Choice | Why | Alternative rejected |
| --- | --- | --- |
| Rename plugin registration name only | "satellite" is the correct domain noun on routes / config / env vars; the brand prefix and the `_webrtc` suffix are the only legitimate wrong parts of `satellite_webrtc` | Original 019 scope: rename routes, config block, env vars, ship `@aivg/sat-sdk 0.2.0` major, build deprecation machinery and migration verb. Rejected because routes describe resources and "satellite" IS the resource. |
| Conflict detector raises from `register()` | Loud failure prevents the silent-shadow trap we hit during today's deploy | Silent skip with log: rejected because today's bug WAS the silent skip. Operator never noticed for hours. |
| Conflict detector uses Hermes plugin manager API | Reuses the same data Hermes already loaded; honors Principle IV's "reuse, don't rebuild" | Custom directory scanner: rejected because Hermes may relocate or rename its bundled-plugin scan logic in a future release; we'd carry a parallel scanner that drifts. |
| Keep `LEGACY_PLUGIN_NAME` constant; add `CANONICAL_PLUGIN_NAME` sibling | Feature 013's setup CLI already uses LEGACY_PLUGIN_NAME for cleanup logic; sibling constant lets the conflict detector share the same source of truth | Inline string literals: rejected because two callers (setup CLI + conflict detector) referring to the same identifier from two literals is the classic drift bug. |
| Class rename + back-compat alias | Clarity for new readers without breaking external importers | Rename without alias: rejected because anyone with an `from aivg_core.adapter import SatelliteWebRTCAdapter` line breaks on upgrade. One-line alias eliminates the risk. |