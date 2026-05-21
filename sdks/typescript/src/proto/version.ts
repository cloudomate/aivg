/**
 * Wire-protocol contract version this SDK speaks.
 *
 * Matches `aivg --contract-version` exactly. Bumping this string is a
 * breaking change to the satellite ↔ gateway protocol — coordinated with
 * the gateway side (feature 011/013).
 *
 * Per spec SC-007: shipping the SDK MUST NOT require a contract bump.
 */
export const CONTRACT_VERSION = "1.0.0";

/**
 * Package version (this SDK build). Substituted by tsup at build time via
 * `define: { __SDK_VERSION__: ... }`. Falls back to "0.0.0" if the
 * substitution didn't run (e.g. direct ts-node consumption during dev).
 */
declare const __SDK_VERSION__: string;

// eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
export const SDK_VERSION: string =
  typeof __SDK_VERSION__ !== "undefined" ? __SDK_VERSION__ : "0.0.0";
