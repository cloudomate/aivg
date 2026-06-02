// libaivg-sat — WebRTC voice-plane transport (feature 022, internal).
//
// Implements the abstract Transport seam by composing the raw LibpeerTransport
// (untouched libpeer wrapper) with the Opus encoder and the offer/answer
// signaling that previously lived in VoiceSession. Behaviour is identical to
// feature 020's WebRTC path — the same calls in the same order, relocated
// behind the seam so VoiceSession is transport-agnostic.
#ifndef AIVG_SAT_TRANSPORT_WEBRTC_TRANSPORT_HPP
#define AIVG_SAT_TRANSPORT_WEBRTC_TRANSPORT_HPP

#include <cstddef>
#include <string>

#include "transport/libpeer_transport.hpp"
#include "transport/opus_bridge.hpp"
#include "transport/transport.hpp"

namespace aivg::sat::detail {

class WebrtcTransport : public Transport {
 public:
  WebrtcTransport(std::string signaling_base, std::string device_id);
  ~WebrtcTransport() override = default;

  bool begin() override;
  const std::string& session_id() const noexcept override { return session_id_; }
  // 48 kHz * 20 ms = 960 samples per Opus frame (the WebRTC plane rate).
  std::size_t mic_frame_samples() const noexcept override { return kOpusFrameSamples; }
  void send_mic(const std::int16_t* pcm16, std::size_t samples) override;
  bool ready() const noexcept override { return libpeer_.is_completed(); }
  void stop() override { libpeer_.stop(); }
  void set_on_remote_audio(OnRemoteAudio cb) override { on_audio_ = std::move(cb); }
  void set_on_event(OnEvent cb) override { on_event_ = std::move(cb); }

 private:
  std::string signaling_base_;
  std::string device_id_;
  std::string session_id_;
  LibpeerTransport libpeer_;
  OpusBridge opus_;  // ENCODE (upstream); decode happens in VoiceSession
  OnRemoteAudio on_audio_;
  OnEvent on_event_;
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_TRANSPORT_WEBRTC_TRANSPORT_HPP
