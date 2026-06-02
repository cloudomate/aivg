# Follow-up: generalize Constitution Principle III to be transport-neutral

**Status**: ✅ **RATIFIED in constitution v2.1.0** (2026-06-02). This document
is the governance follow-up for feature 021's recorded Principle III deviation
(plan.md Complexity Tracking, research R-7). Adopted as a **MINOR** bump (the
draft below proposed PATCH; on review MINOR was adopted because the change
materially expands Principle III's normative scope to a new transport class —
see the constitution's Sync Impact Report for the rationale).

## Why

Principle III ("Separate Control and Voice Connections") currently names the
technologies by which the two planes are realized:

> Each satellite maintains exactly two connections: an always-on control-plane
> WebSocket (`WS /satellite/ws`) and a per-session **WebRTC** voice connection.

Feature 021 introduces a gRPC transport that, for **native** satellites,
replaces the voice plane (Phase 1) and optionally the control plane (Phase 2).
This is a recorded deviation: III's binding **intent** is preserved, but its
**named technologies** no longer cover every supported satellite.

III's intent — and what every transport still honors:

- exactly **two** connections per satellite: one always-on control connection
  and one per-session voice connection;
- control availability is **decoupled from call state** (the control connection
  survives with no active call);
- durable control traffic is **never multiplexed** into the per-session voice
  channel.

Under gRPC: the `Management` service is the long-lived control connection and
`Audio.Stream` is the per-session voice connection — kept separate. Intent met;
only the words "WebSocket" and "WebRTC" are too narrow.

## Proposed change (PATCH)

Reword III to be transport-neutral, mirroring how v2.0.0 generalized Principle
IV from "Reuse Hermes" to "Reuse the Upstream Agent Platform":

- "an always-on control-plane **WebSocket** (`WS /satellite/ws`)"
  → "an always-on **control-plane connection** (WebSocket today; gRPC
  `Management` for native satellites)"
- "a per-session **WebRTC** voice connection"
  → "a per-session **voice connection** (WebRTC for browsers; gRPC `Audio.Stream`
  for native satellites)"
- Keep every rule about the *separation* unchanged: two connections, control
  decoupled from call state, no durable control on the per-session channel.

This is a **PATCH** (clarification/broadening of binding text without changing
intent), per the constitution's own versioning policy — the same class as the
v2.0.1 rebrand patch. Bump **2.0.1 → 2.0.2**, document in the Sync Impact
Report, and re-check the Spec Kit templates (generic Constitution-Check text →
no change expected).

## Until ratified

Feature 021 ships under the **recorded deviation** in plan.md (the established
precedent — feature 020's Principle V `libpeer`/`esp_peer` deviation). The
amendment is a separate governance action via `/speckit-constitution`; it does
not block 021's code.
