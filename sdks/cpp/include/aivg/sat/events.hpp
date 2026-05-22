// libaivg-sat — typed event surface (feature 020).
//
// 1:1 parity with @aivg/sat-sdk's `SatelliteEvents` (17 variants;
// `sdks/typescript/src/events.ts`). Each payload's fields mirror the TS
// interface; field-level parity is asserted in task T032. Events are
// delivered through a single `EventHandler` as a `SatEvent` variant.
#ifndef AIVG_SAT_EVENTS_HPP
#define AIVG_SAT_EVENTS_HPP

#include <cstdint>
#include <functional>
#include <map>
#include <optional>
#include <string>
#include <variant>

#include "aivg/sat/errors.hpp"
#include "aivg/sat/state.hpp"
#include "aivg/sat/wire.hpp"

namespace aivg::sat {

struct StateChangePayload {
  SatelliteState previous;
  SatelliteState current;
};

// Gateway-side voice session state — richer than the local FSM; carries
// values such as "thinking" that have no local-FSM equivalent.
struct GatewayStatePayload {
  std::string state;
  std::optional<std::string> session_id;
};

struct AdoptionEvent {
  std::string previous;  // e.g. "pending"
  std::string current;   // e.g. "adopted"
};

struct CommandEvent {
  std::string id;
  std::string name;
  std::map<std::string, std::string> args;
};

struct TranscriptDelta {
  std::string text;
  bool is_final = false;
};

struct ToolCallEvent {
  std::string name;
  std::string status;
};

struct SkillEvent {
  std::string name;
  std::string status;
};

struct BargeInEvent {
  std::optional<std::string> session_id;
};

struct RemoteStreamEvent {
  std::string kind;
};

struct VoiceSession {
  std::string session_id;
};

struct VoiceSessionResult {
  std::string session_id;
  std::string reason;
};

// Discriminated union of all 17 event payloads. `config_changed`,
// `log`, `ota_manifest`, `ota_progress` reuse the wire.hpp shapes.
using SatEvent = std::variant<StateChangePayload,   // "state"
                              GatewayStatePayload,   // "gateway_state"
                              AdoptionEvent,         // "adoption"
                              SatelliteConfig,       // "config_changed"
                              CommandEvent,          // "command"
                              LogEntry,              // "log"
                              OtaManifest,           // "ota_manifest"
                              OtaProgress,           // "ota_progress"
                              TranscriptDelta,       // "transcript"
                              ToolCallEvent,         // "tool_call"
                              SkillEvent,            // "skill"
                              BargeInEvent,          // "barge_in"
                              RemoteStreamEvent,     // "remote_stream"
                              VoiceSession,          // "session_started"
                              VoiceSessionResult,    // "session_ended"
                              SatError,              // "error" + "transient_error"
                              std::monostate>;       // unmapped/future

using EventHandler = std::function<void(const SatEvent&)>;

}  // namespace aivg::sat

#endif  // AIVG_SAT_EVENTS_HPP
