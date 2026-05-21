/**
 * Closed-set error codes the SDK exposes to consumers (R-11).
 *
 * Adding a code is a minor SemVer bump; removing/renaming is major.
 * Codes that overlap with `aivg --contract-version 1.0.0`'s closed
 * error-code set (`not_adopted`, `permission_denied`, `protocol_mismatch`)
 * are 1:1 with the gateway-side spelling.
 */
export type SdkErrorCode =
  | "no_webrtc_impl"
  | "no_microphone_api"
  | "permission_denied"
  | "ice_failed"
  | "ice_gathering_timeout"
  | "ws_disconnected"
  | "ws_max_retries_exceeded"
  | "signaling_failed"
  | "mixed_content"
  | "not_adopted"
  | "protocol_mismatch"
  | "duplicate_device";

/**
 * Transient error code subset. Transients don't move the FSM to `error`;
 * they're informational so consumers can render a "reconnecting…" banner.
 */
export type TransientErrorCode =
  | "ws_disconnected"
  | "signaling_retry"
  | "ice_retry"
  | "buffer_overflow";

/**
 * Fatal SDK error. Constructed via `sdkError(...)`; instances are also
 * `Error` so `try/catch` + `instanceof Error` works naturally.
 */
export class SdkError extends Error {
  public readonly code: SdkErrorCode;
  public override readonly cause?: unknown;
  public readonly ts: number;

  constructor(code: SdkErrorCode, message: string, cause?: unknown) {
    super(message);
    this.name = "SdkError";
    this.code = code;
    if (cause !== undefined) this.cause = cause;
    this.ts = Date.now();
    // Preserve prototype chain for `instanceof SdkError` across realms.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/** Factory; matches `SdkError(...)` but reads more naturally at call sites. */
export function sdkError(code: SdkErrorCode, message: string, cause?: unknown): SdkError {
  return new SdkError(code, message, cause);
}

export interface TransientError {
  code: TransientErrorCode;
  message: string;
  /** Back-off ms until the next attempt. */
  retryInMs: number;
  /** 1-based attempt counter. */
  attempt: number;
}

/** Type guard. */
export function isSdkError(value: unknown): value is SdkError {
  return value instanceof SdkError;
}
