# Research — `@aivg/sat-sdk` (Phase 0)

**Feature**: 014-aivg-sat-sdk-ts · **Date**: 2026-05-20

Phase 0's job is to nail every "NEEDS CLARIFICATION" left in the Technical
Context and pin down the technology choices that shape the contract /
package layout (locked in plan.md). The spec was clarification-free at the
end of `/speckit-specify`; this document records the *technology* decisions
left implicit in the spec — and the alternatives that were rejected — so
they're not relitigated mid-implementation.

Each section ends with the decision committed to plan.md.

---

## R-1. WebRTC-in-Node strategy (the binding architecture question)

**Question**: The spec mandates the package works in Node.js 20+ but also
forbids native compiled dependencies (FR-024, SC-005). The browser has
`RTCPeerConnection` built in; Node does not. How do Node users get WebRTC
without dragging in a native binary?

**Options considered**:

1. **Bundle a pure-JS WebRTC implementation** (e.g. `pion-wasm` if one
   existed). *Rejected*: no production-grade pure-JS WebRTC stack exists
   today. WebRTC's ICE/DTLS/SRTP layers are too performance-sensitive
   for plain JS.
2. **Bundle a native Node WebRTC binding** (e.g. `@roamhq/wrtc`,
   `node-webrtc`). *Rejected*: violates SC-005. Forces `node-gyp` /
   `prebuildify` paths, breaks Windows installs that don't have the
   toolchain, and Linux distros that disagree about libstdc++ ABIs. It
   would also bloat the npm install for browser/Electron consumers
   who never need it.
3. **Dependency-inject the `RTCPeerConnection` constructor at
   `new Satellite(...)` time**. ✅ *Selected*. The browser/Electron path
   defaults to the host's built-in `globalThis.RTCPeerConnection`; Node
   consumers explicitly pass their own (typically `@roamhq/wrtc` or a
   fake in tests). The SDK is WebRTC-impl-agnostic by construction.

**Decision (R-1)**: WebRTC is a DI hole. The SDK ships one default
factory (returns `globalThis.RTCPeerConnection` if defined, throws a
typed `SdkError(no_webrtc_impl)` if not) and a documented constructor
override. No `peerDependencies` to wrtc libraries — the consumer's
project owns that choice.

**Implication for contracts**: `webrtc-injection.md` documents the
factory shape (returns an instance compatible with the standard W3C
`RTCPeerConnection` interface — addTrack/setRemoteDescription/
createOffer/etc).

---

## R-2. Build / publish pipeline

**Question**: How does the package emit ESM + CJS + `.d.ts` without
adding bundler config sprawl?

**Options considered**:

1. **Hand-rolled `tsc` invocations**. *Rejected*: requires separate
   compile passes for ESM/CJS, separate `tsc --declaration` pass for
   typings, plus glue to copy and rename outputs. The `package.json`
   `exports` field becomes brittle.
2. **`rollup` + plugins**. *Rejected*: rollup is fine but the plugin
   surface is heavy for what we need; would require `@rollup/plugin-typescript`,
   `@rollup/plugin-terser`, a separate `.d.ts` step via `rollup-plugin-dts`.
3. **`tsup`** (esbuild under the hood, single config, emits ESM + CJS +
   `.d.ts` from one entry point in seconds). ✅ *Selected*. Same tool
   `socket.io-client`, `zod`, `hono`, and most modern TS libraries use.

**Decision (R-2)**: `tsup` with a single `tsup.config.ts`:

```ts
export default defineConfig({
  entry: { index: "src/index.ts" },
  format: ["esm", "cjs"],
  dts: true,
  sourcemap: true,
  clean: true,
  target: "es2022",
  platform: "neutral",   // works in both browser and Node
  treeshake: true,
  minify: false,         // consumers minify if they want; we ship readable
});
```

Tested-against bundlers (CI matrix in feature 015 if needed): webpack 5,
Vite 5, esbuild standalone, Rollup 4, Parcel 2, Electron Forge default.

---

## R-3. Test framework

**Question**: One framework or split (unit-Node + browser-headless)?

**Options considered**:

1. **`jest`**. *Rejected*: slower, heavier config, transformer overhead
   for TS. Browser-emulation envs (`jest-environment-jsdom`) are
   maintained but stale relative to current standards.
2. **`mocha` + `chai`**. *Rejected*: TS support requires more plumbing
   (`ts-node` ESM/CJS resolution is still rough on Node 20+).
3. **`vitest`**. ✅ *Selected*. Native ESM, native TS, parallel by default,
   `happy-dom` and `jsdom` envs first-class, drop-in mock API,
   built-in coverage via `c8`. Same DX in unit (Node) and contract
   (DOM-emulated) tests.

**Decision (R-3)**: `vitest`. Two project envs:

- `tests/unit/**` runs under default Node env (state machine, reconnect
  back-off, error mapping, JSON proto shape tests).
- `tests/contract/**` runs under `happy-dom` (default — lighter than
  jsdom, faster to spin up) — these tests exercise the public API
  surface and event shapes against an instance using mocked
  `WebSocket` + `RTCPeerConnection`.
- `tests/integration/**` is skipped locally by default and runs only
  with `GATEWAY_URL=` env set (CI gates it on a live AIVG instance).

---

## R-4. Public API style — events vs callbacks vs async iterators

**Question**: How does the SDK surface state changes, telemetry, errors?

**Options considered**:

1. **Node-style `EventEmitter`**. *Rejected*: not native to browsers,
   needs a polyfill. Loose typing in TS (`emit("foo", anything)`).
2. **Callback registration** (`on(eventName, callback)`). *Acceptable*
   but verbose and loses the convenience of `for await`.
3. **`EventTarget` (DOM standard)** subclass. *Acceptable* and
   native everywhere, but typing each event type is painful — DOM's
   own `EventTarget` types are weak.
4. **Both: typed `on(event, callback)` + an `AsyncIterableIterator`
   for `transcripts()`, `logs()`, etc.** ✅ *Selected*. Lets consumers
   pick: `sat.on("state", cb)` for simple flows; `for await (const e of
   sat.transcripts())` for stream-of-deltas UIs. Internally one typed
   event bus; the iterator wrapper is a thin layer.

**Decision (R-4)**: Typed `on(event, handler)` is the primary surface
(consistent with the existing electron-test mental model). Async
iterators are syntactic sugar over the same bus, generated for the
three streamy event types: `transcripts()`, `logs()`, `state()`. All
events carry a discriminant `type` field so consumers can route on it.

```ts
// Both work:
sat.on("transcript", (d: TranscriptDelta) => append(d.text));
for await (const d of sat.transcripts()) append(d.text);
```

---

## R-5. State machine — explicit FSM lib vs hand-rolled

**Question**: Should we depend on `xstate` or hand-roll the state machine?

**Options considered**:

1. **`xstate`**. *Rejected*: ~30 KB minified — would blow the SC SC-006
   < 50 KB total package budget. Tons of features we don't need
   (visualisers, actors, parallel states). And one of the package's
   value props is "zero non-stdlib deps" — adding xstate dilutes that.
2. **Hand-rolled discriminated-union FSM**. ✅ *Selected*. A typed
   reducer (`State`, `Event`, `transition(state, event): State`) takes
   ~80 lines, is fully tree-shakable, and yields a tighter type story
   than xstate's generic typings.

**Decision (R-5)**: Hand-rolled FSM in `src/state.ts`. Exhaustive switch
on event kind; TS's exhaustiveness check catches missing transitions
at compile time. Test in `tests/unit/state-machine.test.ts` enumerates
every (state, event) pair.

---

## R-6. Reconnect / back-off policy

**Question**: What's the back-off curve for control-plane WS reconnect?
(FR-004, FR-020)

**Reference**: Hermes's own gateway adapters use exponential with jitter
(documented in `gateway/run.py`). The existing electron-test does NOT
auto-reconnect today — it leaves the WS broken until the user reloads.
This is one of the FR delta items the SDK adds.

**Decision (R-6)**:

- Initial back-off: 500 ms
- Exponent: 1.5
- Max ceiling: 30 s
- Jitter: ±20 % uniform on each interval
- Reset: 60 s of successful operation resets back-off to initial

Same shape the WHATWG WebSocket community uses ([RFC 7298 §5.3] roughly).
Codified in `src/control-plane.ts` and tested in
`tests/unit/reconnect-backoff.test.ts` using `vitest`'s fake timers.

---

## R-7. ICE strategy — trickle vs full-gather-then-offer

**Question**: spec carved out "the SDK MUST be the offerer with full
gather then offer". Should we keep `/webrtc/candidate` as a fallback?

**Reference**: existing electron-test does full-gather-then-offer
(`waitForIceCandidates(pc)` then `POST /webrtc/offer`). Works
fine on LAN. Trickle was implemented gateway-side as a fallback
(per constitution III).

**Decision (R-7)**: SDK does full-gather then offer (matches the
electron-test, simplest contract, no SDP munging). `/webrtc/candidate`
fallback path is wired but unused in v1 — emitted only if
`iceGatheringState` doesn't reach `complete` within 5 s. The fallback
codepath is testable but doesn't gate v1 ship.

---

## R-8. JSON proto types — derived from gateway or hand-written?

**Question**: The SDK consumes the same JSON shapes the Python gateway
produces. Should we generate the TypeScript types from a shared schema
(JSON Schema, OpenAPI, Pydantic models)?

**Options considered**:

1. **Generate from a shared schema**. *Rejected for v1*: there is no
   shared schema today — feature 011's contract is documented as
   Markdown + Python type hints. Building a generator is its own
   feature (R-8 follow-up below).
2. **Hand-write TS types that mirror the wire shapes**, with a
   contract test that compares hand-written shapes against a
   recorded gateway capture. ✅ *Selected*. ~150 lines of pure
   type declarations; the contract test in
   `tests/contract/wire-protocol.test.ts` replays captured wire
   payloads through the SDK's parsers and asserts on the typed
   result.

**Decision (R-8)**: Hand-written types in `src/proto/`. Contract test
asserts parity. **Follow-up to track**: feature 015 (C++ SDK) will need
the same JSON shapes; consider promoting the source-of-truth into a
shared schema file (`contracts/wire-protocol.md` or
`schemas/sat-protocol.json`) at that point.

---

## R-9. Audio sink in browser — managed `<audio>` element vs consumer-attached

**Question**: When a remote `MediaStream` arrives over WebRTC, who
attaches it to an audio output? The SDK or the consumer?

**Options considered**:

1. **SDK creates and manages an internal `<audio>` element**.
   *Acceptable* — simplest possible consumer story
   (`new Satellite(...); sat.beginSession();` and audio plays).
   But pollutes the DOM with an SDK-owned element and forecloses
   custom audio routing (e.g., the consumer wants a `<video>` for
   visualisation).
2. **SDK emits `remote_stream` event; consumer attaches**. *Acceptable*
   but every consumer has to write the same 3 lines of attach code.
3. **Both, layered**. ✅ *Selected*. SDK provides a default audio sink
   factory (creates and attaches an `<audio>` element if in
   browser/Electron); consumer may override with their own sink at
   construction time. Node always uses the consumer-supplied sink
   (since there's no DOM).

**Decision (R-9)**: Audio sink is a DI hole. Default factory wires an
internal `<audio>` element in browser/Electron. Documented in
`webrtc-injection.md`.

---

## R-10. Mic constraints — what does the SDK request from `getUserMedia`?

**Question**: The existing electron-test passes `{ echoCancellation: true,
noiseSuppression: true, autoGainControl: true }`. Should the SDK adopt the
same defaults? Allow override?

**Reference**: live-tested in feature 013; echo cancellation + NS +
AGC produced acceptable voice quality in the Electron test. (The
acoustic-echo-on-barge-in issue logged at the end of feature 013 is
NOT a `getUserMedia` constraint problem — it's a satellite-side
sensitivity tuning issue.)

**Decision (R-10)**: SDK defaults to
`{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }`
when calling `getUserMedia({ audio: ... })`. Consumer may pass an
override at construction time (`micConstraints?: MediaTrackConstraints`).

---

## R-11. Error code surface — open vs closed set

**Question**: Spec FR-019 calls for "a single typed error event with a
machine-readable code". Open enum (string) or closed set (TypeScript
literal union)?

**Decision (R-11)**: Closed set, exported as a TypeScript literal union.
Closed sets force forward-compatible thinking — a new code requires
a SemVer bump. Initial set:

```ts
export type SdkErrorCode =
  | "no_webrtc_impl"
  | "no_microphone_api"
  | "permission_denied"
  | "ice_failed"
  | "ice_gathering_timeout"
  | "ws_disconnected"
  | "ws_max_retries_exceeded"
  | "signaling_failed"
  | "mixed_content"
  | "not_adopted"
  | "protocol_mismatch"
  | "duplicate_device";
```

Mapped 1:1 onto the existing `aivg --contract-version 1.0.0` error
codes where they overlap (`not_adopted`, `permission_denied`,
`protocol_mismatch`).

---

## R-12. Examples that ship in the package

**Question**: What demos go under `sdks/typescript/examples/`?

**Decision (R-12)**:

1. **`browser-ptt/`** — a single static HTML file + 30-line `app.ts`.
   `npm install`-able as a tarball, opens in a browser, points at
   `localhost:8643`, completes a voice turn. Doubles as the SC-001
   "under 50 LoC" reference implementation.
2. **`node-headless/`** — a Node script that uses
   `@roamhq/wrtc` (peerDep, not bundled) + reads a `.wav` from disk,
   makes one turn, prints the transcript. Used as the CI smoke
   (skipped without `GATEWAY_URL` env).
3. **`electron-renderer/`** — kept minimal because the *real*
   Electron example is `clients/electron-test/` (refactored in
   this feature). This is a 50-line "hello world" for first-time
   Electron consumers.

---

## R-13. Versioning & release

**Question**: SemVer policy + npm publish workflow + tag scheme.

**Decision (R-13)**:

- Package SemVer is independent of the AIVG repo's feature numbers.
  Initial release: `0.1.0` (pre-1.0 = breaking changes possible
  without a major bump per SemVer §4).
- Promotion to `1.0.0` follows: (1) one external consumer
  (other than `clients/electron-test/`) using the SDK in
  production-shape, (2) C++ SDK (feature 015) ships, proving the
  contract translates.
- npm publish is gated behind a manual `npm run release` script;
  no CI auto-publish in v1. Two-factor required on the npm token.
- Git tags: `sdk-ts-v0.1.0`, etc. — the prefix prevents conflicts
  with feature-numbered branches.

---

## R-14. Out-of-scope items already excluded (documented for posterity)

These were considered and explicitly DEFERRED at spec time
(OOS-001 … OOS-005 in spec.md), repeated here so the implementer
doesn't get tempted mid-flight:

- Browser-side wake-word (openWakeWord-WASM, Porcupine-Web) —
  separate additive surface, post-v1.
- C++ SDK (`libaivg-sat`) — feature 015.
- ESP32 firmware (XIAO + ATOM Echo) — feature 016.
- RPi reference port — feature 017+.
- Multi-tenant auth / API keys — v1 inherits the open-LAN model
  from electron-test. Production hardening is its own feature.
- Server-recorded sample fixtures for offline testing — would let
  unit tests run without a live gateway, but recording infrastructure
  is itself a non-trivial chunk. Live-gateway smoke covers it for v1.
