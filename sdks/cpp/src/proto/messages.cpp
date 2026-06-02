// libaivg-sat — control-plane wire (de)serialization (feature 020).
#include "proto/messages.hpp"

#include <nlohmann/json.hpp>

#include "aivg/sat/state.hpp"

namespace aivg::sat::proto {

using nlohmann::json;

std::string build_register(const std::string& device_id, const std::string& contract_version,
                           const std::vector<std::string>& transport_capabilities) {
  json j{{"type", "register"},
         {"device_id", device_id},
         {"contract_version", contract_version}};
  if (!transport_capabilities.empty()) {
    j["transport_capabilities"] = transport_capabilities;  // best-first (022)
  }
  return j.dump();
}

std::string build_heartbeat(const std::string& device_id, SatelliteState state,
                            std::uint32_t uptime_s, const std::string& firmware_version) {
  return json{{"type", "heartbeat"},
              {"device_id", device_id},
              {"state", to_wire(state)},
              {"uptime_s", uptime_s},
              {"firmware_version", firmware_version}}
      .dump();
}

std::string build_command_result(const std::string& request_id, bool ok,
                                 const std::string& message) {
  json j{{"type", "command_result"}, {"request_id", request_id}, {"ok", ok}};
  if (!message.empty()) {
    j["message"] = message;
  }
  return j.dump();
}

const char* inbound_type_name(InboundType type) noexcept {
  switch (type) {
    case InboundType::Registered:
      return "registered";
    case InboundType::StateUpdate:
      return "state_update";
    case InboundType::ConfigChanged:
      return "config_changed";
    case InboundType::Command:
      return "command";
    case InboundType::LogEntry:
      return "log_entry";
    case InboundType::OtaManifest:
      return "ota_manifest";
    case InboundType::OtaProgress:
      return "ota_progress";
    case InboundType::AgentEvent:
      return "agent_event";
    case InboundType::GatewayState:
      return "state";
    case InboundType::PartialTranscript:
      return "partial_transcript";
    case InboundType::BargeIn:
      return "barge_in";
    case InboundType::Unknown:
      return "__unknown__";
    case InboundType::ParseError:
      return "__parse_error__";
  }
  return "__parse_error__";
}

namespace {
InboundType classify(const std::string& t) noexcept {
  if (t == "registered") return InboundType::Registered;
  if (t == "state_update") return InboundType::StateUpdate;
  if (t == "config_changed") return InboundType::ConfigChanged;
  if (t == "command") return InboundType::Command;
  if (t == "log_entry") return InboundType::LogEntry;
  if (t == "ota_manifest") return InboundType::OtaManifest;
  if (t == "ota_progress") return InboundType::OtaProgress;
  if (t == "agent_event") return InboundType::AgentEvent;
  if (t == "state") return InboundType::GatewayState;
  if (t == "partial_transcript") return InboundType::PartialTranscript;
  if (t == "barge_in") return InboundType::BargeIn;
  return InboundType::Unknown;
}

std::string str_or_empty(const json& j, const char* key) {
  auto it = j.find(key);
  if (it != j.end() && it->is_string()) return it->get<std::string>();
  return {};
}
}  // namespace

Inbound parse_inbound(const std::string& raw) {
  Inbound out;
  out.raw = raw;
  json j = json::parse(raw, nullptr, /*allow_exceptions=*/false);
  if (j.is_discarded() || !j.is_object() || !j.contains("type") || !j["type"].is_string()) {
    out.type = InboundType::ParseError;
    return out;
  }
  out.type = classify(j["type"].get<std::string>());
  out.device_id = str_or_empty(j, "device_id");
  out.adoption_state = str_or_empty(j, "adoption_state");
  out.chosen_transport = str_or_empty(j, "chosen_transport");  // 022 negotiation
  out.session_id = str_or_empty(j, "session_id");
  out.request_id = str_or_empty(j, "request_id");
  out.verb = str_or_empty(j, "verb");
  if (out.type == InboundType::GatewayState) {
    out.gateway_state = str_or_empty(j, "state");
  }
  return out;
}

}  // namespace aivg::sat::proto
