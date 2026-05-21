import { describe, it, expect } from "vitest";
import { applyByExpired, sortByNewest } from "../../src/ota";
import type { OtaManifest } from "../../src/events";
import {
  ControlPlane,
  type WebSocketLike,
  type ControlPlaneOptions,
} from "../../src/control-plane";
import { EventBus, type SatelliteEvents } from "../../src/events";

const manifest = (over: Partial<OtaManifest> = {}): OtaManifest => ({
  version: "0.2.0",
  url: "https://example.com/ota.bin",
  manifestId: "m-1",
  ...over,
});

describe("ota helpers", () => {
  it("applyByExpired returns false when no deadline set", () => {
    expect(applyByExpired(manifest())).toBe(false);
  });

  it("applyByExpired honors an ISO-8601 deadline", () => {
    expect(applyByExpired(manifest({ applyBy: "2020-01-01T00:00:00Z" }))).toBe(true);
    expect(applyByExpired(manifest({ applyBy: "2099-01-01T00:00:00Z" }))).toBe(false);
  });

  it("applyByExpired returns false for malformed deadlines (forward-compat)", () => {
    expect(applyByExpired(manifest({ applyBy: "not-a-date" }))).toBe(false);
  });

  it("sortByNewest sorts version-strings descending", () => {
    const a = manifest({ version: "0.1.0", manifestId: "a" });
    const b = manifest({ version: "0.3.0", manifestId: "b" });
    const c = manifest({ version: "0.2.0", manifestId: "c" });
    expect(sortByNewest([a, b, c]).map((m) => m.manifestId)).toEqual(["b", "c", "a"]);
  });
});

// ----------- end-to-end via control-plane -------------------------------

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

describe("control-plane → OTA event forwarding", () => {
  it("forwards `ota_manifest` and `ota_progress` to typed events", () => {
    FakeWS.instances = [];
    const bus = new EventBus<SatelliteEvents>();
    const seen: { name: string; payload: unknown }[] = [];
    bus.on("ota_manifest", (e) => seen.push({ name: "ota_manifest", payload: e }));
    bus.on("ota_progress", (e) => seen.push({ name: "ota_progress", payload: e }));
    const cp = new ControlPlane({
      gatewayUrl: "http://localhost:8643",
      deviceId: "dev-ota",
      bus,
      getState: () => "idle",
      firmwareVersion: "0.0.1",
      wsFactory: ((url: string) => new FakeWS(url)) as unknown as ControlPlaneOptions["wsFactory"],
    });
    void cp.start();
    const ws = FakeWS.instances[0]!;
    ws.open();
    ws.msg(
      JSON.stringify({
        type: "ota_manifest",
        manifest: {
          version: "0.2.0",
          url: "https://example.com/ota.bin",
          sha256: "abc",
          manifest_id: "m-1",
          apply_by: "2099-01-01T00:00:00Z",
        },
      }),
    );
    ws.msg(
      JSON.stringify({
        type: "ota_progress",
        manifest_id: "m-1",
        state: "downloading",
        progress: 0.42,
      }),
    );

    expect(seen.find((e) => e.name === "ota_manifest")).toBeDefined();
    const m = seen.find((e) => e.name === "ota_manifest")!.payload as OtaManifest;
    expect(m.manifestId).toBe("m-1");
    expect(m.sha256).toBe("abc");
    expect(m.applyBy).toBe("2099-01-01T00:00:00Z");

    const p = seen.find((e) => e.name === "ota_progress")!.payload as {
      manifestId: string;
      state: string;
      progress: number;
    };
    expect(p.manifestId).toBe("m-1");
    expect(p.state).toBe("downloading");
    expect(p.progress).toBe(0.42);

    cp.stop();
  });
});
