# Contract: libaivg-sat Public C++ API

**Feature**: 020-cpp-webrtc-sdk | **Date**: 2026-05-22

The SDK's public surface, expressed in C++17. Parity target:
`@aivg/sat-sdk` (TypeScript). This is the contract consumers compile
against; it MUST be identical across both device tiers (FR-004a).

## Header surface (`include/aivg/sat/`)

```cpp
namespace aivg::sat {

enum class SatelliteState { Idle, Listening, Speaking, Error };

struct ReconnectPolicy {
  uint32_t base_delay_ms = 500;
  uint32_t max_delay_ms  = 30000;
  bool     jitter        = true;
};

using AudioInputCallback  = std::function<size_t(int16_t* buf, size_t frames)>;
using AudioOutputCallback = std::function<void(const int16_t* buf, size_t frames)>;
using EventHandler        = std::function<void(const SatEvent&)>;

struct SatelliteOptions {
  std::string gateway_url;
  std::optional<std::string> signaling_url;
  std::string device_id;
  std::string device_name;
  std::string device_type;
  std::string firmware_version;
  ReconnectPolicy reconnect{};
  AudioInputCallback  audio_input;
  AudioOutputCallback audio_output;
  EventHandler        on_event;
  // timeouts: ice_gather_ms, media_first_audio_ms, signaling_ms
};

class Satellite {
 public:
  explicit Satellite(SatelliteOptions opts);
  ~Satellite();

  // Lifecycle (mirror @aivg/sat-sdk)
  std::future<void> connect();
  std::future<void> disconnect();
  std::future<void> beginSession();
  std::future<void> endSession();
  void mute();
  void unmute();

  // Inspectors
  SatelliteState state() const;
  bool isAdopted() const;
  bool isMicLive() const;
};

}  // namespace aivg::sat
```

> The async return type (`std::future` vs a callback/coroutine) is an
> implementation detail to settle in tasks; the *method names, argument
> counts, and semantics* are the frozen contract.

## Method parity table (vs `@aivg/sat-sdk`)

| C++ | TypeScript | Semantics |
|-----|------------|-----------|
| `connect()` | `connect()` | Open control-plane WS, register, begin heartbeat. |
| `disconnect()` | `disconnect()` | Tear down session (if any) + control WS. |
| `beginSession()` | `beginSession()` | Offer WebRTC, await answer, open voice plane. |
| `endSession()` | `endSession()` | Close the PeerConnection; control WS stays up. |
| `mute()` / `unmute()` | `mute()` / `unmute()` | PTT mic gating WITHOUT tearing down the PeerConnection (FR-010). |
| `state` / `isAdopted` / `isMicLive` | same | Inspectors. |

## Event parity (17 variants, names verbatim)

`state`, `gateway_state`, `adoption`, `config_changed`, `command`,
`log`, `ota_manifest`, `ota_progress`, `transcript`, `tool_call`,
`skill`, `barge_in`, `remote_stream`, `session_started`,
`session_ended`, `error`, `transient_error`.

Delivered through the single `EventHandler` as a `SatEvent` discriminated
union (`std::variant` or a tagged struct). Each payload's fields match
the TS interface in `sdks/typescript/src/events.ts` exactly.

## Error-code parity (stable strings)

Terminal (`error`): `no_webrtc_impl`, `no_microphone_api`,
`permission_denied`, `ice_failed`, `ice_gathering_timeout`,
`ws_disconnected`, `ws_max_retries_exceeded`, `signaling_failed`,
`mixed_content`, `not_adopted`, `protocol_mismatch`, `duplicate_device`.
Transient (`transient_error`): `ws_disconnected`, `signaling_retry`,
`ice_retry`, `buffer_overflow`.

The C++ enum defines the full set for parity; a native client only emits
the codes reachable off-browser (e.g. `no_microphone_api`,
`mixed_content`, `permission_denied` are browser-only and never emitted).

## Acceptance (maps to spec)

- SC-004: this table + the README side-by-side table prove 1:1 surface parity.
- FR-004a: this header compiles unchanged under both tiers; only build flags differ.
