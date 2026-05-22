// libaivg-sat — local FSM transitions (feature 020, internal).
//
// Pure logic, no external dependencies. The local FSM is
// idle|listening|speaking|error (data-model.md). "thinking" is a
// gateway_state value, not a local state.
#ifndef AIVG_SAT_STATE_MACHINE_HPP
#define AIVG_SAT_STATE_MACHINE_HPP

#include "aivg/sat/state.hpp"

namespace aivg::sat::detail {

enum class FsmEvent {
  BeginSessionResolved,  // offer answered → listening
  FirstRemoteAudio,      // reply audio began → speaking
  ReplyComplete,         // reply finished / endSession → idle
  FatalError,            // any fatal → error
  Reset,                 // recovery → idle
};

// Pure transition function. Unhandled (state, event) pairs return the
// current state unchanged (no-op), e.g. mute/unmute during listening.
SatelliteState transition(SatelliteState current, FsmEvent event) noexcept;

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_STATE_MACHINE_HPP
