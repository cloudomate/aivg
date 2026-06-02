// libaivg-sat — control-plane wire (de)serialization (feature 020, internal).
//
// Mirrors `sdks/typescript/src/proto/ws-messages.ts` byte-for-byte at the
// field-name level (contract 0.2.0). nlohmann/json is used only in the
// .cpp — it never leaks into the public headers.
#ifndef AIVG_SAT_PROTO_MESSAGES_HPP
#define AIVG_SAT_PROTO_MESSAGES_HPP

#include <cstdint>
#include <string>
#include <vector>

#include "aivg/sat/state.hpp"

namespace aivg::sat::proto {

// ---- Outbound (SDK → gateway): build the exact JSON the gateway expects ----

// Feature 022 — `transport_capabilities` (best-first) is added to the register
// frame so the gateway can negotiate the voice transport (feature 021 / US3).
// Empty preserves the pre-022 frame exactly (back-compat).
std::string build_register(const std::string& device_id, const std::string& contract_version,
                           const std::vector<std::string>& transport_capabilities = {});

std::string build_heartbeat(const std::string& device_id, SatelliteState state,
                            std::uint32_t uptime_s, const std::string& firmware_version);

std::string build_command_result(const std::string& request_id, bool ok,
                                  const std::string& message = "");

// ---- Inbound (gateway → SDK): classify by the `type` discriminant ----------

enum class InboundType {
  Registered,
  StateUpdate,
  ConfigChanged,
  Command,
  LogEntry,
  OtaManifest,
  OtaProgress,
  AgentEvent,
  GatewayState,        // {"type":"state",...}
  PartialTranscript,
  BargeIn,
  Unknown,             // unknown discriminant — surface protocol_mismatch once
  ParseError,          // malformed JSON / missing type
};

struct Inbound {
  InboundType type = InboundType::ParseError;
  std::string raw;  // original payload, for forward-compat / diagnostics

  // Selected commonly-needed fields (populated when present). Full payload
  // access stays in raw for the dispatcher; this keeps the hot fields cheap.
  std::string device_id;       // state_update / config_changed filter key
  std::string adoption_state;  // registered / state_update: "pending"|"adopted"
  std::string chosen_transport;  // registered: gateway-negotiated transport (022)
  std::string gateway_state;   // {"type":"state"} value (may be "thinking")
  std::string session_id;
  std::string request_id;      // command
  std::string verb;            // command
};

// Always returns a value (forward-compat R-8): malformed/unknown become
// ParseError/Unknown rather than throwing.
Inbound parse_inbound(const std::string& raw);

// Map a {"type":"state"} gateway value or local string to wire string.
const char* inbound_type_name(InboundType type) noexcept;

}  // namespace aivg::sat::proto

#endif  // AIVG_SAT_PROTO_MESSAGES_HPP
