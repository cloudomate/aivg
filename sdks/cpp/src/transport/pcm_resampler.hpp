// libaivg-sat — minimal stateful linear PCM resampler (feature 022, internal).
//
// The gRPC voice plane carries raw 16 kHz PCM on the wire, but the SDK's
// audio callback boundary is 48 kHz mono — the SAME rate the WebRTC/Opus
// plane uses (OpusBridge::kOpusSampleRate). This converts between the two so
// the consumer wires ONE capture/playback rate (48 kHz) regardless of which
// transport is negotiated. Stateful (carries the fractional phase + the
// previous input sample) so 20 ms frame boundaries don't click. Linear
// interpolation matches the gateway's audioop.ratecv quality and adds no
// third-party dependency.
#ifndef AIVG_SAT_TRANSPORT_PCM_RESAMPLER_HPP
#define AIVG_SAT_TRANSPORT_PCM_RESAMPLER_HPP

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace aivg::sat::detail {

// Single-channel s16 linear resampler. Not thread-safe: use one instance per
// direction (the mic pump and reader threads each own their own).
class LinearResampler {
 public:
  LinearResampler(int in_rate, int out_rate)
      : step_(static_cast<double>(in_rate) / static_cast<double>(out_rate)) {}

  // Resample `n` mono s16 input samples, APPENDING the output to `out`.
  // Carries phase across calls, so feeding successive 20 ms frames is
  // seamless. Output length is ~n*out_rate/in_rate and may vary by ±1 per
  // call as the fractional phase carries — the gateway reframes, so a
  // variable chunk length is fine.
  void process(const std::int16_t* in, std::size_t n, std::vector<std::int16_t>& out) {
    for (std::size_t i = 0; i < n; ++i) {
      const double cur = static_cast<double>(in[i]);
      // Emit every output sample whose position falls in [prev_, cur).
      while (pos_ < 1.0) {
        out.push_back(clamp16(prev_ + ((cur - prev_) * pos_)));
        pos_ += step_;
      }
      pos_ -= 1.0;
      prev_ = cur;
    }
  }

 private:
  static std::int16_t clamp16(double s) {
    constexpr long kMin = std::numeric_limits<std::int16_t>::min();
    constexpr long kMax = std::numeric_limits<std::int16_t>::max();
    return static_cast<std::int16_t>(std::clamp(std::lround(s), kMin, kMax));
  }

  double step_;        // input samples advanced per output sample
  double pos_ = 0.0;   // fractional phase within [prev_, cur)
  double prev_ = 0.0;  // last input sample (interpolation anchor)
};

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_TRANSPORT_PCM_RESAMPLER_HPP
