// libaivg-sat — voice session (feature 020, T018; feature 022 transport seam).
#include "voice_session.hpp"

#include <chrono>
#include <utility>
#include <vector>

namespace aivg::sat::detail {

VoiceSession::VoiceSession(std::unique_ptr<Transport> transport, AudioInputCallback in,
                           AudioOutputCallback out)
    : transport_(std::move(transport)), in_(std::move(in)), out_(std::move(out)) {
  transport_->set_on_remote_audio(
      [this](const std::uint8_t* d, std::size_t n, Codec c) { on_remote_audio(d, n, c); });
}

VoiceSession::~VoiceSession() { end(); }

bool VoiceSession::begin() {
  if (!opus_.ok()) return false;  // needed for downstream Opus decode
  if (!transport_ || !transport_->begin()) return false;
  session_id_ = transport_->session_id();
  // Start the mic pump now; it gates internally on transport_->ready() so a
  // frame is only sent once the link can carry it (preserves the feature-020
  // "start immediately, self-drop until ready" behaviour).
  if (!active_.exchange(true)) {
    mic_thread_ = std::thread([this] { mic_pump(); });
  }
  return true;
}

void VoiceSession::end() {
  mic_live_.store(false);
  bool was_active = active_.exchange(false);
  if (was_active && mic_thread_.joinable()) mic_thread_.join();
  if (transport_) transport_->stop();
}

void VoiceSession::mic_pump() {
  const std::size_t n = transport_->mic_frame_samples();
  std::vector<std::int16_t> frame(n);
  while (active_.load()) {
    const bool ready = transport_->ready();
    if (mic_live_.load() && in_ && ready) {
      std::size_t got = in_(frame.data(), n);
      if (got == n) transport_->send_mic(frame.data(), n);
    }
    // 20 ms cadence (one frame).
    std::this_thread::sleep_for(std::chrono::milliseconds(20));
  }
}

void VoiceSession::on_remote_audio(const std::uint8_t* data, std::size_t size, Codec codec) {
  if (!out_) return;
  if (codec == Codec::Opus) {
    std::vector<std::int16_t> pcm;
    std::size_t n = opus_.decode(data, size, pcm);
    if (n > 0) out_(pcm.data(), n);
  } else if (codec == Codec::PcmS16le16k) {
    // Raw PCM16 — hand straight to playback (no decode).
    out_(reinterpret_cast<const std::int16_t*>(data), size / sizeof(std::int16_t));
  }
}

}  // namespace aivg::sat::detail
