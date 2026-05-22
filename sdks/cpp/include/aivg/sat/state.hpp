// libaivg-sat — local satellite state (feature 020).
//
// The LOCAL FSM has exactly four states. Note that "thinking" is NOT a
// local state — it arrives from the gateway as a `gateway_state` event
// value (see events.hpp / data-model.md).
#ifndef AIVG_SAT_STATE_HPP
#define AIVG_SAT_STATE_HPP

namespace aivg::sat {

enum class SatelliteState {
  Idle,
  Listening,
  Speaking,
  Error,
};

// Stable wire string for a local state (mirrors @aivg/sat-sdk).
const char* to_wire(SatelliteState state) noexcept;

}  // namespace aivg::sat

#endif  // AIVG_SAT_STATE_HPP
