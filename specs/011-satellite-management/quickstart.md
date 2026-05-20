# Quickstart: Satellite Management

**Feature**: `011-satellite-management` · **Plan**: [plan.md](./plan.md) ·
**Status**: design — describes the *intended* operator experience once the
plan ships. Until tasks land, the actual `sat-cli` does not exist.

This walks an operator through the five user stories from the spec, using
the platform-neutral `sat-cli` and (optionally) the Hermes agent skill.
Under constitution v2.0.0 the same flow works against any supported agent
platform plugin — Hermes here is the v1 reference.

## Prerequisites

- A gateway host running `satellite_core` with the Hermes plugin
  configured (`~/.satellite/config.yaml` has `platform: hermes`); a
  recent Hermes install with `~/.hermes/config.yaml` providing the
  STT/TTS providers.
- A BLE-capable operator host (macOS or Linux) with `sat-cli` installed
  (`pip install -e .` from the repo root after the rename lands).
- At least one device (RPi/ESP32/Electron) in your environment.

```bash
sat-cli --version              # binary version
sat-cli --contract-version     # contract semver (1.0.0 for v1)
sat-cli --gateway http://gateway.local:8643 list
```

## US1 — See the fleet (P1)

```bash
sat-cli list                                # human table
sat-cli list --json | jq '.[].data'         # for scripts/agents
sat-cli watch                               # live NDJSON stream of state changes
sat-cli logs kitchen --follow --source ota  # tail one device, OTA-only
sat-cli fleet logs --follow --level WARN    # aggregate, warnings and above
```

**Expected (human mode)**: one row per device, status dot + state label +
last-seen + STT/TTS/Wake health chips, offline devices visually
de-emphasized. The Hermes agent skill answers the same question
conversationally — see `skills/hermes-agent/SKILL.md`.

## US2 — Onboard a new headless satellite (P1)

Plug in the device. From your BLE-capable host:

```bash
sat-cli onboard \
  --ssid "MyWiFi" \
  --password "..." \
  --name "kitchen"
```

What happens:

1. `sat-cli` scans BLE for an unprovisioned Improv-Wifi peripheral.
2. Sends credentials over Improv-BLE (constitution V — local-only step
   that cannot be REST).
3. Waits for the device to register over Wi-Fi (`POST
   /satellite/register`).
4. Calls `POST /satellite/<id>/adopt { name: "kitchen" }`.
5. Prints the resulting `DeviceState`.

Failure cases each produce a specific error and exit code:

| Cause | `error.code` | Exit |
|---|---|---|
| no BLE adapter | `ble_unavailable` | 4 |
| device not in BLE range / timeout | `improv_timeout` | 4 |
| wrong password / no Wi-Fi join | `wifi_join_failed` | 4 |
| fleet limit | `device_limit_reached` | 1 |
| gateway not reachable | `gateway_unreachable` | 3 |

## US3 — Configure a satellite (P2)

```bash
sat-cli device config get kitchen
sat-cli device config schema kitchen   # see what's editable

sat-cli device config set kitchen \
  --field wake_word=hey_jarvis \
  --field vad_threshold=0.55 \
  --field output_volume=0.82

# optimistic concurrency:
sat-cli device config set kitchen \
  --if-match 7 --field wake_word=alexa
```

Conflict path: when two surfaces (CLI + agent skill) race, the second
write either lands deterministically (last-writer-wins, `config_version`
bumps) or returns `config_conflict` if `--if-match` was supplied with a
stale version. The new running value is broadcast on the device control
WS and re-emitted to `sat-cli watch`.

Offline device path: write returns `device_offline` (exit 2). Pass
`--queue` to opt into queueing-for-reconnect.

## US4 — OTA update (P2)

```bash
sat-cli ota check kitchen
sat-cli ota manifest kitchen
sat-cli ota apply kitchen 0.2.0 --follow
```

`--follow` streams progress as NDJSON (under `--json`):

```text
{"ok":true,"data":{"state":"downloading","pct":42},"error":null,"v":1}
{"ok":true,"data":{"state":"flashing"},"error":null,"v":1}
{"ok":true,"data":{"state":"rebooting"},"error":null,"v":1}
{"ok":true,"data":{"state":"idle","version":"0.2.0","result":"success"},"error":null,"v":1}
```

If the device reports `failed` or `rolled_back`, the stream emits a final
envelope with `error.code = "ota_failed"` or `"rolled_back"` and the CLI
exits 5. The device returns to a working firmware (constitution V's full-
pipeline rule applies at the device-firmware layer; the management plane
only reports the outcome).

Browser devices return `browser_not_ota_eligible` (exit 1) — the only
sanctioned per-type divergence.

## US5 — Operate & diagnose (P3)

```bash
# Non-destructive
sat-cli device command kitchen identify
sat-cli device command kitchen mute
sat-cli device command kitchen unmute

# Destructive — interactive confirmation
sat-cli device command kitchen factory-reset       # prompts: type 'kitchen' to confirm
sat-cli device delete kitchen                      # prompts to confirm
# or under --json/-y:
sat-cli device command kitchen factory-reset -y --json
```

Live diagnosis:

```bash
sat-cli logs kitchen --follow --source wake
sat-cli logs kitchen --follow --source webrtc --level WARN
```

## Via the Hermes agent skill

After installing `skills/hermes-agent/` to `~/.hermes/skills/`:

> "Onboard a new satellite called bedroom on the home Wi-Fi."
> "Set kitchen's wake word to hey jarvis."
> "Is the fleet healthy?"
> "Update bedroom to the latest firmware and tell me when it's done."

The skill shells out to `sat-cli --json` and interprets the envelope.
Under constitution v2.0.0 the same skill pattern applies for OpenClaw or
other future platforms — the *skill* is per-platform, the *CLI* is not.

## What's deliberately not in v1

- A web UI (single P3 story; not on the critical path).
- Per-device auth or TLS (LAN-only deployment; spec assumption).
- Windows host support (BLE on Windows is out of scope; SoftAP fallback
  is documented but not implemented).
- A working OpenClaw plugin (the seam is there; the implementation is a
  future feature).
