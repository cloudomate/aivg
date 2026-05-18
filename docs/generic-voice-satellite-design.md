# Generic Voice Satellite Design

**Status:** Ideation (v1) — research-backed
**Last updated:** 2026-05-18
**Owner:** Hermes Agent


## 1. The three targets

| # | Satellite | Compute | Mic / DSP | Echo cancellation | Wake word | TTS/ASR |
|---|-----------|---------|-----------|-------------------|-----------|---------|
| 1 | **RPi Zero 2 W + ReSpeaker 2-Mic HAT** | 4×Cortex-A53 @1 GHz, **512 MB RAM** | 2 analog MEMS, WM8960 *or* TLV320AIC3104 codec — **no hardware AEC** | software (SpeexDSP) or half-duplex | Porcupine (openWakeWord marginal) | **remote only** |
| 2 | **ReSpeaker XVF3800 4-mic + XIAO ESP32S3** | ESP32-S3 @240 MHz, 8 MB PSRAM, 8 MB flash | 4-mic circular array, **XMOS XVF3800 does AEC/beamform/NS/AGC/VAD in hardware** | **hardware (XMOS)** | XMOS VAD gate + optional openWakeWord | remote (over WebRTC) |
| 3 | **JS / Electron desktop app** | Desktop-class | Any system mic | **Chromium AEC3 (built-in)** | push-to-talk (v1) / openWakeWord-WASM (v2) | remote (over WebRTC) |

The unifying idea: **the satellite is thin**. It captures audio, decides *when*
to stream (VAD/wake word), transports it, and plays back what comes home.
**ASR and TTS run on the Hermes gateway via its existing pluggable STT/TTS
provider layer** (§8) — the satellite never does ASR/TTS. This is not just a
preference; it is forced by target #1 (the Zero 2 W, §3.1) and it means satellites
inherit Hermes's provider choice (faster-whisper / Groq / OpenAI for STT;
Edge / NeuTTS / ElevenLabs / OpenAI / MiniMax for TTS) for free.

---

## 2. Generic satellite contract

Every satellite, regardless of hardware, MUST implement these four planes.
This is the actual "generic" design — the device-specific sections (§3–5) only
fill in *how* each plane is realized.

### 2.1 Control plane — `WS /satellite/ws` (always-on)

Long-lived WebSocket, independent of any voice call. Auto-reconnect with
exponential backoff. Carries: `register`, `heartbeat` (state snapshot every
`heartbeat_interval`s), `config_changed`, `command` (reboot/restart/…),
`log_entry`, OTA progress. This is the reliable, ordered channel — it must be
up even when there is no active call (config push, "start a call" command,
online/offline tracking). **Never multiplex this into a WebRTC data channel**
(see §6).

### 2.2 Voice plane — WebRTC (per-session)

Bidirectional Opus @48 kHz. Satellite is the **offerer** for all three types
(consistent with `esp_peer` ESP32 role and browser norm). Signaling over the
existing HTTP endpoints:

```
POST /webrtc/offer    { sdp, type:"offer", device_id } -> { sdp, type:"answer" }
POST /webrtc/candidate { candidate, sdpMid, label, device_id } -> 204
GET  /webrtc/status/{device_id}
```

**ICE strategy: full gather, then offer.** Wait for
`iceGatheringState === "complete"` (or `esp_peer` gathering done), put all
candidates in the SDP, then `POST /webrtc/offer`. On a LAN this lets every
satellite skip `/webrtc/candidate` entirely and sidesteps the most common
aiortc trickle-ordering bug (candidates arriving before remote description).
Keep `/webrtc/candidate` wired as a fallback only.

### 2.3 Capture/endpointing plane (device-specific, same semantics)

Audio is only streamed up when speech is present. Each device produces the
same logical signal — "voice active" — from very different sources:

- ESP32: XMOS hardware VAD over I2C
- RPi: Porcupine wake word + software VAD
- Browser: push-to-talk or JS VAD (v1), openWakeWord-WASM (v2)

The gateway does not care which; it just receives gated Opus.

### 2.4 Playback plane (device-specific)

Decoded far-end audio out to a speaker. The **critical constraint** is the
echo path, and it differs per device — see each section. The gateway is
identical for all three.

### 2.5 Shared data models

`SatelliteState` / `SatelliteConfig` / `LogEntry` are defined in **Appendix B**
and used unchanged by all three types. The only per-type divergence: `browser`
has no OTA; echo-handling strategy is an enum
(`hardware_xmos | software_speex | half_duplex | browser_aec3`) rather than a
single global ducking approach.

---

## 3. Satellite #1 — RPi Zero 2 W + ReSpeaker 2-Mic HAT

### 3.1 Hard constraints (from research)

- **512 MB RAM, 4×1 GHz Cortex-A53.** After a headless 64-bit OS, ~300–400 MB
  usable. This is the binding constraint for the whole fleet design.
- **No hardware AEC.** The 2-Mic HAT is just codec + 2 mics + ~1 W amp.
- **Codec varies by board revision:** V1 = Cirrus WM8960, V2.0 = TI
  TLV320AIC3104. Different `seeed-voicecard` overlay. **Confirm the physical
  board before building the OS image.**
- Native 48 kHz capture/playback (matches Opus — good).

### 3.2 Design decisions

| Concern | Decision | Why |
|---|---|---|
| OS | 64-bit Raspberry Pi OS **Lite**, headless | Max free RAM; NEON paths for libopus/tflite. Never 32-bit, never desktop. |
| ASR/TTS | **Remote on gateway. Not negotiable.** | Piper is "far from real-time" and faster-whisper `tiny` is far slower than real-time on a 1 GHz A53 / 512 MB. |
| Wake word | **Porcupine** (~4% of one core). openWakeWord only if a fully-open stack is mandatory, pinned to one core, accepting latency. | openWakeWord on Zero 2 W pins a core ~70–100% and stalls multi-second when sharing CPU with WebRTC. |
| Echo | **SpeexDSP AEC** + **half-duplex fallback** (gate capture/wake word during local TTS playback) | WebRTC-APM AEC + openWakeWord + aiortc together will overload the board; SpeexDSP is lighter. Half-duplex also prevents TTS self-triggering the wake word. |
| WebRTC stack | **Start with aiortc** (audio-only, single PC, no video). Migration path: **GStreamer `webrtcbin`** if CPU/RAM too tight. | aiortc is fastest to build; `webrtcbin` runs at C level, talks to the HAT via ALSA directly, and brings `webrtcdsp` AEC into one pipeline. |
| Audio format | 48 kHz, downmix 2 mics → **mono** before Opus; set Opus bitrate explicitly **~24–32 kbps** | Halves encode/transport; avoids aiortc's ~96 kbps default; stable on 2.4 GHz Wi-Fi. |

### 3.3 Core budget warning

4×1 GHz must cover: wake word + VAD + AEC + Opus + ICE/SRTP + OS/Wi-Fi. Each
component looks fine alone and they contend in practice (this is the exact
failure mode in the wyoming-openwakeword Zero 2 W issues). **Load-test the full
pipeline together**, use core pinning, one engine per heavy task.

### 3.4 Daemon shape

```
hermes-satellite (Python, single venv)
  ├─ control:  WS /satellite/ws  (register, heartbeat, config, commands, logs)
  ├─ capture:  alsa(seeed-voicecard) → SpeexDSP AEC → Porcupine → VAD gate
  ├─ voice:    aiortc PC, offerer, Opus 48k mono ~32 kbps
  └─ playback: aiortc remote track → ALSA out  (and feeds AEC far-end ref)
config: ~/.hermes/satellite.json   OTA: curl + systemctl restart
```

---

## 4. Satellite #2 — ReSpeaker XVF3800 + XIAO ESP32S3

### 4.1 Hard facts (from research)

- XIAO ESP32S3: dual LX7 @240 MHz, **512 KB SRAM, 8 MB PSRAM, 8 MB flash**,
  **2.4 GHz Wi-Fi only**.
- **XMOS XVF3800 does AEC, beamforming, noise suppression, dereverb, AGC, and
  VAD/DoA in hardware.** 4 PDM mics, circular array, ~5 m far-field.
- XVF3800 ↔ XIAO is **I2S**: BCLK=GPIO8, WS=GPIO7, DOUT(XIAO→XMOS)=GPIO44,
  DIN(XMOS→XIAO)=GPIO43. Control over **I2C, addr 0x2C**.
- Supported rates: **16 kHz or 48 kHz only, 32-bit slots.**
- **DECIDED: I2S firmware, 48 kHz variant** (the Home Assistant
  `respeaker_xvf3800_i2s_master_dfu_firmware ... 48k` build). Not USB mode.
  XMOS = I2S **master**, ESP32 = I2S **slave**, no resampling vs Opus 48 kHz.
  Build-time check only: confirm the flashed binary is the I2S-master 48 k
  build (the 16 k variant inverts the master/slave role).
- Onboard **TLV320AIC3104 DAC + amp + JST 5 W speaker + 3.5 mm AUX**. **No
  separate I2S DAC needed on the XIAO.**
- `esp_peer` (Espressif WebRTC: ICE/DTLS-SRTP/SCTP, Opus 48 k, bidirectional)
  fits comfortably in 8 MB PSRAM / 8 MB flash; Opus ≈8–9% CPU/channel @240 MHz.

### 4.2 The echo design — this is the important part

**Do NOT do acoustic ducking.** Ducking is unnecessary on this hardware and
degrades full-duplex/barge-in — the XVF3800's own AEC handles echo (below).

The XVF3800 cancels echo internally **using the far-end signal you feed back
into it as the AEC reference**:

```
received WebRTC Opus ─► esp_peer decode ─► PCM ─► I2S DOUT (GPIO44, ch 0)
                                                   │
                                                   ▼
                                         ┌──────── XVF3800 ────────┐
                                         │  uses ch0 as AEC ref    │
                                         │  AEC/beamform/NS/AGC    │
                                         │  feeds AIC3104 → amp →  │──► speaker
                                         │  returns clean near-end │
                                         └─────────┬───────────────┘
                                                   ▼
                              I2S DIN (GPIO43) ─► esp_peer Opus encode ─► WebRTC up
```

One I2S TX stream serves both speaker playback and the AEC reference
simultaneously, because the far-end physically passes through the XMOS. The
ESP32 does **zero** echo processing.

### 4.3 Design decisions

| Concern | Decision |
|---|---|
| WebRTC | `esp_peer` / `esp-webrtc-solution`, role = offerer (`ESP_PEER_ROLE_CONTROLLING`), Opus 48 kHz send+recv, PSRAM-backed jitter/codec buffers |
| Firmware variant | XVF3800 **48 kHz I2S-master** ("HA") firmware; ESP32 I2S = slave, 32-bit slots, 2 ch |
| Capture format | take processed speech channel from DIN, 32→16-bit, Opus encode |
| Playback format | Opus decode → 16→32-bit, far-end on **ch 0** of DOUT (this *is* the AEC ref) |
| Endpointing | read XMOS **VAD over I2C (0x2C)**; gate transmit on VAD. Optionally also openWakeWord on-device (fits PSRAM) for explicit wake-word UX |
| Echo | **none on ESP32** — XMOS hardware AEC, ref routing as §4.2 |
| Mic gain / AGC | set `AUDIO_MGR_MIC_GAIN` / `PP_AGCGAIN` via I2C at boot; `SAVE_CONFIGURATION` to persist |
| Amp enable | XMOS GPO via I2C |
| Network | Opus ~24–32 kbps + DTX/FEC; design jitter buffer for congested 2.4 GHz |
| Pin budget | I2S(4) + I2C(2) committed to ReSpeaker; almost no free GPIO — use XMOS GPI/GPO via I2C for button/LED |

### 4.4 Provisioning / OTA

AP-fallback provisioning and dual-partition A/B OTA as in the existing docs
remain correct for this device (real ESP-IDF OTA, NVS creds). No changes.

---

## 5. Satellite #3 — JS / Electron desktop app

### 5.1 Why it's the easiest target

Chromium's **AEC3** is purpose-built for the "speaker + mic on one device"
case and has the render loopback reference. It is *better* than the ESP32
ducking idea and removes echo as a concern entirely — **provided** TTS is
played through an `<audio>` element in the **same renderer** (not Web Audio as
the primary path, not an external player).

### 5.2 Design decisions

| Concern | Decision |
|---|---|
| Connections | **Two**, per the generic contract: WS `/satellite/ws` (always-on) + `RTCPeerConnection` per call. Optional **one SCTP datachannel** on the PC for *call-scoped* UI only (partial transcripts, barge-in) |
| Offer | audio transceiver only (no video); full ICE gather → `POST /webrtc/offer`; skip `/webrtc/candidate` on LAN |
| Capture | `getUserMedia({audio:{echoCancellation:true,noiseSuppression:true,autoGainControl:true,channelCount:1,sampleRate:48000}})` |
| Echo | rely entirely on Chromium AEC3; **no ducking, no server-side echo handling**. Withhold mic TX ~1–2 s after stream start / after long TTS so AEC3 reconverges |
| Playback | hidden `<audio autoplay>` with `srcObject = remoteStream`; needs a user gesture (Connect button) for autoplay; let NetEq handle jitter — no manual buffering. Web Audio only for a *tapped* level meter |
| Wake word | **v1: push-to-talk + optional Silero/WebRTC VAD** (no model hosting). **v2: openWakeWord via onnxruntime-web in an AudioWorklet**, reusing the fleet's `openwakeword` models so `wake_word`/`wake_word_engine` config applies uniformly. Feed wake/VAD from the post-AEC track |
| Codec | default Opus negotiation, **no SDP munging**; accept aiortc's fixed ~96 kbps downlink (fine on LAN) |
| macOS | `NSMicrophoneUsageDescription` in Info.plist + audio-input entitlement; `systemPreferences.askForMediaAccess('microphone')` before `getUserMedia`; handle "denied → deep-link to Settings"; sign and test from a real `.app` |
| Background | Tray app, hidden window, `webPreferences.backgroundThrottling:false` so the always-listening pipeline + WS heartbeat aren't throttled; optional login-item auto-start |

---

## 6. Decision: management WS vs voice WebRTC — **two connections**

For all three satellites. The control plane must be available when there is no
active call (online/offline, config push, OTA, "start a call"). A WebRTC data
channel only exists while a PeerConnection is up, so multiplexing control into
SCTP would couple control availability to call state — wrong for a satellite,
and it would force protocol-branching in the gateway registry/dashboard.

Permitted refinement: a **single SCTP datachannel on the existing voice PC**,
used *only* for call-scoped, low-latency UI events (partial ASR transcripts,
"listening/speaking" state, barge-in/interrupt). Everything durable
(register/heartbeat/config/commands/logs/OTA) stays on the WS.


## 7. Build order (recommended)

1. **Gateway WebRTC adapter + browser satellite first.** Browser is the
   lowest-risk end-to-end loop (AEC3 free, no hardware, no flashing). Proves
   the aiortc offer/answer + Opus path wired into Hermes's existing STT/TTS
   provider layer (§8).
2. **ESP32 satellite.** Highest hardware value; AEC is hardware-solved once
   reference routing (§4.2) is correct. Validate I2S firmware master/slave
   role early.
3. **RPi satellite last.** Most constrained; needs the full-pipeline load test
   and a possible aiortc→`webrtcbin` migration. Confirm HAT revision up front.

---

## 8. Hermes gateway integration

Grounded in the Hermes Agent voice-mode docs
(`hermes-agent.nousresearch.com/docs/user-guide/features/voice-mode`). The
satellite system is **not** a standalone pipeline — it is a **new platform
adapter** that plugs into the existing Hermes gateway, exactly like the
Telegram and Discord adapters, and consumes Hermes's existing STT/TTS layer.

### 8.1 What Hermes already provides (do not rebuild)

| Concern | Hermes-provided | Implication for the adapter |
|---|---|---|
| Gateway lifecycle | `hermes gateway`, `hermes gateway setup` | The satellite adapter is registered/configured here, not a separate daemon. |
| Config | `~/.hermes/config.yaml` (`voice:`, `stt:`, `tts:` blocks) | Add a `satellite:` / `webrtc:` block here — same file, same loader. |
| Secrets | `~/.hermes/.env` (`GROQ_API_KEY`, `VOICE_TOOLS_OPENAI_KEY`, …) | Reuse; no new secret store. |
| STT | provider abstraction: `local` faster-whisper (`base`/`small`/`large-v3`), `groq` (whisper-large-v3-turbo), `openai`. Fallback `local > groq > openai` | Adapter feeds decoded PCM into this layer; **never instantiate Whisper directly.** |
| TTS | provider abstraction: `edge` (default), `neutts` (local, needs espeak-ng), `elevenlabs`, `openai`, `minimax` | Adapter takes provider PCM/Opus out and pushes it onto the WebRTC track. **Piper is not a Hermes engine — don't introduce it.** |
| Endpointing | server-side two-stage silence algo: speech-confirm (RMS > `silence_threshold` 200 for 0.3 s), end-detect (`silence_duration` 3.0 s) | Device VAD/wake word only *gates* the stream to save bandwidth; the **authoritative end-of-utterance is Hermes's existing algorithm**, reused unchanged. |
| Audio format | Opus/OGG, `ffmpeg` available | Matches WebRTC Opus; ffmpeg covers any resample/container needs. |
| Logs | `~/.hermes/logs/gateway.log` | Satellite/WebRTC logs go here; the `/satellite/{id}/logs` SSE (App. A) tails per-device entries. |

### 8.2 Adapter placement

```
hermes gateway
  ├─ platform adapter: telegram        (existing)
  ├─ platform adapter: discord         (existing)
  └─ platform adapter: satellite_webrtc   (NEW — this design)
        ├─ aiohttp TCPSite :8644  (WebRTC signaling, §2.2)
        ├─ aiohttp TCPSite :8643  (management plane, App. A)
        └─ per-device Session → Hermes STT layer → agent → Hermes TTS layer
```

The adapter is a thin transport/registry layer. The agent loop, STT, TTS, and
silence detection are **Hermes's**, invoked through its provider interfaces —
the satellite adapter only moves Opus frames in and out and manages the
device registry/control plane.

### 8.3 Config additions (`~/.hermes/config.yaml`)

```yaml
# existing blocks: voice:, stt:, tts:  (unchanged — satellites inherit them)
satellite:
  enabled: true
  management_port: 8643
  webrtc_port: 8644
  heartbeat_interval: 30
  mdns_advertise: true       # publish _hermes-sat._tcp for LAN discovery (§9.1)
  default_config:            # pushed to devices on /satellite/register
    wake_word: "Hey Jarvis"
    routing_mode: "preferred"
    log_level: "INFO"
```

Open item: confirm the exact gateway CLI surface for adapter
enable/restart against the running Hermes build (`hermes gateway setup`
flow). The earlier docs assumed `hermes gateway restart`; the published docs
only show `hermes gateway` and `hermes gateway setup`.

---

## 9. Satellite onboarding & provisioning (Day-0)

Before a satellite can `POST /satellite/register` (App. A) it needs exactly two
facts, and on headless hardware neither can be typed in:

1. **Network access** — WiFi SSID + password (skipped for wired/desktop).
2. **The Hermes gateway endpoint on the LAN** — IP:port of the management
   plane.

Provisioning's *only* job is to deliver those two, persist them, and hand off
to `register`. The gateway remains the source of truth: `register`'s response
`management_server_url` can correct/redirect the device and supplies
`default_config`, so onboarding only needs a **best-effort** gateway hint.

### 9.1 Gateway discovery (shared by all device types)

Resolution order, every satellite:

1. **Persisted endpoint** from a prior provisioning/register (NVS / json /
   electron-store).
2. **mDNS / DNS-SD** — the gateway advertises `_hermes-sat._tcp.local`
   (Avahi/zeroconf; `mdns_advertise` in §8.3) with TXT
   `mgmt=8643 webrtc=8644 ver=<x>`. Zero-config on a flat LAN — this is the
   normal path; the user never types an IP.
3. **Manual hint** entered during provisioning (below). Required only when
   mDNS is blocked (VLAN/AP isolation, enterprise WiFi, `.local` filtering).

### 9.2 ESP32 (XVF3800 + XIAO) — headless MCU

- **Primary: Improv Wi-Fi over BLE.** The ESP/Home-Assistant standard; the
  user provisions from a browser (improv-wifi.com) or companion app over BLE —
  no app install, no typing on the device. XIAO ESP32S3 has BLE 5.0. The
  Improv flow returns the device's resolved URL to the provisioner for display.
- **Fallback: SoftAP captive portal** — detailed in **Appendix C** (SSID
  `HermesSatellite-<id>`, form posts the §9.5 payload). Used when no BLE
  provisioner is available.
- Credentials in **NVS**. Factory reset = long-press the XMOS GPI button (read
  over I2C) → clear NVS → re-enter Improv/AP mode.

### 9.3 RPi Zero 2 W — headless SBC

- **Preferred: pre-baked image (fleet flashing).** Raspberry Pi Imager OS
  customization, or a boot-partition `firstrun.sh` / `custom.toml` /
  NetworkManager `.nmconnection` dropped before first boot, injects WiFi +
  gateway hint. Best for provisioning many units.
- **In-field fallback: NetworkManager hotspot portal.** If no known WiFi
  within a boot timeout, bring up AP `HermesSatellite-<id>` and serve the same
  portal page as the ESP32 (balena `wifi-connect`, Comitup, or a small
  `nmcli`-driven AP + captive portal). On submit: write a NetworkManager
  connection + `~/.hermes/satellite.json` (`hermes_url`), restart networking.
  Symmetric UX with the ESP32 fallback.
- Config persists in `~/.hermes/satellite.json`; daemon under `systemd`;
  `hermes-satellite --reset` clears config and re-enters AP mode.

### 9.4 Browser / Electron — already networked

- No WiFi step. Needs only the gateway endpoint: mDNS discovery from the
  renderer/main process (e.g. `bonjour`/`mdns`), else a settings field.
  Persist in `electron-store`. First-run wizard: discover → confirm gateway →
  mic permission (§5) → register.

### 9.5 Unified provisioning payload

One schema for both the ESP32 and RPi portals:

```
{ wifi_ssid, wifi_password, hermes_url?, device_name, wake_word? }
```

`hermes_url` is **optional** — omit it and the device falls back to mDNS
discovery (§9.1). `device_name` becomes the `device_id` seed; `wake_word`
overrides the gateway default if set.

### 9.6 Reset & re-onboard

- Per device: ESP32 = clear NVS (button/command); RPi = `--reset`; browser =
  clear store — each returns the device to its discovery/provisioning entry.
- Remote: `POST /satellite/{id}/command { command: "factory_reset" }`
  (App. A) triggers the same path on any device type.

---

# Appendices — folded in from the removed docs

Carried forward from the two removed ideation docs (research-corrected where
noted inline). These define the management plane every satellite's control
plane (§2.1) speaks.

## Appendix A — Management endpoints

Served by the Hermes management adapter on a dedicated port (e.g. `8643`).
WebRTC signaling endpoints (`/webrtc/offer`, `/webrtc/candidate`,
`/webrtc/status/{id}`) are in §2.2.

```
# Registration & lifecycle
POST   /satellite/register
       { device_id, device_type, capabilities, firmware_version, ip_address }
       -> { session_token, management_server_url, default_config }
       (device calls on boot; on failure ESP32 enters AP provisioning, App. C)
GET    /satellite/list
       -> [{ device_id, device_type, status, last_seen, firmware_version,
              active_routing_mode, webrtc_state }]
GET    /satellite/{id}/state          -> full SatelliteState (App. B)
DELETE /satellite/{id}                -> 204 (removed from registry; may re-register)

# Configuration
GET    /satellite/{id}/config         -> running config
POST   /satellite/{id}/config         -> applied config (immediate + persisted to device)
GET    /satellite/{id}/config/schema  -> JSON schema (dashboard renders forms)

# Real-time logs (SSE)
GET    /satellite/{id}/logs   ?since=&level=&source=vad|wakeword|asr|tts|webrtc|system
GET    /satellite/logs        (aggregate; + ?device_id= filter)

# Commands & OTA
POST   /satellite/{id}/command
       { command: reboot | restart_voice | restart_manager | reset_config | factory_reset }
       -> { accepted, scheduled_at }
POST   /satellite/{id}/ota/check      -> { update_available, latest_version, changelog_url }
POST   /satellite/{id}/ota/apply      { version, url } -> { started_at, estimated_duration }
GET    /satellite/{id}/ota/manifest   -> { version, url, sha256, signature, changelog }

# Dashboard WebSocket (the §2.1 control plane)
WS     /satellite/ws
       server->client: state_update, log_entry, config_changed,
                        command_response, ota_progress
       client->server: subscribe_device, unsubscribe_device, device_command
```

Security: deferred (no auth for now). Future: per-device API key + TLS.

## Appendix B — Data models

```python
# SatelliteState (heartbeat snapshot)
device_id: str            # "rpi2w02", "esp32-01", "browser-yash-phone"
device_type: str          # "rpi" | "esp32" | "browser"
status: str               # online | offline | connecting | error
last_seen: float; ip_address: str; firmware_version: str
connection_type: str      # websocket | webrtc | http_poll
wake_word: str; wake_word_engine: str       # "porcupine"|"openwakeword"|"xmos_vad"
vad_threshold: float; vad_mode: str         # adaptive | fixed
routing_mode: str         # preferred | full_local | bypass
input_volume: float; output_volume: float
echo_strategy: str        # hardware_xmos | software_speex | half_duplex | browser_aec3
webrtc_state: str; bitrate_tx: int; bitrate_rx: int
latency_ms: float; packet_loss_pct: float
error_count: int; last_error: str | None
ota_state: str            # idle | checking | downloading | flashing | rebooting
ota_version: str | None

# SatelliteConfig (persisted device + server) — defaults shown
wake_word            = "Hey Jarvis"
wake_word_engine     = "openwakeword"        # see per-device §3–5
vad_threshold        = 0.5
vad_mode             = "adaptive"
routing_mode         = "preferred"           # route through Hermes
input_volume         = 1.0
output_volume        = 1.0
echo_strategy        = "<per device, §2.5>"
webrtc_enabled       = True
log_level            = "INFO"
heartbeat_interval   = 30                     # seconds

# LogEntry
device_id: str; timestamp: float; level: str  # DEBUG|INFO|WARN|ERROR
source: str                                    # vad|wakeword|asr|tts|webrtc|system|ota
message: str; metadata: dict | None            # e.g. {"wake_word_confidence":0.94}
```

(`echo_strategy` is the one model change vs the old docs — replaces the
single global ducking assumption; see §2.5.)

## Appendix C — ESP32 AP provisioning

If the device cannot reach the management server within 10 s of boot:

```
1. Start WiFi AP: SSID "HermesSatellite-<device_id>" (open or simple PIN)
2. HTTP server on 192.168.4.1:80
3. User connects (captive portal), submits:
   wifi_ssid, wifi_password, hermes_url (default http://<hermes-ip>:8643),
   device_name, wake_word
4. Save to NVS, reboot, connect; on success AP shuts down
5. Not provisioned within 5 min -> deep sleep (battery devices)
```

## Appendix D — OTA flow

```
satellite                                      Hermes
  | POST /ota/check ------------------------->  |
  | <----------------- { update_available }     |
  | POST /ota/apply { url } ----------------->  |
  | <------- firmware binary (HTTP download)     |
  | flash to inactive OTA partition             |
  | reboot                                      |
  | POST /ota/status { version, result } ---->  |
```

- Hermes serves firmware from `~/.hermes/firmware/` or proxies a URL.
- ESP32: ESP-IDF dual-partition A/B, rollback on boot failure.
- RPi: `curl` download + `systemctl restart` (no partition swap).
- `browser`: no OTA.

## Appendix E — Gateway WebRTC adapter shape (corrected)

One aiortc-based platform adapter serves all three satellite types — they
differ only on the wire upstream of it. It owns **transport + registry only**;
STT, the agent loop, TTS, and endpointing are Hermes's (§8), reached through
Hermes's provider interfaces — never reimplemented here.

```python
# gateway/platforms/satellite_webrtc.py
class SatelliteWebRTCAdapter(BasePlatformAdapter):
    # registered like the telegram/discord adapters under `hermes gateway`
    # config from ~/.hermes/config.yaml `satellite:` block (§8.3)
    # aiohttp TCPSite :8644 -> /webrtc/offer|candidate|status   (§2.2)
    # aiohttp TCPSite :8643 -> /satellite/* + WS /satellite/ws   (App. A)
    # one Session per device_id; tear down + expect re-offer on ICE drop

class Session:
    pc: RTCPeerConnection                  # answerer (satellite is offerer)

    # INBOUND  device Opus --aiortc--> PCM AudioFrame
    #   -> Hermes silence algo (RMS 200 / 0.3s confirm / 3.0s end, §8.1)
    #   -> Hermes STT provider (config stt.provider; local/groq/openai)
    #   -> Hermes agent loop  (same as telegram/discord adapters)
    # OUTBOUND agent text
    #   -> Hermes TTS provider (config tts.provider; edge/neutts/…)
    #   -> PCM -> aiortc Opus encode -> outbound track -> device
    #
    # No Whisper/Piper instances here: call hermes.stt.transcribe(...) /
    # hermes.tts.synthesize(...) (or the equivalent provider interface in
    # the running build) so satellites inherit the gateway's configured
    # providers and fallbacks for free.
```

ESP32 partition table (ESP-IDF, dual-OTA) and ~3 MB-of-8 MB PSRAM budget
(esp_peer ~512 KB, Opus ~128 KB, openwakeword ~2 MB, I2S/net buffers) carry
over unchanged from the prior firmware spec.