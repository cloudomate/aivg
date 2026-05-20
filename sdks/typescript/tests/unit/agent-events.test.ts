import { describe, it, expect } from "vitest";
import { AgentEventDispatcher, KNOWN_AGENT_EVENT_KINDS } from "../../src/agent-events";
import { EventBus, type SatelliteEvents, type ToolCallEvent } from "../../src/events";
import type { WsAgentEventMessage } from "../../src/proto/ws-messages";

const make = (
  kind: string,
  payload: Record<string, unknown>,
): WsAgentEventMessage => ({
  type: "agent_event",
  kind,
  session_id: "s-1",
  seq: 1,
  ts: 1000,
  payload,
});

function setup() {
  const bus = new EventBus<SatelliteEvents>();
  const d = new AgentEventDispatcher();
  const events: { name: string; payload: unknown }[] = [];
  for (const k of ["tool_call", "skill", "transcript", "transient_error"] as const) {
    bus.on(k, (p) => events.push({ name: k, payload: p }));
  }
  return { bus, d, events };
}

describe("AgentEventDispatcher", () => {
  it("KNOWN_AGENT_EVENT_KINDS has 5 entries", () => {
    expect(KNOWN_AGENT_EVENT_KINDS).toHaveLength(5);
  });

  it("dispatches tool_call_started → typed tool_call event", () => {
    const { bus, d, events } = setup();
    d.dispatch(bus, make("tool_call_started", { tool_name: "web_search" }));
    expect(events).toHaveLength(1);
    const ev = events[0]!.payload as ToolCallEvent;
    expect(ev.type).toBe("tool_call_started");
    expect(ev.toolName).toBe("web_search");
    expect(ev.ts).toBe(1000);
  });

  it("dispatches tool_call_completed with result_summary", () => {
    const { bus, d, events } = setup();
    d.dispatch(
      bus,
      make("tool_call_completed", {
        tool_name: "web_search",
        result_summary: "Found 3 results",
      }),
    );
    const ev = events[0]!.payload as ToolCallEvent;
    expect(ev.type).toBe("tool_call_completed");
    expect(ev.resultSummary).toBe("Found 3 results");
  });

  it("dispatches tool_call_failed with error", () => {
    const { bus, d, events } = setup();
    d.dispatch(
      bus,
      make("tool_call_failed", { tool_name: "web_search", error: "Timeout" }),
    );
    const ev = events[0]!.payload as ToolCallEvent;
    expect(ev.type).toBe("tool_call_failed");
    expect(ev.error).toBe("Timeout");
  });

  it("dispatches skill_loaded → typed skill event", () => {
    const { bus, d, events } = setup();
    d.dispatch(
      bus,
      make("skill_loaded", { skill_name: "voice-friendly-replies", source: "built-in" }),
    );
    expect(events).toHaveLength(1);
    expect(events[0]!.name).toBe("skill");
    expect((events[0]!.payload as { skillName: string }).skillName).toBe(
      "voice-friendly-replies",
    );
  });

  it("dispatches transcript_delta → typed transcript event", () => {
    const { bus, d, events } = setup();
    d.dispatch(
      bus,
      make("transcript_delta", { speaker: "assistant", text: "hi", final: false }),
    );
    expect(events).toHaveLength(1);
    expect(events[0]!.name).toBe("transcript");
    expect((events[0]!.payload as { text: string }).text).toBe("hi");
    expect((events[0]!.payload as { seq: number }).seq).toBe(1);
  });

  it("unknown kind → ONE transient_error per session (R-8)", () => {
    const { bus, d, events } = setup();
    d.dispatch(bus, make("future_kind", { foo: "bar" }));
    d.dispatch(bus, make("future_kind", { foo: "baz" }));
    d.dispatch(bus, make("future_kind", { foo: "qux" }));
    const errs = events.filter((e) => e.name === "transient_error");
    expect(errs).toHaveLength(1);
    expect((errs[0]!.payload as { message: string }).message).toContain("future_kind");
  });

  it("missing tool_name defaults to '<unknown>' for forward-compat", () => {
    const { bus, d, events } = setup();
    d.dispatch(bus, make("tool_call_started", {}));
    expect((events[0]!.payload as ToolCallEvent).toolName).toBe("<unknown>");
  });
});
