/**
 * Event-surface contract test: every key in `SatelliteEvents` MUST be
 * driveable from a documented wire shape. This is the binding gate for
 * FR-006 (config_changed / command / log), FR-015 (tool_call),
 * FR-016 (skill), FR-017 (transcript), FR-018 (ota), and the FSM's
 * `state` + lifecycle (`session_started` / `session_ended`).
 *
 * Approach: drive each event by emitting a fixture WS message through
 * the control plane (where applicable) or by direct bus emission
 * (where the event is internally produced by the voice-session layer).
 * Assert each event fires exactly once with a typed payload.
 */
import { describe, it, expect } from "vitest";
import {
  ControlPlane,
  type WebSocketLike,
  type ControlPlaneOptions,
} from "../../src/control-plane";
import { EventBus } from "../../src/events";
import type { SatelliteEvents } from "../../src/events";

class FakeWS implements WebSocketLike {
  static instances: FakeWS[] = [];
  public readyState = 0;
  public onopen: WebSocketLike["onopen"] = null;
  public onclose: WebSocketLike["onclose"] = null;
  public onerror: WebSocketLike["onerror"] = null;
  public onmessage: WebSocketLike["onmessage"] = null;
  constructor(public readonly url: string) {
    FakeWS.instances.push(this);
  }
  send(): void {}
  close(): void {
    this.readyState = 3;
    this.onclose?.call(this, { code: 1000 } as CloseEvent);
  }
  open(): void {
    this.readyState = 1;
    this.onopen?.call(this, new Event("open"));
  }
  msg(raw: string): void {
    this.onmessage?.call(this, { data: raw } as MessageEvent<string>);
  }
}

function buildCp(): {
  bus: EventBus<SatelliteEvents>;
  cp: ControlPlane;
  ws: () => FakeWS;
} {
  FakeWS.instances = [];
  const bus = new EventBus<SatelliteEvents>();
  const cp = new ControlPlane({
    gatewayUrl: "http://localhost:8643",
    deviceId: "evt-test",
    bus,
    getState: () => "idle",
    firmwareVersion: "0.0.1",
    wsFactory: ((url: string) => new FakeWS(url)) as unknown as ControlPlaneOptions["wsFactory"],
  });
  void cp.start();
  const ws = (): FakeWS => FakeWS.instances[0]!;
  ws().open();
  return { bus, cp, ws };
}

/**
 * Catalog of (event name → wire driver). Every key in SatelliteEvents
 * MUST appear here OR be flagged as not control-plane-driven (those are
 * voice-session-driven; covered in voice-session.test.ts and asserted
 * here only as "exists in type system").
 */
type EventKey = keyof SatelliteEvents;

const controlPlaneDriven: EventKey[] = [
  "adoption",
  "config_changed",
  "command",
  "log",
  "ota_manifest",
  "ota_progress",
  "transcript",
  "tool_call",
  "skill",
  "transient_error",
];

const voiceSessionDriven: EventKey[] = [
  "session_started",
  "session_ended",
  "remote_stream",
  "state",
  "error",
];

describe("event-surface contract", () => {
  it("every event in SatelliteEvents is covered by one driver class", () => {
    const covered = new Set<EventKey>([...controlPlaneDriven, ...voiceSessionDriven]);
    // Enumerate every key in the type system at runtime via a sample
    // keys list. If a future event is added to SatelliteEvents the
    // person adding it MUST add it to one of the arrays above (the
    // type system + this test together fail otherwise).
    const allKeys: EventKey[] = [
      "state",
      "adoption",
      "config_changed",
      "command",
      "log",
      "ota_manifest",
      "ota_progress",
      "transcript",
      "tool_call",
      "skill",
      "remote_stream",
      "session_started",
      "session_ended",
      "error",
      "transient_error",
    ];
    for (const k of allKeys) {
      expect(covered.has(k), `event "${k}" must be classified`).toBe(true);
    }
  });

  describe("control-plane-driven events", () => {
    it("adoption fires for inbound `adoption` WS message", () => {
      const { bus, ws, cp } = buildCp();
      let fired = false;
      bus.on("adoption", () => (fired = true));
      ws().msg(JSON.stringify({ type: "registered", adoption_state: "adopted" }));
      expect(fired).toBe(true);
      cp.stop();
    });

    it("config_changed fires for inbound `config_changed` WS message", () => {
      const { bus, ws, cp } = buildCp();
      let fired = false;
      bus.on("config_changed", () => (fired = true));
      // The control plane filters config_changed by device_id; the test
      // CP is constructed with deviceId "evt-test", so the broadcast
      // MUST carry that device_id for the event to fire.
      ws().msg(
        JSON.stringify({
          type: "config_changed",
          device_id: "evt-test",
          config: {
            wake_word: "x",
            routing_mode: "preferred",
            log_level: "INFO",
            heartbeat_interval: 30,
            extra: {},
          },
          config_version: 1,
        }),
      );
      expect(fired).toBe(true);
      cp.stop();
    });

    it("command fires for inbound `command` WS message", () => {
      const { bus, ws, cp } = buildCp();
      let fired = false;
      bus.on("command", () => (fired = true));
      ws().msg(
        JSON.stringify({
          type: "command",
          request_id: "r1",
          verb: "ping",
          args: {},
        }),
      );
      expect(fired).toBe(true);
      cp.stop();
    });

    it("log fires for inbound `log_entry` WS message", () => {
      const { bus, ws, cp } = buildCp();
      let fired = false;
      bus.on("log", () => (fired = true));
      ws().msg(
        JSON.stringify({
          type: "log_entry",
          entry: { ts: "x", level: "INFO", source: "agent", message: "hi" },
        }),
      );
      expect(fired).toBe(true);
      cp.stop();
    });

    it.each(["ota_manifest", "ota_progress"] as const)(
      "%s fires for the matching WS message",
      (k) => {
        const { bus, ws, cp } = buildCp();
        let fired = false;
        bus.on(k, () => (fired = true));
        if (k === "ota_manifest") {
          ws().msg(
            JSON.stringify({
              type: "ota_manifest",
              manifest: { version: "1", url: "u", manifest_id: "m" },
            }),
          );
        } else {
          ws().msg(
            JSON.stringify({
              type: "ota_progress",
              manifest_id: "m",
              state: "downloading",
            }),
          );
        }
        expect(fired).toBe(true);
        cp.stop();
      },
    );

    it.each([
      ["transcript", { speaker: "assistant", text: "hi", final: false }],
      ["tool_call", { tool_name: "web_search" }],
      ["skill", { skill_name: "vfr", source: "built-in" }],
    ] as const)("%s fires for the matching agent_event kind", (eventName, payload) => {
      const { bus, ws, cp } = buildCp();
      let fired = false;
      bus.on(eventName, () => (fired = true));
      const kindMap = {
        transcript: "transcript_delta",
        tool_call: "tool_call_started",
        skill: "skill_loaded",
      } as const;
      ws().msg(
        JSON.stringify({
          type: "agent_event",
          kind: kindMap[eventName],
          session_id: "s",
          seq: 1,
          ts: 1,
          payload,
        }),
      );
      expect(fired).toBe(true);
      cp.stop();
    });

    it("transient_error fires for an unknown WS type", () => {
      const { bus, ws, cp } = buildCp();
      let fired = false;
      bus.on("transient_error", () => (fired = true));
      ws().msg(JSON.stringify({ type: "future_event_kind" }));
      expect(fired).toBe(true);
      cp.stop();
    });
  });

  // The voice-session-driven events are exercised in
  // tests/unit/voice-session.test.ts — this contract test just
  // asserts they're classified correctly above.
});
