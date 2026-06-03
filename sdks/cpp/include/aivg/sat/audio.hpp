// libaivg-sat — audio I/O boundary (feature 020).
//
// The SDK links NO system audio backend (spec FR-005/006). The consumer
// owns the microphone and speaker drivers and supplies these callbacks.
// The callback boundary is always raw PCM16 mono at 48 kHz, regardless of
// the negotiated transport; the SDK performs any codec encode/decode and
// rate conversion internally (transport codec, not STT/TTS — Constitution
// Principle I). WebRTC/Opus is natively 48 kHz; the gRPC transport resamples
// to/from its 16 kHz wire so consumers wire one capture/playback rate.
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
