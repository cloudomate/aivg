import { describe, it, expect } from "vitest";
import { LOG_LEVELS, filterMinLevel, filterBySource, type LogLevel } from "../../src/logs";
import type { LogEntry } from "../../src/events";
import {
  ControlPlane,
  type WebSocketLike,
  type ControlPlaneOptions,
} from "../../src/control-plane";
import { EventBus, type SatelliteEvents } from "../../src/events";

const entry = (level: LogLevel, source: string): LogEntry => ({
  ts: "2026-05-20T15:00:00Z",
  level,
  source,
  message: `${level} from ${source}`,
});

describe("log filter helpers", () => {
  it("LOG_LEVELS is the ordered closed set", () => {
    expect(LOG_LEVELS).toEqual(["DEBUG", "INFO", "WARN", "ERROR"]);
  });

  it("filterMinLevel(INFO) → DEBUG=false, INFO/WARN/ERROR=true", () => {
    expect(filterMinLevel(entry("DEBUG", "x"), "INFO")).toBe(false);
    expect(filterMinLevel(entry("INFO", "x"), "INFO")).toBe(true);
    expect(filterMinLevel(entry("WARN", "x"), "INFO")).toBe(true);
    expect(filterMinLevel(entry("ERROR", "x"), "INFO")).toBe(true);
  });

  it("filterBySource limits to a closed source set", () => {
    expect(filterBySource(entry("INFO", "agent"), ["agent", "asr"])).toBe(true);
    expect(filterBySource(entry("INFO", "gateway"), ["agent", "asr"])).toBe(false);
  });
});

// ----------- end-to-end via control-plane -------------------------------

class FakeWS implements WebSocketLike {
  static instances: FakeWS[] = [];
  public readonly url: string;
  public readyState = 0;
  public onopen: WebSocketLike["onopen"] = null;
  public onclose: WebSocketLike["onclose"] = null;
  public onerror: WebSocketLike["onerror"] = null;
  public onmessage: WebSocketLike["onmessage"] = null;
  constructor(url: string) {
    this.url = url;
    FakeWS.instances.push(this);
  }
  send(): void {}
  close(): void {
    this.readyState = 3;
    this.onclose?.call(this, { code: 1000 } as CloseEvent);
  }
  triggerOpen(): void {
    this.readyState = 1;
    this.onopen?.call(this, new Event("open"));
  }
  triggerMessage(raw: string): void {
    this.onmessage?.call(this, { data: raw } as MessageEvent<string>);
  }
}

describe("control-plane → log forwarding", () => {
  it("`log_entry` WS message → `log` bus event with all fields preserved", () => {
    FakeWS.instances = [];
    const bus = new EventBus<SatelliteEvents>();
    const seen: LogEntry[] = [];
    bus.on("log", (e) => seen.push(e));
    const cp = new ControlPlane({
      gatewayUrl: "http://localhost:8643",
      deviceId: "dev-log",
      bus,
      getState: () => "idle",
      firmwareVersion: "0.0.1",
      wsFactory: ((url: string) => new FakeWS(url)) as unknown as ControlPlaneOptions["wsFactory"],
    });
    void cp.start();
    const ws = FakeWS.instances[0]!;
    ws.triggerOpen();
    ws.triggerMessage(
      JSON.stringify({
        type: "log_entry",
        entry: {
          ts: "2026-05-20T15:46:25Z",
          level: "INFO",
          source: "agent",
          message: "conversation turn started",
          meta: { session_id: "s7" },
        },
      }),
    );
    expect(seen).toHaveLength(1);
    expect(seen[0]!.level).toBe("INFO");
    expect(seen[0]!.source).toBe("agent");
    expect(seen[0]!.message).toBe("conversation turn started");
    expect(seen[0]!.meta).toEqual({ session_id: "s7" });
    cp.stop();
  });
});
