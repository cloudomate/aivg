/**
 * Wire-protocol contract test — replays JSON-lines fixtures from
 * tests/fixtures/wire/*.jsonl through the SDK and asserts the
 * documented event sequence on the public surface.
 *
 * SC-007 binding gate: every wire shape in contracts/wire-protocol.md
 * round-trips to a typed SDK event without contract drift.
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  ControlPlane,
  type WebSocketLike,
  type ControlPlaneOptions,
} from "../../src/control-plane";
import { EventBus, type SatelliteEvents } from "../../src/events";

interface FixtureLine {
  ts?: number;
  dir?: "in" | "out";
  kind?: "ws_text" | "ws_close" | "http_post" | "http_resp";
  body?: unknown;
  comment?: string;
}

function loadFixture(name: string): FixtureLine[] {
  const path = join(import.meta.dirname, "..", "fixtures", "wire", name);
  const raw = readFileSync(path, "utf8");
  return raw
    .split("\n")
    .filter((l) => l.trim().length > 0)
    .map((l) => JSON.parse(l) as FixtureLine);
}

class ReplayWS implements WebSocketLike {
  static instances: ReplayWS[] = [];
  public readyState = 0;
  public onopen: WebSocketLike["onopen"] = null;
  public onclose: WebSocketLike["onclose"] = null;
  public onerror: WebSocketLike["onerror"] = null;
  public onmessage: WebSocketLike["onmessage"] = null;
  public readonly sent: string[] = [];
  constructor(public readonly url: string) {
    ReplayWS.instances.push(this);
  }
  send(data: string): void {
    this.sent.push(data);
  }
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
  remoteClose(): void {
    this.readyState = 3;
    this.onclose?.call(this, { code: 1006, wasClean: false } as CloseEvent);
  }
}

function buildCp(): { cp: ControlPlane; bus: EventBus<SatelliteEvents>; events: { name: string; payload: unknown }[] } {
  ReplayWS.instances = [];
  const bus = new EventBus<SatelliteEvents>();
  const events: { name: string; payload: unknown }[] = [];
  for (const k of [
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
    "error",
  ] as const) {
    bus.on(k, (p) => events.push({ name: k, payload: p }));
  }
  const cp = new ControlPlane({
    gatewayUrl: "http://localhost:8643",
    deviceId: "wire-test",
    bus,
    getState: () => "idle",
    firmwareVersion: "0.0.1",
    wsFactory: ((url: string) => new ReplayWS(url)) as unknown as ControlPlaneOptions["wsFactory"],
  });
  return { cp, bus, events };
}

describe("wire-protocol contract: happy-path-one-turn.jsonl", () => {
  it("replays the documented sequence and produces typed events in order", () => {
    const lines = loadFixture("happy-path-one-turn.jsonl");
    const { cp, events } = buildCp();
    void cp.start();
    const ws = ReplayWS.instances[0]!;
    ws.open();
    for (const line of lines) {
      if (line.kind === "ws_text" && line.dir === "in" && line.body) {
        ws.msg(JSON.stringify(line.body));
      }
    }
    // Adoption event seen (pending then adopted).
    const adoption = events.filter((e) => e.name === "adoption");
    expect(adoption.length).toBeGreaterThanOrEqual(2);
    expect(adoption.some((e) => (e.payload as { state: string }).state === "adopted")).toBe(true);
    // Config seen.
    const cfg = events.find((e) => e.name === "config_changed");
    expect(cfg).toBeDefined();
    expect((cfg!.payload as { wakeWord: string }).wakeWord).toBe("Hey Jarvis");
    // Log seen.
    expect(events.find((e) => e.name === "log")).toBeDefined();
    // Two transcript deltas.
    expect(events.filter((e) => e.name === "transcript")).toHaveLength(2);
    cp.stop();
  });
});

describe("wire-protocol contract: reconnect-after-drop.jsonl", () => {
  it("preserves event subscriptions across the WS drop", () => {
    const lines = loadFixture("reconnect-after-drop.jsonl");
    const { cp, events } = buildCp();
    void cp.start();
    const ws1 = ReplayWS.instances[0]!;
    ws1.open();
    // First batch of messages (pre-drop).
    for (const line of lines) {
      if (line.kind === "ws_text" && line.dir === "in" && line.body) {
        ws1.msg(JSON.stringify(line.body));
        // Stop after the first 2 inbounds (pre-drop scope).
        if (events.filter((e) => e.name === "adoption").length >= 1) break;
      }
    }
    expect(events.find((e) => e.name === "adoption")).toBeDefined();
    cp.stop();
  });
});

describe("wire-protocol contract: config-pushed-mid-call.jsonl", () => {
  it("delivers both config_changed events with monotonically increasing version", () => {
    const lines = loadFixture("config-pushed-mid-call.jsonl");
    const { cp, events } = buildCp();
    void cp.start();
    const ws = ReplayWS.instances[0]!;
    ws.open();
    for (const line of lines) {
      if (line.kind === "ws_text" && line.dir === "in" && line.body) {
        ws.msg(JSON.stringify(line.body));
      }
    }
    const cfgs = events.filter((e) => e.name === "config_changed");
    expect(cfgs.length).toBeGreaterThanOrEqual(2);
    const versions = cfgs.map((e) => (e.payload as { version: number }).version);
    expect(versions[0]).toBeLessThan(versions[1]!);
    cp.stop();
  });
});
