# Quickstart: libaivg-sat-embedded

**Feature**: 020-cpp-webrtc-sdk | **Date**: 2026-05-22

Three paths: the hardware-free desktop smoke (everyday gate), the
ESP32-S3 MCU tier (MVP lead), and the RPi Zero 2 W Linux tier
(validation). All drive one PTT voice turn against the same AIVG gateway
the electron-test uses.

## Prerequisites

- A running AIVG gateway (e.g. local Hermes host on `:8643` control / `:8644` voice).
- Desktop: CMake 3.20+, a C++17 toolchain (Clang 14+/GCC 11+).
- MCU: ESP-IDF v5.x installed; an ESP32-S3 board with ≥ 4 MB PSRAM + Wi-Fi.
- RPi: a Raspberry Pi Zero 2 W class board on 64-bit Linux + the desktop toolchain.

## Path A — Desktop reference smoke (no hardware) ~ minutes

```bash
cd sdks/cpp
cmake -B build -DAIVG_SAT_BUILD_EXAMPLES=ON
cmake --build build
# Drive one turn: WAV in → gateway → reply WAV out
./build/examples/desktop_smoke \
    --gateway ws://localhost:8643 \
    --signaling http://localhost:8644 \
    --device-id cpp-smoke-1 \
    --in prompt.wav --out reply.wav
# PASS: reply.wav is non-empty; transcript printed; exit code 0  (SC-001, FR-021)
```

libpeer, mbedTLS, libsrtp, Opus, nlohmann/json are pulled via
`FetchContent` — no system packages beyond the toolchain (SC-007).

## Path B — ESP32-S3 MCU tier (MVP lead) ~ within 30 s/turn

```bash
cd sdks/cpp/examples/esp32s3_smoke
idf.py set-target esp32s3
idf.py menuconfig          # set Wi-Fi SSID/PSK, gateway URL, device id
idf.py build flash monitor
# On the board: press PTT, speak, release.
# PASS: device registers → adopts → one full mic→STT→agent→TTS→speaker turn  (SC-003)
```

The same `aivg::sat::Satellite` API as Path A; only build-time flags +
the I2S audio driver differ.

## Path C — RPi Zero 2 W validation tier ~ within 20 s/turn

```bash
# On the Pi (64-bit Linux):
cd sdks/cpp
cmake -B build -DAIVG_SAT_BUILD_EXAMPLES=ON
cmake --build build
./build/examples/desktop_smoke --gateway ws://<gateway> --signaling http://<gateway>:8644 \
    --device-id rpi0-2w-1 --in prompt.wav --out reply.wav
# PASS: one turn completes within 20 s of release  (SC-002)
```

## Consuming the SDK (downstream CMake)

```cmake
include(FetchContent)
FetchContent_Declare(aivg_sat
  GIT_REPOSITORY https://github.com/cloudomate/aivg.git
  SOURCE_SUBDIR  sdks/cpp)
FetchContent_MakeAvailable(aivg_sat)
target_link_libraries(my_satellite PRIVATE aivg::sat)   # SC-006: one-block add
```

## Wire-parity check (binding gate)

```bash
# Run a C++ turn and a TS turn against the SAME gateway, diff gateway logs
# at the message-type + field-name level → must be zero (SC-005).
```
