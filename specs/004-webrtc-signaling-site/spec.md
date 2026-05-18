# Feature Specification: Serve the WebRTC Signaling Site & Redeploy

**Feature Branch**: `004-webrtc-signaling-site`
**Created**: 2026-05-18
**Status**: Draft
**Input**: User description: "implement the signaling aiohttp site in feature 001's adapter.start(), then gated-redeploy (T027)"

## Overview

Feature 003's live deployment surfaced a real defect: the deployed adapter
starts only its **control-plane** site — the **WebRTC signaling** site is never
served, so no voice session can be negotiated and the live spoken test
(feature 003 US2) is blocked. This feature closes that gap: make the adapter
serve its WebRTC signaling endpoints alongside the control plane when it
starts, then **redeploy reversibly** to the production gateway using feature
003's existing gated deploy/rollback machinery, so the previously-blocked live
conversation test can proceed.

Narrow fix-forward. It changes only how the adapter brings up its two planes
and reuses the established deploy path; it does not alter the conversation
logic, the constitution's runtime guarantees, or the satellite contract.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The deployed adapter serves WebRTC signaling (Priority: P1)

When the adapter is running, both of its network planes are available: the
always-on control plane **and** the per-call WebRTC signaling endpoints. A
voice client can submit an offer and receive an answer, creating a session.

**Why this priority**: This is the actual fix. Without the signaling endpoints
the voice path is impossible and feature 003's core test cannot run.

**Independent Test**: With the adapter running, the WebRTC signaling endpoints
respond and an offer yields an answer that establishes a session — while the
control-plane endpoints continue to work.

**Acceptance Scenarios**:

1. **Given** the adapter is started, **When** its network planes come up,
   **Then** both the control-plane and the WebRTC-signaling endpoints are
   reachable on their configured ports.
2. **Given** the signaling endpoint is reachable, **When** a client submits a
   voice offer, **Then** it receives an answer and a session is created and
   visible via the control/management surface.
3. **Given** the adapter is stopped, **When** shutdown occurs, **Then** both
   planes are torn down cleanly with no orphaned listeners.
4. **Given** signaling startup fails (e.g. port unavailable), **When** the
   adapter starts, **Then** the failure is reported clearly and the adapter
   does not present itself as fully ready.

---

### User Story 2 - Reversibly redeploy the fixed adapter (Priority: P1)

The operator redeploys the corrected adapter to the production Hermes gateway
using the existing gated, backed-up, one-step-reversible deploy path; existing
gateway platforms remain unaffected.

**Why this priority**: The fix has no value until it is the version running on
the gateway, and production changes must stay safe/reversible (established
posture).

**Independent Test**: Run the gated redeploy; the running adapter is the fixed
version (signaling reachable), pre-existing platforms unchanged, and rollback
still restores the prior state exactly.

**Acceptance Scenarios**:

1. **Given** the fixed adapter, **When** the gated redeploy runs, **Then**
   each host-mutating step is confirmed and a backup is taken first.
2. **Given** the redeploy completes, **When** the gateway is inspected, **Then**
   the running adapter serves signaling AND all pre-existing platforms still
   work.
3. **Given** the redeploy is undone, **When** rollback runs, **Then** the
   gateway returns exactly to its pre-redeploy state.

---

### User Story 3 - The blocked live conversation test can now run (Priority: P2)

With signaling served and the fix deployed, the previously-blocked live test
(feature 003 US2: speak from the Electron client → hear the agent) can be
attempted end-to-end.

**Why this priority**: This is the payoff, but it depends on US1+US2 and on a
human at a microphone, so it is P2 here (the live exchange itself remains
feature 003's scenario).

**Independent Test**: From the Electron client over the forwarded ports, an
offer connects and a spoken exchange produces an agent reply (no "signaling
unavailable" failure).

**Acceptance Scenarios**:

1. **Given** the fixed adapter is deployed and ports are forwarded, **When**
   the Electron client connects, **Then** the WebRTC offer succeeds (no
   connection-refused on the signaling port) and a session is established.
2. **Given** a session is established, **When** the person speaks, **Then** the
   end-to-end voice loop runs (closing feature 003 T018–T020).

### Edge Cases

- The signaling port is already in use → startup reports the conflict; the
  adapter does not falsely report ready (ties to US1 AS4).
- Control plane up but signaling down (the exact pre-fix state) → the adapter
  MUST be considered not-ready, not "connected", so this regression cannot
  silently recur.
- Redeploy onto an already-deployed adapter → replaces it cleanly with no
  stale listeners or duplicate sessions (reuses feature 003 redeploy behaviour).
- Voice session/ICE drop after the fix → existing teardown behaviour applies;
  a fresh offer works without a gateway restart.
- Rollback after this redeploy → restores the pre-redeploy gateway state
  exactly (reuses feature 003 rollback, which is the tested undo).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: When the adapter starts, it MUST serve its WebRTC signaling
  endpoints (offer/answer, candidate fallback, status) on the configured
  WebRTC port, in addition to the always-on control-plane endpoints.
- **FR-002**: A submitted voice offer MUST produce an answer that establishes a
  session discoverable via the management/control surface.
- **FR-003**: The control plane and WebRTC signaling MUST remain **separate
  endpoints/ports** (no merging of the two planes).
- **FR-004**: Adapter shutdown MUST tear down BOTH planes cleanly (no orphaned
  listeners or sessions).
- **FR-005**: If signaling fails to start, the adapter MUST surface the failure
  and MUST NOT report itself fully ready/connected (prevents silent recurrence
  of the control-up/signaling-down state).
- **FR-006**: Redeployment MUST use the existing gated, backup-first,
  one-step-reversible deploy path; each host-mutating step is explicitly
  confirmed (reuses feature 003 deploy/rollback — not a new mechanism).
- **FR-007**: Redeployment MUST NOT degrade or remove any pre-existing gateway
  platform or capability.
- **FR-008**: Rollback MUST restore the gateway to its exact pre-redeploy state.
- **FR-009**: This change MUST preserve the constitution's runtime guarantees —
  adapter remains thin (signaling is transport only; no embedded
  STT/TTS/agent/endpointing), agent stays gateway-owned, control vs voice
  remain two separate connections.
- **FR-010**: The conversation/turn logic and the satellite contract MUST be
  unchanged by this feature (scope limited to plane bring-up + redeploy).

### Key Entities *(include if feature involves data)*

- **Adapter Lifecycle**: The start/stop behaviour that now brings up and tears
  down two network planes (control + WebRTC signaling) together.
- **WebRTC Signaling Endpoint Set**: The offer/answer/candidate/status surface
  that must be reachable for any voice session.
- **Redeployment**: A gated, backed-up application of the fixed adapter to the
  production gateway (reuses feature 003's Deployment/Backup entities).
- **Hermes Gateway / existing platforms**: Reused; must remain unaffected.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After the adapter starts, both the control-plane port and the
  WebRTC signaling port are accepting connections (0 connection-refused on
  either) in 100% of starts.
- **SC-002**: A voice offer to the deployed adapter yields an answer and a
  visible session in 100% of attempts under nominal conditions.
- **SC-003**: 0 regressions to pre-existing gateway platforms after redeploy
  (verified before and after).
- **SC-004**: 100% of host-mutating redeploy steps are explicitly confirmed
  with a prior backup; rollback restores the exact pre-redeploy state in under
  5 minutes.
- **SC-005**: The control-up/signaling-down state is detectable as
  not-ready in 100% of induced cases (the pre-fix defect cannot silently
  recur).
- **SC-006**: After the fix is deployed, the Electron client's WebRTC offer
  connects (no signaling-port failure), unblocking the feature 003 live test.

## Assumptions

- Scope is limited to (a) serving the WebRTC signaling site from the adapter's
  start lifecycle and (b) a gated redeploy via feature 003's existing
  `deploy/deploy-to-hermes.sh` / `rollback.sh` (the T027 redeploy path) — no
  new deploy mechanism, no conversation-logic changes.
- The host already has the required runtime dependencies (verified in feature
  003 Phase 0); no host dependency installation is needed.
- The adapter is currently deployed on the production gateway (feature 003)
  with the signaling gap; redeploy replaces it in place and rollback remains
  the tested undo.
- The signaling endpoint behaviour itself (offer→answer, full-gather, Opus)
  is already specified by feature 001's WebRTC signaling contract and is
  reused unchanged; this feature only ensures that endpoint set is actually
  served and lifecycle-managed.
- The live spoken exchange (feature 003 T019/T020) still requires a human at a
  microphone and remains feature 003's scenario; this feature only removes the
  signaling blocker.
- Security/auth for the forwarded ports remains deferred (LAN/SSH-forward
  posture from features 001/003); out of scope here.
- Host-mutating steps require explicit confirmation and a prior backup,
  consistent with the project's outward-action posture and constitution
  Principle V.
