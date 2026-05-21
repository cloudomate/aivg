import { describe, it, expect, vi } from "vitest";
import {
  ControlPlane,
  computeBackoff,
  buildWsUrl,
  DEFAULT_RECONNECT_POLICY,
  type ControlPlaneOptions,
  type WebSocketLike,
} from "../../src/control-plane";
import { EventBus } from "../../src/events";
import type { SatelliteEvents } from "../../src/events";

// ----------- helpers -----------------------------------------------------

class FakeWS implements WebSocketLike {
  static instances: FakeWS[] = [];
  public readonly url: string;
  public readyState = 0; // CONNECTING
  public onopen: WebSocketLike["onopen"] = null;
  public onclose: WebSocketLike["onclose"] = null;
  public onerror: WebSocketLike["onerror"] = null;
  public onmessage: WebSocketLike["onmessage"] = null;
  public readonly sent: string[] = [];
  public closeCalls = 0;

  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    this.closeCalls += 1;
    this.readyState = 3; // CLOSED
    this.onclose?.call(this, { code: 1000, reason: "test", wasClean: true } as CloseEvent);
  }

  triggerOpen(): void {
    this.readyState = 1; // OPEN
    this.onopen?.call(this, new Event("open"));
  }

  triggerMessage(raw: string): void {
    this.onmessage?.call(this, { data: raw } as MessageEvent<string>);
  }

  triggerClose(): void {
    this.readyState = 3;
    this.onclose?.call(this, { code: 1006, reason: "remote", wasClean: false } as CloseEvent);
  }
}

function makeCp(overrides: Partial<ControlPlaneOptions> = {}): {
  cp: ControlPlane;
  bus: EventBus<SatelliteEvents>;
  factory: ReturnType<typeof vi.fn>;
  events: { name: string; payload: unknown }[];
} {
  const bus = new EventBus<SatelliteEvents>();
  const events: { name: string; payload: unknown }[] = [];
  // Tap every event for assertions.
  for (const k of [
    "adoption",
    "config_changed",
    "command",
    "log",
    "ota_manifest",
    "ota_progress",
    "transcript",
    "error",
    "transient_error",
  ] as const) {
    bus.on(k, (p) => events.push({ name: k, payload: p }));
  }
  FakeWS.instances = [];
  const factory = vi.fn((url: string) => new FakeWS(url));
  const cp = new ControlPlane({
    gatewayUrl: "http://localhost:8643",
    deviceId: "test-dev",
    bus,
    getState: () => "idle",
    firmwareVersion: "0.0.1",
    wsFactory: factory as unknown as ControlPlaneOptions["wsFactory"],
    ...overrides,
  });
  return { cp, bus, factory, events };
}

// ----------- tests -------------------------------------------------------

describe("buildWsUrl", () => {
  it("upgrades http → ws and appends /satellite/ws + device_id", () => {
    const url = buildWsUrl("http://localhost:8643", "dev-1");
    expect(url).toBe("ws://localhost:8643/satellite/ws?device_id=dev-1");
  });

  it("upgrades https → wss", () => {
    const url = buildWsUrl("https://gw.example.com:443/", "dev-2");
    expect(url.startsWith("wss://gw.example.com")).toBe(true);
    expect(url).toContain("/satellite/ws?device_id=dev-2");
  });
});

describe("computeBackoff", () => {
  it("schedules initial → factor → ceiling", () => {
    const policy = { ...DEFAULT_RECONNECT_POLICY, jitter: 0 };
    expect(computeBackoff(policy, 1, () => 0.5)).toBe(500);
    expect(computeBackoff(policy, 2, () => 0.5)).toBe(750);
    expect(computeBackoff(policy, 3, () => 0.5)).toBe(1125);
    // Clamps to maxMs (30 000).
    expect(computeBackoff(policy, 20, () => 0.5)).toBe(30_000);
  });

  it("applies ±jitter", () => {
    const policy = { ...DEFAULT_RECONNECT_POLICY, jitter: 0.2 };
    // rng=0 → factor 0.8; rng=1 → factor 1.2
    expect(computeBackoff(policy, 1, () => 0)).toBe(400);
    expect(computeBackoff(policy, 1, () => 1)).toBe(600);
  });
});

describe("ControlPlane — connect + register + heartbeat", () => {
  it("starts connecting and sends register on open", async () => {
    const { cp, factory } = makeCp();
    const startedPromise = cp.start();
    expect(factory).toHaveBeenCalledTimes(1);
    const ws = FakeWS.instances[0]!;
    ws.triggerOpen();
    await startedPromise;
    expect(ws.sent.length).toBeGreaterThanOrEqual(1);
    const registerMsg = JSON.parse(ws.sent[0]!) as { type: string; contract_version: string };
    expect(registerMsg.type).toBe("register");
    expect(registerMsg.contract_version).toBe("0.2.0");
    cp.stop();
  });

  it("dispatches inbound `adoption` → bus event", () => {
    const { cp, events } = makeCp();
    void cp.start();
    const ws = FakeWS.instances[0]!;
    ws.triggerOpen();
    ws.triggerMessage(JSON.stringify({ type: "registered", adoption_state: "adopted" }));
    const adoption = events.find((e) => e.name === "adoption");
    expect(adoption).toBeDefined();
    expect((adoption?.payload as { state: string }).state).toBe("adopted");
    cp.stop();
  });

  it("dispatches inbound `log_entry` → bus `log` event", () => {
    const { cp, events } = makeCp();
    void cp.start();
    FakeWS.instances[0]!.triggerOpen();
    FakeWS.instances[0]!.triggerMessage(
      JSON.stringify({
        type: "log_entry",
        entry: {
          ts: "2026-05-20T15:00:00Z",
          level: "INFO",
          source: "agent",
          message: "test",
        },
      }),
    );
    const log = events.find((e) => e.name === "log");
    expect(log).toBeDefined();
    expect((log?.payload as { source: string }).source).toBe("agent");
    cp.stop();
  });

  it("unknown WS type → emits transient_error", () => {
    const { cp, events } = makeCp();
    void cp.start();
    FakeWS.instances[0]!.triggerOpen();
    FakeWS.instances[0]!.triggerMessage('{"type":"some_future_event"}');
    const transient = events.find((e) => e.name === "transient_error");
    expect(transient).toBeDefined();
    cp.stop();
  });

  it("send() is a no-op when WS is not open", () => {
    const { cp } = makeCp();
    // Without start() → no WS → send is a silent no-op.
    expect(() =>
      cp.send({
        type: "heartbeat",
        device_id: "x",
        state: "idle",
        uptime_s: 0,
        firmware_version: "0.0.0",
      }),
    ).not.toThrow();
  });

  it("stop() closes the WS and cancels heartbeat", () => {
    const { cp } = makeCp();
    void cp.start();
    const ws = FakeWS.instances[0]!;
    ws.triggerOpen();
    cp.stop();
    expect(ws.closeCalls).toBeGreaterThanOrEqual(1);
  });
});
