/**
 * Operator-issued command surface (US2 / FR-006).
 *
 * The actual WS dispatch + reply-channel construction lives in
 * control-plane.ts (it's the message owner). This module owns:
 *
 *   - the closed-set verb validator (so unknown verbs trigger
 *     transient_error rather than silently invoking a handler);
 *   - typed helpers for consumers building command-result payloads.
 *
 * Verbs (closed set per feature-011 R-14, mirrored in
 * data-model.md §7): reboot | restart | refresh_config | tail_logs | ping.
 */

import type { CommandResult } from "./events";

export const KNOWN_COMMAND_VERBS = [
  "reboot",
  "restart",
  "refresh_config",
  "tail_logs",
  "ping",
] as const;

export type CommandVerb = (typeof KNOWN_COMMAND_VERBS)[number];

export function isKnownVerb(verb: string): verb is CommandVerb {
  return (KNOWN_COMMAND_VERBS as readonly string[]).includes(verb);
}

/** Convenience builders for the typical success/failure shapes. */
export const commandResult = {
  ok(message?: string, data?: Record<string, unknown>): CommandResult {
    const out: CommandResult = { ok: true };
    if (message !== undefined) out.message = message;
    if (data !== undefined) out.data = data;
    return out;
  },
  fail(message: string, data?: Record<string, unknown>): CommandResult {
    const out: CommandResult = { ok: false, message };
    if (data !== undefined) out.data = data;
    return out;
  },
} as const;

/**
 * Re-exported here so consumers can type-narrow command handlers
 * without reaching into `./events`.
 */
export type { CommandEvent, CommandResult } from "./events";
