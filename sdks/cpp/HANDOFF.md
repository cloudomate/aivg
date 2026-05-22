# Device-side handover — libaivg-sat (feature 020)

**Audience**: the agent/developer implementing the **device firmware and
hardware rigs** that consume this SDK, in the companion repo
[`cloudomate/aivg-devices`](https://github.com/cloudomate/aivg-devices)
(clone at `~/coderepo/aivg-devices/`). Per the project convention,
device-side firmware lives there, not in aivg-core.

This SDK (`sdks/cpp/` in aivg-core) is the **protocol library**. You build
the **device application** (mic/speaker drivers, Wi-Fi, PTT UI, board
bring-up) that links it.

---

## What is DONE in aivg-core (this repo)

The verifiable, dependency-free slice of the SDK is implemented and
compile-checked (clang++ `-std=c++17` + CMake/ctest green):

- Public API headers — `sdks/cpp/include/aivg/sat/`
  (`satellite.hpp`, `events.hpp`, `errors.hpp`, `audio.hpp`, `state.hpp`, `wire.hpp`)
- Local FSM + wire-string tables — `sdks/cpp/src/state_machine.{hpp,cpp}`
- Control-plane WS interface — `sdks/cpp/src/platform/ws_client.hpp`
- Build scaffolding — root `CMakeLists.txt` (POSIX) + `idf_component.yml` (ESP-IDF)
- Compile-check — `sdks/cpp/tests/compile_check.cpp`

## What is NOT done yet (the integration the SDK still needs, in aivg-core)

These are aivg-core SDK tasks (tasks.md T012–T020, T031–T039), NOT device
work — but you depend on them. They require the libpeer + mbedTLS + Opus
integration to be fleshed out before any real turn works:

- `ws_client_posix.cpp` (mbedTLS WS), control plane, reconnect
- `libpeer_transport.cpp` (PeerConnection, ICE, DTLS-SRTP), `signaling.cpp`, `opus_bridge.cpp`
- `satellite.cpp` (the `Satellite::Impl` orchestration)

Coordinate with whoever owns the aivg-core SDK before expecting a green turn.

---

## The API you consume (frozen contract)

See `sdks/cpp/contracts/public-api.md` for the full table. In short:

```cpp
#include <aivg/sat/satellite.hpp>

aivg::sat::SatelliteOptions opts;
opts.gateway_url      = "ws://<gateway>:8643";   // control plane
opts.signaling_url    = "http://<gateway>:8644"; // voice plane
opts.device_id        = "esp32s3-1";
opts.device_name      = "Living Room";
opts.device_type      = "esp32s3";
opts.firmware_version = "0.1.0";
opts.audio_input  = /* PCM16 mono from your I2S mic  */;
opts.audio_output = /* PCM16 mono to your I2S speaker */;
opts.on_event     = [](const aivg::sat::SatEvent& e){ /* dispatch */ };

aivg::sat::Satellite sat(std::move(opts));
sat.connect().get();        // control WS + register + heartbeat
sat.beginSession().get();   // open WebRTC voice plane
sat.unmute(); /* speak */ sat.mute();   // PTT — do NOT tear down per cycle
```

- **You own**: the I2S mic/speaker drivers, Wi-Fi bring-up, the PTT button, the status LED, the board's `sdkconfig`. The SDK never touches audio hardware (spec FR-005/006).
- **The callback boundary is raw PCM16 mono.** The SDK does Opus encode/decode internally — do NOT Opus-encode in your firmware.
- **Long-lived session + mute/unmute** is the PTT model (FR-010). Tearing down the PeerConnection per press races the gateway's silence detector — don't.

## Hard constraints (do not violate)

1. **WebRTC library = `libpeer` (MIT)**, for both tiers. **Do NOT** pull
   Espressif's `esp-adf-libs` / `esp_peer` WebRTC stack — its components
   are under the product-locked `LicenseRef-Espressif-Modified-MIT`
   (redistribution for non-Espressif use prohibited). This is the binding
   reason `libpeer` was chosen (spec FR-018, plan deviation).
2. **PSRAM floor ≥ 4 MB** on the MCU. libpeer/Opus/DTLS buffers go in
   PSRAM (`CONFIG_SPIRAM`). Below-floor boards are unsupported (OOS-001).
3. **No wire/contract changes.** The SDK speaks contract `0.2.0` verbatim;
   the gateway is untouched. Your firmware must not invent endpoints.

---

## Your device-side deliverables (in aivg-devices repo)

### ESP32-S3 tier — the MVP lead (maps to tasks.md US2: T022–T027)

- ESP-IDF v5.x project that adds `sdks/cpp` as a managed/vendored component
  (via `idf_component.yml` here), targets `esp32s3`.
- `ws_client_espidf.cpp` impl of the `WsClient` interface over
  `esp_websocket_client` (this is arguably SDK code — agree ownership with aivg-core).
- `sdkconfig.defaults`: enable PSRAM, place WebRTC/Opus buffers in PSRAM.
- App: Wi-Fi join, I2S mic+speaker, PTT button, `Satellite` wiring.
- **Acceptance (SC-003)**: register → adopt → one PTT turn (mic→STT→agent→TTS→speaker) within 30 s of first press, on a real ESP32-S3 + ≥4 MB PSRAM board.
- **Principle V gate (T026)**: a combined-load test — Wi-Fi + Opus +
  ICE/DTLS-SRTP running together on hardware — must pass before the tier
  is declared viable. Record measured PSRAM headroom.

### RPi Zero 2 W tier — validation (maps to tasks.md US1: T028–T030)

- 64-bit Linux; build `sdks/cpp` with CMake (`-DAIVG_SAT_BUILD_EXAMPLES=ON`).
- App: ALSA (or your choice) mic/speaker drivers + PTT.
- **Acceptance (SC-002)**: one PTT turn within 20 s of release on a real RPi Zero 2 W.

### Reference rigs / docs

- Add both boards to the supported-hardware matrix (PSRAM floor, excluded boards) — coordinate with the SDK README (FR-019, SC-008).
- A wiring/BOM note per rig is welcome in aivg-devices.

## Verifying parity (when the SDK turn works)

Run a device turn and an `@aivg/sat-sdk` (TS) turn against the **same**
gateway; the gateway logs must match at message-type + field-name level
(SC-005). The contract version (`aivg --contract-version`) must stay
`0.2.0` (SC-006).

## Pointers

- API contract: `sdks/cpp/contracts/public-api.md`, `sdks/cpp/contracts/wire-parity.md`
- Data model / FSM: `specs/020-cpp-webrtc-sdk/data-model.md`
- Decisions (incl. libpeer/license rationale): `specs/020-cpp-webrtc-sdk/research.md`
- Build recipes: `specs/020-cpp-webrtc-sdk/quickstart.md`
- Task list + acceptance: `specs/020-cpp-webrtc-sdk/tasks.md`
