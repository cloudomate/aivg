// libaivg-sat — audio I/O boundary (feature 020).
//
// The SDK links NO system audio backend (spec FR-005/006). The consumer
// owns the microphone and speaker drivers and supplies these callbacks.
// The callback boundary is always raw PCM16 mono at the negotiated rate;
// the SDK performs Opus encode/decode internally (transport codec, not
// STT/TTS — Constitution Principle I).
#ifndef AIVG_SAT_AUDIO_HPP
#define AIVG_SAT_AUDIO_HPP

#include <cstddef>
#include <cstdint>
#include <functional>

namespace aivg::sat {

// Fills `buf` with up to `frames` PCM16 mono samples; returns the number
// of samples produced. Return 0 to signal "no audio right now" (muted)
// or end-of-stream.
using AudioInputCallback =
    std::function<std::size_t(std::int16_t* buf, std::size_t frames)>;

// Consumes exactly `frames` PCM16 mono reply samples for playback.
using AudioOutputCallback =
    std::function<void(const std::int16_t* buf, std::size_t frames)>;

}  // namespace aivg::sat

#endif  // AIVG_SAT_AUDIO_HPP
