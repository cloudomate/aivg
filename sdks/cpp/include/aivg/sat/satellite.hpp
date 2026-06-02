// libaivg-sat — primary public surface (feature 020).
//
// C++17 satellite-client SDK. Public API mirrors @aivg/sat-sdk; WebRTC is
// the only transport. The same header compiles unchanged on both tiers
// (POSIX / ESP32-S3) — tier differences are build-time only (spec FR-004a).
// See contracts/public-api.md for the full parity table.
#ifndef AIVG_SAT_SATELLITE_HPP
#define AIVG_SAT_SATELLITE_HPP

#include <cstdint>
#include <future>
#include <memory>
#include <optional>
#include <string>

#include "aivg/sat/audio.hpp"
#include "aivg/sat/errors.hpp"
#include "aivg/sat/events.hpp"
#include "aivg/sat/state.hpp"
#include "aivg/sat/wire.hpp"

namespace aivg::sat {

struct ReconnectPolicy {
  std::uint32_t base_delay_ms = 500;
  std::uint32_t max_delay_ms = 30000;
  bool jitter = true;
};

struct Timeouts {
  std::uint32_t ice_gather_ms = 5000;
  std::uint32_t media_first_audio_ms = 10000;
  std::uint32_t signaling_ms = 8000;
};

// Feature 022 — voice-plane transport selection. `Auto` advertises every
// transport this build supports and uses the one the gateway negotiates
// (preferring gRPC for native). `Webrtc`/`Grpc` pin a transport; an
// unsatisfiable pin (not compiled into this build) surfaces a SatError.
// Default `Auto` preserves feature-020 behaviour (WebRTC-only builds → WebRTC).
enum class TransportPref { Auto, Webrtc, Grpc };

struct SatelliteOptions {
  std::string gateway_url;                  // management plane (control WS + REST)
  std::optional<std::string> signaling_url;  // voice plane; defaults from gateway_url
  std::string device_id;
  std::string device_name;
  std::string device_type;
  std::string firmware_version;
  ReconnectPolicy reconnect{};
  Timeouts timeouts{};
  AudioInputCallback audio_input;
  AudioOutputCallback audio_output;
  EventHandler on_event;
  // Feature 022 — additive transport options (defaults preserve WebRTC).
  TransportPref transport = TransportPref::Auto;
  std::uint16_t grpc_port = 8645;  // gRPC audio-plane port on the gateway host
  bool grpc_tls = false;           // insecure (trusted LAN) vs SSL/mTLS (fleet)
};

// Owns one always-on control-plane WS and at most one active WebRTC voice
// session. Method names/semantics are the frozen contract; the async
// return type (std::future here) is an implementation detail.
class Satellite {
 public:
  explicit Satellite(SatelliteOptions options);
  ~Satellite();

  Satellite(const Satellite&) = delete;
  Satellite& operator=(const Satellite&) = delete;
  Satellite(Satellite&&) noexcept;
  Satellite& operator=(Satellite&&) noexcept;

  // Lifecycle (mirror @aivg/sat-sdk).
  std::future<void> connect();
  std::future<void> disconnect();
  std::future<void> beginSession();
  std::future<void> endSession();
  void mute();
  void unmute();

  // Inspectors.
  SatelliteState state() const noexcept;
  bool isAdopted() const noexcept;
  bool isMicLive() const noexcept;

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace aivg::sat

#endif  // AIVG_SAT_SATELLITE_HPP
