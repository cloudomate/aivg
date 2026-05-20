/**
 * Control-plane WebSocket message shapes per
 * `specs/014-aivg-sat-sdk-ts/contracts/wire-protocol.md`.
 *
 * Every message is JSON-encoded; the `type` field is the discriminant.
 *
 * Forward-compat policy (R-8):
 *  - Unknown `type` values are kept as `WsUnknownMessage` and emitted to
 *    consumers via `transient_error(protocol_mismatch)` once per session.
 *  - Unknown fields on known messages are preserved in `_unknown` so
 *    diagnostic tooling can see them. The SDK never validates field types
 *    beyond the discriminant.
 */

import type { SatelliteState } from "../state";

// ---------------------------------------------------------------------
// Outbound — SDK → gateway
// ---------------------------------------------------------------------

export interface WsRegisterMessage {
  type: "register";
  device_id: string;
  contract_version: string;
}

export interface WsHeartbeatMessage {
  type: "heartbeat";
  device_id: string;
  state: SatelliteState;
  uptime_s: number;
  firmware_version: string;
}

export interface WsCommandResultMessage {
  type: "command_result";
  request_id: string;
  ok: boolean;
  message?: string;
  data?: Record<string, unknown>;
}

export type WsOutboundMessage =
  | WsRegisterMessage
  | WsHeartbeatMessage
  | WsCommandResultMessage;

// ---------------------------------------------------------------------
// Inbound — gateway → SDK
// ---------------------------------------------------------------------

export type AdoptionWireState = "pending" | "adopted";

export interface WsAdoptionMessage {
  type: "adoption";
  state: AdoptionWireState;
}

/**
 * Mirrors `contracts/wire-protocol.md` "HTTP shapes" → `GET .../config` body.
 * The SDK re-uses this shape on both the GET response and the
 * `config_changed` push.
 */
export interface SatelliteConfigWire {
  wake_word: string;
  routing_mode: "preferred" | "any" | "off";
  log_level: "DEBUG" | "INFO" | "WARN" | "ERROR";
  heartbeat_interval: number;
  extra: Record<string, unknown>;
  version: number;
}

export interface WsConfigChangedMessage {
  type: "config_changed";
  config: SatelliteConfigWire;
}

export interface WsCommandMessage {
  type: "command";
  request_id: string;
  verb: "reboot" | "restart" | "refresh_config" | "tail_logs" | "ping";
  args: Record<string, unknown>;
}

export interface WsLogEntryMessage {
  type: "log_entry";
  entry: {
    ts: string;
    level: "DEBUG" | "INFO" | "WARN" | "ERROR";
    source: string;
    message: string;
    meta?: Record<string, unknown>;
  };
}

export interface WsOtaManifestMessage {
  type: "ota_manifest";
  manifest: {
    version: string;
    url: string;
    sha256?: string;
    manifest_id: string;
    apply_by?: string;
  };
}

export interface WsOtaProgressMessage {
  type: "ota_progress";
  manifest_id: string;
  state: "checking" | "downloading" | "flashing" | "rebooting" | "idle" | "failed";
  progress?: number;
  message?: string;
}

export type AgentEventKind =
  | "tool_call_started"
  | "tool_call_completed"
  | "tool_call_failed"
  | "skill_loaded"
  | "transcript_delta";

export interface WsAgentEventMessage {
  type: "agent_event";
  kind: AgentEventKind | string; // string for forward-compat unknowns
  session_id: string;
  seq: number;
  ts: number;
  payload: Record<string, unknown>;
}

/** Fallback bucket — discriminant on `type` was a string the SDK doesn't know. */
export interface WsUnknownMessage {
  type: string;
  _unknown: Record<string, unknown>;
}

export type WsInboundMessage =
  | WsAdoptionMessage
  | WsConfigChangedMessage
  | WsCommandMessage
  | WsLogEntryMessage
  | WsOtaManifestMessage
  | WsOtaProgressMessage
  | WsAgentEventMessage
  | WsUnknownMessage;

/**
 * Parse a raw JSON string into a `WsInboundMessage`. Always returns a
 * value — malformed JSON or missing `type` discriminant become an
 * `WsUnknownMessage` with the raw payload stashed in `_unknown`.
 *
 * This is the SDK's parsing entrypoint and the single place that
 * touches the wire format. The dispatcher in `control-plane.ts` then
 * routes by `.type`.
 */
export function parseWsInbound(raw: string): WsInboundMessage {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { type: "__parse_error__", _unknown: { raw } };
  }
  if (typeof parsed !== "object" || parsed === null || !("type" in parsed)) {
    return { type: "__missing_type__", _unknown: (parsed ?? {}) as Record<string, unknown> };
  }
  const t = (parsed as { type: unknown }).type;
  if (typeof t !== "string") {
    return { type: "__non_string_type__", _unknown: parsed as Record<string, unknown> };
  }
  const known: Set<string> = new Set([
    "adoption",
    "config_changed",
    "command",
    "log_entry",
    "ota_manifest",
    "ota_progress",
    "agent_event",
  ]);
  if (!known.has(t)) {
    return { type: t, _unknown: parsed as Record<string, unknown> };
  }
  // Known type — return as-is. We trust the gateway's shape per R-8;
  // runtime validators were rejected for package-size reasons.
  return parsed as WsInboundMessage;
}
