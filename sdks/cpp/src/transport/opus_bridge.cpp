// libaivg-sat — Opus codec bridge (feature 020, T017).
#include "transport/opus_bridge.hpp"

#include <opus/opus.h>

namespace aivg::sat::detail {

OpusBridge::OpusBridge() {
  int err = OPUS_OK;
  enc_ = opus_encoder_create(kOpusSampleRate, kOpusChannels, OPUS_APPLICATION_VOIP, &err);
  if (err != OPUS_OK) enc_ = nullptr;
  dec_ = opus_decoder_create(kOpusSampleRate, kOpusChannels, &err);
  if (err != OPUS_OK) dec_ = nullptr;
}

OpusBridge::~OpusBridge() {
  if (enc_) opus_encoder_destroy(enc_);
  if (dec_) opus_decoder_destroy(dec_);
}

std::vector<std::uint8_t> OpusBridge::encode(const std::int16_t* pcm, std::size_t samples) {
  std::vector<std::uint8_t> out;
  if (!enc_ || pcm == nullptr || samples == 0) return out;
  out.resize(4000);  // max Opus packet for one frame
  opus_int32 n = opus_encode(enc_, pcm, static_cast<int>(samples), out.data(),
                             static_cast<opus_int32>(out.size()));
  if (n < 0) {
    out.clear();
    return out;
  }
  out.resize(static_cast<std::size_t>(n));
  return out;
}

std::size_t OpusBridge::decode(const std::uint8_t* payload, std::size_t bytes,
                               std::vector<std::int16_t>& out) {
  if (!dec_ || payload == nullptr || bytes == 0) return 0;
  std::int16_t frame[kOpusFrameSamples * 2];  // headroom for up to 40 ms
  int n = opus_decode(dec_, payload, static_cast<opus_int32>(bytes), frame,
                      kOpusFrameSamples * 2, 0);
  if (n <= 0) return 0;
  out.insert(out.end(), frame, frame + n);
  return static_cast<std::size_t>(n);
}

}  // namespace aivg::sat::detail
