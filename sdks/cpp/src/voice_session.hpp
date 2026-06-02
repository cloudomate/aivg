// libaivg-sat — voice session (feature 020, T018; feature 022 transport seam).
//
// Long-lived voice session with mute/unmute PTT (FR-010): the voice link is
// NOT torn down per PTT cycle. Feature 022 makes it transport-agnostic — it
// drives an abstract Transport (WebRTC or gRPC) and decodes downstream audio
// per the codec the transport reports. Signaling + upstream encode now live
// inside each Transport, not here.
#ifndef AIVG_SAT_VOICE_SESSION_HPP
#define AIVG_SAT_VOICE_SESSION_HPP

#include <atomic>
#include <memory>
#include <string>
#include <thread>

#include "aivg/sat/audio.hpp"
#include "transport/opus_bridge.hpp"
#include "transport/transport.hpp"

namespace aivg::sat::detail {

class VoiceSession {
 public:
  VoiceSession(std::unique_ptr<Transport> transport, AudioInputCallback in,
               AudioOutputCallback out);
  ~VoiceSession();

  VoiceSession(const VoiceSession&) = delete;
  VoiceSession& operator=(const VoiceSession&) = delete;

  // Establish the voice link via the transport, then pump the mic. Returns
  // true if the link came up (media starts when the transport is ready()).
  bool begin();
  void end();
  void mute() { mic_live_.store(false); }
  void unmute() { mic_live_.store(true); }

  bool is_mic_live() const noexcept { return mic_live_.load(); }
  bool is_active() const noexcept { return active_.load(); }
  const std::string& session_id() const noexcept { return session_id_; }

 private:
  void mic_pump();
  void on_remote_audio(const std::uint8_t* data, std::size_t size, Codec codec);

  std::unique_ptr<Transport> transport_;
  AudioInputCallback in_;
  AudioOutputCallback out_;
  OpusBridge opus_;  // DECODE (downstream Opus); upstream encode is in-transport
  std::thread mic_thread_;
  std::atomic<bool> active_{false};
  std::atomic<bool> mic_live_{false};
  std::string session_id_;
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_VOICE_SESSION_HPP
