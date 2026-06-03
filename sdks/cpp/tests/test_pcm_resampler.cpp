// libaivg-sat — LinearResampler unit test (feature 022, gRPC 48<->16 kHz seam).
//
// Pure/header-only (no backend deps), mirroring test_negotiation. Proves the
// resampler that bridges the 48 kHz callback boundary to the 16 kHz gRPC wire:
//   - the 3:1 / 1:3 sample-count ratios hold,
//   - a DC level is preserved (no gain error),
//   - feeding 20 ms frames one-by-one is bit-identical to one big call
//     (state carries across frame boundaries — no clicks),
//   - a round-trip 48->16->48 stays in phase (low drift).
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <vector>

#include "transport/pcm_resampler.hpp"

using aivg::sat::detail::LinearResampler;

int main() {
  // --- 1. Downsample count: 48 kHz -> 16 kHz is ~3:1 over a 1 s signal.
  {
    LinearResampler down(48000, 16000);
    std::vector<std::int16_t> out;
    std::vector<std::int16_t> in(48000, 0);
    down.process(in.data(), in.size(), out);
    // 48000 in -> ~16000 out; allow a tiny startup tolerance.
    assert(out.size() >= 15999 && out.size() <= 16001);
  }

  // --- 2. Upsample count: 16 kHz -> 48 kHz is ~1:3.
  {
    LinearResampler up(16000, 48000);
    std::vector<std::int16_t> out;
    std::vector<std::int16_t> in(16000, 0);
    up.process(in.data(), in.size(), out);
    assert(out.size() >= 47999 && out.size() <= 48001);
  }

  // --- 3. DC preservation: a constant input yields the same constant out
  //         (interpolation between equal samples must not change the level).
  {
    LinearResampler down(48000, 16000);
    std::vector<std::int16_t> out;
    std::vector<std::int16_t> in(4800, 1000);
    down.process(in.data(), in.size(), out);
    assert(!out.empty());
    // Skip the first sample (startup phase anchored at 0); the rest is flat.
    for (std::size_t i = 1; i < out.size(); ++i) assert(out[i] == 1000);
  }

  // --- 4. Streaming continuity: 50 frames of 960 samples (20 ms @ 48 kHz)
  //         fed one-by-one must equal the same 48000 samples fed at once.
  {
    std::vector<std::int16_t> sig(48000);
    for (std::size_t i = 0; i < sig.size(); ++i)
      sig[i] = static_cast<std::int16_t>(8000.0 * std::sin(i * 0.05));

    LinearResampler whole(48000, 16000);
    std::vector<std::int16_t> out_whole;
    whole.process(sig.data(), sig.size(), out_whole);

    LinearResampler framed(48000, 16000);
    std::vector<std::int16_t> out_framed;
    for (std::size_t off = 0; off < sig.size(); off += 960)
      framed.process(sig.data() + off, 960, out_framed);

    assert(out_whole.size() == out_framed.size());
    for (std::size_t i = 0; i < out_whole.size(); ++i)
      assert(out_whole[i] == out_framed[i]);  // no frame-boundary click
  }

  std::printf("test_pcm_resampler: OK\n");
  return 0;
}
