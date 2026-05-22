// libaivg-sat — compile/link check for the dependency-free core (feature 020).
//
// Verifies the public headers compile under C++17 and that the FSM +
// wire-string tables link. This is NOT a functional test (no gateway, no
// libpeer); it guards the API surface and pure logic (tasks T005-T011).
#include <cassert>
#include <cstdio>

#include "aivg/sat/satellite.hpp"
#include "state_machine.hpp"

namespace sat = aivg::sat;

int main() {
  using sat::SatelliteState;
  using sat::detail::FsmEvent;
  using sat::detail::transition;

  // FSM happy path: idle → listening → speaking → idle.
  SatelliteState s = SatelliteState::Idle;
  s = transition(s, FsmEvent::BeginSessionResolved);
  assert(s == SatelliteState::Listening);
  s = transition(s, FsmEvent::FirstRemoteAudio);
  assert(s == SatelliteState::Speaking);
  s = transition(s, FsmEvent::ReplyComplete);
  assert(s == SatelliteState::Idle);

  // Fatal → error → reset → idle.
  s = transition(s, FsmEvent::FatalError);
  assert(s == SatelliteState::Error);
  s = transition(s, FsmEvent::Reset);
  assert(s == SatelliteState::Idle);

  // No-op transition (FirstRemoteAudio from idle stays idle).
  assert(transition(SatelliteState::Idle, FsmEvent::FirstRemoteAudio) ==
         SatelliteState::Idle);

  // Wire-string tables.
  assert(std::string(sat::to_wire(SatelliteState::Listening)) == "listening");
  assert(std::string(sat::to_wire(sat::SatErrorCode::IceFailed)) == "ice_failed");
  assert(std::string(sat::to_wire(sat::SatErrorCode::BufferOverflow)) ==
         "buffer_overflow");

  // Options struct + event variant instantiate.
  sat::SatelliteOptions opts;
  opts.gateway_url = "ws://localhost:8643";
  opts.device_id = "cpp-compile-check";
  opts.on_event = [](const sat::SatEvent&) {};
  sat::SatEvent ev = sat::StateChangePayload{SatelliteState::Idle, SatelliteState::Listening};
  (void)ev;
  (void)opts;

  std::puts("compile_check OK");
  return 0;
}
