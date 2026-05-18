# Phase 0 Research: Deploy & Live-Test on the Hermes Gateway

Resolved by **read-only** inspection of the live host (`ssh hermes`,
hermes-agent v0.13.0, `/home/ubuntu/.hermes/hermes-agent/`). No host state was
modified. Spec Assumptions resolved the client/networking choices.

## D1 — Runtime dependencies are already present (constraint lifted)

- **Decision**: Run feature 001's production aiortc transport directly on the
  host venv.
- **Finding/Rationale**: `aiortc`, `aiohttp`, and `av` all import in
  `/home/ubuntu/.hermes/hermes-agent/venv`. Feature 001 assumed these might be
  absent and isolated them behind lazy imports; on this host they exist, so the
  real transport runs with no extra install.
- **Alternatives considered**: `pip install` into the venv (rejected —
  unnecessary, and a mutation we'd have to back out); GStreamer `webrtcbin`
  (rejected — device-side RPi path, irrelevant to the gateway host).

## D2 — Deploy as a platform plugin (verified mechanism)

- **Decision**: Deploy as `plugins/platforms/satellite_webrtc/` mirroring
  `plugins/platforms/irc/`: `plugin.yaml` (`kind: platform`, `name`, `label`,
  `version`, `description`, `author`, optional `requires_env`/`optional_env`)
  + `__init__.py` that imports the adapter and calls
  `platform_registry.register(PlatformEntry(...))`; `adapter.py` is the
  vendored 001 package (or imports it).
- **Rationale**: `platform_registry` self-registration + sequential startup
  discovery is the documented plugin path; `irc` is a working reference
  (same shape). Uses 001 T044's verified `PlatformEntry` exactly.
- **Alternatives considered**: built-in under `gateway/platforms/` (rejected —
  edits core tree, harder to roll back, not plugin-isolated); ad-hoc
  PYTHONPATH injection (rejected — not discovered by the gateway, fragile).

## D3 — Config: `satellite:` block in existing config.yaml, backed up first

- **Decision**: Add a `satellite:` block to `~/.hermes/config.yaml` read by the
  existing `gateway.config.load_gateway_config()` (PlatformEntry
  `apply_yaml_config_fn` maps it); take an explicit timestamped backup
  `config.yaml.bak.<ISO>` before writing.
- **Rationale**: Constitution IV (reuse the existing loader/file). Hermes
  already keeps `config.yaml.bak.*`; an additional explicit, feature-owned
  backup makes rollback deterministic and attributable (FR-003/SC-006).
- **Alternatives considered**: separate config file (rejected — constitution
  IV); rely only on Hermes's auto-backups (rejected — not feature-owned/
  deterministic for SC-006).

## D4 — Electron client = design satellite #3, minimal, PTT v1

- **Decision**: Minimal Electron app: `getUserMedia({echoCancellation:true,…})`,
  one `RTCPeerConnection` (offerer; **full ICE gather then POST
  /webrtc/offer**), always-on control WebSocket, hidden `<audio>` playback,
  **push-to-talk button** for v1 (no wake word). Echo handled by Chromium AEC
  (`browser_aec3`).
- **Rationale**: Exactly the design's §5 satellite #3 and the lowest-risk
  end-to-end client (matches feature 001's build-order #1). PTT removes
  wake-word complexity for the first live proof.
- **Alternatives considered**: browser tab (rejected — packaging/perms less
  controllable than Electron, and the user explicitly chose Electron); wake
  word v1 (rejected — design defers it to v2; adds risk to first live test).

## D5 — Networking: SSH port-forward the adapter ports

- **Decision**: Electron client on the developer machine reaches the deployed
  adapter via `ssh -L` forwarding the management (8643) and WebRTC-signaling
  (8644) ports from the host; media flows over the negotiated WebRTC path on
  those forwarded ports (LAN-style, loopback to the client).
- **Rationale**: Reuses the already-trusted `ssh hermes` access; no inbound
  ports opened on the host; consistent with the LAN-scoped, security-deferred
  posture of feature 001.
- **Alternatives considered**: expose host ports publicly (rejected — security,
  the project explicitly defers transport auth); run Electron on the host
  (rejected — no audio devices there).

## D6 — Safety: backup → confirm → deploy → verify → rollback

- **Decision**: `deploy-to-hermes.sh` performs, in order: read-only
  preflight (gateway reachable, deps present, capture pre-state) → **explicit
  confirmation** → backup `config.yaml` → vendor plugin tree → add `satellite:`
  block → restart gateway → post-verify (adapter registered + a pre-existing
  platform still works). `rollback.sh` restores the backup, removes the plugin
  dir, restarts, and re-verifies. Any mid-failure leaves prior state or flags
  "rollback required" (FR-006).
- **Rationale**: Production gateway; matches the project's outward-action
  posture and constitution V. Each mutation is individually confirmed (FR-004).
- **Alternatives considered**: one-shot unattended deploy (rejected — violates
  FR-004/006 and the session's safety posture).

## D7 — "Test actual implementation" = human-driven, real providers

- **Decision**: The pass criterion is a real person speaking into the Electron
  app and hearing the real Hermes agent reply via the gateway's configured
  STT/TTS — no synthetic audio, no test doubles in the deployed path (FR-009).
  Record pass/fail + measured end-of-speech→reply latency (FR-012).
- **Rationale**: The user asked to "test actual implementation"; only a real
  exchange validates STT/agent/TTS/transport together against the live build.
- **Alternatives considered**: scripted WAV injection (rejected — not the
  actual implementation; misses mic/AEC/playback realities).

## Remaining deploy-time confirmations (small, not blocking)

- Exact `plugin.yaml` `kind`/field names for a platform plugin → copy
  `plugins/platforms/irc/plugin.yaml` shape verbatim (verified present).
- Gateway restart command surface (`hermes gateway` vs a service restart) →
  confirm against the host at deploy time (read-only first); feature 002's
  vendored `hermes-agent` skill documents `hermes gateway restart`.

**No NEEDS CLARIFICATION remain.**
