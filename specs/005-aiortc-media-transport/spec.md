# Feature Specification: Real WebRTC Media Transport (audio actually flows)

**Feature Branch**: `005-aiortc-media-transport`
**Created**: 2026-05-18
**Status**: Draft
**Input**: User description: "implement the real aiortc media transport (aiortc_transport_factory → an AiortcTransport adapting RTCPeerConnection audio tracks to MediaTransport, Opus↔PCM via av)"

## Overview

Feature 004 made the gateway *serve* the WebRTC signaling endpoint, but feature
003/004 testing surfaced the next-layer blocker: the media transport is a
stub — a real voice offer fails because no component actually carries audio
between the WebRTC peer and the conversation engine. Feature 001 built and
tested the whole conversation loop against a **fake** transport; the **real**
audio path (decode the caller's speech, play back the agent's speech) was never
implemented. This feature implements that real media transport so audio
genuinely flows, then redeploys reversibly so the end-to-end spoken
conversation (blocked since feature 003) can finally complete.

It is the last missing piece of the voice path. It changes only the
transport realisation behind the existing internal media interface; the
conversation logic, signaling, control plane, and Hermes integration are
unchanged.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The caller's speech reaches the agent and the reply is heard (Priority: P1)

A person connected via the voice client speaks; their audio actually arrives at
the gateway and is transcribed; the agent's spoken reply is actually delivered
back and plays in the client. Real audio in, real audio out — not a stub.

**Why this priority**: This is the entire point. Without real media flow there
is no voice product; every prior feature is inert until this works.

**Independent Test**: From the voice client, a spoken phrase produces a
transcription on the gateway and an audible agent reply in the client.

**Acceptance Scenarios**:

1. **Given** a voice session is negotiated, **When** the person speaks, **Then**
   their audio is delivered to the gateway's transcription with intelligible
   quality (words recognised as spoken).
2. **Given** the agent produces a spoken reply, **When** it is sent back,
   **Then** the client plays clear, intelligible audio of that reply.
3. **Given** a multi-turn exchange, **When** turns alternate, **Then** audio
   continues to flow correctly in both directions without degradation.
4. **Given** the caller stops speaking, **When** the turn ends, **Then** the
   gateway's existing end-of-utterance handling fires on the real audio (not a
   synthetic signal).

---

### User Story 2 - Barge-in works over real audio (Priority: P1)

While the agent's reply is playing, the person talks over it; playback stops
promptly and their new speech is captured as the next turn — on the real media
path, not the fake.

**Why this priority**: Barge-in is a defining behaviour of natural
conversation and was only ever proven against the fake transport; it must hold
with real audio.

**Independent Test**: During real playback, speak; confirm playback stops
quickly and the interrupting speech is transcribed as the next turn.

**Acceptance Scenarios**:

1. **Given** the agent reply is playing, **When** the person speaks, **Then**
   outbound audio stops promptly and the new utterance becomes the next turn.
2. **Given** an interruption, **When** the agent responds again, **Then** the
   response addresses the interrupting utterance.

---

### User Story 3 - Reversibly redeploy the media-complete adapter (Priority: P2)

The operator redeploys the now media-complete adapter to the production
gateway using the existing gated, backed-up, one-step-reversible path; existing
gateway platforms remain unaffected.

**Why this priority**: The fix has no value until it is the running version;
production changes stay safe/reversible (established posture).

**Independent Test**: Gated redeploy → media-complete adapter live, both planes
listening, pre-existing platforms intact; rollback restores prior state.

**Acceptance Scenarios**:

1. **Given** the media-complete adapter, **When** the gated redeploy runs,
   **Then** each host-mutating step is confirmed and backed up first.
2. **Given** the redeploy completes, **When** the gateway is inspected, **Then**
   the adapter serves both planes AND all pre-existing platforms still work.
3. **Given** rollback is invoked, **Then** the gateway returns exactly to its
   pre-redeploy state.

---

### User Story 4 - The end-to-end live spoken test finally completes (Priority: P2)

With real media flowing and the fix deployed, the human-driven spoken
conversation blocked since feature 003 (T019/T020) and feature 004 (T014/T015)
can be performed and pass.

**Why this priority**: It is the long-blocked payoff and the definitive proof,
but depends on US1–US3 and a human at a microphone.

**Independent Test**: From the desktop client over the forwarded ports, a real
spoken exchange yields an agent reply within a conversational delay, with
parity to the gateway's configured speech providers.

**Acceptance Scenarios**:

1. **Given** the media-complete adapter is deployed, **When** the person holds
   a short spoken conversation, **Then** they hear a correct agent reply within
   a conversational delay.
2. **Given** the same phrase is processed directly by the gateway's speech
   providers, **When** compared, **Then** quality through the adapter shows no
   meaningful regression.

### Edge Cases

- No inbound audio track in the offer → the session fails clearly, not a hang.
- The inbound track ends mid-call (client mutes/drops) → the session ends or
  returns to idle cleanly; no crash.
- Outbound send attempted before the media path is ready → buffered or safely
  dropped, never an error that kills the session.
- Audio sample-rate/format mismatch between the peer and the speech engine →
  reconciled so transcription/playback remain intelligible (no chipmunk/
  slow-motion audio).
- Packet loss / jitter on the network → audio remains usable (existing jitter
  handling applies); no permanent desync.
- ICE/connection drop → media path torn down cleanly; a fresh offer
  re-establishes audio without a gateway restart.
- Agent reply is empty/tool-only → no broken or zero-length audio is emitted;
  session returns to listening.
- Barge-in cancels an in-flight reply → outbound audio stops without leaving
  the transport in a wedged state for the next turn.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST carry the caller's inbound speech from the WebRTC
  peer to the gateway's existing transcription path as intelligible audio.
- **FR-002**: The system MUST carry the agent's synthesized reply from the
  gateway back to the WebRTC peer as intelligible audio that plays in the
  client.
- **FR-003**: The real media transport MUST satisfy the same internal media
  interface the conversation logic already uses (the fake test transport's
  contract) so no conversation-logic change is required.
- **FR-004**: The system MUST reconcile any audio sample-rate/format difference
  between the WebRTC peer and the speech engine so transcription and playback
  remain intelligible.
- **FR-005**: The system MUST support barge-in on the real path: in-flight
  outbound audio stops promptly when the caller speaks, and the transport is
  left usable for the next turn.
- **FR-006**: The system MUST tear the media path down cleanly on
  ICE/connection drop or session end (no orphaned media tasks), and a fresh
  offer MUST re-establish audio without a gateway restart.
- **FR-007**: A voice offer MUST now succeed end-to-end (no
  "not implemented"/stub failure); the negotiated answer establishes a working
  bidirectional audio session.
- **FR-008**: The change MUST be limited to the media-transport realisation;
  signaling, the control plane, the conversation/turn logic, and the Hermes
  STT/agent/TTS integration MUST be unchanged.
- **FR-009**: Redeployment MUST use the existing gated, backup-first,
  one-step-reversible deploy path; each host-mutating step explicitly
  confirmed (reuse features 003/004 deploy/rollback — no new mechanism).
- **FR-010**: Redeployment MUST NOT degrade or remove any pre-existing gateway
  platform or capability.
- **FR-011**: The change MUST preserve the constitution's runtime guarantees —
  the adapter stays a thin transport (no embedded STT/TTS/agent/endpointing),
  the agent stays gateway-owned, and control vs voice remain separate
  connections.
- **FR-012**: Feature 001's existing fake-transport test suite MUST remain
  green (the real transport is added alongside the fake, not by changing the
  interface or the conversation logic).

### Key Entities *(include if feature involves data)*

- **Media Transport (real)**: The component that adapts the live WebRTC peer's
  audio tracks to the conversation engine's media interface — inbound decode,
  outbound encode, playback-stop, teardown, connection state.
- **Audio Stream (inbound / outbound)**: The caller's speech and the agent's
  reply as they cross the transport, including any format reconciliation.
- **Voice Session**: Reused unchanged from feature 001 — now backed by the real
  transport instead of the fake one.
- **WebRTC Peer**: The negotiated connection to the client (reused; this
  feature gives it a working media adapter).
- **Hermes STT / Agent / TTS**: Reused unchanged; consume/produce the audio
  the transport now really moves.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A real spoken phrase from the client is transcribed by the
  gateway with accuracy equivalent to feeding that audio to the gateway's
  speech provider directly (no transport-induced degradation).
- **SC-002**: The agent's spoken reply is heard in the client and is
  intelligible (a listener can understand it without replays).
- **SC-003**: A spoken reply begins playing within 1.5 seconds of the caller
  finishing speaking, under nominal network/provider conditions.
- **SC-004**: Barge-in stops outbound audio within 300 milliseconds of detected
  caller speech on the real path.
- **SC-005**: A voice offer succeeds end-to-end in 100% of attempts under
  nominal conditions (0 stub/not-implemented failures).
- **SC-006**: At least 3 consecutive conversational turns complete with audio
  intact in both directions (no progressive desync or dropout).
- **SC-007**: 0 regressions to pre-existing gateway platforms after redeploy;
  rollback restores the exact pre-redeploy state in under 5 minutes.
- **SC-008**: Feature 001's fake-transport test suite remains 100% green after
  this change.

## Assumptions

- The required media libraries are already present on the gateway host
  (verified in feature 003: aiortc/aiohttp/av) — no host dependency install.
- The internal media interface is feature 001's existing `MediaTransport`
  contract (receive inbound / send outbound / stop playback / close /
  connection-state); this feature implements a real backer for it and does not
  change the interface or `session.py`.
- Audio is Opus at 48 kHz mono on the wire (feature 001 / design contract);
  internal PCM is 16-bit mono at the rate the speech path already expects;
  format reconciliation uses the media library already on the host.
- Redeploy reuses features 003/004's `deploy/deploy-to-hermes.sh` /
  `rollback.sh` (the gated, reversible path) — no new deploy mechanism; the
  both-planes post-verify from feature 004 still applies.
- Local automated tests cannot exercise real WebRTC media (the media stack is
  not a local test dependency); correctness of the real path is proven by the
  host-side live spoken test (constitution V — verify before relying), with the
  fake-transport suite guarding the unchanged conversation logic.
- The human-driven spoken exchange (feature 003 T019/T020) still requires a
  person at a microphone and remains that scenario; this feature removes the
  final technical blocker.
- Security/auth for the forwarded ports remains deferred (LAN/SSH-forward
  posture from prior features); out of scope here.
- Host-mutating steps require explicit confirmation and a prior backup,
  consistent with the project's outward-action posture and constitution
  Principle V.
