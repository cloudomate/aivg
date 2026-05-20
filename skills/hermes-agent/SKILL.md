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
aivg --json device config set kitchen --field wake_word=hey_jarvis
```

Confirm the new running value from the response, not from the request.

### 4. OTA (US4)

```bash
aivg --json ota check kitchen
aivg --json ota apply kitchen 0.2.0 --follow
```

Browser devices return `browser_not_ota_eligible` — surface this clearly
("browser satellites can't OTA update").

### 5. Diagnostics (US5)

```bash
aivg --json device command kitchen identify --yes
aivg --json logs kitchen --follow --source webrtc --level WARN
```

Destructive verbs (`factory-reset`, `device delete`) MUST be confirmed
with the user in the chat before adding `--yes`.

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
