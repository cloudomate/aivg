/**
 * Typed event bus + the canonical `SatelliteEvents` event map.
 *
 * Per data-model.md §11. We use a hand-rolled bus over Node's
 * `EventEmitter` / `EventTarget`:
 *   - `EventEmitter` is Node-only — needs a polyfill in browsers.
 *   - `EventTarget` is everywhere but its typings are weak.
 * A bare typed Map of Sets is plenty for our needs and weighs nothing.
 *
 * Handler exceptions are caught and logged via `console.error`; one bad
 * handler MUST NOT break other handlers (parity with browser
 * `EventTarget` semantics, contract: satellite-api.md "Event surface").
 */

import type { SatelliteState } from "./state";
import type { SdkError, TransientError } from "./errors";

// ---------- payload shapes (mirrored from data-model.md §11) ----------

export interface StateChangePayload {
  previous: SatelliteState;
  current: SatelliteState;
}

export interface AdoptionEvent {
  state: "pending" | "adopted";
  /** True the first time we observe `adopted` for this device. */
  firstApproval: boolean;
}

export interface SatelliteConfig {
  wakeWord: string;
  routingMode: "preferred" | "any" | "off";
  logLevel: "debug" | "info" | "warn" | "error";
  heartbeatInterval: number;
  extra: Record<string, unknown>;
  version: number;
}

export interface CommandEvent {
  verb: "reboot" | "restart" | "refresh_config" | "tail_logs" | "ping";
  args: Record<string, unknown>;
  /** Reply channel — invoke with the result; SDK forwards over WS. */
  reply: (result: CommandResult) => void;
}

export interface CommandResult {
  ok: boolean;
  message?: string;
  data?: Record<string, unknown>;
}

export interface LogEntry {
  ts: string;
  level: "DEBUG" | "INFO" | "WARN" | "ERROR";
  source: string;
  message: string;
  meta?: Record<string, unknown>;
}

export interface OtaManifest {
  version: string;
  url: string;
  sha256?: string;
  manifestId: string;
  applyBy?: string;
}

export interface OtaProgress {
  manifestId: string;
  state: "checking" | "downloading" | "flashing" | "rebooting" | "idle" | "failed";
  progress?: number;
  message?: string;
}

export interface TranscriptDelta {
  speaker: "user" | "assistant";
  text: string;
  final: boolean;
  seq: number;
  ts: number;
}

export interface ToolCallEvent {
  type: "tool_call_started" | "tool_call_completed" | "tool_call_failed";
  toolName: string;
  resultSummary?: string;
  error?: string;
  ts: number;
}

export interface SkillEvent {
  type: "skill_loaded";
  skillName: string;
  source: "built-in" | "plugin" | "tap";
  ts: number;
}

export interface RemoteStreamEvent {
  stream: MediaStream;
}

export interface VoiceSession {
  sessionId: string;
  startedAt: number;
  ended: Promise<VoiceSessionResult>;
}

export interface VoiceSessionResult {
  endedAt: number;
  turnCount: number;
  reason:
    | "operator_ended"
    | "gateway_closed"
    | "ice_failed"
    | "ws_disconnected"
    | "fatal_error";
  error?: SdkError;
}

// ---------- the canonical event map ---------------------------------

export interface SatelliteEvents {
  state: StateChangePayload;
  adoption: AdoptionEvent;
  config_changed: SatelliteConfig;
  command: CommandEvent;
  log: LogEntry;
  ota_manifest: OtaManifest;
  ota_progress: OtaProgress;
  transcript: TranscriptDelta;
  tool_call: ToolCallEvent;
  skill: SkillEvent;
  remote_stream: RemoteStreamEvent;
  session_started: VoiceSession;
  session_ended: VoiceSessionResult;
  error: SdkError;
  transient_error: TransientError;
}

// ---------- typed bus ------------------------------------------------

type Handler<T> = (payload: T) => void;
type Unsubscribe = () => void;

// `any` here is the published surface for the *value* type, not the *key*.
// The class is consumed via EventBus<SatelliteEvents> where each event has
// its own concrete payload type; the internal Map only needs to carry a
// loose value to handle the heterogeneous payloads. The public on/off/emit
// signatures are strongly typed via the M[E] indexing.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export class EventBus<M extends Record<string, any>> {
  private readonly listeners = new Map<keyof M, Set<Handler<M[keyof M]>>>();

  on<E extends keyof M>(event: E, handler: Handler<M[E]>): Unsubscribe {
    let set = this.listeners.get(event);
    if (!set) {
      set = new Set();
      this.listeners.set(event, set);
    }
    set.add(handler as Handler<M[keyof M]>);
    return () => { this.off(event, handler); };
  }

  off<E extends keyof M>(event: E, handler: Handler<M[E]>): void {
    this.listeners.get(event)?.delete(handler as Handler<M[keyof M]>);
  }

  emit<E extends keyof M>(event: E, payload: M[E]): void {
    const set = this.listeners.get(event);
    if (!set || set.size === 0) return;
    // Snapshot so a handler that unsubscribes mid-iteration doesn't
    // corrupt the iterator state.
    for (const h of [...set]) {
      try {
        (h as Handler<M[E]>)(payload);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error(`[aivg/sat-sdk] handler for "${String(event)}" threw:`, err);
      }
    }
  }

  /** For test introspection; not exported on the public surface. */
  listenerCount<E extends keyof M>(event: E): number {
    return this.listeners.get(event)?.size ?? 0;
  }
}

// ---------- async-iterator sugar -------------------------------------

/**
 * Bounded-queue async iterator backed by an `EventBus`. When the queue
 * exceeds `maxBuffer`, the OLDEST item is dropped and a `transient_error`
 * (code `buffer_overflow`) is emitted on the bus per contract.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function iterate<M extends Record<string, any>, E extends keyof M>(
  bus: EventBus<M>,
  event: E,
  opts: { maxBuffer?: number } = {},
): AsyncIterableIterator<M[E]> {
  const maxBuffer = opts.maxBuffer ?? 1024;
  const queue: M[E][] = [];
  const waiters: ((v: IteratorResult<M[E]>) => void)[] = [];
  let closed = false;

  const unsubscribe = bus.on(event, (payload) => {
    if (closed) return;
    const w = waiters.shift();
    if (w) {
      w({ value: payload, done: false });
      return;
    }
    queue.push(payload);
    if (queue.length > maxBuffer) {
      queue.shift();
      // Best-effort overflow signal — emit on the same bus so consumers
      // notice. Cast: TransientError is in the SatelliteEvents map under
      // "transient_error"; if the consuming bus doesn't have that event
      // type the emit is a no-op (no listeners).
      (
        bus as unknown as { emit: (e: string, p: unknown) => void }
      ).emit("transient_error", {
        code: "buffer_overflow",
        message: `async iterator over "${String(event)}" dropped an event`,
        retryInMs: 0,
        attempt: 1,
      });
    }
  });

  const iter: AsyncIterableIterator<M[E]> = {
    [Symbol.asyncIterator](): AsyncIterableIterator<M[E]> {
      return iter;
    },
    next(): Promise<IteratorResult<M[E]>> {
      if (queue.length > 0) {
        return Promise.resolve({ value: queue.shift()!, done: false });
      }
      if (closed) return Promise.resolve({ value: undefined as never, done: true });
      return new Promise((res) => waiters.push(res));
    },
    return(): Promise<IteratorResult<M[E]>> {
      closed = true;
      unsubscribe();
      while (waiters.length > 0) {
        const w = waiters.shift();
        w?.({ value: undefined as never, done: true });
      }
      return Promise.resolve({ value: undefined as never, done: true });
    },
  };
  return iter;
}
