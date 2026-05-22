// libaivg-sat — Opus codec bridge (feature 020, T017, internal).
//
// Bridges the SDK's raw-PCM16 callback boundary to libpeer's Opus RTP
// transport: encode mic PCM (48 kHz mono) -> Opus payload for
// peer_connection_send_audio; decode the onaudiotrack Opus payload ->
// PCM for the consumer's AudioOutputCallback. This is the ONLY place the
// SDK touches a codec; it is transport compression, not STT/TTS
// (Constitution Principle I). Uses libopus.
#ifndef AIVG_SAT_TRANSPORT_OPUS_BRIDGE_HPP
#define AIVG_SAT_TRANSPORT_OPUS_BRIDGE_HPP

#include <cstddef>
#include <cstdint>
#include <vector>

struct OpusEncoder;
struct OpusDecoder;

namespace aivg::sat::detail {

// 48 kHz mono — matches the gateway's opus/48000 voice plane and the
// internal pipeline sample rate.
constexpr int kOpusSampleRate = 48000;
constexpr int kOpusChannels = 1;
// 20 ms frame at 48 kHz = 960 samples.
constexpr int kOpusFrameSamples = 960;

class OpusBridge {
 public:
  OpusBridge();
  ~OpusBridge();

  OpusBridge(const OpusBridge&) = delete;
  OpusBridge& operator=(const OpusBridge&) = delete;

  bool ok() const noexcept { return enc_ != nullptr && dec_ != nullptr; }

  // Encode exactly kOpusFrameSamples PCM16 mono samples -> Opus payload.
  // Returns the encoded byte vector (empty on error).
  std::vector<std::uint8_t> encode(const std::int16_t* pcm, std::size_t samples);

  // Decode an Opus payload -> PCM16 mono samples appended to `out`.
  // Returns number of samples decoded (0 on error).
  std::size_t decode(const std::uint8_t* payload, std::size_t bytes, std::vector<std::int16_t>& out);

 private:
  OpusEncoder* enc_ = nullptr;
  OpusDecoder* dec_ = nullptr;
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_TRANSPORT_OPUS_BRIDGE_HPP
