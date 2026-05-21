# Implementation Plan: ESPHome Voice Assistant transport

**Branch**: `017-esphome-voice-transport` · **Date**: 2026-05-21 · **Spec**: [spec.md](./spec.md)

## Summary

Add an ESPHome native API transport server to the AIVG gateway as an
**additive** transport alongside the existing WebRTC path. Existing
ESPHome voice satellites (Home Assistant Voice Preview Edition,
M5Stack Atom Echo, custom ESP32 firmware built from ESPHome's voice
satellite YAML) connect via TCP on port `6053`, register with the
existing `aivg_core.registry.Registry`, and stream audio through the
same `AgentPlatform` Protocol the WebRTC clients use today
(constitution Principle IV runtime closure, feature 015).

Three clarifications from `/speckit-clarify` Session 2026-05-20 lock
the technical shape:

- **Q1**: depend on `aioesphomeapi` (PyPI) for proto types + framing.
- **Q2**: one `asyncio.Task` per connected device.
- **Q3**: reuse `aivg_core.webrtc.session.Session` verbatim via the
  existing `MediaTransport` Protocol seam.

Result: a single new module `src/aivg_core/transports/esphome/`
(~700-900 LoC budget) plus one wiring line in `adapter.py`. Zero
modifications to `aivg_core/platforms/`, `aivg_core/webrtc/session.py`,
or any plugin-internal file. Wire-surface impact: additive bump from
`contract_version 1.0.0` → `1.1.0`; `@aivg/sat-sdk 0.1.3` electron-test
keeps working verbatim.

## Technical Context

**Language/Version**: Python 3.11+ (matches `aivg_core` baseline; same
runtime as the existing gateway).

**Primary Dependencies**:

- `aioesphomeapi` (PyPI, MIT) — proto-generated message types
  (`aioesphomeapi.api_pb2`) and the varint framing helpers
  (`aioesphomeapi.core`). Pin: `>=23.0,<28.0` (the version range
  shipping with current ESPHome / Home Assistant releases).
- `protobuf` (transitive via `aioesphomeapi`).
- `aiohttp` (already in deps; used for the management plane — no new
  use here, but the new server runs on the same asyncio event loop).
- No new system packages; CMake / native-build deps unchanged.

**Storage**: None new. ESPHome device records live in the existing
`aivg_core.registry.Registry` (in-memory + persisted via the existing
mechanism). The optional per-device API-key store is a small JSON
file under `~/.aivg/devices/keys.json` (new), parallel to the existing
config; no DB.

**Testing**: pytest (existing harness). New tests:

- `tests/unit/test_esphome_framing.py` — varint length-prefix
  encode/decode + opcode routing against `aioesphomeapi.api_pb2`
  fixtures.
- `tests/unit/test_no_transport_imports_in_platforms.py` — grep-gate
  regression boundary for SC-005.
- `tests/integration/test_esphome_transport_basic.py` — drive one
  voice turn through the new transport against the echo platform
  fixture (no Hermes import).
- `tests/integration/test_esphome_multi_device.py` — N=4 concurrent
  ESPHome clients each completing a turn (SC-006).
- `tests/integration/test_esphome_disconnect_cleanup.py` — 100 sessions
  opened-and-dropped, task-count returns to baseline (SC-007).

**Target Platform**: Same as the existing gateway — Linux + macOS
userspace, Python 3.11+, runs anywhere `aivg_core` runs today. The
**device** side (the ESPHome firmware) is targeted by the upstream
ESPHome project, NOT by AIVG; this feature ships zero embedded code.

**Project Type**: Library / service component. New module added to
the existing `aivg_core` package.

**Performance Goals**:

- One voice turn over the new transport completes within the same
  feature-010 latency envelope (median end-of-utterance → first-audio-out
  within ±20 % of WebRTC's measured baseline; we relax the ±10 % of
  feature 015 to ±20 % here because ESPHome's per-frame protobuf
  overhead is a small additional cost we don't yet have a measurement
  for).
- 4 concurrent devices each within 1.5× single-device latency (SC-006).
- Mid-turn disconnect cleanup ≤ 5 s to baseline open-task count (SC-007).

**Constraints**:

- Wire-surface invariance: existing WebRTC + REST + management WS
  surfaces are NOT modified (FR-002).
- Constitutional Principle IV: zero modifications to
  `src/aivg_core/platforms/` — the new transport calls
  `AgentPlatform` verbs through `Session` only (FR-007, FR-008,
  SC-003, SC-005).
- Same maintainability bar: a single developer extends the transport,
  builds, runs the test suite, and ships in one sitting.
- One transport, one PyPI dep (no `protobuf-compiler`, no
  build-from-source step).

**Scale/Scope**: ~700-900 LoC source net + ~300-400 LoC tests.
Targeted at v1 device counts of 3-20 satellites per gateway (homelab
scale). Larger deployments are not part of v1's binding gate; the
one-task-per-device model is documented to suffice up to ~100 devices
on a modest server (Q2 / FR-021).

## Constitution Check

Evaluated against AIVG Constitution **v2.0.1**
(`.specify/memory/constitution.md`).

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) — ✅ PASS

The new transport is **gateway-side**. It does not add STT, TTS,
agent loop, or endpointing logic anywhere. The transport handler
sits BELOW `Session`, which calls the active `AgentPlatform` plugin's
verbs (`transcribe`, `agent_step`, `synthesize`, `endpoint`) — same
seam the WebRTC path uses. Principle I's "STT/TTS reached only
through the active platform's provider interfaces" rule is
strengthened, not weakened: this feature makes the same plugin reachable
from a second transport.

The device side (ESPHome firmware) is the upstream ESPHome project's
concern and already implements device-side wake-word gating; AIVG
adds nothing on the device.

### II. Generic Four-Plane Contract — ✅ PASS

The four-plane contract is preserved:

- **Control plane**: ESPHome devices appear in the existing
  registry / management WS / `aivg list` outputs with a `transport`
  discriminator (FR-013, FR-014). Same WS message types as today.
- **Voice plane**: a parallel TCP listener on a new port (`6053`);
  the existing 8643 / 8644 sockets are untouched (FR-002).
- **Capture/endpointing**: device-side wake-word + gateway-side
  `AgentPlatform.endpoint` — same as the WebRTC path.
- **Playback**: ESPHome's `VoiceAssistantAudio` outbound frames →
  `MediaTransport.send_audio` → ESPHome connection writes back to
  device. Same playback semantics.

Per-platform divergence stays inside the platform plugin, behind the
`AgentPlatform` interface. Per-transport divergence stays inside
`transports/esphome/`. The gateway code (registry, management,
adapter) remains transport-neutral except for one wiring line.

### III. Separate Control and Voice Connections — ⚠ PARTIAL, justified

ESPHome's protocol uses a **single TCP connection per device** that
carries both control messages (Hello, Connect, Auth, Ping,
DeviceInfo, ListEntities) AND audio frames
(`VoiceAssistantAudio*`). This **deviates** from Principle III's
"exactly two connections" rule, which was authored against WebRTC's
control-WS-plus-voice-PC topology.

**Justification**: this is the upstream ESPHome protocol's existing
shape — millions of deployed devices speak it. Forcing a two-socket
topology onto ESPHome firmware is not feasible from AIVG's side
(we don't ship firmware). The constitutional intent of Principle III
(control stays available when no call is active) is preserved
because:

- The ESPHome connection is always-on (the device maintains it
  continuously, with ESPHome's own reconnect-with-backoff).
- "Voice session" is just a logical state within the same connection,
  not a separate transport.
- A device that is "online but idle" still appears in the registry
  and receives state updates.

The Principle III rule that "durable control traffic MUST NOT be
multiplexed into a WebRTC data channel" remains in force — that rule
is WebRTC-specific. For ESPHome the analogous rule is "the connection
is always-on, never tied to a voice-session lifecycle" — and we
guarantee that.

**No constitutional amendment needed**; the rule is WebRTC-scoped.
This deviation is documented in Complexity Tracking below.

### IV. Reuse the Upstream Agent Platform, Don't Rebuild — ✅ PASS

This is the binding test. Feature 015 closed the runtime side of the
`AgentPlatform` seam. Feature 017 adds a **new caller** of those
verbs without touching the verbs themselves, the plugin
implementations, or the plugin directory layout.

Binding rules this plan commits to:

- ZERO modifications to `src/aivg_core/platforms/` (SC-003 / SC-005
  grep gate).
- The new code lives entirely under `src/aivg_core/transports/esphome/`.
- One new wiring line in `adapter.py` to start the ESPHome listener
  alongside the existing two servers — that line names `transports`,
  not `platforms`.
- The new transport calls `AgentPlatform` verbs **only** through the
  existing `Session` class (`webrtc/session.py`) via the
  `MediaTransport` Protocol adapter (FR-009). It never imports any
  plugin module directly.

### V. Research-Backed, Constraint-Driven Decisions — ✅ PASS

Three ADRs in [research.md](./research.md) carry the binding
research:

- **R-1**: depend on `aioesphomeapi` for proto + framing (Q1
  resolution) — the OHF-Voice `linux-voice-assistant` precedent
  proves the import shape works.
- **R-2**: one `asyncio.Task` per device (Q2) — matches the existing
  aiortc-session pattern; no new concurrency model.
- **R-3**: reuse `webrtc.Session` verbatim via `MediaTransport`
  adapter (Q3) — the abstraction holds based on
  [src/aivg_core/webrtc/session.py:70-83](../../src/aivg_core/webrtc/session.py#L70-L83)
  Protocol surface inspection.

Principle V's load-test rule applies to constrained-device features;
this is a server-side addition and is exercised end-to-end against a
real ESPHome device (SC-001 / FR-020 live smoke) before declared
shipped.

### Overall Gate Result

**PASS** with one **justified partial** on Principle III (single
TCP connection vs two-connection rule). Documented in Complexity
Tracking below; no constitutional amendment required.

### Post-Design Re-Check (after Phase 1)

After producing [research.md](./research.md),
[data-model.md](./data-model.md),
[contracts/esphome-transport.md](./contracts/esphome-transport.md),
and [quickstart.md](./quickstart.md), the gates are re-evaluated:

- **I. Thin Satellite** — strengthened. The new transport makes
  the existing `AgentPlatform` reachable from a second wire shape
  without adding any STT/TTS/agent/endpointing code anywhere. The
  device-side wake-word event mapping in R-4 explicitly preserves
  the constitutional rule that server-side endpointing wins.
- **II. Generic Four-Plane Contract** — strengthened. The contract
  document § 6 + § 7 bind the wire-surface invariance. The
  management plane gains a `transport` discriminator additively;
  the four planes' semantics are unchanged.
- **III. Separate Control/Voice Connections** — partial,
  documented in Complexity Tracking. The single-TCP-connection
  shape is forced by upstream ESPHome protocol; the
  always-on-not-tied-to-voice-session intent is preserved.
- **IV. Reuse Upstream Agent Platform** — this is THE feature.
  Contract § 6 makes the "zero `platforms/` modifications" rule a
  grep-gate-enforced regression boundary. The
  `EsphomeMediaTransport` adapter (data-model § 3) is the
  composition seam that lets `Session` work verbatim.
- **V. Research-Backed Decisions** — R-1, R-2, R-3 are pinned in
  the spec via `## Clarifications`; R-4 (voice-event mapping) is
  the new ADR added in Phase 0. All four ADRs have explicit
  rationale and rejected alternatives.

**PASS — no new violations introduced by Phase 1 design.**

## Project Structure

### Documentation (this feature)

```text
specs/017-esphome-voice-transport/
├── plan.md                    # This file (/speckit-plan output)
├── research.md                # Phase 0 — 3 ADRs (R-1, R-2, R-3)
├── data-model.md              # Phase 1 — type signatures + state machine
├── quickstart.md              # Phase 1 — verify locally
├── contracts/
│   └── esphome-transport.md   # Phase 1 — wire contract + MediaTransport adapter
└── tasks.md                   # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
src/aivg_core/
├── transports/                          # NEW directory
│   ├── __init__.py                      # re-export EsphomeTransport
│   └── esphome/                         # NEW — this feature's surface
│       ├── __init__.py                  # public: EsphomeTransport class
│       ├── server.py                    # asyncio.start_server listener
│       ├── connection.py                # EsphomeConnection (one task/device)
│       ├── media_adapter.py             # EsphomeMediaTransport (MediaTransport impl)
│       ├── auth.py                      # plaintext API-key validation
│       ├── framing.py                   # thin wrapper around aioesphomeapi.core
│       └── voice_protocol.py            # voice_assistant_* message handlers
├── adapter.py                           # +1 wiring line — start EsphomeTransport
│                                        # alongside existing two aiohttp sites
├── config.py                            # +1 transport-config block
│                                        # (transports.esphome_api.enabled, port, key)
├── models.py                            # +1 field: VoiceSession.transport (str)
└── (everything else: UNCHANGED)

tests/
├── unit/
│   ├── test_esphome_framing.py          # NEW
│   ├── test_esphome_auth.py             # NEW
│   ├── test_esphome_media_adapter.py    # NEW (MediaTransport contract test)
│   └── test_no_transport_imports_in_platforms.py  # NEW (SC-005 grep gate)
├── integration/
│   ├── test_esphome_transport_basic.py  # NEW (one turn, echo platform)
│   ├── test_esphome_multi_device.py     # NEW (SC-006 concurrency)
│   └── test_esphome_disconnect_cleanup.py  # NEW (SC-007 resource hygiene)
└── fixtures/
    └── esphome_client.py                # NEW — minimal in-process protobuf client
                                          # for integration tests (no real socket required)

clients/electron-test/                   # NO change (SC-002 binds)
sdks/typescript/                         # NO change (SC-002 binds)
```

**Structure Decision**:

The feature is **strictly additive** in source structure. A new
sibling directory `src/aivg_core/transports/` lives next to
`platforms/` and `webrtc/`. The two existing siblings
(`platforms/`, `webrtc/`) are untouched.

1. `transports/esphome/` is the only new directory. Six small files
   (~700-900 LoC) keep each file under ~200 lines.
2. `EsphomeMediaTransport` (in `media_adapter.py`) is the seam
   that lets `webrtc.Session` work verbatim — it implements the
   existing `MediaTransport` Protocol from
   `webrtc/session.py:70-83` against ESPHome's `VoiceAssistantAudio`
   frames.
3. The new tests/fixture `tests/fixtures/esphome_client.py` is a
   minimal protobuf client (no real socket — uses two in-process
   queues) so integration tests are deterministic and fast.
4. `config.py` gains a new `TransportsConfig.esphome_api` block;
   the existing `SatelliteAdapterConfig` is extended, not replaced.
   Old configs without the block default to `enabled: false` —
   opt-in for v1 deployments.

## Complexity Tracking

The only justified deviation: Principle III's "exactly two
connections" rule. ESPHome's wire protocol uses one TCP connection
per device that carries both control and audio. We document the
rule as **WebRTC-scoped**, not universal, and ESPHome's analogous
rule ("the connection is always-on, never tied to a voice-session
lifecycle") is preserved.

| Choice | Why | Alternative rejected |
| --- | --- | --- |
| Single TCP connection (ESPHome's shape) | Upstream protocol; millions of devices already speak it. Forcing two sockets would require firmware changes outside AIVG's scope. | Wrap ESPHome's connection in a two-socket adapter — rejected: pure protocol-shape mismatch with upstream; would not interoperate with existing ESPHome firmware (defeats US1). |
| New top-level `src/aivg_core/transports/` directory | Mirrors `platforms/` and `webrtc/` siblings; signals that future transports (e.g., MQTT, gRPC) plug into the same seam. | Add the ESPHome code under `webrtc/` — rejected: misleading; the new code has nothing to do with WebRTC and would muddy the layout. |
| One `asyncio.Task` per device (Q2 resolution) | Matches aiortc-session pattern (one task per session); per-device cleanup is straightforward. | Pooled multiplexer task — rejected: more complex teardown for marginal task-count savings at v1's device-count scale (3-20). |
| Reuse `Session` verbatim via `MediaTransport` adapter (Q3) | The `MediaTransport` Protocol surface is already abstract over the transport (see [webrtc/session.py:70-83](../../src/aivg_core/webrtc/session.py#L70-L83)). | Extract a transport-neutral `Session` base — rejected: ~2× the code churn for no testable behaviour delta given the existing Protocol works. |
| Depend on `aioesphomeapi` (Q1) | Single PyPI dep handles proto schema + framing + version skew tracking. Mirrors OHF-Voice's choice. | Vendor `.proto` files locally — rejected: drifts from upstream; manual refresh burden. |
