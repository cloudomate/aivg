// libaivg-sat — voice session (feature 020, T018).
#include "voice_session.hpp"

#include <chrono>
#include <utility>
#include <vector>

#include "signaling.hpp"

namespace aivg::sat::detail {

VoiceSession::VoiceSession(std::string signaling_base, std::string device_id, AudioInputCallback in,
                           AudioOutputCallback out)
    : signaling_base_(std::move(signaling_base)),
      device_id_(std::move(device_id)),
      in_(std::move(in)),
      out_(std::move(out)) {
  transport_.set_on_remote_opus(
      [this](const std::uint8_t* d, std::size_t n) { on_remote_opus(d, n); });
  transport_.set_on_connected([this] {
    if (!active_.exchange(true)) {
      mic_thread_ = std::thread([this] { mic_pump(); });
    }
  });
}

VoiceSession::~VoiceSession() { end(); }

bool VoiceSession::begin() {
  if (!opus_.ok()) return false;
  std::string offer = transport_.create_offer();
  if (offer.empty()) return false;
  OfferResult ans = post_offer(signaling_base_, device_id_, offer);
  if (!ans.ok) return false;
  session_id_ = ans.session_id;
  return transport_.set_answer_and_run(ans.sdp);
}

void VoiceSession::end() {
  mic_live_.store(false);
  bool was_active = active_.exchange(false);
  if (was_active && mic_thread_.joinable()) mic_thread_.join();
  transport_.stop();
}

void VoiceSession::mic_pump() {
  std::vector<std::int16_t> frame(kOpusFrameSamples);
  while (active_.load()) {
    if (mic_live_.load() && in_) {
      std::size_t got = in_(frame.data(), kOpusFrameSamples);
      if (got == kOpusFrameSamples) {
        auto payload = opus_.encode(frame.data(), kOpusFrameSamples);
        if (!payload.empty()) transport_.send_opus(payload.data(), payload.size());
      }
    }
    // 20 ms cadence (one Opus frame at 48 kHz).
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
}

void VoiceSession::on_remote_opus(const std::uint8_t* data, std::size_t size) {
  if (!out_) return;
  std::vector<std::int16_t> pcm;
  std::size_t n = opus_.decode(data, size, pcm);
  if (n > 0) out_(pcm.data(), n);
}

}  // namespace aivg::sat::detail
