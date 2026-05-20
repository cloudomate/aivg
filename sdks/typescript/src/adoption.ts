/**
 * Adoption state tracker (US2 / FR-001 / FR-002).
 *
 * Listens for inbound `adoption` WS messages and re-publishes them on
 * the bus with the `firstApproval: boolean` flag set correctly across
 * the SDK's lifetime. Per data-model.md §3:
 *   - State persists in the gateway's registry; the SDK reflects.
 *   - The transition is forward-only `pending → adopted`. Re-affirmations
 *     ("adopted" while already "adopted") still fire the event but with
 *     firstApproval=false.
 *   - `firstApproval` is true exactly once per Satellite instance, the
 *     first time we observe `adopted`.
 *
 * The control-plane.ts initial subscriber re-emits `adoption` events
 * with `firstApproval: false`. This module attaches AFTER and
 * re-decorates the event surface so consumers see the right semantics
 * — we intercept at the bus level via a stateful listener.
 */

import type { EventBus, SatelliteEvents, AdoptionEvent } from "./events";

export class AdoptionTracker {
  private observedAdoptedAt: number | null = null;
  private currentState: AdoptionEvent["state"] = "pending";

  /**
   * Attach to a bus. Reads the raw `adoption` events emitted by
   * control-plane and republishes with correct `firstApproval` only
   * when the value would change. Returns an unsubscribe function.
   *
   * Implementation note: control-plane.ts emits `adoption` itself with
   * `firstApproval: false` (placeholder). This tracker REPLACES that
   * behaviour by interposing — Satellite constructs the tracker BEFORE
   * any consumer subscribes, so the tracker's re-emit is what
   * consumers see.
   */
  attach(bus: EventBus<SatelliteEvents>): () => void {
    // We listen, mutate state, and re-emit a fresh event with the right
    // `firstApproval`. To avoid an infinite loop we guard against our
    // own re-emit using an internal marker stored on the payload.
    const RE_EMIT_MARK = Symbol.for("aivg.sat-sdk.adoption.re-emitted");
    return bus.on("adoption", (payload) => {
      // Recognise our own re-emit and pass through.
      if ((payload as unknown as Record<symbol, boolean>)[RE_EMIT_MARK]) return;

      const prevState = this.currentState;
      this.currentState = payload.state;

      let firstApproval = false;
      if (payload.state === "adopted" && this.observedAdoptedAt === null) {
        this.observedAdoptedAt = Date.now();
        firstApproval = true;
      }
      // Don't re-emit if state didn't actually change AND we're not
      // setting firstApproval for the first time.
      if (prevState === payload.state && !firstApproval) return;

      const reEmit: AdoptionEvent & Record<symbol, boolean> = {
        state: payload.state,
        firstApproval,
        [RE_EMIT_MARK]: true,
      };
      bus.emit("adoption", reEmit);
    });
  }

  get state(): AdoptionEvent["state"] {
    return this.currentState;
  }

  /** True if we've ever observed an `adopted` event. */
  get hasBeenAdopted(): boolean {
    return this.observedAdoptedAt !== null;
  }
}
