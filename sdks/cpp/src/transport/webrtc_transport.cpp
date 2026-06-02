// libaivg-sat — WebRTC voice-plane transport (feature 022).
#include "transport/webrtc_transport.hpp"

#include <utility>

#include "signaling.hpp"

namespace aivg::sat::detail {

WebrtcTransport::WebrtcTransport(std::string signaling_base, std::string device_id)
    : signaling_base_(std::move(signaling_base)), device_id_(std::move(device_id)) {
  // Remote Opus from libpeer -> surface as codec=Opus (VoiceSession decodes).
  libpeer_.set_on_remote_opus([this](const std::uint8_t* d, std::size_t n) {
    if (on_audio_) on_audio_(d, n, Codec::Opus);
  });
  // Peer failure -> a transport drop event (FR-013).
  libpeer_.set_on_failed([this] {
    if (on_event_) {
      TransportEvent te{};
      te.kind = TransportEvent::Kind::StreamDropped;
      te.reason = "webrtc peer connection failed";
      on_event_(te);
    }
  });
}

bool WebrtcTransport::begin() {
  if (!opus_.ok()) return false;
  // Identical to feature 020's VoiceSession::begin(): offer -> POST -> answer.
  std::string offer = libpeer_.create_offer();
  if (offer.empty()) return false;
  OfferResult ans = post_offer(signaling_base_, device_id_, offer);
  if (!ans.ok) return false;
  session_id_ = ans.session_id;
  return libpeer_.set_answer_and_run(ans.sdp);
}

void WebrtcTransport::send_mic(const std::int16_t* pcm16, std::size_t samples) {
  // Opus-encode on the device (the WebRTC plane), then hand to libpeer.
  // peer_connection_send_audio self-drops until DTLS-SRTP completes.
  auto payload = opus_.encode(pcm16, samples);
  if (!payload.empty()) libpeer_.send_opus(payload.data(), payload.size());
}

}  // namespace aivg::sat::detail
