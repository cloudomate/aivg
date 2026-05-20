# Contract: `sat-cli` — Satellite Management CLI

**Feature**: `011-satellite-management` · **Plan**: [../plan.md](../plan.md) ·
**Version**: 1.0.0 · **Companions**:
[management-api.yaml](./management-api.yaml),
[management-ws.md](./management-ws.md)

`sat-cli` is the **platform-neutral** management CLI (constitution v2.0.0
Principle IV). It is a separate binary from any agent platform's own CLI
(distinct from `hermes`). The Hermes agent skill and any other per-platform
skill invoke `sat-cli` as their single execution surface; agents and
scripts consume the JSON output documented below.

## Binary

- Package: `sat_cli` (Python).
- Entry point in `pyproject.toml`: `console_scripts = sat-cli = sat_cli.cli:app`.
- Help: `sat-cli --help`, `sat-cli <subcommand> --help`.
- Version & contract: `sat-cli --version` (binary version),
  `sat-cli --contract-version` (semver of this contract — `1.0.0` for v1).

## Global flags

| Flag | Env | Default | Meaning |
|---|---|---|---|
| `--gateway URL` | `SAT_GATEWAY_URL` | `http://localhost:8643` | Management plane base URL. |
| `--json` | `SAT_JSON=1` | off | Emit one NDJSON line per output (see envelope below). Required for agent consumption. |
| `--yes` / `-y` | — | off | Skip the interactive confirmation on destructive actions (`factory_reset`, `delete`). |
| `--timeout SECONDS` | `SAT_TIMEOUT` | `10` | Per-request HTTP timeout. |
| `--verbose` | — | off | Human mode: include extra detail. (Ignored under `--json`.) |
| `--no-color` | `NO_COLOR=1` | (auto) | Disable Rich colors. (Always off under `--json`.) |

## JSON envelope (FR-006, R-8)

Under `--json`, every command writes **one newline-terminated JSON object
per output unit** on stdout. Stderr stays for human progress/errors only.

```json
{
  "ok": true,
  "data": { ... command-specific ... },
  "error": null,
  "v": 1
}
```

On failure:

```json
{
  "ok": false,
  "data": null,
  "error": { "code": "device_offline", "message": "kitchen is offline" },
  "v": 1
}
```

- `v` is the envelope version (1 for this contract).
- `error.code` is one of a closed set (below). `error.message` is
  human-readable; agents key off `code`.
- Streaming commands (`logs follow`, `watch`) emit one envelope per line
  (NDJSON). Each line stands alone.

### Stable `error.code` set (v1)

`bad_input` · `unknown_device` · `device_offline` · `gateway_unreachable` ·
`device_limit_reached` · `already_adopted` · `browser_not_ota_eligible` ·
`ota_in_progress` · `ota_failed` · `rolled_back` · `ble_unavailable` ·
`ble_provisioning_failed` · `improv_timeout` · `wifi_join_failed` ·
`config_conflict` · `internal_error`.

Adding new codes is a minor bump (additive). Removing or renaming is a
major bump.

## Exit codes (R-9)

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | User input / bad command / unknown device / config conflict. |
| 2 | Device offline or unreachable for the requested action. |
| 3 | Gateway unreachable (network, wrong URL). |
| 4 | BLE / Improv provisioning failure on the host. |
| 5 | OTA failure (device reported `failed` or `rolled_back`). |
| 64+ | Reserved. |

## Commands

All commands accept `--json`. Output `data` shape is per command.

### `sat-cli list`

List the fleet.

- Flags: `--state {all|adopted|pending}` (default `all`).
- JSON `data`: `DeviceSummary[]` from `management-api.yaml`.
- Human: a one-line-per-device table; status dots agree with state colors.

### `sat-cli watch`

Long-running fleet/device watcher; emits one NDJSON envelope per change
event (state_update, device added/removed, OTA progress) consumed from the
gateway's SSE state stream.

- Flags: `--device DEVICE_ID` (default: whole fleet).
- Exit: only on Ctrl+C, gateway loss (code 3), or signal.

### `sat-cli device get DEVICE_ID`

Full state of one device (`GET /satellite/{id}/state`).

### `sat-cli device config get DEVICE_ID`

Running config (`GET /satellite/{id}/config`).

### `sat-cli device config set DEVICE_ID --field VALUE ...`

Partial config update (`POST /satellite/{id}/config`).

- Repeated `--field key=value` pairs OR `--from-file PATH` (JSON file).
- Optional `--if-match VERSION` for optimistic concurrency (R-11).
- Optional `--queue` to allow queueing if the device is offline (else
  `device_offline` is returned per FR-016).

### `sat-cli device config schema DEVICE_ID`

`GET /satellite/{id}/config/schema` — JSON Schema for editable fields.
Used by skills/UI to know which fields exist.

### `sat-cli device command DEVICE_ID VERB [--args JSON]`

Send a command (`POST /satellite/{id}/command`). `VERB` is one of:
`reboot`, `restart-voice`, `restart-manager`, `reset-config`,
`factory-reset`, `mute`, `unmute`, `identify`.

- Destructive verbs (`factory-reset`) require an interactive confirmation
  prompt unless `--yes` is passed (FR-019).
- Maps to `CommandRequest { command, args }` over REST.

### `sat-cli device delete DEVICE_ID`

Unpair (`DELETE /satellite/{id}`). Destructive — confirmation required
unless `--yes`.

### `sat-cli logs DEVICE_ID [--follow] [--level X] [--source S] [--since T]`

Tail logs. Without `--follow`, prints recent entries and exits. With
`--follow`, streams indefinitely (one NDJSON envelope per `LogEntry` under
`--json`).

### `sat-cli fleet logs [--follow] [--device D] [--level X] [--source S]`

Aggregate fleet log (`GET /satellite/logs`). Same flags as `logs`.

### `sat-cli onboard [--ssid X --password Y] [--gateway URL] [--name N]`

Local Improv-over-BLE provisioning + adopt (R-2, FR-010). Steps:

1. Scan BLE for an unprovisioned Improv-Wifi peripheral (timeout
   `--scan-timeout`, default 30 s).
2. Send Wi-Fi credentials + optional gateway hint via Improv RPC.
3. Wait for the device to report it has joined Wi-Fi.
4. Poll `POST /satellite/register` arrival for that device id (timeout
   `--register-timeout`, default 90 s).
5. Call `POST /satellite/{id}/adopt { name }` and print the resulting
   `DeviceState`.

Failure modes return specific exit codes (4 for BLE/Improv, others
mapping to REST). Without `--name`, an interactive prompt collects it
(skipped under `--json`/`--yes` which then requires `--name`).

### `sat-cli ota check DEVICE_ID`

`POST /satellite/{id}/ota/check`. Browser device → `browser_not_ota_eligible`.

### `sat-cli ota apply DEVICE_ID VERSION [--follow]`

`POST /satellite/{id}/ota/apply`. With `--follow`, attach to the device's
log stream filtered to `source=ota` and emit each progress event as an
NDJSON envelope until terminal state (success / failed / rolled_back).

### `sat-cli ota manifest DEVICE_ID`

`GET /satellite/{id}/ota/manifest` — the device-type manifest.

## Help / version expectations

- `sat-cli --help` and per-command `--help` print Typer's standard
  usage; the help text is **part of the contract** insofar as flag names
  and required arguments are stable across v1.x.
- `sat-cli --json --version` writes `{"ok":true,"data":{"version":"x.y.z","contract_version":"1.0.0"},"error":null,"v":1}`.

## Versioning (R-13)

- Contract version semver:
  - **MAJOR**: removed/renamed command, removed/renamed flag, removed
    error code, changed envelope shape, changed exit-code meaning.
  - **MINOR**: added command, added optional flag, added error code,
    added field inside `data`.
  - **PATCH**: typo, help-text, performance.
- Coordinated bumps: any contract change that crosses REST + WS + CLI
  bumps all three in lockstep.

## Non-goals

- `sat-cli` does **NOT** know which agent platform is active. Platform
  selection is server-side. Constitution v2.0.0 Principle IV: no
  `if platform == "hermes":` in the CLI.
- `sat-cli` does **NOT** implement device-firmware OTA; it only initiates
  the gateway-orchestrated flow.
- `sat-cli` does **NOT** speak the device control WS — it only consumes
  REST + SSE.
