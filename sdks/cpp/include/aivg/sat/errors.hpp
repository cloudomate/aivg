// libaivg-sat — typed errors (feature 020).
//
// Code strings are part of the satellite↔gateway contract and are
// verbatim-equal to @aivg/sat-sdk (`sdks/typescript/src/errors.ts`).
// Consumers MAY key off the stable strings. Some codes are browser-only
// and are never emitted by a native client (noted below); the enum
// defines the full set for 1:1 parity (spec FR-004, SC-004).
#ifndef AIVG_SAT_ERRORS_HPP
#define AIVG_SAT_ERRORS_HPP

#include <map>
#include <optional>
#include <string>

namespace aivg::sat {

enum class SatErrorCode {
  // --- terminal (delivered on the `error` event) ---
  NoWebrtcImpl,         // "no_webrtc_impl"        (browser-only; not emitted natively)
  NoMicrophoneApi,      // "no_microphone_api"     (browser-only)
  PermissionDenied,     // "permission_denied"     (browser-only)
  IceFailed,            // "ice_failed"
  IceGatheringTimeout,  // "ice_gathering_timeout"
  WsDisconnected,       // "ws_disconnected"       (also a transient code)
  WsMaxRetriesExceeded, // "ws_max_retries_exceeded"
  SignalingFailed,      // "signaling_failed"
  MixedContent,         // "mixed_content"         (browser-only)
  NotAdopted,           // "not_adopted"
  ProtocolMismatch,     // "protocol_mismatch"
  DuplicateDevice,      // "duplicate_device"
  // --- transient-only (delivered on the `transient_error` event) ---
  SignalingRetry,       // "signaling_retry"
  IceRetry,             // "ice_retry"
  BufferOverflow,       // "buffer_overflow"
};

// Stable wire string for a code (e.g. SatErrorCode::IceFailed -> "ice_failed").
const char* to_wire(SatErrorCode code) noexcept;

struct SatError {
  SatErrorCode code;
  std::string message;
  std::optional<std::map<std::string, std::string>> context;
};

}  // namespace aivg::sat

#endif  // AIVG_SAT_ERRORS_HPP
