// libaivg-sat — management-plane reconnect backoff (feature 020, internal).
//
// Exponential backoff + jitter, capped (spec FR-015). Pure + injectable
// RNG so the policy is deterministically testable. The control plane
// retries automatically; the consumer only sees gateway_state transitions.
#ifndef AIVG_SAT_RECONNECT_HPP
#define AIVG_SAT_RECONNECT_HPP

#include <cstdint>

#include "aivg/sat/satellite.hpp"

namespace aivg::sat::detail {

// Returns the delay (ms) before retry attempt `attempt` (0-based).
// `rng_unit` is a value in [0,1) supplied by the caller (injected for
// tests; production passes a uniform random draw). With jitter enabled we
// use "full jitter": delay = random in [0, capped_exponential].
std::uint32_t next_backoff_ms(const ReconnectPolicy& policy, std::uint32_t attempt,
                              double rng_unit) noexcept;

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_RECONNECT_HPP
