# libaivg-sat — C++ satellite SDK

A C++17 client SDK for building **AIVG voice satellites**. A satellite captures
microphone audio, decides *when* to stream it, transports it to the gateway, and
plays back the reply. **Speech recognition, the agent, and TTS all run on the
gateway** — the SDK is a thin transport + control layer (Constitution Principle
I). Public API mirrors [`@aivg/sat-sdk`](../typescript) (the TypeScript SDK).

- **Transports**: WebRTC (libpeer) and, on the Linux/RPi tier, **gRPC**
  (feature 022). Selected per-build and negotiated with the gateway.
- **Tiers**: RPi Zero 2 W-class Linux/POSIX, and ESP32-S3 (ESP-IDF). Same public
  header on both; differences are build-time only.
- **No system audio backend** — *you* own the mic/speaker and supply two PCM16
  callbacks.

> Reference: [`docs/api.md`](docs/api.md). Examples:
> [`examples/desktop_smoke`](examples/desktop_smoke) (WAV-in/WAV-out turn) and
> [`examples/rpi_pipewire`](examples/rpi_pipewire) (PipeWire + openWakeWord).

## Build

The voice plane needs a **pre-built [libpeer](https://github.com/sepfy/libpeer)**
patched for the DTLS-client role (`rpi-builder/patches/0001-offerer-dtls-client.patch`).
The simplest reproducible toolchain is the bundled container
([`rpi-builder/`](rpi-builder), arm64 Debian Bookworm = the Pi's ABI).

| Build flag | Effect |
|---|---|
| `-DAIVG_SAT_ENABLE_VOICE=ON` | build the WebRTC voice plane (needs libpeer + opus) |
| `-DAIVG_SAT_LIBPEER_ROOT=<dir>` | path to a built libpeer (`<dir>/build/src/libpeer.a`) |
| `-DAIVG_SAT_ENABLE_GRPC=ON` | **also** build the gRPC transport (Linux/POSIX only) |
| `-DAIVG_SAT_BUILD_TESTS=ON` | build the ctest suite |

```bash
# WebRTC + gRPC, with tests (inside rpi-builder, repo mounted at /workspace):
cmake -S sdks/cpp -B build \
  -DAIVG_SAT_ENABLE_VOICE=ON -DAIVG_SAT_LIBPEER_ROOT=/opt/libpeer \
  -DAIVG_SAT_ENABLE_GRPC=ON -DAIVG_SAT_BUILD_TESTS=ON
cmake --build build -j && (cd build && ctest)
```

A `-DAIVG_SAT_ENABLE_GRPC=OFF` build is behaviour-identical to the original
WebRTC-only SDK — gRPC is purely additive and opt-in.

## Hello satellite (the whole public API)

```cpp
#include <aivg/sat/satellite.hpp>
#include <variant>
using namespace aivg::sat;

SatelliteOptions o;
o.gateway_url      = "ws://192.168.1.5:8643";   // management plane (control WS)
o.device_id        = "kitchen";
o.device_name      = "Kitchen satellite";
o.device_type      = "linux";                   // informational only
o.firmware_version = "1.0.0";

// You own capture + playback. PCM16 mono at the transport's rate (WebRTC 48 kHz,
// gRPC 16 kHz). Fill `frames` samples; return how many (0 = no audio / muted).
o.audio_input = [](std::int16_t* buf, std::size_t frames) -> std::size_t {
  return my_capture(buf, frames);          // your mic
};
o.audio_output = [](const std::int16_t* buf, std::size_t frames) {
  my_playback(buf, frames);                // your speaker
};

// One handler for every event (a std::variant — match what you care about).
o.on_event = [](const SatEvent& ev) {
  if (auto* t = std::get_if<TranscriptDelta>(&ev))
    printf("transcript: %s%s\n", t->text.c_str(), t->is_final ? " (final)" : "");
  else if (auto* r = std::get_if<VoiceSessionResult>(&ev))
    printf("session ended: %s\n", r->reason.c_str());   // e.g. "dropped"
  else if (auto* e = std::get_if<SatError>(&ev))
    printf("error: %s\n", e->message.c_str());
};

Satellite sat(std::move(o));
sat.connect().get();           // open the control plane + register/adopt
sat.beginSession().get();      // open the voice plane (mic streams; reply plays)
// sat.mute(); sat.unmute();   // push-to-talk (the session stays up)
sat.endSession().get();
sat.disconnect().get();
```

`connect()`/`beginSession()`/`endSession()`/`disconnect()` return
`std::future<void>` (call `.get()` to await). Inspect with `sat.state()`,
`sat.isAdopted()`, `sat.isMicLive()`.

## Choosing a transport

By default the SDK **negotiates** with the gateway: it advertises every
transport this build supports and uses the one the gateway picks (preferring
gRPC for native). Override if you need to:

```cpp
o.transport = TransportPref::Auto;     // default — negotiate
// o.transport = TransportPref::Grpc;  // pin gRPC (SatError if not compiled in)
// o.transport = TransportPref::Webrtc;
o.grpc_port = 8645;                    // gateway gRPC audio port
o.grpc_tls  = false;                   // insecure (trusted LAN) | true => SSL/mTLS
```

A WebRTC-only build advertises only `["webrtc"]`, so a gateway never steers it
to gRPC — existing integrations need no change. See
[`docs/api.md` §6](docs/api.md) for the transport details and the shared
`proto/aivg/satellite/v1/` contract.

## Events you can handle

`SatEvent` is a `std::variant`; use `std::get_if<T>(&ev)`. The common ones:

| Event | When |
|---|---|
| `AdoptionEvent{previous, current}` | adoption state changed (`pending`→`adopted`) |
| `TranscriptDelta{text, is_final}` | streaming recognized text |
| `RemoteStreamEvent{kind}` | `speaking_started` / `speaking_ended` / `vad_detected` |
| `GatewayStatePayload{state, session_id}` | gateway turn state (e.g. `thinking`) |
| `VoiceSession{session_id}` | a voice session started |
| `VoiceSessionResult{session_id, reason}` | session ended (`ended`, `dropped`, `gateway_reconnected`) |
| `CommandEvent{...}` / `OtaManifest` / `OtaProgress` | operator commands / OTA |
| `SatError{code, message}` | recoverable or fatal error |

Full list + fields: [`include/aivg/sat/events.hpp`](include/aivg/sat/events.hpp).

## Notes

- **Thin satellite**: never put STT/TTS/agent logic in the client — that's the
  gateway's job. The SDK only moves audio.
- **gRPC tier**: Linux/POSIX only. The ESP32-S3 tier stays on WebRTC (the gRPC
  stack doesn't fit the device — see
  [`specs/022-cpp-sdk-grpc-transport/esp32-grpc-spike.md`](../../specs/022-cpp-sdk-grpc-transport/esp32-grpc-spike.md)).
- Production device firmware/rigs live in the companion repo
  [`cloudomate/aivg-devices`](https://github.com/cloudomate/aivg-devices).
- Versioning + changes: [`CHANGELOG.md`](CHANGELOG.md). License: MIT.
