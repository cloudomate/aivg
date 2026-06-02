// libaivg-sat — transport-negotiation unit test (feature 022, US3 / T020,T025).
//
// Pure choose_transport() cases: capability negotiation, gateway selection,
// operator pin, unsatisfiable pin, and the WebRTC-only / pre-021-gateway
// back-compat fallbacks. No network, no backend.
#include <cassert>
#include <cstdio>

#include "negotiate.hpp"

using namespace aivg::sat::detail;

int main() {
  const std::vector<std::string> both = {"grpc", "webrtc"};
  const std::vector<std::string> webonly = {"webrtc"};

  // Auto: honour the gateway's choice when this build can speak it.
  assert(choose_transport(both, "", "grpc").transport == "grpc");
  assert(choose_transport(both, "", "webrtc").transport == "webrtc");

  // Auto + no gateway choice (pre-021 gateway) -> WebRTC (back-compat, T025).
  assert(choose_transport(both, "", "").transport == "webrtc");

  // WebRTC-only build: even if the gateway named grpc, fall back to WebRTC
  // (a feature-020 SDK never advertised grpc, so this is defensive — T025).
  assert(choose_transport(webonly, "", "").transport == "webrtc");
  assert(choose_transport(webonly, "", "grpc").transport == "webrtc");

  // Operator pin, satisfiable.
  assert(choose_transport(both, "grpc", "webrtc").transport == "grpc");
  assert(choose_transport(both, "webrtc", "grpc").transport == "webrtc");

  // Operator pin, UNSATISFIABLE (pinned transport not in this build) -> error.
  {
    auto bad = choose_transport(webonly, "grpc", "");
    assert(!bad.ok && !bad.error.empty());
  }

  // No transports compiled in -> error.
  assert(!choose_transport({}, "", "").ok);

  std::printf("test_negotiation: OK\n");
  return 0;
}
