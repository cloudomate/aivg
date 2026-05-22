// libaivg-sat — local FSM + wire-string tables (feature 020).
#include "state_machine.hpp"

#include "aivg/sat/errors.hpp"
#include "aivg/sat/state.hpp"

namespace aivg::sat {

const char* to_wire(SatelliteState state) noexcept {
  switch (state) {
    case SatelliteState::Idle:
      return "idle";
    case SatelliteState::Listening:
      return "listening";
    case SatelliteState::Speaking:
      return "speaking";
    case SatelliteState::Error:
      return "error";
  }
  return "idle";
}

const char* to_wire(SatErrorCode code) noexcept {
  switch (code) {
    case SatErrorCode::NoWebrtcImpl:
      return "no_webrtc_impl";
    case SatErrorCode::NoMicrophoneApi:
      return "no_microphone_api";
    case SatErrorCode::PermissionDenied:
      return "permission_denied";
    case SatErrorCode::IceFailed:
      return "ice_failed";
    case SatErrorCode::IceGatheringTimeout:
      return "ice_gathering_timeout";
    case SatErrorCode::WsDisconnected:
      return "ws_disconnected";
    case SatErrorCode::WsMaxRetriesExceeded:
      return "ws_max_retries_exceeded";
    case SatErrorCode::SignalingFailed:
      return "signaling_failed";
    case SatErrorCode::MixedContent:
      return "mixed_content";
    case SatErrorCode::NotAdopted:
      return "not_adopted";
    case SatErrorCode::ProtocolMismatch:
      return "protocol_mismatch";
    case SatErrorCode::DuplicateDevice:
      return "duplicate_device";
    case SatErrorCode::SignalingRetry:
      return "signaling_retry";
    case SatErrorCode::IceRetry:
      return "ice_retry";
    case SatErrorCode::BufferOverflow:
      return "buffer_overflow";
  }
  return "";
}

namespace detail {

SatelliteState transition(SatelliteState current, FsmEvent event) noexcept {
  switch (event) {
    case FsmEvent::FatalError:
      return SatelliteState::Error;
    case FsmEvent::Reset:
      return SatelliteState::Idle;
    case FsmEvent::BeginSessionResolved:
      // Only meaningful from idle; otherwise no-op.
      return current == SatelliteState::Idle ? SatelliteState::Listening : current;
    case FsmEvent::FirstRemoteAudio:
      return current == SatelliteState::Listening ? SatelliteState::Speaking : current;
    case FsmEvent::ReplyComplete:
      return (current == SatelliteState::Speaking || current == SatelliteState::Listening)
                 ? SatelliteState::Idle
                 : current;
  }
  return current;
}

}  // namespace detail
}  // namespace aivg::sat
