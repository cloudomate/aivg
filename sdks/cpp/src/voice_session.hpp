// libaivg-sat — voice session (feature 020, T018, internal).
//
// Long-lived WebRTC voice session with mute/unmute PTT (FR-010): the
// PeerConnection is NOT torn down per PTT cycle. Wires the audio callbacks
// through the Opus bridge to the libpeer transport, and runs signaling.
#ifndef AIVG_SAT_VOICE_SESSION_HPP
#define AIVG_SAT_VOICE_SESSION_HPP

#include <atomic>
#include <memory>
#include <string>
#include <thread>

#include "aivg/sat/audio.hpp"
#include "transport/libpeer_transport.hpp"
#include "transport/opus_bridge.hpp"

namespace aivg::sat::detail {

class VoiceSession {
 public:
  VoiceSession(std::string signaling_base, std::string device_id, AudioInputCallback in,
               AudioOutputCallback out);
  ~VoiceSession();

  VoiceSession(const VoiceSession&) = delete;
  VoiceSession& operator=(const VoiceSession&) = delete;

  // Offer -> POST /webrtc/offer -> answer -> pump. Returns true if the
  // signaling round-trip succeeded (media starts when ICE completes).
  bool begin();
  void end();
  void mute() { mic_live_.store(false); }
  void unmute() { mic_live_.store(true); }

  bool is_mic_live() const noexcept { return mic_live_.load(); }
  bool is_active() const noexcept { return active_.load(); }
  const std::string& session_id() const noexcept { return session_id_; }

 private:
  void mic_pump();
  void on_remote_opus(const std::uint8_t* data, std::size_t size);

  std::string signaling_base_;
  std::string device_id_;
  AudioInputCallback in_;
  AudioOutputCallback out_;

  LibpeerTransport transport_;
  OpusBridge opus_;
  std::thread mic_thread_;
  std::atomic<bool> active_{false};
  std::atomic<bool> mic_live_{false};
  std::string session_id_;
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_VOICE_SESSION_HPP
