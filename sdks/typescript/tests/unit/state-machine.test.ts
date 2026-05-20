import { describe, it, expect } from "vitest";
import { transition, type SatelliteState, type SatelliteFsmEvent } from "../../src/state";

describe("state machine — transition()", () => {
  // -------- happy-path transitions per data-model.md §2 --------

  it("idle + begin_session_resolved → listening", () => {
    expect(transition("idle", { kind: "begin_session_resolved" })).toBe("listening");
  });

  it("listening + first_remote_audio → speaking", () => {
    expect(transition("listening", { kind: "first_remote_audio" })).toBe("speaking");
  });

  it("listening + end_session_resolved → idle", () => {
    expect(transition("listening", { kind: "end_session_resolved" })).toBe("idle");
  });

  it("listening + session_ended → idle", () => {
    expect(transition("listening", { kind: "session_ended" })).toBe("idle");
  });

  it("speaking + session_ended → idle", () => {
    expect(transition("speaking", { kind: "session_ended" })).toBe("idle");
  });

  it("speaking + end_session_resolved → idle", () => {
    expect(transition("speaking", { kind: "end_session_resolved" })).toBe("idle");
  });

  it("error + recover → idle", () => {
    expect(transition("error", { kind: "recover" })).toBe("idle");
  });

  // -------- fatal_error is the universal trapdoor --------

  it.each(["idle", "listening", "speaking", "error"] as SatelliteState[])(
    "%s + fatal_error → error",
    (from) => {
      expect(transition(from, { kind: "fatal_error" })).toBe("error");
    },
  );

  // -------- impossible transitions are no-ops --------

  const impossible: { state: SatelliteState; event: SatelliteFsmEvent }[] = [
    { state: "idle", event: { kind: "first_remote_audio" } },
    { state: "idle", event: { kind: "session_ended" } },
    { state: "idle", event: { kind: "end_session_resolved" } },
    { state: "idle", event: { kind: "recover" } },
    { state: "listening", event: { kind: "begin_session_resolved" } },
    { state: "listening", event: { kind: "recover" } },
    { state: "speaking", event: { kind: "begin_session_resolved" } },
    { state: "speaking", event: { kind: "first_remote_audio" } },
    { state: "speaking", event: { kind: "recover" } },
    { state: "error", event: { kind: "begin_session_resolved" } },
    { state: "error", event: { kind: "first_remote_audio" } },
    { state: "error", event: { kind: "session_ended" } },
    { state: "error", event: { kind: "end_session_resolved" } },
  ];

  it.each(impossible)("$state + $event.kind is a no-op", ({ state, event }) => {
    expect(transition(state, event)).toBe(state);
  });
});
