# Contract: Wire-Protocol Parity (consumed, not defined)

**Feature**: 020-cpp-webrtc-sdk | **Date**: 2026-05-22

This SDK **consumes** the existing satellite ↔ gateway contract verbatim.
It defines **no new** wire surface. Contract version: **`0.2.0`**
(`aivg --contract-version`). Authoritative byte-shape reference:
`sdks/typescript/src/proto/{rest-shapes,ws-messages,version}.ts`.

## Control plane (always-on WebSocket)

- `WS /satellite/ws?device_id=<id>` — register, heartbeat, config push, commands, logs, OTA notifications, online/offline.
- REST: `POST /devices/register` (and the management endpoints the TS SDK already uses) on the management port.
- The SDK MUST NOT move durable control traffic onto a WebRTC datachannel (Constitution Principle III).

## Voice plane (per-session WebRTC)

- The SDK is the **offerer**; ICE uses full gather-then-offer.
- `POST /webrtc/offer` on the voice-plane signaling port (separate from the management port; `signaling_url` configurable).
- Media: Opus, PCM16-mono at the callback boundary; DTLS-SRTP encrypted (FR-012).
- Answer-shape tolerance: when the gateway returns only `{ sdp, type:"answer" }`, the SDK fabricates a local session id (matches TS SDK behavior, FR-011).
- A single SCTP datachannel carries call-scoped UI events (partial transcript / state / barge-in) only.

## Versioning

- On connect, read the gateway's contract-version envelope; accept when **major** matches `0.2.0`; warn (do not abort) on mismatch (FR-014).
- This feature MUST NOT bump the contract (SC-006). No gateway, REST, WS, or SDP changes are in scope (OOS-002).

## Parity verification (binding gate)

- Run a libaivg-sat turn and an `@aivg/sat-sdk` turn against the **same** gateway.
- Diff the gateway logs at the **message-type + field-name** level → MUST be zero (SC-005); only payload values (timestamps, session ids) may differ.
- The desktop smoke binary's exit code is the pass/fail signal for this gate (FR-021).
