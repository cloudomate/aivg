/**
 * Hand-rolled satellite lifecycle state machine.
 *
 * Per data-model.md §2: `idle | listening | speaking | error`. Pure
 * function (`transition`) so the FSM is trivially testable and the
 * exhaustive switch lets TypeScript catch unhandled (state, event) pairs.
 *
 * NOT a `class`. The owning `Satellite` instance holds the current state
 * and calls `transition()` from its event handlers.
 */

export type SatelliteState = "idle" | "listening" | "speaking" | "error";

/**
 * Events that drive transitions. These are internal — distinct from the
 * public event bus events. The bus events that map onto FSM events are
 * dispatched by the owning Satellite class.
 */
export type SatelliteFsmEvent =
  | { kind: "begin_session_resolved" }
  | { kind: "first_remote_audio" }
  | { kind: "session_ended" }
  | { kind: "end_session_resolved" }
  | { kind: "fatal_error" }
  | { kind: "recover" };

/**
 * Compute the next state given the current state + an event. Pure;
 * idempotent for impossible transitions (returns the input state).
 *
 * Per data-model.md §2's transition table:
 *  | From       | Event                       | To          |
 *  |-----------|-----------------------------|-------------|
 *  | idle      | begin_session_resolved      | listening   |
 *  | listening | first_remote_audio          | speaking    |
 *  | listening | end_session_resolved        | idle        |
 *  | speaking  | session_ended               | idle        |
 *  | speaking  | end_session_resolved        | idle        |
 *  | any       | fatal_error                 | error       |
 *  | error     | recover                     | idle        |
 */
export function transition(state: SatelliteState, event: SatelliteFsmEvent): SatelliteState {
  // `fatal_error` is the universal trapdoor — handle first so every state
  // routes through one branch.
  if (event.kind === "fatal_error") return "error";

  switch (state) {
    case "idle":
      if (event.kind === "begin_session_resolved") return "listening";
      return state;

    case "listening":
      if (event.kind === "first_remote_audio") return "speaking";
      if (event.kind === "end_session_resolved") return "idle";
      if (event.kind === "session_ended") return "idle";
      return state;

    case "speaking":
      if (event.kind === "session_ended") return "idle";
      if (event.kind === "end_session_resolved") return "idle";
      return state;

    case "error":
      if (event.kind === "recover") return "idle";
      return state;

    default: {
      // Exhaustiveness check — TypeScript flags any state we forgot.
      const _exhaustive: never = state;
      return _exhaustive;
    }
  }
}
