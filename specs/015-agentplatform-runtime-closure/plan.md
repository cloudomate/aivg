# Implementation Plan: AgentPlatform Runtime Closure

**Branch**: `015-agentplatform-runtime-closure` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/015-agentplatform-runtime-closure/spec.md`

## Summary

Close the AgentPlatform Protocol seam at the runtime layer of `aivg_core`.
Three `# AgentPlatform-coupling-TODO` markers in `adapter.py`,
`webrtc/session.py`, and `webrtc/signaling.py` import `HermesBridge`
symbolically; we delete those imports, change three constructors to
take an `AgentPlatform` instance, replace five call sites in
`session.py` with calls to the canonical Protocol verbs (`transcribe`,
`agent_step`/`agent_stream`, `synthesize`, `endpoint`), and move
`HermesBridge` to be a plugin-internal implementation detail behind a
new `HermesAgentPlatform` adapter that satisfies the canonical
Protocol surface.

Two minor signature alignments come along for the ride (documented as
ADRs R-1 and R-2 in [research.md](./research.md)): the Protocol's
`endpoint` return type is upgraded from bare `bool` to a small
platform-neutral `EndpointResult` dataclass (Hermes's existing
`EndpointSignal` lifted into `platforms/base.py`), and `agent_step`
adopts a consistent empty-reply convention so the loop can detect
"empty / tool-only reply" without introspecting platform-specific
types.

The visible effect: a fake non-Hermes plugin satisfying
`AgentPlatform` drives one complete voice turn end-to-end through
the satellite adapter; the existing live Hermes deployment (proven
through feature 013, exercised live in feature 014's electron-test)
continues to work byte-equivalently with no client change and within
±10 % of feature-010's latency baseline.

## Technical Context

**Language/Version**: Python 3.11+ (matches existing project setup; no version bump).

**Primary Dependencies**: NO new runtime dependencies. Feature uses only the existing `aivg_core` + `aivg_cli` modules plus the stdlib + pytest test stack already in `pyproject.toml`.

**Storage**: None added. The existing `~/.aivg/` registry + Hermes's `~/.hermes/` config remain untouched.

**Testing**: pytest, pytest-asyncio (existing). Two new test files (`tests/unit/test_no_hermes_imports_in_core.py`, `tests/integration/test_voice_loop_platform_agnostic.py`); ~3 existing test files get small edits where fixtures hold a `HermesBridge` reference that now flows through `HermesAgentPlatform` — test-helper migration only, semantics unchanged.

**Target Platform**: Linux (production gateway) + macOS (development). No new platform support added.

**Project Type**: Internal Python library refactor inside an existing monorepo. No new top-level directory.

**Performance Goals**:

- Post-refactor median end-of-utterance → first-audio-out latency MUST be within ±10 % of feature-010's baseline (SC-003). The refactor is structural; one extra method-call indirection through `HermesAgentPlatform` is well under 10 %.
- Test suite total wall time MUST NOT grow by more than 10 % (266 currently passing; the new tests add ~10-15 cases).

**Constraints**:

- ZERO public wire-surface change (SC-007). `aivg --contract-version` stays `1.0.0`.
- ZERO `@aivg/sat-sdk` change. The TS SDK is a wire-only consumer.
- ZERO Hermes-import in `src/aivg_core/` outside `src/aivg_core/platforms/hermes/` (SC-006, grep-enforced).
- Three `# AgentPlatform-coupling-TODO` markers gone (SC-001, grep-enforced).
- Constitution v2.0.1 / Principle IV unchanged. The `EndpointResult` lift is a structural reorganisation (the existing `EndpointSignal` dataclass moves modules), not a principle-level amendment.

**Scale/Scope**:

- ~5 production source files modified (`adapter.py`, `webrtc/session.py`, `webrtc/signaling.py`, `platforms/base.py`, `platforms/hermes/__init__.py`, `platforms/hermes/bridge.py`); 1 new (`platforms/hermes/platform.py`).
- ~3 test files edited (places holding a `HermesBridge` in fixtures); ~3 new (`test_no_hermes_imports_in_core.py`, `test_no_coupling_todo_markers.py`, `test_voice_loop_platform_agnostic.py`).
- ~250-400 LoC source net + ~150-200 LoC tests. The compression in the loop (single `_platform` field replacing `_bridge` / fallback paths) roughly cancels the new wrapper code.

## Constitution Check

Evaluated against AIVG Constitution v2.0.1 (`.specify/memory/constitution.md`).

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) — ✅ PASS

The refactor *removes* the loop's direct dependency on Hermes — it
does not add STT/TTS/agent logic to the satellite. The verbs the loop
consumes (`transcribe`, `agent_step`, `synthesize`, `endpoint`)
delegate to the active platform plugin's implementation, which in
Hermes's case continues to call Hermes's real STT/TTS providers
unchanged. Principle I rule: "A satellite or the WebRTC adapter MUST
NOT instantiate Whisper, Piper, or any STT/TTS engine directly.
STT/TTS MUST be reached only through the active agent platform's
provider interfaces" — this feature *enforces* that rule at the
import level (`grep` SC-006 binding gate).

### II. Generic Four-Plane Contract — ✅ PASS

The refactor sits below the four-plane contract — it cleans up *how*
the runtime voice-plane delegates to the active platform. The four
planes' wire shapes (WS / REST) are unchanged (SC-007). The shared
data models (`SatelliteState`, `SatelliteConfig`, `LogEntry`) are not
touched.

### III. Separate Control and Voice Connections — ✅ PASS

The refactor does not alter the dual-connection invariant. The
control-plane WS and per-session voice PeerConnection lifecycles are
unchanged. The signaling service merely receives an `AgentPlatform`
instance instead of a `HermesBridge` reference — its constructor and
externally-visible behaviour are unchanged.

### IV. Reuse the Upstream Agent Platform, Don't Rebuild — ✅ PASS (this is the feature)

This feature *closes* Principle IV at the runtime layer. Before:
`adapter.py`, `webrtc/session.py`, `webrtc/signaling.py` import
`HermesBridge` directly, violating "Adding a new platform MUST NOT
require changes anywhere else in the satellite core." After: those
three files import only the platform-neutral `AgentPlatform` type
from `aivg_core/platforms/base.py`; the Hermes plugin's `PLATFORM`
is loaded via the existing `PluginRegistry.load("hermes")` path.

Binding rules this plan commits to:

- The voice loop calls platform verbs by their canonical Protocol
  names (`transcribe`, `agent_step`, `synthesize`, `endpoint`). The
  Hermes-bridge-flavoured names (`stt_transcribe`, `tts_synthesize`,
  `detect_endpoint`, `agent_turn`) MUST NOT appear in any caller
  under `aivg_core/webrtc/` or `aivg_core/adapter.py` (SC-005/SC-006).
- `HermesBridge` becomes a plugin-internal symbol. It MUST NOT be
  re-exported from `aivg_core/platforms/hermes/__init__.py` and MUST
  NOT be referenced by name from outside `aivg_core/platforms/hermes/`
  (FR-008, FR-011).
- All Hermes-specific config access (`~/.hermes/config.yaml`,
  `~/.hermes/.env`, Hermes's session DB) stays inside the Hermes
  plugin (FR-010 — already true today; this feature preserves it).
- A hypothetical second platform plugin under
  `aivg_core/platforms/<name>/` works without any change outside
  that directory (SC-010 — tree-shake test).

### V. Research-Backed, Constraint-Driven Decisions — ✅ PASS

Two design decisions in this feature require explicit ADRs:

- **R-1**: `endpoint` return type — bare `bool` (constitution literal)
  vs. richer `EndpointResult` (preserves `speech_started` field the
  loop consumes). See [research.md §R-1](./research.md).
- **R-2**: `agent_step` empty-reply detection — `AgentReply.is_empty`
  is Hermes-internal; protocol's streaming `AsyncIterator[str]`
  returns no deltas for empty replies, so the loop detects empty by
  accumulated-string-is-empty rather than introspecting a
  plugin-specific type.

Both decisions are validated by binding gates (SC-002 live Hermes
parity, SC-003 latency parity, SC-004 echo-platform integration
test). Principle V's load-test mandate applies to constrained
devices (RPi / ESP32) and is N/A to this server-side refactor.

### Overall Gate Result

**PASS** — no violations to justify in Complexity Tracking.

### Post-Design Re-Check (after Phase 1)

After producing [research.md](./research.md), [data-model.md](./data-model.md),
[contracts/agent-platform.md](./contracts/agent-platform.md), and
[quickstart.md](./quickstart.md), the gates are re-evaluated:

- **I. Thin Satellite** — strengthened, not weakened. The contract
  (§ 2) names the platform-neutral verbs the loop is permitted to
  call; the grep gates (quickstart § 1) make any future regression
  CI-detectable.
- **II. Generic Four-Plane Contract** — unchanged. The contract's § 6
  ("wire-surface invariance") makes FR-014 a binding test
  (`test_wire_surface_unchanged`) rather than a hope.
- **III. Separate Control/Voice Connections** — unchanged; the
  refactor is below this layer.
- **IV. Reuse Upstream Agent Platform** — this is the feature. The
  contract's § 1 (plugin discovery via `PLATFORM` symbol) and § 5
  (validation contract) together make Principle IV runtime-enforced.
  Quickstart § 7 demonstrates a non-Hermes plugin driving the same
  loop without touching `aivg_core`.
- **V. Research-Backed Decisions** — R-1 (EndpointResult shape) is
  pinned in data-model § 2 and contract § 2.4; R-2 (empty-reply via
  accumulated-string) is pinned in contract § 2.2. Both are
  exercised by contract tests (test 5 + 7 in the contract table).

**PASS — no new violations introduced by Phase 1 design.**

## Project Structure

### Documentation (this feature)

```text
specs/015-agentplatform-runtime-closure/
├── plan.md                    # This file (/speckit-plan output)
├── research.md                # Phase 0 — R-1 + R-2 ADRs
├── data-model.md              # Phase 1 — Protocol shape + entity types
├── quickstart.md              # Phase 1 — how to verify locally
├── contracts/
│   └── agent-platform.md      # Phase 1 — canonical AgentPlatform contract
└── tasks.md                   # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
src/aivg_core/
├── platforms/
│   ├── base.py                       # Protocol surface — alignment in this feature
│   │                                 # (lift EndpointResult into the module)
│   └── hermes/
│       ├── __init__.py               # Export PLATFORM only — NO HermesBridge re-export
│       ├── bridge.py                 # HermesBridge stays HERE; plugin-internal only
│       └── platform.py               # NEW — HermesAgentPlatform: AgentPlatform-conforming
│                                     # wrapper mapping canonical verbs onto bridge methods.
├── adapter.py                        # Remove HermesBridge import; take AgentPlatform.
│                                     # The _SatellitePlatformAdapter factory holds the
│                                     # active AgentPlatform instance and constructs the
│                                     # voice session + signaling against it.
└── webrtc/
    ├── session.py                    # Remove HermesBridge import; take AgentPlatform.
    │                                 # Five call sites swap to Protocol verbs.
    └── signaling.py                  # Remove HermesBridge import; take AgentPlatform.

tests/
├── unit/
│   ├── test_no_hermes_imports_in_core.py    # NEW — grep-enforced regression gate (SC-006)
│   ├── test_no_coupling_todo_markers.py     # NEW — grep-enforced (SC-001)
│   └── (existing fake-bridge tests stay — semantics unchanged)
├── integration/
│   ├── test_agent_platform_seam.py          # existing (feature 011) — loader-only stays
│   ├── test_voice_loop_platform_agnostic.py # NEW — turn against echo platform (SC-004)
│   ├── test_voice_turn_latency.py           # existing (feature 010) — no change; SC-003
│   └── (existing Hermes-integration tests stay)
└── fixtures/platforms/echo/
    └── __init__.py                          # existing — verbs already conform; minor
                                             # signature alignment may be needed for R-1.

clients/electron-test/                       # NO change (SC-002 binds via 0.1.3+ consumer)
sdks/typescript/                             # NO change (SC-007 binds — no wire change)
```

**Structure Decision**:

The refactor is **strictly internal** to `src/aivg_core/`. No new
top-level directories, no public API surface added.

1. The new `src/aivg_core/platforms/hermes/platform.py` is the
   plugin-internal wrapper that maps the canonical Protocol verbs
   (`transcribe`, `agent_step`, `synthesize`, `endpoint`) onto
   Hermes's existing `HermesV013Bridge` methods (`stt_transcribe`,
   `agent_turn`/`agent_stream`, `tts_synthesize`, `detect_endpoint`).
   Putting the wrapper in its own file keeps the existing `bridge.py`
   git history intact and signals the architectural layering: bridge
   = low-level Hermes provider calls; platform = AgentPlatform
   contract.
2. `HermesBridge` (Protocol type) + `HermesV013Bridge` (impl) +
   `UnboundHermesBridge` (test stub) all stay in `bridge.py` as
   plugin-internal symbols. Nothing outside `aivg_core/platforms/hermes/`
   imports them. The plugin's `__init__.py` re-exports ONLY
   `PLATFORM` (the AgentPlatform instance) and the `SETUP`
   capability — `HermesBridge` is removed from `__all__`.

## Complexity Tracking

No constitution violations to justify. The plan is intentionally
simple: focused refactor of one seam, two ADRs captured in
research.md, three grep-based regression-gate tests, one
echo-platform integration test.

| Choice | Why | Alternative rejected |
| --- | --- | --- |
| `HermesAgentPlatform` in a new file (`platform.py`) | Keeps `bridge.py` git history clean; signals the layering. | Inline the wrapper into `bridge.py`. Rejected: muddies the file and obscures which symbol is the protocol surface vs internal impl. |
| Lift `EndpointSignal` → `EndpointResult` in `platforms/base.py` | The loop genuinely needs both `end_of_utterance` and `speech_started`; richer return type is the smallest constitutional refinement (semantic-equivalent to the principle's "end_of_utterance?" wording). | Drop `speech_started` and let the loop derive it from raw PCM RMS. Rejected: duplicates VAD logic the platform already runs server-side and forks behaviour across plugins. |
| Loop calls `agent_step` and shape-detects optional `agent_stream` | Matches spec preference (P3 / FR-006). | Make `agent_stream` a required Protocol method. Rejected: would force every future plugin to implement both, even text-only ones. |

## Implementation Outcome

Landed 2026-05-20. See [tasks.md](./tasks.md) and
[baseline.md](./baseline.md) for the per-task receipts.

**Code delta**:

- 5 production source files modified
  ([`platforms/base.py`](../../src/aivg_core/platforms/base.py),
  [`platforms/hermes/__init__.py`](../../src/aivg_core/platforms/hermes/__init__.py),
  [`platforms/hermes/bridge.py`](../../src/aivg_core/platforms/hermes/bridge.py),
  [`webrtc/session.py`](../../src/aivg_core/webrtc/session.py),
  [`webrtc/signaling.py`](../../src/aivg_core/webrtc/signaling.py),
  [`adapter.py`](../../src/aivg_core/adapter.py),
  [`__main__.py`](../../src/aivg_core/__main__.py))
- 1 new production file:
  [`platforms/hermes/platform.py`](../../src/aivg_core/platforms/hermes/platform.py)
  (the `HermesAgentPlatform` wrapper)
- 4 new test files:
  [`tests/unit/test_no_coupling_todo_markers.py`](../../tests/unit/test_no_coupling_todo_markers.py),
  [`tests/unit/test_no_hermes_imports_in_core.py`](../../tests/unit/test_no_hermes_imports_in_core.py),
  [`tests/contract/test_agent_platform_runtime_contract.py`](../../tests/contract/test_agent_platform_runtime_contract.py),
  [`tests/integration/test_voice_loop_platform_agnostic.py`](../../tests/integration/test_voice_loop_platform_agnostic.py),
  [`tests/integration/test_agent_stream_optional.py`](../../tests/integration/test_agent_stream_optional.py)

**Test count delta**: full suite went from 267 → 290 tests (+23 new
binding gates). 4/4 consecutive `pytest tests/` runs after the rewire:
**290 passed, 1 xpassed, 0 failed**.

**Constitution gates**:

- SC-001 ✓ `rg '# AgentPlatform-coupling-TODO' src/aivg_core/` → 0 (was 3 markers)
- SC-006 ✓ `rg 'from .*\.platforms\.hermes\.' src/aivg_core/` outside the plugin → 0 (was 4)
- SC-004 ✓ `test_voice_loop_platform_agnostic.py` drives one voice turn against the echo platform end-to-end; no Hermes symbol imported in the test
- SC-005 ✓ all pre-refactor tests still pass; no Hermes-specific test
  was altered semantically
- SC-010 ✓ tree-shake: `test_loading_echo_does_not_import_hermes_plugin`
  in `test_voice_loop_platform_agnostic.py` proves a non-Hermes plugin
  can load and run without importing the Hermes plugin module

**Deferred to next host visit**:

- SC-002 (live electron-test smoke) — quickstart § 6 / tasks T032-T033
- SC-003 (live latency parity ±10 %) — quickstart § 5 / task T034
- SC-007 (`aivg --contract-version` = `1.0.0` unchanged) — task T049

  These three are the host-only gates that bind the refactor to live
  Hermes runtime; the wire-surface invariance (FR-014 / contract § 6)
  was preserved by inspection: this feature touched zero
  REST/WebSocket handlers and zero TS SDK code.

**Notable design decisions during implementation**:

- Lifted `AllProvidersUnavailable` from
  `aivg_core.platforms.hermes.bridge` to `aivg_core.platforms.base`
  (plugin-neutral base exception). The bridge re-exports it so every
  existing test import path keeps working verbatim — SC-006 grep gate
  is then trivially satisfied for the satellite core's
  ``from ..platforms.base import AllProvidersUnavailable``.
- Decided **not** to add new `agent_text_deltas` / `detect_endpoint_frame`
  helpers to `HermesV013Bridge` (the original plan's T007/T008).
  Instead `HermesAgentPlatform.agent_step` yields the bridge's
  `agent_turn` reply as a single delta (the Hermes path almost always
  takes `agent_stream` anyway), and `HermesAgentPlatform.endpoint`
  wraps the single frame in a one-element async generator before
  calling the bridge's existing stream-style `detect_endpoint`. Net
  reduction in plugin surface area.
- Fixed a pre-existing transport-EOF race in
  `Session._handle_turn`: when the pipeline finished first, the
  cancelled barge-in watcher could silently swallow an inbound
  `None` (transport closed), causing the next
  `_collect_utterance.receive()` to block forever. Added a sticky
  `_eof_seen` flag and code in the cancel-cleanup path to re-stash
  any consumed real frame or signal the EOF. Verified by 4
  consecutive green full-suite runs against the 12-way concurrency
  test (`test_sc005_ten_plus_concurrent_sessions`).
- `FakeHermesBridge` now dual-implements `HermesBridge` *and* the
  canonical `AgentPlatform` Protocol (added `name`, `startup`,
  `shutdown`, `transcribe`, `agent_step`, `synthesize`, `endpoint`
  alongside the existing bridge methods). This let every integration
  test that previously constructed `Session(bridge=FakeHermesBridge())`
  keep its fixture unchanged — just one positional `bridge=` →
  `platform=` rename in the adapter-sites unit test.
