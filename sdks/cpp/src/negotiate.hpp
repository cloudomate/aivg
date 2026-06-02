// libaivg-sat — client-side transport negotiation (feature 022, US3, internal).
//
// Pure selection: given what this build supports, an optional operator pin, and
// the gateway's chosen_transport, decide which transport to use. Mirrors the
// gateway-side rule (feature 021 / R-5) on the client. Header-only + pure so it
// unit-tests with no network or backend deps.
#ifndef AIVG_SAT_NEGOTIATE_HPP
#define AIVG_SAT_NEGOTIATE_HPP

#include <string>
#include <vector>

namespace aivg::sat::detail {

struct TransportChoice {
  bool ok = false;
  std::string transport;  // "grpc" | "webrtc" (valid when ok)
  std::string error;      // human-readable reason (when !ok)
};

inline bool caps_contains(const std::vector<std::string>& caps, const std::string& s) {
  for (const auto& c : caps) {
    if (c == s) return true;
  }
  return false;
}

// caps   : transports compiled into this build (e.g. {"grpc","webrtc"}, best-first)
// pin    : "" (Auto) | "webrtc" | "grpc" — an operator override
// chosen : the gateway's chosen_transport from the register reply ("" if absent/pre-021)
inline TransportChoice choose_transport(const std::vector<std::string>& caps,
                                        const std::string& pin, const std::string& chosen) {
  if (caps.empty()) {
    return {false, "", "no voice transport is compiled into this build"};
  }
  if (!pin.empty()) {
    if (caps_contains(caps, pin)) return {true, pin, ""};
    return {false, "", "pinned transport '" + pin + "' is not supported by this build"};
  }
  // Honour the gateway's selection when this build can speak it.
  if (!chosen.empty() && caps_contains(caps, chosen)) return {true, chosen, ""};
  // No (usable) gateway selection — e.g. a pre-021 gateway. Prefer WebRTC for
  // back-compat, else the first compiled-in transport.
  if (caps_contains(caps, "webrtc")) return {true, "webrtc", ""};
  return {true, caps.front(), ""};
}

}  // namespace aivg::sat::detail

#endif  // AIVG_SAT_NEGOTIATE_HPP
