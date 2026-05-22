// libaivg-sat — reconnect backoff (feature 020).
#include "reconnect.hpp"

#include <algorithm>

namespace aivg::sat::detail {

std::uint32_t next_backoff_ms(const ReconnectPolicy& policy, std::uint32_t attempt,
                              double rng_unit) noexcept {
  // Capped exponential: base * 2^attempt, clamped to max. Guard the shift
  // against overflow for large attempt counts.
  std::uint64_t exp = policy.base_delay_ms;
  for (std::uint32_t i = 0; i < attempt && exp < policy.max_delay_ms; ++i) {
    exp <<= 1;
  }
  std::uint64_t capped = std::min<std::uint64_t>(exp, policy.max_delay_ms);

  if (!policy.jitter) {
    return static_cast<std::uint32_t>(capped);
  }
  // Full jitter: uniform in [0, capped]. Clamp rng_unit defensively.
  double u = rng_unit < 0.0 ? 0.0 : (rng_unit > 1.0 ? 1.0 : rng_unit);
  return static_cast<std::uint32_t>(static_cast<double>(capped) * u);
}

}  // namespace aivg::sat::detail
