---
name: satellite-management
description: Manage the AIVG (AI Voice Gateway) satellite fleet from the Hermes agent — onboard, list, configure, command, OTA — by invoking the platform-neutral `aivg` binary. v1 Hermes-platform skill for AIVG (constitution v2.0.1).
version: 0.2.0
license: MIT
---

# Satellite management

This skill lets a Hermes agent operate the **AIVG (AI Voice Gateway)**
management plane through the platform-neutral **`aivg`** binary
(features 011 and 012). The CLI is the **single execution surface** —
the skill does not call REST directly. Other agent platforms (e.g.
OpenClaw) ship the same shape of skill in their own plugin folder; the
underlying `aivg` is shared.

> The legacy binary `sat-cli` still works for one release (deprecation
> notice on stderr). New scripts should use `aivg` directly.

## When to use this skill

- The user asks about voice satellites in the fleet: status, health, what
  a device is doing right now.
- The user wants to **onboard** a new headless satellite (Improv-over-
  BLE).
- The user wants to **configure** a device (wake word, volume, etc.).
- The user wants to **update firmware** on a device (OTA).
- The user wants to **diagnose** a misbehaving device (logs).

## Tool contract

All commands return a stable JSON envelope on stdout:

```json
{ "ok": true, "data": ..., "error": null, "v": 1 }
```

On failure:

```json
{ "ok": false, "data": null, "error": { "code": "...", "message": "..." }, "v": 1 }
```

**Always pass `--json`** so the output is machine-readable. Match on
`error.code`; do not parse human prose. The closed `error.code` set lives
in `cli-contract.md`.

Exit codes (R-9): `0` ok, `1` user/config error, `2` device offline,
`3` gateway unreachable, `4` BLE/Improv failure, `5` OTA failure.

## Example invocations

### 1. Fleet visibility (US1 — MVP)

```bash
aivg --json list
aivg --json list --state pending
aivg --json device get kitchen
aivg --json logs kitchen --level WARN
```

User says: *"is the fleet healthy?"*
→ `aivg --json list` and report any device with `status != "online"`
or `ota_state` in `{"failed","rolled_back"}` or a name in the pending
list waiting to be adopted.

User says: *"what's the kitchen satellite doing right now?"*
→ `aivg --json device get kitchen`; report `session.state` (idle /
listening / thinking / speaking) and `ota_state`.

### 2. Onboarding (US2 — Improv-over-BLE)

```bash
aivg --json onboard --ssid "MyWiFi" --password "..." --name "bedroom"
```

This is host-side (BLE) and may take ~30 s to ~5 min. Stream NDJSON
phases; report `error.code` on failure.

### 3. Configuration (US3)

```bash
aivg --json device config get kitchen
aivg --json device config schema kitchen        # what fields exist + their types

# Set a single field. Values are JSON-parsed: numbers/bools/strings work.
aivg --json device config set kitchen --field wake_word=hey_jarvis

# Optimistic concurrency: prevent overwriting a newer config the user
# didn't see. Read the running config_version first; pass it back.
aivg --json device config set kitchen \
  --if-match 7 --field vad_threshold=0.55

# Offline device → 503 device_offline by default. To queue the change:
aivg --json device config set kitchen --queue --field output_volume=0.8
```

User says: *"set the kitchen satellite wake word to hey jarvis"*
→ `aivg --json device config set kitchen --field wake_word=hey_jarvis`
and report `data.wake_word` + `data.config_version` from the response.

User says: *"show the bedroom config"*
→ `aivg --json device config get bedroom` and summarize.

### 4. OTA (US4)

```bash
aivg --json ota check kitchen
aivg --json ota manifest kitchen
aivg --json ota apply kitchen 0.2.0 --follow    # streams NDJSON progress
```

Browser devices return `browser_not_ota_eligible` (HTTP 409, exit 1) —
surface clearly: "browser satellites can't OTA update". An offline
device on `ota apply` returns `device_offline` (exit 2).

User says: *"update bedroom to the latest firmware and tell me when
it's done"*
→ first `aivg --json ota check bedroom` to find the latest version
→ then `aivg --json ota apply bedroom <latest> --follow` and report
each progress NDJSON line; on terminal `result: success` confirm
completion, on `failed` / `rolled_back` (exit 5) report the
`failure_reason`.

### 5. Diagnostics (US5)

```bash
# Non-destructive — proceed without confirmation.
aivg --json device command kitchen identify
aivg --json device command kitchen mute
aivg --json device command kitchen unmute

# Destructive — ALWAYS confirm in chat first, then add --yes.
aivg --json device command kitchen factory-reset --yes
aivg --json device delete kitchen --yes

# Live diagnosis.
aivg --json logs kitchen --follow --source webrtc --level WARN
```

User says: *"identify the kitchen satellite"*
→ `aivg --json device command kitchen identify` (non-destructive; no
confirmation needed). The device's LED should respond; report success
from the `accepted: true` envelope.

User says: *"factory-reset bedroom"*
→ **Pause and ask the user**: "Factory reset will wipe bedroom's
config and force it back into the pending list. Confirm by typing
'yes'." Only after the user confirms in chat, run
`aivg --json device command bedroom factory-reset --yes`. Without
the `--yes` flag the CLI refuses (`error.code = bad_input`), which is
the safety net — never bypass it by running without `--json`.

Destructive verbs (`factory-reset`, `device delete`) MUST be confirmed
with the user in the chat before adding `--yes`. The CLI also refuses
destructive actions under `--json` without `--yes` — that refusal is
the safety net for an agent that forgot to ask.

## Conventions

- Do not pipe through `jq` or other transforms in the suggested command
  — the agent reads the envelope directly.
- Prefer point-in-time queries; `--follow` is for live diagnosis only.
- Refuse destructive actions unless the user has explicitly confirmed.
- If the user says "the kitchen satellite" but the fleet has multiple
  matches, ask which.

## Related

- Contract: `specs/011-satellite-management/contracts/cli-contract.md`
- Constitution v2.0.0 Principle IV — this skill is one of several
  per-platform skills (OpenClaw skill is a planned sibling).
