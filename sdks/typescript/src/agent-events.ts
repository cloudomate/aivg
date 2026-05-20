/**
 * Agent telemetry fan-out (US3 / FR-015..FR-017).
 *
 * The control-plane lays an inbound `agent_event` into the bus by
 * `kind` (currently only `transcript_delta` is fanned out there). This
 * module is the dedicated owner of the FULL agent-event taxonomy and
 * dispatches into the typed channels:
 *
 *   - tool_call_started   → bus.emit("tool_call", { type: "tool_call_started", ... })
 *   - tool_call_completed → bus.emit("tool_call", { type: "tool_call_completed", ... })
 *   - tool_call_failed    → bus.emit("tool_call", { type: "tool_call_failed", ... })
 *   - skill_loaded        → bus.emit("skill", { type: "skill_loaded", ... })
 *   - transcript_delta    → bus.emit("transcript", ...)
 *   - <anything else>     → bus.emit("transient_error", protocol_mismatch) once per session
 *
 * Per R-8 forward-compat: unknown `kind` values fire ONE
 * transient_error per session and are otherwise silently dropped on
 * subsequent occurrences.
 *
 * This module subscribes to a raw `__agent_event_raw` event the
 * control-plane emits (added below). That side-channel keeps US1's
 * MVP transcript path untouched while letting US3 layer richer
 * dispatch on top.
 */

import type {
  EventBus,
  SatelliteEvents,
  ToolCallEvent,
  SkillEvent,
  TranscriptDelta,
} from "./events";
import type { WsAgentEventMessage } from "./proto/ws-messages";

const KNOWN_KINDS: readonly string[] = [
  "tool_call_started",
  "tool_call_completed",
  "tool_call_failed",
  "skill_loaded",
  "transcript_delta",
];

export class AgentEventDispatcher {
  private unknownKindsSeen = new Set<string>();

  /**
   * Dispatch one `agent_event` message into typed bus events.
   *
   * Called by control-plane.ts. Returns true if recognised, false if
   * unknown (so the caller can log + emit transient_error once).
   */
  dispatch(bus: EventBus<SatelliteEvents>, msg: WsAgentEventMessage): boolean {
    const kind = msg.kind;
    const payload = msg.payload;
    const ts = msg.ts;

    switch (kind) {
      case "tool_call_started":
      case "tool_call_completed":
      case "tool_call_failed": {
        const p = payload as {
          tool_name?: string;
          result_summary?: string;
          error?: string;
        };
        const ev: ToolCallEvent = {
          type: kind,
          toolName: p.tool_name ?? "<unknown>",
          ts,
        };
        if (p.result_summary !== undefined) ev.resultSummary = p.result_summary;
        if (p.error !== undefined) ev.error = p.error;
        bus.emit("tool_call", ev);
        return true;
      }

      case "skill_loaded": {
        const p = payload as {
          skill_name?: string;
          source?: "built-in" | "plugin" | "tap";
        };
        const ev: SkillEvent = {
          type: "skill_loaded",
          skillName: p.skill_name ?? "<unknown>",
          source: p.source ?? "built-in",
          ts,
        };
        bus.emit("skill", ev);
        return true;
      }

      case "transcript_delta": {
        const p = payload as {
          speaker?: "user" | "assistant";
          text?: string;
          final?: boolean;
        };
        const ev: TranscriptDelta = {
          speaker: p.speaker ?? "assistant",
          text: p.text ?? "",
          final: p.final ?? false,
          seq: msg.seq,
          ts,
        };
        bus.emit("transcript", ev);
        return true;
      }

      default: {
        // Forward-compat (R-8) — emit transient_error ONCE per kind.
        if (!this.unknownKindsSeen.has(kind)) {
          this.unknownKindsSeen.add(kind);
          bus.emit("transient_error", {
            code: "signaling_retry",
            message: `unknown agent_event kind: ${kind}`,
            retryInMs: 0,
            attempt: 1,
          });
        }
        return false;
      }
    }
  }

  /** Test-only: reset the seen set. */
  reset(): void {
    this.unknownKindsSeen.clear();
  }
}

export const KNOWN_AGENT_EVENT_KINDS = KNOWN_KINDS;
