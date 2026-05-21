# Changelog

All notable changes to `@aivg/sat-sdk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.3] — 2026-05-20

### Added

- `Satellite.mute()` / `Satellite.unmute()` — toggle the outbound mic
  track without tearing down the voice session. Use for push-to-talk
  UX: build the session once on connect/adopt and toggle the mic
  per utterance, instead of building a fresh PeerConnection on every
  PTT mousedown.
- `Satellite.isMicLive` — read-only flag; `true` when there's an
  active session and the mic track is enabled.
- `VoiceSession.setMicEnabled(boolean)` — underlying primitive that
  `mute()`/`unmute()` delegate to.

### Fixed

- **PTT race against the gateway silence detector.** 0.1.0–0.1.2's
  recommended PTT pattern called `beginSession()` on mousedown and
  `endSession()` on mouseup. The gateway's endpoint detector waits
  ~3 s of silence after speech before triggering STT, so a mouseup
  that tore down the PC inside that window meant STT never ran for
  the utterance. Result on live electron-test: many sessions created,
  zero transcripts produced. The new mute/unmute model keeps the PC
  alive across utterances and lets the silence detector trigger
  normally.

### Changed

- `clients/electron-test/renderer.js` refactored to the new PTT model:
  opens the voice session ONCE on first `adoption: adopted` event
  (muted), then PTT mousedown/mouseup just toggle the mic.

## [0.1.2] — 2026-05-20

### Fixed

- **Signaling URL was using the wrong port** — POST `/webrtc/offer`
  went to the management plane (8643) instead of the WebRTC signaling
  plane (8644), 404ing every voice session. Added a separate
  `signalingUrl` field to `SatelliteOptions`; defaults to `gatewayUrl`
  with the port bumped by +1 (matches the gateway's `management_port` /
  `webrtc_port` default convention from `aivg_core/config.py`).
- **`/webrtc/offer` response shape** — the gateway returns
  `{sdp, type: "answer"}` only; the SDK was demanding `session_id`
  too and rejecting the response with `signaling_failed`. SDK now
  fabricates a local session_id when the gateway doesn't supply one.
- **Three more unknown WS message types** the gateway emits over
  the control-plane:
    * `state` — per-session FSM transition (`idle | listening |
      thinking | speaking | …`). Surfaced as a new `gateway_state`
      bus event (distinct from the SDK's own local FSM `state`).
    * `partial_transcript` — live ASR text. Routed to the existing
      `transcript` event as a non-final `speaker: "user"` delta.
    * `barge_in` — gateway-detected barge-in. New `barge_in` event.
  None of these trigger `transient_error` warnings anymore.

### Internal

- Tests: 148 passing (added one for the new offer-shape forgiveness;
  retired one that asserted the old over-strict response validation).

## [0.1.1] — 2026-05-20

### Fixed

- **Protocol drift caught in live electron-test:** the gateway sends
  WS messages of types `registered` (reply to outbound register) and
  `state_update` (adoption-state broadcast to every connected client),
  not the `adoption` shape the SDK 0.1.0 expected. 0.1.0 surfaced both
  as `transient_error(signaling_retry: unknown WS message type)`
  warnings in the console.
- `parseWsInbound()` now treats both `registered` and `state_update`
  as known top-level types and routes them to the existing `adoption`
  event with the gateway's `adoption_state` field.
- `state_update` is broadcast to ALL connected WS clients; the SDK
  now filters by `device_id` and only acts on messages addressed to
  its own device. Avoids spurious `adoption` events when other devices
  in the fleet change state.
- `config_changed` was also broadcast-to-all on the gateway side and
  carried `config_version` as a sibling field (not inside `config`).
  The SDK now filters by `device_id` AND flattens the version field
  into the public `SatelliteConfig.version` shape.

### Internal

- Wire fixtures + contract tests updated to match the real gateway shapes.
- Test totals: 147 passing (up from 146).

## [0.1.0] — 2026-05-20

Initial release. Feature 014 of the AIVG monorepo.

### Added

- `Satellite` class — top-level handle owning the control-plane WS,
  the per-session WebRTC PC, and the typed event surface.
  - `connect()` / `disconnect()` — control-plane lifecycle, idempotent.
  - `beginSession()` / `endSession()` — voice-plane lifecycle,
    idempotent.
  - `getConfig()` / `setConfig()` — management-plane config push/pull
    with optimistic-concurrency conflict detection (throws
    `ConfigVersionConflict` on 409).
- **Control plane**: long-lived WebSocket against `/satellite/ws`,
  exponential-back-off reconnect (500 ms → ×1.5 → 30 s ceiling,
  ±20 % jitter, 60 s success-reset).
- **Voice plane**: WebRTC offerer flow with full-gather ICE then
  `POST /webrtc/offer`. Mic constraints default to
  `{ echoCancellation: true, noiseSuppression: true, autoGainControl: true }`.
- **State machine**: `idle | listening | speaking | error`. Pure
  function reducer; exhaustive-switch typing.
- **Adoption flow**: tracks `pending → adopted` with one-shot
  `firstApproval: true` semantics.
- **Typed event surface** (`on(event, handler)` returns unsubscribe;
  `off(event, handler)` mirrors): `adoption`, `state`, `config_changed`,
  `command`, `log`, `ota_manifest`, `ota_progress`, `transcript`,
  `tool_call`, `skill`, `remote_stream`, `session_started`,
  `session_ended`, `error`, `transient_error`.
- **Async-iterator sugar**: `transcripts()`, `logs()`, `states()` —
  bounded-queue (1024) iterators that emit `transient_error(buffer_overflow)`
  on drop.
- **OTA forwarding**: receives `ota_manifest` / `ota_progress` events
  from the gateway and forwards them to consumer handlers. NEVER
  auto-applies (browser/Electron OTA is application-side).
- **Closed error-code set** (12 codes): `no_webrtc_impl`,
  `no_microphone_api`, `permission_denied`, `ice_failed`,
  `ice_gathering_timeout`, `ws_disconnected`, `ws_max_retries_exceeded`,
  `signaling_failed`, `mixed_content`, `not_adopted`,
  `protocol_mismatch`, `duplicate_device`.
- **Dependency injection**: `webrtcFactory` (use `@roamhq/wrtc` for Node),
  `audioSinkFactory` (consumer-provided in Node; managed `<audio>` in
  browser/Electron).
- **Forward-compat parsing**: unknown WS message `type` values + unknown
  `agent_event` kinds emit ONE `transient_error(protocol_mismatch)`
  per session and are otherwise silent.

### Targets

- Modern browsers (Chrome/Firefox/Safari).
- Electron 28+ (renderer + main, both fine).
- Node.js 20+ (consumer must pass `webrtcFactory: () => new wrtc.RTCPeerConnection(...)`).

### Contract

- Wire-protocol contract version: `1.0.0` (matches `aivg --contract-version`).
- Single artefact pair: `dist/index.js` (ESM) + `dist/index.cjs` (CJS) +
  `dist/index.d.ts` (TypeScript declarations).
- Bundle size: ~10 KB gzipped (5× under the 50 KB internal budget).
- Zero native dependencies.

[0.1.0]: https://github.com/cloudomate/aivg/releases/tag/sdk-ts-v0.1.0
