# Feature Specification: AgentPlatform Runtime Closure

**Feature Branch**: `015-agentplatform-runtime-closure`
**Created**: 2026-05-20
**Status**: Draft
**Input**: User description: "rewire the voice loop to depend on the AgentPlatform Protocol (constitution v2.0.0 Principle IV runtime closure). Delete the three `# AgentPlatform-coupling-TODO` markers in webrtc/session.py, webrtc/signaling.py, adapter.py. The voice loop and signaling service take an `AgentPlatform` instance (loaded via PluginRegistry) instead of importing HermesBridge directly. HermesBridge becomes a plugin-internal implementation detail of the hermes platform plugin. Goal: a non-Hermes platform plugin (OpenClaw or any future one) can satisfy the AgentPlatform Protocol and the voice loop runs against it without touching aivg_core. Out of scope: shipping an actual OpenClaw plugin, C++ SDK (feature 016), changes to the public WS/REST wire surface, changes to the TS SDK. AgentPlatform.agent_step is the canonical name; HermesBridge maps internally. Keep both: a baseline agent_step and an optional agent_stream for delta-capable platforms. Canonical verbs: transcribe(audio) → text, synthesize(text) → audio, endpoint(audio_frame) → end_of_utterance?, agent_step(text, session) → reply_stream."

## Background & Motivation

AIVG Constitution v2.0.0 Principle IV defines the satellite system as
**agent-platform-agnostic**: the runtime voice loop, signaling service,
and adapter consume only the platform-neutral
[`AgentPlatform` Protocol](../../src/aivg_core/platforms/base.py), and
each upstream platform (Hermes v1, OpenClaw planned) ships its own
plugin under `aivg_core/platforms/<name>/` satisfying that Protocol.

This is closed at the **deploy** layer (feature 013 added the
`SetupCapability` plugin seam; `aivg setup` installs the Hermes plugin
without importing any Hermes names) and at the **satellite-client**
layer (feature 014's `@aivg/sat-sdk` imports zero Hermes-specific
names). It is NOT closed at the **runtime voice loop**:
[adapter.py:18](../../src/aivg_core/adapter.py#L18) +
[adapter.py:127](../../src/aivg_core/adapter.py#L127),
[webrtc/session.py:23](../../src/aivg_core/webrtc/session.py#L23), and
[webrtc/signaling.py:17](../../src/aivg_core/webrtc/signaling.py#L17)
each import `HermesBridge` symbolically with a tracking comment:

```python
from .platforms.hermes.bridge import HermesBridge  # AgentPlatform-coupling-TODO
```

These three markers are the "runtime debt" line left behind in features
011/012. Without their closure, a non-Hermes platform plugin (OpenClaw
or any third-party) literally cannot drive the satellite voice loop —
the loop would NameError before the plugin's first method was called.

This feature is the focused constitutional-debt repayment whose visible
effect is: a fake non-Hermes plugin satisfying `AgentPlatform` can drive
one complete voice turn end-to-end against the in-process voice loop,
**and** the existing live Hermes deployment (proven through feature 013
+ feature 014) continues to work byte-equivalently. It does not add
OpenClaw, does not change the public wire surface, and does not touch
the TypeScript SDK.

## User Scenarios & Testing *(mandatory)*

### User Story 1 — A non-Hermes platform plugin drives the voice loop without changing aivg_core (Priority: P1) 🎯 MVP

A developer building a new agent-platform plugin (OpenClaw, a vendor
integration, anything) writes their plugin under
`aivg_core/platforms/<name>/` with a module-level `PLATFORM` satisfying
`AgentPlatform`. They run the voice loop pointed at their plugin and
one full STT → agent → TTS turn completes — without touching
`aivg_core/adapter.py`, `aivg_core/webrtc/*`, or any Hermes-specific
code.

**Why this priority**: this is the entire feature. Every other story
is a binding gate on this one.

**Independent Test**: SC-001 — the existing
`tests/integration/test_agent_platform_seam.py` (the echo-platform
fixture used for the *load* path) is extended with a voice-loop
integration test that constructs a `Session` against the echo
`AgentPlatform` (NOT against `HermesBridge`/`FakeHermesBridge`) and
drives one turn to completion. Grep verifies `grep -rE
'# AgentPlatform-coupling-TODO' src/aivg_core/` returns zero matches.

**Acceptance Scenarios**:

1. **Given** the echo `AgentPlatform` fixture under `tests/fixtures/platforms/echo/` exposing the four protocol verbs (`transcribe`, `agent_step`, `synthesize`, `endpoint`), **When** the satellite adapter is constructed with that platform instance (no `HermesBridge` import path), **Then** the adapter starts, accepts a fake WebRTC offer, drives one turn through STT → agent → TTS, and tears down cleanly.
2. **Given** the running test suite, **When** `grep -rE '# AgentPlatform-coupling-TODO' src/aivg_core/` is executed, **Then** zero matches are returned (the three markers are gone).
3. **Given** a hypothetical second platform plugin under `aivg_core/platforms/openclaw/` exposing the same Protocol surface, **When** the satellite adapter is started with `platform: openclaw` in `gateway_config`, **Then** the adapter selects and drives the openclaw platform without any code change anywhere outside `aivg_core/platforms/openclaw/`.

---

### User Story 2 — The Hermes plugin keeps working at byte-equivalent parity (Priority: P1)

The existing Hermes integration (live-tested through feature 013 and
exercised live in feature 014's electron-test) MUST continue to work
end-to-end after the refactor — same voice turns, same latency, same
log lines, same reconnect behaviour. The change is internal-only.

**Why this priority**: every existing user is on Hermes. A regression
here breaks every running deployment.

**Independent Test**: SC-002 — the existing live electron-test
sequence (PTT, transcript, agent reply, TTS audio out) reproduces
against the refactored loop, matching the feature 014 / 0.1.3
verification baseline.

**Acceptance Scenarios**:

1. **Given** the post-refactor `aivg_core` installed into the Hermes venv via `aivg setup --force --yes`, **When** the gateway is started and the Electron test client (`@aivg/sat-sdk 0.1.3+`) connects + adopts + holds PTT + speaks + releases, **Then** the gateway log shows one full STT → conversation_loop → Piper TTS cycle within the same latency band as feature 014 baseline.
2. **Given** the satellite adapter, **When** the Hermes plugin's `PLATFORM.startup(gateway_config=…)` is invoked, **Then** every Hermes-specific construction (provider warm-up, session DB wiring, agent caching) that previously lived in `HermesBridge` happens behind the platform interface — the loop sees only the `AgentPlatform` verbs.

---

### User Story 3 — Streaming agent replies remain available where the platform supports them (Priority: P2)

The constitutionally-mandated `agent_step(text, session) → reply_stream`
is the baseline. Feature 008's text-delta streaming (the
`agent_stream` path used today by `HermesBridge` for sub-sentence
latency) is preserved as an OPTIONAL extension that delta-capable
platforms may expose. The voice loop prefers `agent_stream` when
present and falls back to `agent_step` otherwise.

**Why this priority**: feature 008/009/010 latency wins ride on the
delta seam. Losing them would be a measurable regression on
production Hermes deployments.

**Independent Test**: SC-003 — under the same `aivg setup --legacy-hermes`
config used in the feature-010 latency benchmarks, one voice turn's
end-of-utterance → first-audio-out latency is within ±10 % of the
pre-refactor baseline.

**Acceptance Scenarios**:

1. **Given** an `AgentPlatform` implementation that exposes only `agent_step` (no `agent_stream`), **When** the loop runs a voice turn, **Then** it consumes deltas from `agent_step()` directly and the turn completes successfully (no requirement that streaming be present).
2. **Given** the Hermes plugin (which DOES expose `agent_stream`), **When** the loop runs a voice turn, **Then** it uses `agent_stream` for sub-sentence streaming and the timing breakdown shows non-zero `agent_first_output` and `first_unit_ready` latency instants matching the feature 010 baseline.

---

### User Story 4 — Test suite reflects the new shape: a working test against a non-Hermes platform fixture (Priority: P2)

The test suite includes at least one integration test that drives
the voice loop against a non-Hermes platform fixture, proving the
abstraction at the test layer (not just the type system).

**Why this priority**: prevents the next refactor from silently
re-coupling. Tests are the regression boundary.

**Independent Test**: a new test under
`tests/integration/test_voice_loop_platform_agnostic.py` drives one
voice turn end-to-end against the echo platform; the existing
Hermes-integration tests continue to pass unchanged.

**Acceptance Scenarios**:

1. **Given** the echo platform fixture (transcribes to a known string, replies with known text, synthesises to known PCM, detects EOU at a known frame index), **When** the test runs one voice turn through the satellite adapter, **Then** the assertions on the captured transcript / reply / audio bytes match the fixture's known values exactly.
2. **Given** the full test suite, **When** `pytest -q` is run, **Then** all existing tests pass (including every feature-008/009/010 test that exercises Hermes-side streaming + latency).

---

### Edge Cases

- **Platform plugin missing a required method**: the loop MUST fail fast at adapter startup (in `AgentPlatform.startup`) with a clear error message listing the missing verb, not at first call mid-turn.
- **Platform plugin's `agent_step` returns no deltas**: treated as "empty / tool-only reply" exactly like the current `HermesBridge` empty-reply path; no audio synthesised, session returns to listening (constitutional Principle I — no Piper fallback).
- **Platform plugin exposes both `agent_step` and `agent_stream`**: the loop prefers `agent_stream`; `agent_step` is the fallback when `agent_stream` is absent or raises a documented capability-unavailable error.
- **Platform plugin's `endpoint(frame)` never returns True**: the existing inactivity / max-turn-duration timeout (already present in the voice loop) catches the session; no change to that limit.
- **Two `# AgentPlatform-coupling-TODO` markers re-introduced** in a future change: a CI grep job MUST fail the build. (Not part of this feature's surface, but called out so the regression boundary is explicit.)
- **Hermes plugin's `HermesBridge` referenced from outside `aivg_core/platforms/hermes/`**: after this feature, any such import is a constitutional violation and MUST trip a grep-based test.

## Requirements *(mandatory)*

### Functional Requirements

#### Voice loop & signaling decoupling

- **FR-001**: The satellite adapter MUST consume the active platform via the `AgentPlatform` Protocol (loaded through `PluginRegistry.load`), not via any direct import of a platform-specific bridge class.
- **FR-002**: The voice session class MUST be constructable from an `AgentPlatform` instance, with no module-level import of any platform-specific class.
- **FR-003**: The signaling service MUST be constructable from an `AgentPlatform` instance, with no module-level import of any platform-specific class.
- **FR-004**: All three `# AgentPlatform-coupling-TODO` markers (in `adapter.py`, `webrtc/session.py`, `webrtc/signaling.py`) MUST be removed.

#### Protocol shape

- **FR-005**: The voice loop MUST call platform verbs by their canonical Protocol names: `transcribe(audio, *, sample_rate)`, `agent_step(text, session_id, *, history)`, `synthesize(text)`, and `endpoint(frame)`. Hermes-bridge-flavoured names (`stt_transcribe`, `tts_synthesize`, `detect_endpoint`, `agent_turn`) MUST NOT appear in any caller under `aivg_core/webrtc/` or `aivg_core/adapter.py`.
- **FR-006**: The voice loop MUST detect, at construction time, whether the active platform exposes an OPTIONAL `agent_stream(text, session_id, *, history)` extension method; if present, the loop MUST prefer it for the agent step (feature 008 latency win), and otherwise MUST fall back to `agent_step`.
- **FR-007**: The satellite adapter MUST fail fast at startup with a clear error listing missing required protocol verbs when a platform plugin omits any of `transcribe`, `agent_step`, `synthesize`, `endpoint`.

#### Hermes plugin internals

- **FR-008**: `HermesBridge` MUST become a plugin-internal implementation detail of `aivg_core/platforms/hermes/`: it MUST NOT be exported from the plugin's public module symbols (no re-export at `aivg_core/platforms/hermes/__init__.py`) and MUST NOT be referenced by any name from outside `aivg_core/platforms/hermes/`.
- **FR-009**: The Hermes plugin's `PLATFORM` value MUST be the canonical `AgentPlatform`-conforming object that the loop sees; whether it wraps `HermesBridge` or replaces it entirely is a plugin-internal choice.
- **FR-010**: All Hermes-specific configuration access (`~/.hermes/config.yaml`, `~/.hermes/.env`, Hermes's session DB, the agent-cache singleton) MUST remain inside the Hermes plugin (constitutional Principle IV rule). No new Hermes-specific config keys leak into `aivg_core/`.

#### Regression boundary

- **FR-011**: A new test under `tests/unit/test_no_hermes_imports_in_core.py` (or equivalent) MUST grep the `aivg_core/` tree (excluding `aivg_core/platforms/hermes/`) and assert zero imports of any `hermes`-prefixed symbol from outside the plugin.
- **FR-012**: A new test (CI-runnable) MUST assert that `grep -rE '# AgentPlatform-coupling-TODO' src/aivg_core/` returns zero matches.
- **FR-013**: The existing test suite (Hermes-integration tests under `tests/integration/`, fake-bridge tests under `tests/unit/`, latency tests under `tests/integration/test_voice_turn_latency.py`) MUST continue to pass unchanged after the refactor.

#### Live-parity gates

- **FR-014**: The live electron-test client (`clients/electron-test/`, feature 014's living integration test) MUST complete one full voice turn against the refactored loop against the same gateway it works against today, with no client-side changes.
- **FR-015**: Feature 010's latency timing instants (`endpoint_detected`, `agent_first_output`, `first_unit_ready`, `first_audio_synth`, `first_audio_delivered`) MUST continue to be emitted with the same semantics; the post-refactor median end-of-utterance → first-audio-out latency MUST be within ±10 % of the pre-refactor baseline for the same `aivg setup --legacy-hermes` config.

#### Out of scope (v1)

- **OOS-001**: Shipping an actual OpenClaw platform plugin. This feature closes the seam; OpenClaw is its own future feature.
- **OOS-002**: Changes to the public WS/REST wire surface, the JSON message shapes, or the management plane contract version. The wire side is frozen at `aivg --contract-version 1.0.0`.
- **OOS-003**: Changes to the TypeScript SDK (`@aivg/sat-sdk`). The SDK is a *consumer* of the wire surface, which doesn't change in this feature.
- **OOS-004**: The C++ SDK (`libaivg-sat`) — that is the planned next feature (016).
- **OOS-005**: Constitutional amendment. Principle IV stays at v2.0.0 / current text; this feature *closes* the principle's runtime obligation, it does not redefine it.

### Key Entities

- **`AgentPlatform`**: the platform-neutral Protocol the voice loop now consumes. Already defined in `src/aivg_core/platforms/base.py` with `name`, `startup`, `transcribe`, `agent_step`, `synthesize`, `endpoint`, `shutdown` verbs.
- **Optional `agent_stream` extension**: a delta-capable platform may expose `async def agent_stream(text, session_id, *, history, turn=None) -> AsyncIterator[bytes]` for sub-sentence audio streaming (feature 008 lineage). Detection is shape-based (`hasattr(platform, "agent_stream")`); not part of the required Protocol.
- **`PluginRegistry`**: the loader (already implemented) that resolves `platform: "hermes"` etc. to an `AgentPlatform` instance via `aivg_core.platforms.<name>.PLATFORM`.
- **`HermesBridge`**: from this feature forward, an internal implementation detail of `aivg_core/platforms/hermes/`. The plugin's `PLATFORM` either *is* a `HermesBridge`-derived object satisfying the canonical Protocol verbs, or *delegates to* one — invisible to the loop.
- **Echo platform fixture**: existing `tests/fixtures/platforms/echo/` plugin used at the loader-test level (feature 011) is the proof-of-genericity vehicle; gains a voice-loop integration test in this feature.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After implementation, `grep -rE '# AgentPlatform-coupling-TODO' src/aivg_core/` returns **zero** matches (was three).
- **SC-002**: The live electron-test client (`@aivg/sat-sdk 0.1.3+`) completes one full voice turn against the refactored loop, matching the feature 014 baseline behaviour (transcript and reply UI fields populate within 5 seconds of release).
- **SC-003**: The post-refactor median end-of-utterance → first-audio-out latency is within ±10 % of the pre-refactor feature-010 baseline under the same `aivg setup --legacy-hermes` configuration.
- **SC-004**: A new echo-platform integration test (`tests/integration/test_voice_loop_platform_agnostic.py`) drives one voice turn through the satellite adapter using the echo `AgentPlatform` only — no `HermesBridge` reference — and passes deterministically.
- **SC-005**: The full existing test suite (every `pytest` test that passed before this feature) continues to pass; no test asserting Hermes-specific behaviour is altered semantically.
- **SC-006**: `grep -rE 'from.*\\.hermes\\.' src/aivg_core/` outside `src/aivg_core/platforms/hermes/` returns zero matches.
- **SC-007**: No public wire surface changes — the existing `aivg --contract-version` value is **unchanged** at `1.0.0`.
- **SC-008**: `aivg setup --force --yes` against a Hermes host re-installs cleanly and the resulting deployment can complete a voice turn within 60 seconds of the gateway restart, matching feature-013 live verification behaviour.
- **SC-009**: The constitutional check in any post-feature spec planning step (the `Constitution Check` gate in `/speckit-plan`) passes Principle IV without an "outstanding TODO" deferral note.
- **SC-010**: A hypothetical second platform plugin can be added under `aivg_core/platforms/<name>/` (with its own `PLATFORM = ...`) and selected via `platform: <name>` in the satellite config, requiring zero changes to any file outside `aivg_core/platforms/<name>/`. Verified by a tree-shake test (a contract test that simulates adding a fake plugin and confirms it loads + the loop runs against it).

## Assumptions

- The `AgentPlatform` Protocol in `src/aivg_core/platforms/base.py` is **the** canonical surface; minor signature adjustments to match what the loop needs are acceptable provided the constitution's named verbs are preserved (`transcribe`, `agent_step`, `synthesize`, `endpoint`).
- Hermes's existing `HermesBridge` may keep its current method names (`stt_transcribe`, `tts_synthesize`, `agent_turn`, `detect_endpoint`) internally as thin wrappers that the plugin's `PLATFORM` exposes through the canonical names. The loop sees only the canonical names; the Hermes-bridge-flavoured names are quarantined inside the plugin.
- Feature 008's `agent_stream` delta seam is preserved verbatim, just promoted from "the bridge's method" to "an optional protocol extension". The loop's prefer-`agent_stream` logic moves from `HermesBridge`-flavoured detection (`getattr(self._bridge, "agent_stream", None)`) to platform-flavoured detection (`getattr(self._platform, "agent_stream", None)`) — one-line change in `webrtc/session._respond`.
- The echo platform fixture in `tests/fixtures/platforms/echo/` already exposes `transcribe`, `agent_step`, `synthesize`, `endpoint` per feature 011; this feature reuses it as the proof-of-genericity test target. If the fixture's signatures drift from the canonical Protocol's, they are aligned in this feature.
- No new constitutional amendment is required; Principle IV's text already commits to the protocol surface this feature is closing. The constitution file (`.specify/memory/constitution.md`) is unchanged in this feature.
- No public CLI surface changes. `aivg setup`, `aivg list`, `aivg device …`, `aivg logs`, `aivg --contract-version` all behave identically.
- Tests are written, run, and gated locally; the user has no CI yet, so the "CI grep job" mentioned in edge cases is implemented as a unit test in `tests/unit/` that runs under the existing `pytest` invocation.

## Dependencies

- `AgentPlatform` Protocol + `PluginRegistry` in `aivg_core/platforms/base.py` (feature 011 / constitution v2.0.0).
- Hermes plugin scaffold at `aivg_core/platforms/hermes/` (feature 011 + 012 rebrand + 013 setup capability + 014's pip-install distribution).
- The echo platform fixture at `tests/fixtures/platforms/echo/` (feature 011 T017 + feature 013 T034 extension).
- The Electron test client (`clients/electron-test/`) consuming `@aivg/sat-sdk 0.1.3` — used as the live SC-002 verification target.
- Feature 008/009/010 — `agent_stream` delta seam, markdown-strip behaviour, and latency instrumentation — preserved as-is.
