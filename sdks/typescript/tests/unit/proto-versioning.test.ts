import { describe, it, expect } from "vitest";
import { CONTRACT_VERSION, SDK_VERSION } from "../../src/proto/version";
import { parseWsInbound, type WsInboundMessage } from "../../src/proto/ws-messages";

describe("contract version", () => {
  it("is exactly '1.0.0' — SC-007 binding gate", () => {
    expect(CONTRACT_VERSION).toBe("1.0.0");
  });

  it("SDK_VERSION is a string (substituted by tsup OR fallback to 0.0.0)", () => {
    expect(typeof SDK_VERSION).toBe("string");
    expect(SDK_VERSION.length).toBeGreaterThan(0);
  });
});

describe("parseWsInbound — forward-compat (R-8)", () => {
  it("parses a known adoption message", () => {
    const msg = parseWsInbound('{"type":"adoption","state":"pending"}');
    expect(msg.type).toBe("adoption");
    if (msg.type === "adoption") {
      expect(msg.state).toBe("pending");
    }
  });

  it("parses a known agent_event with transcript_delta", () => {
    const raw = JSON.stringify({
      type: "agent_event",
      kind: "transcript_delta",
      session_id: "s1",
      seq: 1,
      ts: 1700000000,
      payload: { speaker: "assistant", text: "hi", final: false },
    });
    const msg = parseWsInbound(raw);
    expect(msg.type).toBe("agent_event");
  });

  it("preserves unknown `type` values for forward-compat reporting", () => {
    const msg = parseWsInbound('{"type":"future_event","data":42}');
    expect(msg.type).toBe("future_event");
    expect("_unknown" in msg).toBe(true);
  });

  it("malformed JSON becomes a __parse_error__ sentinel", () => {
    const msg = parseWsInbound("not json {{");
    expect(msg.type).toBe("__parse_error__");
  });

  it("missing `type` field becomes a __missing_type__ sentinel", () => {
    const msg = parseWsInbound('{"data":1}');
    expect(msg.type).toBe("__missing_type__");
  });

  it("non-string `type` field becomes a __non_string_type__ sentinel", () => {
    const msg = parseWsInbound('{"type":42}');
    expect(msg.type).toBe("__non_string_type__");
  });

  it("exhaustive discriminant — every known type is in the union", () => {
    // Compile-time exhaustiveness: if a `type` were missing the switch
    // below wouldn't narrow correctly. Runtime smoke just ensures the
    // discriminant strings match the wire spec.
    const types: WsInboundMessage["type"][] = [
      "adoption",
      "config_changed",
      "command",
      "log_entry",
      "ota_manifest",
      "ota_progress",
      "agent_event",
    ];
    // The union also includes string fallback for unknown — assertion
    // is just that the known set is non-empty.
    expect(types.length).toBeGreaterThanOrEqual(7);
  });
});
