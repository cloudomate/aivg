// libaivg-sat — reconnect backoff + error-code parity (feature 020).
#include <cassert>
#include <cstdio>
#include <set>
#include <string>

#include "aivg/sat/errors.hpp"
#include "aivg/sat/satellite.hpp"
#include "reconnect.hpp"

using namespace aivg::sat;

int main() {
  // --- T014: reconnect backoff (capped exponential + full jitter) ---
  {
    ReconnectPolicy p;
    p.base_delay_ms = 500;
    p.max_delay_ms = 30000;
    p.jitter = false;  // deterministic: capped exponential

    assert(detail::next_backoff_ms(p, 0, 0.0) == 500);    // 500 * 2^0
    assert(detail::next_backoff_ms(p, 1, 0.0) == 1000);   // 2^1
    assert(detail::next_backoff_ms(p, 2, 0.0) == 2000);   // 2^2
    assert(detail::next_backoff_ms(p, 6, 0.0) == 30000);  // 500*64=32000 -> capped
    assert(detail::next_backoff_ms(p, 99, 0.0) == 30000); // no overflow, stays capped

    // Full jitter: delay = u * capped. rng_unit injected.
    p.jitter = true;
    assert(detail::next_backoff_ms(p, 1, 0.0) == 0);     // u=0 -> 0
    assert(detail::next_backoff_ms(p, 1, 1.0) == 1000);  // u=1 -> capped
    assert(detail::next_backoff_ms(p, 1, 0.5) == 500);   // u=0.5 -> half of 1000
    // jitter never exceeds the capped exponential
    assert(detail::next_backoff_ms(p, 2, 0.99) <= 2000);
  }

  // --- T032: error-code wire strings == @aivg/sat-sdk (errors.ts) ---
  {
    const SatErrorCode all[] = {
        SatErrorCode::NoWebrtcImpl,        SatErrorCode::NoMicrophoneApi,
        SatErrorCode::PermissionDenied,    SatErrorCode::IceFailed,
        SatErrorCode::IceGatheringTimeout, SatErrorCode::WsDisconnected,
        SatErrorCode::WsMaxRetriesExceeded, SatErrorCode::SignalingFailed,
        SatErrorCode::MixedContent,        SatErrorCode::NotAdopted,
        SatErrorCode::ProtocolMismatch,    SatErrorCode::DuplicateDevice,
        SatErrorCode::SignalingRetry,      SatErrorCode::IceRetry,
        SatErrorCode::BufferOverflow,
    };
    std::set<std::string> got;
    for (auto c : all) got.insert(to_wire(c));

    // Verbatim union of terminal + transient codes from
    // sdks/typescript/src/errors.ts (ws_disconnected is shared).
    const std::set<std::string> expected = {
        "no_webrtc_impl", "no_microphone_api", "permission_denied", "ice_failed",
        "ice_gathering_timeout", "ws_disconnected", "ws_max_retries_exceeded",
        "signaling_failed", "mixed_content", "not_adopted", "protocol_mismatch",
        "duplicate_device", "signaling_retry", "ice_retry", "buffer_overflow",
    };
    assert(got == expected);
  }

  std::puts("test_logic OK");
  return 0;
}
