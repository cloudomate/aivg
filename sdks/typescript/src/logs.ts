/**
 * Log-forwarding helpers (US2 / FR-021).
 *
 * The WS-side dispatch of `log_entry` → bus `log` events lives in
 * control-plane.ts. This module owns:
 *
 *   - filter helpers a consumer UI can use to subset live logs;
 *   - typed level/source constants for forward-compatible code.
 */

import type { LogEntry } from "./events";

export const LOG_LEVELS = ["DEBUG", "INFO", "WARN", "ERROR"] as const;
export type LogLevel = (typeof LOG_LEVELS)[number];

/** Inclusive ≥ filter — `filterMinLevel(entry, "WARN")` returns true for WARN+ERROR. */
export function filterMinLevel(entry: LogEntry, min: LogLevel): boolean {
  const order: Record<LogLevel, number> = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };
  return order[entry.level] >= order[min];
}

export function filterBySource(entry: LogEntry, sources: readonly string[]): boolean {
  return sources.includes(entry.source);
}

export type { LogEntry } from "./events";
