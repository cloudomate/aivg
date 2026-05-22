# Phase 0 Research: libaivg-sat-embedded

**Feature**: 020-cpp-webrtc-sdk | **Date**: 2026-05-22

All Technical-Context unknowns and dependency choices resolved below.
Each entry: Decision / Rationale / Alternatives considered.

## R1 — Embedded WebRTC library (both tiers)

- **Decision**: `libpeer` (github.com/sepfy/libpeer), MIT, used identically on the ESP32-S3 (ESP-IDF) and Linux/RPi tiers.
- **Rationale**: It is a C WebRTC implementation that uses **mbedTLS for DTLS** and **libsrtp for SRTP**, supports **Opus** (matching the gateway's voice-plane codec), and explicitly targets ESP32 *and* Linux/Raspberry Pi. MIT satisfies the redistribution requirement. One library across both tiers maximizes shared transport code behind the common API (FR-004a). Verified 2026-05-22.
- **Alternatives considered**:
  - *Espressif `esp_peer` / esp-webrtc-solution* — **rejected on license**. Depends on `esp-adf-libs` components under `LicenseRef-Espressif-Modified-MIT` ("use EXCLUSIVELY with Espressif Systems products … redistribution for non-Espressif products strictly prohibited"). GitHub's license API 404s on the repo (non-OSI). Unusable for a redistributable open SDK. This is the binding constraint behind the constitution deviation recorded in plan.md.
  - *libdatachannel* — desktop-grade (OpenSSL/GnuTLS, libjuice, plog); excellent for the Linux tier but does not fit an ESP32-S3, so it would force two different stacks. Rejected to keep one transport library.
  - *Google libwebrtc* — hundreds of MB of source, multi-hour build; violates the small-SDK / fast-build goals.

## R2 — ESP32-S3 PSRAM feasibility (Principle V combined-load gate)

- **Decision**: Treat full WebRTC (ICE + DTLS-SRTP + Opus) on ESP32-S3 as **feasible-but-unproven**; declare the MCU tier "viable" only after a combined-load test on real hardware (Wi-Fi + Opus + ICE/DTLS-SRTP + the SDK running together), per Constitution Principle V. The ≥ 4 MB PSRAM floor is the binding constraint that makes it plausible; `libpeer` does not publish a PSRAM figure, so it must be measured.
- **Rationale**: Principle V forbids declaring a constrained target viable from component-level reasoning alone. mbedTLS DTLS handshake buffers + libsrtp + Opus + Wi-Fi/TLS stacks are the memory pressure points; PSRAM (not the 512 KB internal SRAM) is where libpeer/Opus buffers must live.
- **Alternatives considered**: Asserting feasibility from libpeer's ESP32 examples alone — rejected; libpeer's shipped ESP32 example is MJPEG-over-datachannel, not Opus audio + DTLS-SRTP under Wi-Fi load, so it is not evidence for our workload.

## R3 — Build systems per tier

- **Decision**: Linux/macOS/RPi tier builds with **CMake 3.20+** (`add_subdirectory` + `FetchContent` for libpeer). MCU tier builds as an **ESP-IDF v5.x component** (`idf_component.yml`; libpeer + mbedTLS + libsrtp + Opus pulled as managed components / IDF built-ins).
- **Rationale**: ESP-IDF mandates its own CMake-based component build producing a flashable image; a single CMake invocation cannot target both. The public API and `src/` are shared; only build wiring and the WS-client shim differ (FR-004a, FR-017, FR-018).
- **Alternatives considered**: A single unified CMake build — impossible across the IDF toolchain boundary. Meson/Bazel — rejected; CMake + ESP-IDF are the mainstream toolchains the spec assumes.

## R4 — Management-plane WebSocket client (control plane)

- **Decision**: Abstract the always-on control-plane WS (`WS /satellite/ws`) behind a small internal `WsClient` interface with two implementations: **`esp_websocket_client`** (ESP-IDF built-in component) on the MCU, and a **small portable C/C++ WS client** on Linux/macOS (candidate: a single-purpose client over the same mbedTLS libpeer already pulls, or a compact lib if simpler).
- **Rationale**: Per Constitution Principle III the control plane is a *separate* connection from WebRTC and must stay up with no active call; libpeer covers the voice plane only, not this WS. The MCU already has a first-party WS client in IDF, so reusing it avoids extra footprint. Reusing mbedTLS (already a libpeer dep) avoids adding a second TLS stack.
- **Alternatives considered**: libwebsockets everywhere — heavier than needed on the MCU and redundant with `esp_websocket_client`. Multiplexing control onto a WebRTC datachannel — **prohibited by Principle III** (datachannel exists only while a PeerConnection is up).

## R5 — JSON

- **Decision**: `nlohmann/json` (header-only) for management-plane frame (de)serialization on both tiers.
- **Rationale**: Header-only (no link step), ubiquitous, trivial FetchContent / single-header drop-in; works under ESP-IDF. Matches the 016 draft's default.
- **Alternatives considered**: RapidJSON (faster, more ceremony), hand-rolled parser (error-prone). Neither justified for the small control-plane payloads.

## R6 — Reference-sample audio backend

- **Decision**: `desktop_smoke` reads/writes **WAV files** as the portable default and MAY use a single-header backend (**miniaudio**, public-domain) for live mic/speaker — confined to `examples/` (FR-007). `esp32s3_smoke` uses the board's I2S codec directly (consumer's domain per FR-005/006).
- **Rationale**: Keeps the SDK proper free of any audio dependency; preserves the "builds in minutes" promise (SC-007). WAV-only path guarantees a deterministic, hardware-free smoke.
- **Alternatives considered**: PortAudio (adds a system package step); bundling a backend in the SDK proper (violates OOS-003).

## R7 — Wire-protocol parity strategy

- **Decision**: Mirror the byte shapes in `sdks/typescript/src/proto/` (`rest-shapes.ts`, `ws-messages.ts`, `version.ts`) as the authoritative reference. The C++ SDK consumes contract version **`0.2.0`** verbatim (no new endpoint/frame/SDP munging), keys compatibility off the **major** version, and reuses the TS SDK's exact error-code strings.
- **Rationale**: SC-005/SC-006 require zero wire-shape diff and an unchanged contract version. The TS proto module is the existing source of truth; parity is validated by comparing gateway logs from a C++ turn vs a TS turn.
- **Error codes (verbatim from `sdks/typescript/src/errors.ts`)**: terminal — `no_webrtc_impl`, `no_microphone_api`, `permission_denied`, `ice_failed`, `ice_gathering_timeout`, `ws_disconnected`, `ws_max_retries_exceeded`, `signaling_failed`, `mixed_content`, `not_adopted`, `protocol_mismatch`, `duplicate_device`; transient — `ws_disconnected`, `signaling_retry`, `ice_retry`, `buffer_overflow`. (Some are browser-specific, e.g. `no_microphone_api`/`mixed_content`/`permission_denied`; the C++ SDK defines the enum for full parity but only emits the codes reachable on a native client.)

## R8 — Opus on ESP32-S3

- **Decision**: Use the Opus codec libpeer expects, built for Xtensa under ESP-IDF (Opus has an established ESP-IDF port / managed component); Opus encode/decode buffers live in PSRAM.
- **Rationale**: The gateway's voice plane is Opus; the SDK must encode mic PCM → Opus and decode Opus → PCM for the consumer's callbacks. This is transport compression, not STT/TTS (Constitution Principle I compliant).
- **Alternatives considered**: G.711 (libpeer supports it, far cheaper on CPU) — rejected unless the load test (R2) shows Opus is infeasible on ESP32-S3; G.711 would be a fallback only if the gateway negotiates it, which today it does not, so it stays out of scope.

## R9 — libpeer API + Opus reality (verified in rpi-builder, 2026-05-22)

- **libpeer builds clean on aarch64** (`libpeer.a`) in the rpi-builder container with its vendored, submodule-built mbedTLS (patched for `MBEDTLS_SSL_DTLS_SRTP`), libsrtp, usrsctp, cJSON. All 6 submodules (incl. coreHTTP/coreMQTT) must be initialized or configure fails.
- **Opus IS supported despite a stale header comment.** `include/peer_connection.h` marks `CODEC_OPUS // not implemented yet`, but the source contradicts it: `src/sdp.c::sdp_append_opus` emits `m=audio … 111` + `a=rtpmap:111 opus/48000/2`, and `src/rtp.c` packetizes `PT_OPUS=111`. libpeer handles Opus **RTP/SDP transport**; the **codec (encode/decode) is the app's job** via libopus — that is exactly our `opus_bridge` (T017). This matches the gateway's `opus/48000` voice plane.
- **Signaling: we use our own REST, not libpeer's built-in `peer_signaling`.** Flow: `peer_init()` → `peer_connection_create(cfg{audio_codec=CODEC_OPUS, onaudiotrack, oniceconnectionstatechange})` → `peer_connection_create_offer()` → `POST /webrtc/offer` to the gateway → `peer_connection_set_remote_description(answer, SDP_TYPE_ANSWER)` → pump `peer_connection_loop()` in a thread → on `PEER_CONNECTION_COMPLETED`, start media (`peer_connection_send_audio` out; `onaudiotrack` in).
- **Control plane proven live**: a from-scratch RFC6455 client (mbedTLS sha1/base64 handshake) registered against the real gateway and received `registered`(adopted)+`state_update`; heartbeat accepted.

## Cross-cutting finding — spec correction needed (SC-004 / FR-003)

The spec says the SDK mirrors "the nine documented events." The
**authoritative** `@aivg/sat-sdk` surface (`SatelliteEvents` in
`sdks/typescript/src/events.ts`) currently exposes **17** events:
`state`, `gateway_state`, `adoption`, `config_changed`, `command`,
`log`, `ota_manifest`, `ota_progress`, `transcript`, `tool_call`,
`skill`, `barge_in`, `remote_stream`, `session_started`,
`session_ended`, `error`, `transient_error`. The binding requirement
(FR-003 / SC-004) is **1:1 parity with the TS SDK**, so the artifacts
use the full 17-event list. Recommend a one-word spec edit (SC-004:
"nine" → "the full TS event set") at the next spec touch; not a blocker
for planning.

The local `SatelliteState` FSM is **4 states** (`idle | listening |
speaking | error`); "thinking" is a *gateway_state* value, not a local
FSM state — reflected in data-model.md.
