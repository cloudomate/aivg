import { describe, it, expect } from "vitest";
import { AdoptionTracker } from "../../src/adoption";
import { EventBus, type SatelliteEvents } from "../../src/events";

describe("AdoptionTracker", () => {
  function build() {
    const bus = new EventBus<SatelliteEvents>();
    const tracker = new AdoptionTracker();
    tracker.attach(bus);
    const seen: { state: string; firstApproval: boolean }[] = [];
    bus.on("adoption", (e) => seen.push({ state: e.state, firstApproval: e.firstApproval }));
    return { bus, tracker, seen };
  }

  it("starts in `pending`", () => {
    const { tracker } = build();
    expect(tracker.state).toBe("pending");
    expect(tracker.hasBeenAdopted).toBe(false);
  });

  it("pending → adopted: firstApproval=true exactly once", () => {
    const { bus, tracker, seen } = build();
    bus.emit("adoption", { state: "adopted", firstApproval: false });
    expect(tracker.state).toBe("adopted");
    expect(tracker.hasBeenAdopted).toBe(true);
    expect(seen.find((e) => e.firstApproval)?.state).toBe("adopted");
    // Find only the re-emitted (truthy firstApproval) once.
    const firstApprovals = seen.filter((e) => e.firstApproval);
    expect(firstApprovals).toHaveLength(1);
  });

  it("re-affirmations of `adopted` do not fire firstApproval again", () => {
    const { bus, tracker, seen } = build();
    bus.emit("adoption", { state: "adopted", firstApproval: false });
    bus.emit("adoption", { state: "adopted", firstApproval: false });
    bus.emit("adoption", { state: "adopted", firstApproval: false });
    const firstApprovals = seen.filter((e) => e.firstApproval);
    expect(firstApprovals).toHaveLength(1);
    expect(tracker.hasBeenAdopted).toBe(true);
  });

  it("preserves the raw event for downstream listeners (pending after adopted)", () => {
    // Gateway should never actually flip back, but the tracker shouldn't
    // crash if it sees `pending` after `adopted`.
    const { bus, tracker } = build();
    bus.emit("adoption", { state: "adopted", firstApproval: false });
    bus.emit("adoption", { state: "pending", firstApproval: false });
    expect(tracker.state).toBe("pending");
    expect(tracker.hasBeenAdopted).toBe(true); // sticky
  });

  it("ignores its own re-emitted events (no infinite loop)", () => {
    const { bus, seen } = build();
    bus.emit("adoption", { state: "adopted", firstApproval: false });
    // The tracker re-emits with firstApproval=true. If we get caught in
    // a loop the test would hang. We just assert the count is bounded.
    expect(seen.length).toBeLessThan(10);
  });
});
