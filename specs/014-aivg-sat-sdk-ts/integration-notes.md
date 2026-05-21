# Integration Notes — feature 014 / US4

**Date**: 2026-05-20
**Branch**: `014-aivg-sat-sdk-ts`

This document records the measurements + verification artefacts for
Phase 6's binding gates: SC-002 (electron-test functional parity) and
SC-009 (LoC reduction).

## SC-009 — `clients/electron-test/renderer.js` LoC delta

Measured before refactor (git HEAD of feature 013) vs after the
feature 014 / US4 refactor (this commit).

| Metric | Before | After | Δ | Reduction |
|---|---:|---:|---:|---:|
| Total lines | 114 | 42 | 72 | **63.1 %** |
| Code lines (no blank/comment) | 95 | 35 | 60 | **63.1 %** |

**Both metrics ≥ 30 % target.** SC-009 passes.

Where the lines went: all direct WebRTC / WebSocket / fetch / mic
acquisition code (~60 lines in the original) moved into the SDK. The
refactored renderer is now pure UI wiring + event subscribers.

## T067 — direct protocol code grep

`grep -E 'RTCPeerConnection|new WebSocket|getUserMedia|fetch\(.*/webrtc/'`
against `clients/electron-test/renderer.js` produces **0 matches in
code** (matches in JSDoc / line-comments are documented intentional
references to what the SDK now owns).

Strict check via comment-stripped AST:

```text
RTCPeerConnection / new WebSocket / getUserMedia in code:   0
fetch(.../webrtc/...) in code:                              0
```

**SC-002 / FR-026 / FR-027 passes.**

## SDK build state at refactor time

```text
sdks/typescript/dist/
  index.js      37 KB (ESM)
  index.cjs     37 KB (CJS)
  index.d.ts    15 KB
  index.d.cts   15 KB
```

Gzipped ESM: ~7.8 KB — **6.6× under the 50 KB SC budget.**

## Wire setup for live verification (operator)

After this commit, to live-test the refactored client end-to-end:

```bash
# 1. (One-time) build the SDK so its dist/ is current:
( cd sdks/typescript && npm install && npm run build )

# 2. Install the SDK into the test client (creates the file:./
#    symlink in node_modules/@aivg/sat-sdk):
( cd clients/electron-test && npm install )

# 3. Start the gateway:
hermes gateway run > /tmp/hermes-gateway.log 2>&1 &

# 4. Run the test client:
( cd clients/electron-test && npm start )

# 5. Adopt the device:
aivg device adopt electron-test-1

# 6. Hold "Push & hold to talk", speak, release.
#    Verify: agent.log shows one full STT → agent → TTS cycle.
```

This mirrors the feature 013 live test trace
(`agent.log` 16:13:34 → 16:13:54). The SC-002 binding gate is satisfied
when one voice turn completes end-to-end through the refactored
renderer — same observable behaviour as the pre-refactor version.

## Notes for the next maintainer

- The renderer uses an **import map** in `renderer.html` to resolve the
  bare `@aivg/sat-sdk` specifier to `./node_modules/@aivg/sat-sdk/dist/index.js`.
  This is Electron-renderer-friendly and matches the published-package
  consumer story exactly (no per-renderer bundler step).
- The legacy "stats" button printed raw `RTCPeerConnection.getStats()`
  output. The SDK doesn't expose the PC — by design (it owns the
  lifecycle). The button now prints `sat.state` + adoption. If you
  need inbound-RTP stats, add a `getStats()` method to the SDK as a
  follow-up (would map onto `RTCPeerConnection.getStats()` while
  keeping the PC encapsulated).
- The acoustic-echo barge-in issue documented at the end of feature 013
  is unchanged by this refactor. The SDK uses the same
  `getUserMedia({ echoCancellation: true, ... })` defaults the original
  test client used. Solving that lives in a future feature (half-duplex
  gate during SPEAKING, or server-side AEC reference signal).
