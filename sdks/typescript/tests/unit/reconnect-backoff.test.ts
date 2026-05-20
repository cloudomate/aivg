import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  computeBackoff,
  DEFAULT_RECONNECT_POLICY,
  ControlPlane,
  type WebSocketLike,
} from "../../src/control-plane";
import { EventBus, type SatelliteEvents } from "../../src/events";

describe("computeBackoff — schedule + jitter (R-6)", () => {
  it("initial 500 → ×1.5 → 30 000 ceiling", () => {
    const p = { ...DEFAULT_RECONNECT_POLICY, jitter: 0 };
    expect(computeBackoff(p, 1, () => 0.5)).toBe(500);
    expect(computeBackoff(p, 2, () => 0.5)).toBe(750);
    expect(computeBackoff(p, 3, () => 0.5)).toBe(1125);
    expect(computeBackoff(p, 4, () => 0.5)).toBe(1688);
    expect(computeBackoff(p, 5, () => 0.5)).toBe(2531);
  });

  it("clamps to maxMs (30 000)", () => {
    const p = { ...DEFAULT_RECONNECT_POLICY, jitter: 0 };
    expect(computeBackoff(p, 99, () => 0.5)).toBe(30_000);
  });

  it("respects ±jitter window (±20%)", () => {
    const p = { ...DEFAULT_RECONNECT_POLICY, jitter: 0.2 };
    // attempt 3 base = 1125. With ±20% it lives in [900, 1350].
    for (let i = 0; i < 100; i++) {
      const v = computeBackoff(p, 3, Math.random);
      expect(v).toBeGreaterThanOrEqual(900);
      expect(v).toBeLessThanOrEqual(1350);
    }
  });

  it("attempt < 1 is normalised to 1", () => {
    const p = { ...DEFAULT_RECONNECT_POLICY, jitter: 0 };
    expect(computeBackoff(p, 0, () => 0.5)).toBe(500);
    expect(computeBackoff(p, -5, () => 0.5)).toBe(500);
  });
});

// ----------- integration of compute + reconnect timer -------------------

class FakeWSReconnect implements WebSocketLike {
  static instances: FakeWSReconnect[] = [];
  public readyState = 0;
  public onopen: WebSocketLike["onopen"] = null;
  public onclose: WebSocketLike["onclose"] = null;
  public onerror: WebSocketLike["onerror"] = null;
  public onmessage: WebSocketLike["onmessage"] = null;
  constructor(public readonly url: string) {
    FakeWSReconnect.instances.push(this);
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
  remoteClose(): void {
    this.readyState = 3;
    this.onclose?.call(this, { code: 1006, wasClean: false } as CloseEvent);
  }
}

describe("ControlPlane — reconnect with fake timers", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    FakeWSReconnect.instances = [];
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("max_retries=N — emits ws_max_retries_exceeded after N attempts", async () => {
    const bus = new EventBus<SatelliteEvents>();
    const errors: unknown[] = [];
    bus.on("error", (e) => errors.push(e));

    const cp = new ControlPlane({
      gatewayUrl: "http://localhost:8643",
      deviceId: "dev-x",
      bus,
      getState: () => "idle",
      firmwareVersion: "0.0.0",
      wsFactory: (url) => new FakeWSReconnect(url),
      reconnectPolicy: {
        ...DEFAULT_RECONNECT_POLICY,
        initialMs: 1,
        factor: 1,
        maxMs: 1,
        jitter: 0,
        maxRetries: 2,
      },
    });
    const start = cp.start();
    // Catch the rejection so it doesn't propagate to the test runner.
    const startFailed = start.catch((e: unknown) => e);

    // First connect: open, then remote-close.
    FakeWSReconnect.instances[0]!.open();
    FakeWSReconnect.instances[0]!.remoteClose();
    // First reconnect attempt fires after 1 ms — open and close again.
    await vi.advanceTimersByTimeAsync(2);
    FakeWSReconnect.instances[1]!.open();
    FakeWSReconnect.instances[1]!.remoteClose();
    // Second attempt — open and close.
    await vi.advanceTimersByTimeAsync(2);
    FakeWSReconnect.instances[2]!.open();
    FakeWSReconnect.instances[2]!.remoteClose();
    // Third attempt should be the one that exceeds maxRetries=2.
    await vi.advanceTimersByTimeAsync(2);

    await startFailed;
    expect(errors.length).toBeGreaterThan(0);
    const err = errors[0] as { code: string };
    expect(err.code).toBe("ws_max_retries_exceeded");
    cp.stop();
  });
});
