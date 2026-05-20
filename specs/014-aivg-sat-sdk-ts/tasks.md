---
description: "Task list for feature 014-aivg-sat-sdk-ts"
---

# Tasks: `@aivg/sat-sdk` (TypeScript)

**Input**: Design documents from [/specs/014-aivg-sat-sdk-ts/](.)
**Constitution**: v2.0.1 (no amendment in this feature)
**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Tests**: included — the plan calls for unit + contract + integration coverage; the binding gates are SC-001 (< 50 LoC consumer code), SC-002 (electron-test functional parity), SC-003 (30 s reconnect), SC-004 (no `any` in public surface), SC-007 (contract version stays `1.0.0`), SC-008 (event-surface latency ≤ 200 ms), SC-009 (electron-test renderer LoC reduced ≥ 30%).
**Organization**: tasks grouped by user story (US1–US4). Phase 1 (Setup) and Phase 2 (Foundational) block all stories.

## Format: `[ID] [P?] [Story?] Description with file path`

## Path conventions

New top-level `sdks/typescript/` directory inside the existing monorepo. Refactor target is the existing `clients/electron-test/`. No other top-level directories created. All paths absolute from repo root unless noted.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: bootstrap the new npm package layout and tooling. Nothing consumer-visible yet.

- [X] T001 Create `sdks/typescript/` directory + initial `sdks/typescript/package.json` with `name=@aivg/sat-sdk`, `version=0.0.0`, `type=module`, `private=false`, `publishConfig.access=public`, `exports` map gating `./` deep-imports, `files=["dist/**","README.md","CHANGELOG.md","LICENSE"]`, scripts (`build`, `test`, `lint`, `format`, `prepublishOnly`).
- [X] T002 [P] Create `sdks/typescript/tsconfig.json` with `strict: true`, `exactOptionalPropertyTypes: true`, `noUncheckedIndexedAccess: true`, `target: "ES2022"`, `module: "ESNext"`, `moduleResolution: "Bundler"`, `declaration: true`, `declarationMap: true`, `sourceMap: true`, `outDir: "./dist"`, `rootDir: "./src"`, `lib: ["ES2022","DOM","DOM.Iterable"]`.
- [X] T003 [P] Create `sdks/typescript/tsup.config.ts` per plan §"R-2": `entry: { index: "src/index.ts" }`, `format: ["esm","cjs"]`, `dts: true`, `sourcemap: true`, `clean: true`, `target: "es2022"`, `platform: "neutral"`, `treeshake: true`, `minify: false`, define `__SDK_VERSION__` from `package.json#version`.
- [X] T004 [P] Create `sdks/typescript/vitest.config.ts` with two project envs: `unit` (default Node), `contract` (`happy-dom`); coverage gate ≥ 85 % lines via `@vitest/coverage-v8`; `setupFiles` for fake-webrtc helper.
- [X] T005 [P] Create `sdks/typescript/.eslintrc.cjs` (typescript-eslint strict-type-checked + no-floating-promises + no-misused-promises) and `sdks/typescript/.prettierrc` (default + `printWidth: 100`).
- [X] T006 [P] Create `sdks/typescript/README.md` skeleton (install / 30-line example / link to spec) and `sdks/typescript/CHANGELOG.md` (Keep-a-Changelog format, single `0.1.0 (unreleased)` section).
- [X] T007 [P] Create `sdks/typescript/LICENSE` (MIT, mirroring repo root if present; create if absent).
- [X] T008 [P] Append `sdks/typescript/dist/`, `sdks/typescript/node_modules/`, `sdks/typescript/coverage/` to repo-root `.gitignore`.
- [X] T009 [P] Create `sdks/typescript/tests/helpers/fake-webrtc.ts` — in-process `FakePC` implementing the subset of `RTCPeerConnection` documented in `contracts/webrtc-injection.md` (addTrack, createOffer, set{Local,Remote}Description, gathering state machine, ontrack, close). Used by every unit/contract test.

**Checkpoint**: `cd sdks/typescript && npm install && npm run build` produces an empty-but-typed `dist/` (only the version constant + an `export {}` barrel). Tooling validated.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: ship the cross-cutting building blocks every user story depends on — wire shapes, error codes, state machine, event bus, and the public-surface skeleton. NO functional behavior yet (Satellite class is hollow); the goal is "everything compiles and the typed surface matches the contracts".

**⚠️ CRITICAL**: No user-story phase work until Phase 2 is complete.

- [X] T010 Create `sdks/typescript/src/proto/version.ts` exporting `CONTRACT_VERSION = "1.0.0"` (matches `aivg --contract-version`).
- [X] T011 [P] Create `sdks/typescript/src/proto/ws-messages.ts` — every inbound + outbound WS shape per [contracts/wire-protocol.md](./contracts/wire-protocol.md) "WebSocket protocol" section, as discriminated unions on `type`. Include `_unknown: Record<string, unknown>` slot per R-8's forward-compat rule.
- [X] T012 [P] Create `sdks/typescript/src/proto/rest-shapes.ts` — every REST request/response shape per [contracts/wire-protocol.md](./contracts/wire-protocol.md) "HTTP shapes" section.
- [X] T013 [P] Create `sdks/typescript/src/errors.ts` exporting the closed `SdkErrorCode` union (R-11, 12 codes), `SdkError` class, `TransientError` interface, and helper `sdkError(code, message, cause?)` factory.
- [X] T014 [P] Create `sdks/typescript/src/state.ts` — `SatelliteState` literal union + `transition(state, event): SatelliteState` pure function. Exhaustive-switch shape so TS catches missing cases.
- [X] T015 [P] Create `sdks/typescript/src/events.ts` — typed `EventBus<EventMap>` (no `EventEmitter` polyfill; pure Map-based listener registry). `SatelliteEvents` map per [data-model.md §11](./data-model.md). Async-iterator helper `iterate<E>(bus, event)` for the streamy events.
- [X] T016 [P] Create `sdks/typescript/src/webrtc/injectable.ts` — type-only file defining `WebrtcFactory`, `AudioSink`, `AudioSinkFactory`, `MicSourceFactory`. No runtime code; pure contracts.
- [X] T017 Create `sdks/typescript/src/index.ts` barrel skeleton — exports `CONTRACT_VERSION`, every type from `proto/`/`errors`/`state`/`events`/`webrtc/injectable`. `Satellite` class is exported as `export {} from "./satellite"` (placeholder; `satellite.ts` is added in US1).
- [X] T018 [P] Unit test: `sdks/typescript/tests/unit/state-machine.test.ts` — enumerate every (state, event) transition from [data-model.md §2](./data-model.md); assert `transition()` returns the documented next state; assert invalid events stay in the current state.
- [X] T019 [P] Unit test: `sdks/typescript/tests/unit/errors.test.ts` — every `SdkErrorCode` literal is exported; `sdkError(code, msg)` produces an `instanceof SdkError`; `instanceof Error` chain works.
- [X] T020 [P] Unit test: `sdks/typescript/tests/unit/events.test.ts` — subscribe/unsubscribe; multi-handler dispatch; one bad handler doesn't break others (parity with `EventTarget`); async iterator backs out on `return()`.
- [X] T021 [P] Unit test: `sdks/typescript/tests/unit/proto-versioning.test.ts` — `CONTRACT_VERSION === "1.0.0"`; ws-messages discriminant exhaustiveness; unknown-`type` parser returns `{ kind: "unknown", _unknown: ... }`.

**Checkpoint**: `npm test --workspace sdks/typescript` passes; `npm run build` emits a valid (but functionally empty) `dist/index.{mjs,cjs}` and `dist/index.d.ts`. The four core foundational tests (T018–T021) form the regression net for everything below.

---

## Phase 3: User Story 1 — Working voice satellite (Priority: P1) 🎯 MVP

**Goal**: a consumer can write a fresh PWA/Electron/Node app in < 50 LoC that registers, completes one voice turn, and tears down — proving the package is useful at all.

**Independent Test**: SC-001 — `sdks/typescript/examples/browser-ptt/` opens against `http://localhost:8643`, the operator adopts it via `aivg device adopt`, the app's PTT button completes a voice turn (gateway logs show one full STT → agent → TTS cycle) and the SDK state machine transitions `idle → listening → speaking → idle`.

### Implementation (US1)

- [X] T022 [P] [US1] Create `sdks/typescript/src/control-plane.ts` — `ControlPlane` class: opens WS to `<gateway>/satellite/ws?device_id=<id>`, sends `register` per [contracts/wire-protocol.md](./contracts/wire-protocol.md), parses inbound messages via the `proto/ws-messages` switch, dispatches into the `EventBus`. Auto-reconnect with exponential back-off (initial 500 ms, factor 1.5, ceiling 30 s, ±20 % jitter, 60 s success-reset) per R-6.
- [X] T023 [P] [US1] Implement heartbeat loop in `sdks/typescript/src/control-plane.ts` — sends `heartbeat` every `heartbeatIntervalMs` (default gateway-suggested 30 s) carrying current `SatelliteState`. Cancellable on disconnect.
- [X] T024 [P] [US1] Create `sdks/typescript/src/signaling.ts` — `postOffer(gatewayUrl, deviceId, sdp): Promise<RTCSessionDescriptionInit>` (POST `/webrtc/offer`); `postCandidate(...)` fallback (only used if gathering times out > 5 s per R-7); typed errors mapped to `SdkErrorCode` (`signaling_failed`, `ice_gathering_timeout`).
- [X] T025 [P] [US1] Create `sdks/typescript/src/webrtc/browser.ts` — `defaultWebrtcFactory` that returns `new globalThis.RTCPeerConnection({iceServers:[]})` or throws `SdkError("no_webrtc_impl", …)`. Exported from `index.ts` so consumers can compose it.
- [X] T026 [P] [US1] Create `sdks/typescript/src/webrtc/audio-sink.ts` — `defaultAudioSinkFactory` that creates a managed `<audio autoplay>` element and attaches it on `attach(stream)`; throws `SdkError("no_microphone_api", …)` when run outside the DOM.
- [X] T027 [US1] Create `sdks/typescript/src/voice-session.ts` — `VoiceSession` class: instantiated by `Satellite.beginSession()`. Calls `getUserMedia(micConstraints)`, builds PC via injected factory, attaches mic, sets up `ontrack` for remote stream forwarded to audio sink, runs full-gather ICE, posts offer, applies answer, transitions FSM `idle → listening`, transitions to `speaking` on first inbound audio frame. Emits `session_started` + `session_ended`. Cleans up mic tracks + PC on close. Depends on T022, T024, T025, T026.
- [X] T028 [US1] Create `sdks/typescript/src/satellite.ts` — `Satellite` class per [contracts/satellite-api.md](./contracts/satellite-api.md): constructor, `connect()`, `disconnect()`, `beginSession()`, `endSession()`, `state`, `adoptionState` (read from control-plane; full adoption flow lands in US2), `on()`/`off()`. Wires `ControlPlane` + `VoiceSession` + `EventBus` + `state.ts` reducer. Idempotent `connect()` and `beginSession()` per FR-008/FR-009.
- [X] T029 [US1] Wire US1 surface in `sdks/typescript/src/index.ts` — export `Satellite`, `SatelliteOptions`, `SatelliteState`, `defaultWebrtcFactory`, `defaultAudioSinkFactory`, `CONTRACT_VERSION`, `SDK_VERSION`. Remove the placeholder re-export from T017.

### Tests (US1)

- [X] T030 [P] [US1] Unit test: `sdks/typescript/tests/unit/control-plane.test.ts` — open/register/heartbeat happy path; on-message dispatch invokes event bus; close stops heartbeat. Mocked `WebSocket`.
- [X] T031 [P] [US1] Unit test: `sdks/typescript/tests/unit/reconnect-backoff.test.ts` — vitest fake timers; verify back-off schedule (500 → 750 → 1125 → ... clamped to 30 000); verify ±20 % jitter band; verify reset after 60 s of stability; verify `max_retries` ceiling fires `error` event.
- [X] T032 [P] [US1] Unit test: `sdks/typescript/tests/unit/signaling.test.ts` — happy path POST `/webrtc/offer`; 4xx/5xx mapped to `signaling_failed`; timeout mapped to `ice_gathering_timeout`. Mocked `fetch`.
- [X] T033 [P] [US1] Unit test: `sdks/typescript/tests/unit/voice-session.test.ts` — drives `FakePC` from `tests/helpers/fake-webrtc.ts` through the full state machine; asserts mic released on `endSession()`; asserts FSM transitions reach `idle → listening → speaking → idle`; asserts idempotent `beginSession()` returns the same instance.
- [X] T034 [US1] Contract test: `sdks/typescript/tests/contract/public-api.test.ts` — read [contracts/satellite-api.md](./contracts/satellite-api.md) "Package exports" section; for each named export, assert `typeof import("@aivg/sat-sdk")[name] !== "undefined"` and (for types) assert the `.d.ts` declaration exists via a `tsc --noEmit --strict` check on a fixture file that uses all names. **Binding gate for the published-surface contract.**

### Examples (US1)

- [X] T035 [P] [US1] Create `sdks/typescript/examples/browser-ptt/index.html` + `app.ts` per [quickstart.md §"Flow 1"](./quickstart.md) — exactly the < 50 LoC reference implementation. Buildable with `npx tsc app.ts`, served by `npx http-server`.
- [X] T036 [P] [US1] Create `sdks/typescript/examples/node-headless/smoke.ts` per [quickstart.md §"Flow 3"](./quickstart.md) — uses `@roamhq/wrtc` injected; reads `GATEWAY_URL` env; exits 0 on transcript received, 1 otherwise.
- [X] T037 [P] [US1] Create `sdks/typescript/examples/electron-renderer/` skeleton — minimal renderer that imports `@aivg/sat-sdk` and prints state transitions. Not the full Electron client refactor (that's US4).

### Live integration tests (US1)

- [X] T038 [US1] Integration test: `sdks/typescript/tests/integration/node-live.spec.ts` — gates on `GATEWAY_URL` env; uses `@roamhq/wrtc` injected; registers, makes one voice call, expects at least one `transcript` event for the assistant. Marked `test.skip()` when env unset. **Binding gate for SC-001 (live MVP voice turn).**
- [X] T039 [US1] Integration test: `sdks/typescript/tests/integration/browser-live.spec.ts` — playwright, headless Chromium, points at the `browser-ptt` example, simulates a button click + injected audio. CI-gated; not run locally by default.

**Checkpoint**: a fresh user can `npm install @aivg/sat-sdk`, write the 30-line `browser-ptt` example, run `aivg device adopt`, and complete one voice turn against the live gateway. US2/US3/US4 not yet shipped.

---

## Phase 4: User Story 2 — Fleet management citizen (Priority: P2)

**Goal**: SDK-based satellites appear in `aivg list`, accept config pushes, receive operator commands, and stream logs — full management-plane parity with the existing Electron test client.

**Independent Test**: SC-010 — a SDK-consumer satellite running shows up in `aivg list` as `online / adopted`, accepts `aivg device config set --field log_level=DEBUG` (verified by an event on the SDK side), and an operator-issued `aivg device command <id> reboot` arrives as a `CommandEvent` the consumer can handle.

### Implementation (US2)

- [X] T040 [P] [US2] Create `sdks/typescript/src/adoption.ts` — `AdoptionTracker` class: subscribes to inbound `adoption` WS messages; maintains `pending → adopted` state; emits `adoption` event with `firstApproval: boolean` per [data-model.md §3](./data-model.md). Wired into `Satellite.adoptionState`.
- [X] T041 [P] [US2] Create `sdks/typescript/src/config.ts` — `ConfigClient`: `getConfig()` via `GET /satellite/{id}/config`; `setConfig(patch)` via `POST /satellite/{id}/config` with `if_match_version` for optimistic concurrency; 409 → typed retry hint. Subscribes to `config_changed` WS messages and emits via the bus.
- [X] T042 [P] [US2] Create `sdks/typescript/src/commands.ts` — `CommandDispatcher`: parses `command` WS messages, builds `CommandEvent` with `reply()` channel that posts `command_result` back over WS. Closed-set verbs per [data-model.md §7](./data-model.md).
- [X] T043 [P] [US2] Create `sdks/typescript/src/logs.ts` — `LogForwarder`: maps inbound `log_entry` WS messages to typed `LogEntry` events, dispatched via the bus.
- [X] T044 [US2] Wire US2 modules into `sdks/typescript/src/satellite.ts` — instantiate `AdoptionTracker`, `ConfigClient`, `CommandDispatcher`, `LogForwarder` from the constructor; expose `getConfig()`/`setConfig()` methods; ensure `not_adopted` short-circuit on `beginSession()` until `adoptionState === "adopted"` (FR-001, edge case).
- [X] T045 [US2] Update `sdks/typescript/src/index.ts` exports for US2 — add `AdoptionState`, `AdoptionEvent`, `SatelliteConfig`, `CommandEvent`, `CommandResult`, `LogEntry` types.

### Tests (US2)

- [X] T046 [P] [US2] Unit test: `sdks/typescript/tests/unit/adoption.test.ts` — pending → adopted transition; `firstApproval` true exactly once; ignored re-affirmations.
- [X] T047 [P] [US2] Unit test: `sdks/typescript/tests/unit/config.test.ts` — happy-path get/set; 409 conflict surfaces `version_conflict` for the consumer to retry; `config_changed` WS push surfaces as event.
- [X] T048 [P] [US2] Unit test: `sdks/typescript/tests/unit/commands.test.ts` — verb dispatch for each closed-set verb; `reply()` posts `command_result` over WS with matching `request_id`; reply timeout (consumer didn't call reply) does not leak.
- [X] T049 [P] [US2] Unit test: `sdks/typescript/tests/unit/logs.test.ts` — `log_entry` WS push surfaces as `LogEntry` event; level/source/message preserved.

### Contract tests + fixtures (US2)

- [X] T050 [US2] Contract test: `sdks/typescript/tests/contract/wire-protocol.test.ts` — replays JSON-lines fixtures through the SDK with mocked WS + fetch; asserts the documented event sequence. Per [contracts/wire-protocol.md](./contracts/wire-protocol.md) "Captured fixture format". **Binding gate for SC-007 (contract version preserved).**
- [X] T051 [P] [US2] Create fixture: `sdks/typescript/tests/fixtures/wire/happy-path-one-turn.jsonl` — captured (or hand-crafted) from a clean register/adopt/voice-turn/disconnect sequence.
- [X] T052 [P] [US2] Create fixture: `sdks/typescript/tests/fixtures/wire/reconnect-after-drop.jsonl` — WS drop mid-session + recovery within 30 s. **Binding gate for SC-003.**
- [X] T053 [P] [US2] Create fixture: `sdks/typescript/tests/fixtures/wire/config-pushed-mid-call.jsonl` — operator pushes config change during an active voice session.

**Checkpoint**: an SDK satellite is now a full management-plane citizen. `aivg list`, `aivg device config set/get`, `aivg device command`, and `aivg logs` all work against it identically to the legacy Electron test client.

---

## Phase 5: User Story 3 — Agent telemetry (Priority: P3)

**Goal**: a chat-style UI on top of the SDK can show what the agent is doing in real time — which tools it called, which skill it loaded, the partial assistant text as it streams.

**Independent Test**: SC-008 — a voice turn whose agent invokes a tool produces a sequence of `tool_call_started → tool_call_completed → transcript_delta(final=true)` events at the SDK event surface, with the gateway-to-handler latency ≤ 200 ms p99.

### Implementation (US3)

- [X] T054 [P] [US3] Create `sdks/typescript/src/agent-events.ts` — parses inbound `agent_event` WS messages by `kind` (`tool_call_started`, `tool_call_completed`, `tool_call_failed`, `skill_loaded`, `transcript_delta`); fans out to typed events (`tool_call`, `skill`, `transcript`) on the bus. Unknown `kind` values emit `transient_error(protocol_mismatch)` once per session per R-8.
- [X] T055 [P] [US3] Create `sdks/typescript/src/ota.ts` — parses inbound `ota_manifest` + `ota_progress` WS messages; emits `ota_manifest` / `ota_progress` events. Never auto-applies (FR-018) — pure forwarder.
- [X] T056 [US3] Wire `agent-events.ts` + `ota.ts` into `sdks/typescript/src/satellite.ts`.
- [X] T057 [US3] Implement async-iterator wrappers in `sdks/typescript/src/satellite.ts` — `transcripts()`, `logs()`, `states()` per [contracts/satellite-api.md](./contracts/satellite-api.md) "Async-iterator sugar". Bounded queue (1024) per iterator; overflow emits `transient_error(buffer_overflow)`.
- [X] T058 [US3] Update `sdks/typescript/src/index.ts` exports for US3 — add `ToolCallEvent`, `SkillEvent`, `TranscriptDelta`, `OtaManifest`, `OtaProgress` types.

### Tests (US3)

- [X] T059 [P] [US3] Unit test: `sdks/typescript/tests/unit/agent-events.test.ts` — each `kind` round-trip; unknown `kind` emits exactly one `transient_error` per session; speaker/seq/ts preserved on `transcript_delta`.
- [X] T060 [P] [US3] Unit test: `sdks/typescript/tests/unit/ota.test.ts` — manifest + progress shapes round-trip; SDK never auto-fetches or auto-applies; consumer events fire.
- [X] T061 [US3] Contract test: `sdks/typescript/tests/contract/event-surface.test.ts` — for every key in `SatelliteEvents`, drive a fixture that should fire it; assert the event fires with the documented payload shape. **Binding gate for FR-006/FR-015/FR-016/FR-017/FR-018.**

### Fixtures (US3)

- [X] T062 [P] [US3] Create fixture: `sdks/typescript/tests/fixtures/wire/tool-call-turn.jsonl` — turn that invokes one tool (started + completed events).
- [X] T063 [P] [US3] Create fixture: `sdks/typescript/tests/fixtures/wire/ota-during-session.jsonl` — OTA manifest arrives while in `speaking` state (verifies non-auto-disconnect).
- [X] T064 [P] [US3] Create fixture: `sdks/typescript/tests/fixtures/wire/unknown-event-kind.jsonl` — forward-compat smoke (R-8).

**Checkpoint**: a consumer UI can render tool calls in flight, show streaming assistant text, and let the user see which skill the agent loaded mid-turn.

---

## Phase 6: User Story 4 — Refactor `clients/electron-test/` as living integration test (Priority: P2)

**Goal**: prove the SDK's API covers everything the test client needs by rewriting the test client to consume it, removing every direct WebRTC/WebSocket primitive call. The refactored client becomes the continuously-runnable integration sanity check for every future SDK change.

**Independent Test**: SC-002 — the refactored `clients/electron-test/` achieves byte-equivalent end-to-end behavior against the same gateway as the pre-refactor version verified during feature 013 live testing. AND SC-009: `clients/electron-test/renderer.js` line count drops ≥ 30 %.

### Implementation (US4)

- [X] T065 [US4] Add `@aivg/sat-sdk` to `clients/electron-test/package.json` `dependencies` using a `file:../../sdks/typescript` path during dev; tweak `package.json#main`/`module` resolution if needed (Electron 31 + Vite/esbuild bundler).
- [X] T066 [US4] Rewrite `clients/electron-test/renderer.js` to consume `Satellite` only — instantiate from input fields, subscribe to the documented events, drive `connect()`/`beginSession()`/`endSession()` from the existing buttons. Use the skeleton from [quickstart.md §"Flow 2"](./quickstart.md) as the starting point.
- [X] T067 [US4] Delete `clients/electron-test/renderer.js` blocks that directly use `RTCPeerConnection`, `WebSocket`, `fetch(.../webrtc/...)`, or `navigator.mediaDevices.getUserMedia`. After this task, `grep -E 'RTCPeerConnection|new WebSocket|/webrtc/offer|getUserMedia' clients/electron-test/renderer.js` MUST return zero matches.
- [X] T068 [US4] Live-verify functional parity — start the gateway (`hermes gateway run`), run `npm start` in `clients/electron-test/`, run `aivg device adopt electron-test-1`, hold PTT, confirm one full voice turn completes with transcript surfaced in the UI. Mirror the feature-013 live test trace at agent.log lines 16:13:34 → 16:13:54.
- [X] T069 [US4] Verify SC-009 line-count reduction — `git diff --stat clients/electron-test/renderer.js` before/after MUST show ≥ 30 % deletions in non-blank, non-comment lines. Record measurement in `specs/014-aivg-sat-sdk-ts/integration-notes.md`.

**Checkpoint**: every future SDK protocol change has an immediately-runnable integration test: launch `clients/electron-test/`, complete a voice turn. The Electron test client is now an SDK consumer, not a fork.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: package-quality items + documentation + verification of the no-leak / no-`any` / size budgets called for in spec success criteria.

- [X] T070 [P] Contract test: `sdks/typescript/tests/contract/no-any-in-public.test.ts` — uses `ts-morph` to walk `dist/index.d.ts`; asserts no `any` type appears in any exported symbol's declaration. **Binding gate for SC-004.**
- [X] T071 [P] Package-size check script `sdks/typescript/scripts/check-size.mjs` — builds `dist/`, runs `gzip-size` on `index.mjs`, asserts ≤ 50 KB. Wired into the `prepublishOnly` script.
- [X] T072 [P] Write `sdks/typescript/README.md` — install instructions, 30-line example (from `browser-ptt`), feature list, links to spec / data-model / contracts.
- [X] T073 [P] Finalize `sdks/typescript/CHANGELOG.md` with the `0.1.0` release notes covering US1+US2+US3+US4 (Keep-a-Changelog).
- [X] T074 [P] Run `npm run lint` + `npm run format` clean; commit the autofix.
- [X] T075 [P] Add CI snippet to `.github/workflows/sdk-ts.yml` (if `.github/workflows/` exists) or to `sdks/typescript/README.md` "CI" section: build + unit + contract + size check + lint. Integration tests run only when `GATEWAY_URL` env is set (CI-gated).
- [X] T076 Run `npm pack` in `sdks/typescript/`; inspect the resulting tarball — assert `dist/index.{mjs,cjs,d.ts}` are present, `tests/` + `examples/` + `node_modules/` + fixture `.jsonl` files are EXCLUDED. Verify `package.json#files` works as intended.
- [X] T077 Update `specs/014-aivg-sat-sdk-ts/quickstart.md` to reflect the final import paths and example file locations once everything has shipped.
- [X] T078 Tag and announce — bump `sdks/typescript/package.json#version` to `0.1.0`, create git tag `sdk-ts-v0.1.0` per R-13.

---

## Dependencies

```
Phase 1 (Setup) — T001..T009
   ↓ (everything blocks on package skeleton)
Phase 2 (Foundational) — T010..T021
   ↓ (every story needs proto + errors + state + events)
   ├──► Phase 3 (US1) — T022..T039       [MVP — P1]
   ├──► Phase 4 (US2) — T040..T053       [P2; can overlap US3 once US1 done]
   ├──► Phase 5 (US3) — T054..T064       [P3; can overlap US2 once US1 done]
   └──► Phase 6 (US4) — T065..T069       [P2; depends on US1+US2 done]
            ↓
         Phase 7 (Polish) — T070..T078
```

### Story dependencies (post-Phase-2)

- **US1 (P1)** is foundational for everything else — no `beginSession` flow until US1 ships.
- **US2 (P2)** depends only on US1's `ControlPlane` being live; adoption events arrive over the same WS US1 opens.
- **US3 (P3)** depends only on US1's `ControlPlane`; agent telemetry rides the same WS. US3 + US2 are fully parallel.
- **US4 (P2)** depends on US1 (voice path) + US2 (config push/pull, logs) being functionally complete — refactoring electron-test requires the SDK surface to cover everything electron-test does today. US4 may begin after US2 lands; US3 can land in parallel or after.

### MVP slice

**T001…T039 alone** ships a working `@aivg/sat-sdk` v0.1.0-MVP capable of completing voice turns. US2/US3/US4 polish the integration; releasing 0.1.0 requires all phases through Polish.

---

## Parallel execution examples

### Phase 1 (Setup) — six parallel files

```text
T002 [P] tsconfig.json          ┐
T003 [P] tsup.config.ts         │
T004 [P] vitest.config.ts       │── all independent files
T005 [P] eslint+prettier        │   → spawn six PRs/branches/agents
T006 [P] README + CHANGELOG     │
T009 [P] fake-webrtc helper     ┘
```

### Phase 2 (Foundational) — eight parallel files

```text
T011..T016 (proto, errors, state, events, webrtc/injectable, ...)   ← all [P]
T018..T021 (unit tests for the above)                               ← all [P], gated on their target file
```

### Phase 3 (US1) — split

```text
Wave 1 (parallel):
  T022..T023 control-plane.ts        ← single file → sequential within
  T024 [P]   signaling.ts
  T025 [P]   webrtc/browser.ts
  T026 [P]   webrtc/audio-sink.ts

Wave 2 (sequential):
  T027   voice-session.ts            ← depends on T022/T024/T025/T026
  T028   satellite.ts                ← depends on T027
  T029   index.ts wiring             ← depends on T028

Wave 3 (parallel, gated on wave 2):
  T030..T037 (unit tests + examples) ← all [P]

Wave 4 (sequential, CI-gated):
  T038 node-live integration
  T039 browser-live integration
```

### Phase 4 + 5 (US2 + US3) — full parallel

After US1 lands, US2 (T040..T053) and US3 (T054..T064) touch disjoint
files and disjoint WS messages — can be implemented and reviewed in
parallel branches.

---

## Implementation strategy

1. **MVP first**: Phase 1 → Phase 2 → Phase 3 (US1). This is the shippable
   "@aivg/sat-sdk v0.1.0-MVP" — useful, documented, demoable. Estimated
   ~40 % of total feature LOC.
2. **Fleet citizenship**: Phase 4 (US2) brings management-plane parity.
   ~25 % of total feature LOC.
3. **Agent telemetry**: Phase 5 (US3) — chat-UI-ready. ~15 % LOC.
4. **Dog-food**: Phase 6 (US4) — the refactor proves SDK completeness and
   surfaces any missing affordances. Often the highest-signal phase.
   ~10 % LOC (mostly deletions in electron-test).
5. **Polish**: Phase 7 — size check, type check, docs, publish dry-run.
   ~10 % LOC, but blocks the `0.1.0` git tag.

Each completed phase is independently demoable. The MVP slice
(Phases 1–3) is the smallest unit any consumer can use. Phases 4+5
are independent of each other and can be parallelised on a two-person
team. Phase 6 (electron-test refactor) is the unifying integration test
and SHOULD land before the `0.1.0` git tag.

---

## Format validation

Every task in this file follows: `- [ ] T### [P?] [USn?] Description with file path`. Setup (T001..T009), Foundational (T010..T021), and Polish (T070..T078) tasks have no `[USn]` label per the rule. Every implementation task references a concrete file path under `sdks/typescript/` or `clients/electron-test/` so an LLM can execute without further context.
