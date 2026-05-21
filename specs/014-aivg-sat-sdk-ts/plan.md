# Implementation Plan: `@aivg/sat-sdk` (TypeScript)

**Branch**: `014-aivg-sat-sdk-ts` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/014-aivg-sat-sdk-ts/spec.md`

## Summary

Extract the working WebRTC + WebSocket protocol code from
[clients/electron-test/](../../clients/electron-test) into an installable,
typed npm package (`@aivg/sat-sdk`) living at `sdks/typescript/`. The
package exposes a `Satellite` class that wraps the four-plane satellite
contract (control WS, voice WebRTC, capture/endpointing, playback) and
emits a stable event stream covering adoption state, agent telemetry,
configuration changes, OTA notifications, and logs.

The package is intentionally headless and runtime-environment-agnostic:
the same artefact must work in modern browsers, Electron renderer + main,
and Node.js 20+. Where the host lacks a built-in WebRTC implementation
(Node), consumers inject one at construction time. The published surface
mirrors the existing `aivg --contract-version 1.0.0` shape with zero
contract drift, and the existing `clients/electron-test/` is refactored
to consume the new package as a living integration test.

This feature is the contract foundation for feature 015 (C++ SDK) — every
public type and event shape that lands here MUST be translatable directly
to its C++ equivalent.

## Technical Context

**Language/Version**: TypeScript 5.4+ (`strict: true`, `exactOptionalPropertyTypes: true`). Targets ES2022 (Node 20 baseline). Source `.ts`; published artefacts include `.d.ts` first-class.

**Primary Dependencies**: ZERO runtime native deps. Hard-dependency surface:

- Standards-only runtime: `RTCPeerConnection`, `WebSocket`, `fetch`, `MediaDevices.getUserMedia`, `MediaStream`, `HTMLAudioElement` — all DOM/WHATWG standards.
- Dev/build only: `tsup` (zero-config bundler around esbuild) for emitting ESM + CJS + `.d.ts`; `vitest` for unit/contract tests with `jsdom`/`happy-dom` for browser-like environment; `@types/node`, `@types/dom-webcodecs` for the typings.

**Storage**: None in the SDK itself. Consumers may persist `deviceId` via their own storage (localStorage, electron-store, fs). The SDK accepts `deviceId` at construction and never writes to disk.

**Testing**: `vitest` (default Node + happy-dom env) + a single `playwright` headless-browser integration smoke that runs against a live gateway (skip-able locally; CI-only) + a Node integration test using `@roamhq/wrtc` (the maintained successor to the abandoned `node-wrtc`) injected as the WebRTC backing. Coverage gate ≥ 85% lines for `sdks/typescript/src/`.

**Target Platform**: Browser (Chrome/Firefox/Safari current stable), Electron (renderer + main process), Node.js 20+ (with consumer-injected `RTCPeerConnection`).

**Project Type**: Library (npm package) inside an existing Python+TS monorepo. New top-level dir `sdks/typescript/` with its own `package.json`, `tsconfig.json`, `vitest.config.ts`.

**Performance Goals**:
- Package size: < 50 KB minified+gzipped for the main bundle (no native deps means we control this directly; the goal is parity with `socket.io-client` class libraries).
- Cold start: < 50 ms from `import` to `new Satellite(...)` ready (excluding network/permission prompts).
- Event-surface latency: SDK forwards a gateway-pushed event to a consumer handler in < 5 ms p99 on a modern desktop (most of the SC-008 200 ms budget belongs to the network, not us).

**Constraints**:
- ZERO native compiled dependencies (no `node-gyp`, no `prebuildify`, no `.node` files). Forces the WebRTC-in-Node story to be DI-only.
- Contract-version preserved at `1.0.0` (SC-007). The SDK consumes — does not extend — the management-plane contract.
- Same code path for browser/Electron/Node: ONE compiled artefact pair (ESM + CJS), no per-runtime forks. Runtime-specific behaviour (e.g., `getUserMedia` availability) is detected at first use, not at bundle time.
- Public surface uses no `any` (SC-004); everything either has a typed shape or is `unknown` with a typed discriminant.
- Bundler-agnostic: the package must work under webpack, Vite, esbuild, Rollup, Parcel, and Electron's default bundler without per-bundler configuration.

**Scale/Scope**:
- ~1,500-2,500 LoC TypeScript source (rough budget for the surface described in the spec).
- One published npm package; one example app (the refactored electron-test) consuming it.
- ~80-120 lines of test code per FR (27 FRs × ~3-5 assertions / FR + edge-case suite ≈ 1,500-2,000 LoC tests).

## Constitution Check

Evaluated against AIVG Constitution v2.0.1 (.specify/memory/constitution.md).

### I. Thin Satellite, Gateway-Owned Intelligence (NON-NEGOTIABLE) — ✅ PASS

The SDK is a satellite *implementation aid*; it ships in the satellite tier
of the architecture, not the gateway. It MUST NOT embed STT, TTS, or the
agent loop, and MUST NOT bypass the gateway for any of those.

Binding implementation rules this plan commits to:

- The SDK source tree MUST NOT depend on or bundle any STT/TTS library, on-device
  whisper, on-device piper, on-device kokoro, or any speech engine package.
- The SDK MUST NOT add an `analyzeAudio` / `transcribe` / `synthesize` method
  to its public surface. Audio capture and playback flow through standard
  browser APIs straight into / out of `RTCPeerConnection`; the gateway runs
  the speech stack.
- Device-side VAD/wake-word is OUT OF SCOPE per the spec (`OOS-001`); the v1
  ingress is push-to-talk, consumer-driven. Any future wake-word adapter is
  additive and itself bound by Principle I (no transcription on device).

### II. Generic Four-Plane Contract — ✅ PASS

The SDK is, by construction, the four-plane contract rendered in TypeScript:

- Control plane → `Satellite` owns the `/satellite/ws` connection
- Voice plane → `VoiceSession` owns the `RTCPeerConnection` lifecycle
- Capture/endpointing plane → consumer-driven (PTT v1); SDK exposes a stable
  `beginSession()` / `endSession()` ingress
- Playback plane → `MediaStream` from the WebRTC remote track is attached
  to a consumer-supplied audio sink (or an `HTMLAudioElement` the SDK manages
  on the consumer's behalf in browser/Electron)

Binding rules:

- Shared data models (`SatelliteState`, `SatelliteConfig`, `LogEntry`,
  `AdoptionState`, `OtaManifest`) reuse the existing wire shapes exactly
  (per FR-007, SC-007). The SDK does NOT define alternative names or
  alternative shapes — types are derived from the management contract.
- No per-runtime branching on `device_type` in the SDK. The host environment
  (browser vs Node) only affects audio I/O wiring, never protocol behaviour.

### III. Separate Control and Voice Connections — ✅ PASS

The SDK is structurally a renaming of the existing electron-test, whose
behaviour already conforms: long-lived control WS, per-session WebRTC.

Binding rules:

- The SDK MUST instantiate exactly two connection types: ONE long-lived
  `WebSocket` against `/satellite/ws`, ONE per-session `RTCPeerConnection`.
- Live UI events (`partial_transcript`, `state`, `barge_in`) MAY ride the
  voice PC's SCTP datachannel (constitutional carve-out) but config /
  commands / OTA / heartbeats MUST stay on the WS.
- The SDK is the WebRTC offerer for every session (consistent with the
  existing electron-test). ICE: full gather then offer; `/webrtc/candidate`
  remains a fallback.
- Operator surfaces (CLI, skills) are unaffected — the SDK is a satellite
  client, not an operator surface.

### IV. Reuse the Upstream Agent Platform, Don't Rebuild — ✅ PASS

This SDK is the satellite-side of the contract; it has nothing to add to or
subtract from the upstream agent platform interface. The Hermes plugin (v1)
keeps its existing role unchanged.

Binding rules:

- The SDK MUST NOT import any Hermes-specific name, branch on
  `platform: "hermes"`, or consume any Hermes-specific config key. Every
  field it touches is part of the platform-agnostic management contract.
- The agent telemetry forwarded by the SDK (`ToolCallEvent`, `SkillEvent`,
  `TranscriptDelta`) MUST flow through the existing gateway-side seam — the
  SDK does not invent a new agent-event channel.

### V. Research-Backed, Constraint-Driven Decisions — ✅ PASS (with deferral)

The TypeScript SDK runs on hosts where the binding constraints are NOT
hardware (browsers and Node have effectively unlimited resources by
satellite standards). The Principle V load-test mandate applies to
constrained satellites (ESP32, RPi); it does NOT bind this SDK.

Binding rules:

- The SDK's design DOES make explicit, researched choices on each technology
  axis (build tool, test framework, WebRTC-in-Node strategy, bundling) —
  documented in research.md with the rejected alternatives.
- Field validation: the refactored `clients/electron-test/` running against
  a real gateway IS the constitutional end-to-end test. SC-002 mandates
  byte-equivalent parity vs the pre-refactor behaviour.

### Overall Gate Result

**PASS** — no violations to justify in Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/014-aivg-sat-sdk-ts/
├── plan.md              # This file (/speckit-plan output)
├── research.md          # Phase 0 — tech choices + rejected alternatives
├── data-model.md        # Phase 1 — TS types + state machine
├── quickstart.md        # Phase 1 — install + first voice turn in < 20 LoC
├── contracts/           # Phase 1 — public API contracts
│   ├── satellite-api.md       # Satellite class + events + errors
│   ├── webrtc-injection.md    # Node DI contract for RTCPeerConnection
│   └── wire-protocol.md       # JSON shapes we consume (gateway-side, frozen)
└── tasks.md             # Phase 2 — generated by /speckit-tasks
```

### Source Code (repository root)

```text
sdks/                                       # NEW top-level — feature 014
└── typescript/                             # this feature
    ├── package.json                        # name=@aivg/sat-sdk, npm publishConfig
    ├── tsconfig.json                       # strict, target=ES2022, declaration=true
    ├── tsup.config.ts                      # emits ESM + CJS + .d.ts
    ├── vitest.config.ts                    # node + happy-dom envs
    ├── README.md                           # publishable docs
    ├── CHANGELOG.md                        # keepachangelog format
    ├── src/
    │   ├── index.ts                        # public surface barrel
    │   ├── satellite.ts                    # Satellite class — top-level handle
    │   ├── state.ts                        # state machine (idle|listening|speaking|error)
    │   ├── adoption.ts                     # pending → adopted flow
    │   ├── control-plane.ts                # /satellite/ws client + reconnect
    │   ├── voice-session.ts                # RTCPeerConnection lifecycle
    │   ├── signaling.ts                    # POST /webrtc/offer flow
    │   ├── config.ts                       # SatelliteConfig push/pull
    │   ├── commands.ts                     # operator command surface
    │   ├── agent-events.ts                 # tool-call/skill/transcript fan-out
    │   ├── ota.ts                          # OTA manifest forwarding (no auto-apply)
    │   ├── logs.ts                         # log_entry forwarding
    │   ├── errors.ts                       # SdkError + closed error-code set
    │   ├── events.ts                       # typed event emitter
    │   ├── webrtc/                         # WebRTC adapter layer
    │   │   ├── injectable.ts               # RTCPeerConnection factory injection
    │   │   ├── browser.ts                  # browser/Electron default factory
    │   │   └── audio-sink.ts               # HTMLAudioElement helper for browsers
    │   └── proto/                          # JSON shapes (one per wire message)
    │       ├── ws-messages.ts              # control-plane message types
    │       ├── rest-shapes.ts              # REST request/response types
    │       └── version.ts                  # contract-version constant ("1.0.0")
    ├── examples/
    │   ├── browser-ptt/                    # 30-LoC PTT demo HTML page
    │   ├── node-headless/                  # CI smoke against a live gateway
    │   └── electron-renderer/              # mini Electron example
    └── tests/
        ├── unit/
        │   ├── state-machine.test.ts
        │   ├── adoption.test.ts
        │   ├── control-plane.test.ts
        │   ├── reconnect-backoff.test.ts
        │   ├── voice-session.test.ts
        │   ├── signaling.test.ts
        │   ├── config.test.ts
        │   ├── commands.test.ts
        │   ├── agent-events.test.ts
        │   ├── ota.test.ts
        │   ├── logs.test.ts
        │   ├── errors.test.ts
        │   └── proto-versioning.test.ts
        ├── contract/
        │   ├── public-api.test.ts          # exhaustive shape of index.ts
        │   ├── event-surface.test.ts       # every documented event name fires
        │   ├── wire-protocol.test.ts       # against a recorded gateway capture
        │   └── no-any-in-public.test.ts    # SC-004 gate
        └── integration/
            ├── browser-live.spec.ts        # playwright vs a live gateway
            └── node-live.spec.ts           # @roamhq/wrtc vs a live gateway

clients/
└── electron-test/                          # EXISTING — refactored in this feature
    ├── renderer.html                       # unchanged structure
    ├── renderer.js                         # heavy refactor — consumes @aivg/sat-sdk
    ├── main.js                             # unchanged
    ├── preload.js                          # unchanged
    └── package.json                        # add `@aivg/sat-sdk` as a dep
```

**Structure Decision**:

A new top-level `sdks/` directory parallels the existing `clients/`,
`src/`, `tests/`, `specs/`, and `deploy/` directories. The choice of `sdks/`
(plural) leaves room for the upcoming C++ SDK (feature 015 → `sdks/cpp/`)
without a future restructure. The TypeScript package lives at
`sdks/typescript/` with its own `package.json`; the existing repo
`pyproject.toml` is unaffected.

Within `sdks/typescript/`, file layout follows npm-package conventions:
`src/` for source, `tests/` for tests, `examples/` for runnable demos,
`README.md` and `CHANGELOG.md` at the package root. Source is split by
*concern*, not by *plane* — each plane spans multiple files
(control-plane.ts + ota.ts + config.ts + logs.ts + commands.ts) because
the spec's FRs cluster around concerns, not transport planes.

The refactor of `clients/electron-test/` is local to that directory; no
restructure or rename. It gains `@aivg/sat-sdk` as a dependency (linked
locally via workspace protocol during development) and its `renderer.js`
shrinks ≥ 30 % per SC-009.

## Complexity Tracking

No constitution violations to justify. The plan is intentionally simple:
single npm package, single source-language, single bundle pipeline,
zero native deps.

The one decision worth flagging here (not a violation, just a tradeoff):

| Choice | Why | Alternative rejected |
| ------ | --- | -------------------- |
| Single artefact for browser + Node | Bundler portability + zero per-runtime drift | Per-runtime entry points (`./browser.js` vs `./node.js`) — rejected because conditional exports require bundler cooperation and historically produce subtle drift between runtimes. See research.md §"WebRTC-in-Node strategy". |
