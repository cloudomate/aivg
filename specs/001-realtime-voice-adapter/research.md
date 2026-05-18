# Phase 0 Research: Realtime Voice Platform Adapter

All Technical Context unknowns resolved below. Items that depend on the
**running Hermes build** cannot be confirmed from this repo (it contains no
Hermes source — only the design doc and Spec Kit scaffolding); each such item
carries a **Verification gate** that MUST pass during implementation before the
decision is relied upon (constitution Principle V).

---

## D1 — WebRTC stack for the gateway adapter

- **Decision**: `aiortc` (audio-only, one `RTCPeerConnection` per session, no
  video). Adapter is the **answerer**; the client/satellite is the **offerer**
  for all device types.
- **Rationale**: Design Appendix E mandates one aiortc-based adapter for all
  three satellite types; §2.2 fixes the satellite as offerer (consistent with
  `esp_peer` and browser norms). aiortc is pure-Python, integrates with the
  asyncio Hermes gateway, and is the fastest path to the build-order #1
  browser loop.
- **Alternatives considered**: GStreamer `webrtcbin` (C-level, lower CPU) —
  rejected for the gateway side; it is the *device-side* RPi migration path,
  not relevant to the server adapter. Raw SDP/ICE implementation — rejected
  (needless re-implementation, violates "don't rebuild").

## D2 — Signaling and ICE strategy

- **Decision**: HTTP signaling — `POST /webrtc/offer` returns the answer,
  `POST /webrtc/candidate` kept only as fallback, `GET /webrtc/status/{id}`.
  Client does **full ICE gather then offer**; adapter sets remote description
  from the complete SDP.
- **Rationale**: §2.2 — full-gather-then-offer lets LAN clients skip trickle
  entirely and sidesteps the known aiortc bug where candidates arrive before
  the remote description. Two endpoints + one status read is the minimum
  surface.
- **Alternatives considered**: WebSocket-based trickle signaling — rejected;
  more moving parts and reintroduces the ordering bug on LAN.

## D3 — Two connections, never multiplexed

- **Decision**: Always-on control plane = `WS /satellite/ws` on the management
  site (`:8643`). Per-call voice = WebRTC PC negotiated via `:8644`. A single
  optional SCTP datachannel on the voice PC is permitted **only** for
  call-scoped UI events (partial transcript, listening/speaking, barge-in
  notice); everything durable (register/heartbeat/config/command/log/OTA)
  stays on the WS.
- **Rationale**: Constitution III / design §6 — a data channel exists only
  while a PC is up; multiplexing durable control there couples control
  availability to call state and forces gateway protocol-branching.
- **Alternatives considered**: Single WebRTC datachannel for everything —
  rejected (constitution violation, SC-006 unmet when idle).

## D4 — Audio format & pipeline

- **Decision**: Opus @48 kHz, mono. Inbound: aiortc decodes Opus → PCM frames
  → resample as needed for the Hermes STT provider input. Outbound: Hermes TTS
  provider PCM/Opus → (resample via ffmpeg/`av` if needed) → aiortc Opus
  encode → outbound track. Explicit Opus bitrate ~24–32 kbps.
- **Rationale**: §2.2 / §3.2 — 48 kHz matches Opus and the device codecs;
  mono halves transport; explicit bitrate avoids aiortc's ~96 kbps default and
  stays stable on 2.4 GHz Wi-Fi. ffmpeg is already available in Hermes (§8.1).
- **Alternatives considered**: Stereo / SDP munging — rejected (no benefit,
  added fragility; §5 says no SDP munging).

## D5 — Hermes STT/TTS integration (thin bridge)

- **Decision**: A single module `hermes_bridge.py` exposes
  `stt_transcribe(pcm) -> text`, `tts_synthesize(text) -> audio`,
  `agent_turn(text, session_ctx) -> reply`, `detect_endpoint(pcm_stream)` —
  each a **delegation-only wrapper** over the running Hermes build's provider
  interfaces. No Whisper/Piper/engine objects are ever constructed in this
  codebase.
- **Rationale**: Constitution I & IV; design §8.1 and Appendix E ("call
  hermes.stt.transcribe(...) / hermes.tts.synthesize(...) or the equivalent
  provider interface in the running build"). Centralizing the boundary in one
  module makes the non-negotiable structurally auditable.
- **Verification gate (running build)**: Confirm the exact provider interface
  module/callable names and signatures in the deployed Hermes build before
  wiring. `hermes_bridge` is the only file that changes if names differ; an
  adapter interface (Protocol) decouples the rest of the package from the
  concrete Hermes API.
- **Alternatives considered**: Calling provider HTTP endpoints — rejected if
  in-process interfaces exist (extra hop, latency budget SC-001). Direct
  engine instantiation — prohibited by constitution.

## D6 — Authoritative end-of-utterance

- **Decision**: Reuse Hermes's existing server-side two-stage silence
  algorithm (speech-confirm RMS > `silence_threshold` ~200 for ~0.3 s;
  end-detect after `silence_duration` ~3.0 s) via the bridge. Any client VAD
  signal only gates whether audio is streamed up; it never declares turn end.
- **Rationale**: Constitution I (endpointing is Hermes's) and design §8.1.
- **Verification gate**: Confirm the silence-algo entrypoint and that its
  thresholds remain configuration-driven in the running build.

## D7 — Agent invoked as an entity

- **Decision**: Each completed user turn is handed to the Hermes agent through
  the **same agent invocation path the telegram/discord adapters use**, with a
  per-session conversation context. One agent turn in flight per session.
- **Rationale**: User request ("hermes agent is involved as an entity") +
  design §8.2/Appendix E ("Hermes agent loop, same as telegram/discord
  adapters").
- **Verification gate**: Confirm the shared adapter→agent entrypoint and the
  session/conversation-context object the existing adapters pass.

## D8 — Adapter registration & configuration surface

- **Decision**: Implement against the existing platform-adapter base
  (`BasePlatformAdapter`-style) and register like telegram/discord under
  `hermes gateway`. Config is a new `satellite:` block in the existing
  `~/.hermes/config.yaml` (ports 8643/8644, heartbeat_interval,
  mdns_advertise, default_config); secrets reuse `~/.hermes/.env`.
- **Rationale**: Constitution IV; design §8.2/§8.3.
- **Verification gate (running build)**: Design §8.3 explicitly flags this —
  confirm the adapter registration hook and the enable/restart CLI surface
  (`hermes gateway` vs `hermes gateway setup`; whether `hermes gateway
  restart` exists). Treat config schema as authoritative regardless of CLI.
- **Alternatives considered**: Separate daemon + own config file — rejected
  (constitution IV violation).

## D9 — Barge-in / one-turn-at-a-time

- **Decision**: Session state machine `idle → listening → thinking → speaking`
  with a single in-flight turn. Inbound speech detected during `speaking`
  cancels the current TTS playback/agent turn promptly and transitions back to
  `listening` with the new utterance. Late second utterances are treated as
  barge-in, never producing overlapping replies.
- **Rationale**: Spec FR-011/FR-012, SC-003 (≤300 ms stop), edge cases.
- **Alternatives considered**: Queueing concurrent turns — rejected (produces
  stale/overlapping replies; conversation feels broken).

## D10 — Resilience & reconnect

- **Decision**: Control WS auto-reconnect with exponential backoff (client
  side per design; adapter side: tolerate WS drop, keep registry entry as
  `offline`, accept re-`register`). On ICE/voice drop, tear down the Session
  and expect a fresh offer; gateway restart ends active calls, clients
  re-register (no manual cleanup).
- **Rationale**: Spec US4 / FR-014 / SC-007; design Appendix E ("tear down +
  expect re-offer on ICE drop").

## D11 — Concurrency target

- **Decision**: Design for ~10–25 concurrent sessions on one gateway host;
  asyncio task-per-session; load test the full path (10× concurrent) before
  declaring SC-005 met.
- **Rationale**: Spec SC-005 + Assumptions (small LAN fleet); constitution V
  (load-test before relying).

## D12 — Testing strategy

- **Decision**: `pytest`+`pytest-asyncio`. Unit: registry, config loader,
  session state machine, models. Contract: management REST + WS message
  schemas, signaling SDP exchange. Integration: aiortc loopback PC ↔ adapter ↔
  **fake Hermes bridge double** (deterministic STT/agent/TTS) covering the P1
  loop, barge-in, reconnect, provider-fallback, and 10× concurrency.
- **Rationale**: Lets the entire feature be validated without a live Hermes
  build or real hardware (build-order #1 is the lowest-risk loop); the bridge
  double also exercises the constitution-I boundary.

---

## Running-build verification gates — RESOLVED (hermes-agent v0.13.0)

Resolved 2026-05-18 by **read-only** inspection of the live Hermes over
`ssh hermes` (editable install at `/home/ubuntu/.hermes/hermes-agent/`, source
root confirmed via the `__editable__` finder; CLI `/home/ubuntu/.local/bin/hermes`
→ venv `/home/ubuntu/.hermes/hermes-agent/venv`). No files on the host were
modified. ⚠️ The host's SSH key changed (`known_hosts:55`,
`SHA256:pvyq5gFR2qA1kfDqsIKj7RDE7BeTD8gfwMIL8g7USkE`) — confirm this is
expected re-provisioning, not a MITM, before fully trusting these findings.

| Gate | Verified entrypoint | Decision |
|------|---------------------|----------|
| **VG-1 STT** ✅ | `tools.transcription_tools.transcribe_audio(file_path: str, model: Optional[str]=None) -> Dict`; provider/fallback from `_load_stt_config()` (local/groq/openai/mistral/xai); `is_stt_enabled()`; `_extract_transcript_text` | Bridge writes accumulated inbound PCM to a temp WAV (ffmpeg/`av`), calls `transcribe_audio()`, returns extracted text. Provider/fallback inherited from config — adapter passes none (FR-006). |
| **VG-1 TTS** ✅ | `tools.tts_tool.text_to_speech_tool(text: str, output_path: Optional[str]=None) -> str` (JSON: success/file_path/`MEDIA:` tag); provider+voice from `tts:` config | Bridge calls it, parses JSON, reads `file_path` audio → PCM → Opus outbound. Hermes also bundles Piper/Kitten internally; the adapter never selects a provider, so constitution-I "don't introduce Piper" holds. |
| **VG-2 endpointing** ✅ (with nuance) | `tools.voice_mode`: `SILENCE_RMS_THRESHOLD=200`, `SILENCE_DURATION_SECONDS=3.0`, speech-confirm/resume logic in `AudioRecorder` | The **authoritative rule** (RMS<200 ⇒ silence; 3.0 s ⇒ end) is reused exactly (matches spec FR-005 / design §8.1). The `AudioRecorder` class is sounddevice/mic-bound and is **not** reusable for an RTP stream; the bridge applies the same constants/logic to decoded WebRTC PCM frames. Faithful reuse of the algorithm; different transport. |
| **VG-3 agent** ✅ (architecture) | Built-in adapters (`discord.py`, `simplex.py`) contain **no** agent call — the gateway session loop owns the agent; adapters are transport-only | Adapter delivers the user turn as a platform message; the gateway invokes the agent (exactly constitution IV). **Narrowed sub-item:** the precise adapter inbound/outbound message methods (connect/receive/send-reply) — lift by reading one full built-in adapter on the host; touches only the registration shim. |
| **VG-4 registration** ✅ | `gateway.platform_registry.PlatformRegistry.register(PlatformEntry(name,label,adapter_factory:Callable[[PlatformConfig],adapter],check_fn,validate_config?,is_connected?,required_env,source,plugin_name))`; lifecycle `hermes gateway`; config `hermes gateway setup` | Register `PlatformEntry(name="satellite_webrtc", source="plugin", adapter_factory=…, check_fn=aiortc-available)`. Config block `satellite:` in the existing `~/.hermes/config.yaml` (same `GatewayConfig` loader as `stt:`/`tts:`). |

### D13–D17 (added by the re-plan)

- **D13 STT path**: PCM→temp WAV→`transcribe_audio`. Rationale: it is the
  public, fallback-aware STT entrypoint and is file-based. Alternative
  (private `_transcribe_*`) rejected — bypasses fallback/config.
- **D14 TTS path**: `text_to_speech_tool`→JSON→file→bytes. Rationale: only
  public TTS entrypoint, config-driven provider/voice. No SDP/codec coupling.
- **D15 endpointing**: reuse `voice_mode` constants + RMS/duration logic over
  WebRTC PCM; do **not** reuse `AudioRecorder` (mic-bound). Honest partial
  reuse; same authoritative rule.
- **D16 agent**: adapter is a transport-only `PlatformRegistry` platform; the
  gateway session drives the agent (no per-adapter agent call), matching
  constitution IV. One in-flight turn per session enforced adapter-side.
- **D17 registration**: `PlatformEntry` factory + `check_fn`; ship as a
  plugin-source platform; `hermes gateway` / `hermes gateway setup` lifecycle.

Only `hermes_bridge.py` (new `HermesV013Bridge`) and `adapter.py` (concrete
`PlatformEntry`) change. Package core, `session.py`, two-plane split, and the
full fake-driven test suite are untouched — the seam worked as designed.
