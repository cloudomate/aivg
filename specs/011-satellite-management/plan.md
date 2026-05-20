# Implementation Plan: Satellite Management — Onboard, Configure & OTA

**Branch**: `011-satellite-management` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/011-satellite-management/spec.md`
**Constitution**: v2.0.0 (amended this turn — Principle IV widened from
"Reuse Hermes" to "Reuse the Upstream Agent Platform")

## Summary

The satellite voice plane already exists (features 001/005/006/008 — Opus
WebRTC into an upstream agent platform's STT/agent/TTS) and the gateway-side
management plane is partially built in
[src/hermes_satellite_adapter/management.py](src/hermes_satellite_adapter/management.py):
`ManagementService` already implements register / heartbeat / list / state /
delete / config GET-POST / log query / control WebSocket subscription, and
[src/hermes_satellite_adapter/registry.py](src/hermes_satellite_adapter/registry.py)
holds an in-memory registry that explicitly forbids `device_type` protocol
branching (constitution II).

This feature delivers four things, under the constitution v2.0.0
agent-platform-agnostic redefinition of Principle IV:

1. **Rename + restructure** — move the existing Python package
   `hermes_satellite_adapter` → `satellite_core`. The Hermes-specific code
   (bridge to Hermes's STT/TTS/agent/endpointing) moves to
   `satellite_core/platforms/hermes/`. A new `AgentPlatform` interface lives
   at `satellite_core/platforms/base.py`. OpenClaw is sketched at
   `satellite_core/platforms/openclaw/__init__.py` (interface stub, no
   implementation in this PR — it's the canonical "second plugin" proof
   that the seam works).
2. **Finish the management plane** in `satellite_core/management/` —
   adoption flow (pending → claimed), live log streaming via SSE, the
   command verbs, the OTA endpoints with browser-no-OTA enforcement,
   aggregate fleet log, device-limit enforcement, and atomic JSON
   persistence to `~/.satellite/state.json` (note: not `~/.hermes/`,
   because the satellite core is no longer Hermes-tied — the Hermes plugin
   still reads `~/.hermes/config.yaml` for its own provider config).
3. **Ship a platform-neutral management CLI** — new package `sat_cli`,
   binary **`sat-cli`** (entry point in `pyproject.toml`). Primarily a thin
   translator from CLI calls to the REST API + control WS; also hosts the
   **local-only Improv-over-BLE provisioning** step that runs on the
   operator's BLE-capable host before the REST adopt call. Exposes a
   **stable documented command/JSON-output contract** so non-Hermes agents
   and scripts (OpenClaw skills, ad-hoc automation) are first-class
   consumers. The CLI never imports a platform plugin — platform selection
   happens server-side via `satellite_core` config.
4. **Ship per-platform agent skills** — `skills/hermes-agent/SKILL.md`
   (v1, written) and `skills/openclaw/SKILL.md` (stub). Each skill invokes
   `sat-cli --json ...` as its single execution surface. The skills are
   *thin* — they are policy + examples, not implementations.

The **optional web UI from spec FR-009 is explicitly off the critical
path** (single P3 story) and is not built in this plan.

Operator↔gateway transport is **REST** (the App. A request/response
endpoints). **SSE is retained only for live log tailing and OTA-progress**
consumed by the CLI's `watch`/`follow` modes. The **gateway↔device always-
on control WebSocket (`WS /satellite/ws`) is unchanged** and remains how
devices stay registered and how config/commands/OTA progress reach them
(constitution III).

## Technical Context

**Language/Version**: Python 3.11 (matches existing
[pyproject.toml](pyproject.toml)). Skill files are Markdown + YAML
frontmatter, no language binding.

**Primary Dependencies**:

- `satellite_core` (renamed from `hermes_satellite_adapter`): `aiohttp`
  (already there; add `aiohttp-sse` for SSE), `aiortc` (unchanged — voice),
  `dataclasses` + `Enum` (stdlib, R-4). The `AgentPlatform` interface has
  no extra deps.
- `satellite_core/platforms/hermes/`: same Hermes integration code carried
  over from the current `hermes_bridge.py` — no new deps.
- `satellite_core/platforms/openclaw/`: stub only — interface methods
  raise `NotImplementedError`. No deps.
- `sat_cli`: `typer>=0.12`, `httpx>=0.27`, `bleak>=0.22`, `rich` (humans
  only), optional `websockets>=12` if any non-SSE WS read is needed for
  watch mode.
- `skills/hermes-agent/`, `skills/openclaw/`: no Python; shell-out to
  `sat-cli`.

**Storage**: In-memory `Registry`. Persisted state goes to
`~/.satellite/state.json` (note: under `~/.satellite/`, not `~/.hermes/` —
constitution IV v2.0.0 forbids leaking satellite state into a single
platform's data directory). Firmware blobs and OTA manifests live under
`~/.satellite/firmware/<device_type>/manifest.json`.

**Testing**: `pytest` + `pytest-asyncio` (configured). Three tiers under
[tests/](tests/):

- `tests/contract/` — schema-driven REST tests against
  `contracts/management-api.yaml`; CLI ↔ REST round-trip.
- `tests/integration/` — adoption flow, SSE log stream, OTA happy +
  rollback, command verbs, concurrent config, device-limit, the
  **`AgentPlatform` seam** with a fake platform (asserts no Hermes import
  is reachable from `satellite_core` core code).
- `tests/unit/` — `ManagementService`, model invariants, Improv-BLE GATT
  framing (mock peripheral), CLI argument parsing, JSON output stability,
  persistence atomicity, **`AgentPlatform` interface contract**.

**Target Platform**: Operator host runs macOS or Linux with a working BLE
adapter (onboarding only). Gateway host is Linux/macOS. Windows: out of
scope v1.

**Project Type**: Single-repo Python project with two packages
(`satellite_core`, `sat_cli`) and a sibling `skills/` directory containing
one folder per agent platform that ships a skill.

**Performance Goals** (from spec SCs):

- Online↔offline transition reflected within one heartbeat (default 30 s);
  `sat-cli watch` catches it without re-invocation (SC-004, FR-026).
- Configuration write applied within 5 s and surviving reboot (SC-003).
- Factory-state → adopted in under 5 min (SC-001).
- 10-device fleet list output under 500 ms JSON, ≤5 s human-comprehension
  (SC-007).

**Constraints**:

- **No new STT/TTS engine, no new config loader, no new secret store**
  (constitution I & IV v2.0.0 — gated by
  `tests/unit/test_no_embedded_engines.py`).
- **No `device_type` protocol branching in the gateway** (constitution II
  — gated in `registry.py`).
- **No `platform` branching anywhere outside `satellite_core/platforms/`**
  (constitution IV v2.0.0 — new gate added in
  `tests/unit/test_no_platform_branching.py`).
- Always-on device WS must work with no active voice call (constitution
  III — already exercised).
- The management CLI is a **separate binary** from any platform's own CLI
  (clarification 2026-05-20 first batch).
- **Platform-neutral naming**: no `hermes_*` symbols outside
  `satellite_core/platforms/hermes/`.

**Scale/Scope**: 1–10 devices per gateway. Three device types (rpi, esp32,
browser; browser is OTA-exempt). Two agent platforms in v1: Hermes
(implementation), OpenClaw (interface stub).

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

Checked against **v2.0.0** (amended this turn — see
[.specify/memory/constitution.md](.specify/memory/constitution.md)).
**Status: PASS, no violations.**

| Principle | Check | Status |
|---|---|---|
| I. Thin Satellite | Plan adds no STT/TTS/agent engine; OTA serves firmware blobs only. `tests/unit/test_no_embedded_engines.py` continues to gate this against `satellite_core/`. | ✅ PASS |
| II. Generic Four-Plane Contract | New endpoints are device-type-neutral; browser-no-OTA and `echo_strategy` remain the only sanctioned per-type divergences. New gate `tests/unit/test_no_platform_branching.py` extends the same neutrality to the agent-platform axis (no `if platform_name == "hermes":` outside `platforms/`). | ✅ PASS |
| III. Separate Control/Voice Connections | Operator REST + log SSE on port 8643, unrelated to the WebRTC voice PC. Always-on `WS /satellite/ws` unchanged. Operator surfaces use REST + scoped SSE per the spec's transport clarification. | ✅ PASS |
| IV. Reuse Upstream Agent Platform (v2.0.0) | The plan defines the `AgentPlatform` interface, ships a `HermesAgentPlatform` v1 implementation, and stubs `OpenClawAgentPlatform`. `satellite_core` core code never imports a specific platform; all platform-specific code is confined under `satellite_core/platforms/<name>/`. The Hermes plugin reuses `~/.hermes/config.yaml`, Hermes's STT/TTS providers, and Hermes's logs verbatim. **The plugin seam is the v2.0.0 enabler.** | ✅ PASS |
| V. Research-Backed | Each Phase 0 decision cites a binding constraint. The OpenClaw stub is explicitly not "supported" until it passes the same end-to-end voice loop (Principle V rule added in v2.0.0). | ✅ PASS |

No violations → **Complexity Tracking table left empty.**

## Project Structure

### Documentation (this feature)

```text
specs/011-satellite-management/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── management-api.yaml   # OpenAPI 3.1 for the App. A REST surface
│   ├── management-ws.md      # gateway↔device WS message schema
│   ├── cli-contract.md       # sat-cli commands, flags, exit codes, JSON shape
│   └── agent-platform.md     # AgentPlatform Python interface (v2.0.0 seam)
├── checklists/
│   └── requirements.md
└── tasks.md                  # /speckit-tasks output (not created here)
```

### Source Code (repository root)

```text
hermes-voice/
├── src/
│   ├── satellite_core/                  # NEW NAME — formerly hermes_satellite_adapter
│   │   ├── __init__.py
│   │   ├── __main__.py                  # adapter entry-point (loaded by the active platform)
│   │   ├── adapter.py                   # transport + registry-only (constitution IV: no platform imports)
│   │   ├── config.py                    # loads ~/.satellite/config.yaml; selects platform plugin by name
│   │   ├── models.py                    # Appendix-B data models (carried over)
│   │   ├── registry.py                  # in-memory registry + pending/adopted lifecycle (extended in this feature)
│   │   ├── persistence.py               # NEW — atomic JSON to ~/.satellite/state.json
│   │   ├── logsink.py                   # extended for SSE iterator
│   │   │
│   │   ├── management/                  # NEW subpackage — the App. A REST surface
│   │   │   ├── __init__.py
│   │   │   ├── service.py               # ManagementService (carried over from management.py, refactored)
│   │   │   ├── app.py                   # aiohttp wiring (carried over from management.py)
│   │   │   ├── adopt.py                 # NEW — pending → adopted flow
│   │   │   ├── command.py               # NEW — closed verb enum surface
│   │   │   ├── ota.py                   # NEW — manifest loader, blob serving, browser-exempt gate
│   │   │   └── log_sse.py               # NEW — SSE iterator over LogSink
│   │   │
│   │   ├── webrtc/                      # voice plane (carried over from signaling.py/session.py/media.py/streamasm.py)
│   │   │   ├── signaling.py
│   │   │   ├── session.py
│   │   │   ├── media.py
│   │   │   └── streamasm.py
│   │   │
│   │   └── platforms/                   # NEW — constitution-IV v2.0.0 plugin seam
│   │       ├── __init__.py
│   │       ├── base.py                  # AgentPlatform interface + Registry
│   │       ├── hermes/                  # v1 canonical plugin
│   │       │   ├── __init__.py          # name = "hermes"
│   │       │   ├── bridge.py            # the current hermes_bridge.py logic, moved verbatim
│   │       │   ├── textseg.py           # carried over (Hermes-specific text-segment helpers)
│   │       │   ├── streamasm.py         # already platform-agnostic — possibly stays in webrtc/
│   │       │   └── README.md            # how to install + Hermes-specific config (~/.hermes/config.yaml)
│   │       └── openclaw/                # NEW — stub (interface compile only)
│   │           ├── __init__.py          # name = "openclaw"; methods raise NotImplementedError
│   │           └── README.md            # "planned plugin — not shipping in this feature"
│   │
│   └── sat_cli/                         # NEW — platform-neutral management CLI (binary `sat-cli`)
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py                       # Typer app
│       ├── rest_client.py               # httpx wrapper over management-api.yaml
│       ├── stream.py                    # SSE follow (logs, ota-progress) + watch mode
│       ├── output.py                    # human (rich) vs --json (machine) formatters
│       ├── exit_codes.py                # documented exit codes (cli-contract.md)
│       └── onboard/
│           ├── __init__.py
│           ├── improv_ble.py            # bleak central; Improv-Wifi GATT service UUIDs
│           └── flow.py                  # local Improv → REST adopt orchestration
│
├── skills/                              # per-agent-platform skills (not Claude Code skills)
│   ├── hermes-agent/                    # v1
│   │   ├── SKILL.md
│   │   └── README.md
│   └── openclaw/                        # stub
│       ├── SKILL.md
│       └── README.md
│
├── tests/
│   ├── contract/
│   │   ├── test_register.py             # (existing — kept; updated import path)
│   │   ├── test_list_state_logs.py      # (existing — updated import path)
│   │   ├── test_webrtc_offer.py         # (existing — updated import path)
│   │   ├── test_adopt.py                # NEW
│   │   ├── test_command.py              # NEW
│   │   ├── test_ota.py                  # NEW
│   │   ├── test_log_sse.py              # NEW
│   │   └── test_cli_contract.py         # NEW — sat-cli --json envelope vs management-api.yaml
│   │
│   ├── integration/
│   │   ├── test_adoption_flow.py        # NEW
│   │   ├── test_ota_rollback.py         # NEW
│   │   ├── test_concurrent_config.py    # NEW
│   │   ├── test_device_limit.py         # NEW
│   │   ├── test_cli_roundtrip.py        # NEW
│   │   ├── test_agent_platform_seam.py  # NEW — fake platform plugin proves seam works
│   │   └── (existing integration tests retained, import paths updated)
│   │
│   └── unit/
│       ├── test_models_config_registry.py  # (existing — extended)
│       ├── test_no_embedded_engines.py     # (existing — still gates I/IV)
│       ├── test_no_platform_branching.py   # NEW — gates v2.0.0 Principle II/IV neutrality
│       ├── test_improv_ble.py              # NEW
│       ├── test_cli_json_output.py         # NEW
│       ├── test_persistence.py             # NEW
│       └── test_agent_platform_contract.py # NEW — AgentPlatform abstract-method contract
│
├── pyproject.toml                       # update: rename package, add sat_cli; console_scripts: sat-cli
└── docs/
    └── generic-voice-satellite-design.md  # source of truth (read as "Hermes plugin" under v2.0.0)
```

**Structure Decision**: **Single-repo, two-Python-package layout with a
documented agent-platform plugin seam**:

- `satellite_core` — platform-neutral management plane, registry, voice
  plane, plugin loader. **Never imports a specific platform.**
- `satellite_core/platforms/hermes/` — v1 canonical platform plugin.
  Houses all current Hermes-bridge code.
- `satellite_core/platforms/openclaw/` — stub showing the seam works
  (interface only; not shipping a working plugin in this PR).
- `sat_cli` — platform-neutral management CLI. Binary `sat-cli`.
- `skills/hermes-agent/` and `skills/openclaw/` — per-platform skill
  folders that wrap `sat-cli`; the satellite core has no agent-skill code.

The optional web UI (spec FR-009) is deferred.

**Migration of the existing `hermes_satellite_adapter` package** is part
of this plan's task list, not a separate refactor:

> **Note**: superseded in feature 012 by `aivg_core` / `aivg_cli`; the
> `satellite_core` and `sat_cli` paths in this table now become compat
> shims themselves. See [../012-aivg-branding/plan.md](../012-aivg-branding/plan.md).

| Old path | New path |
|---|---|
| `src/hermes_satellite_adapter/adapter.py` | `src/satellite_core/adapter.py` |
| `src/hermes_satellite_adapter/config.py` | `src/satellite_core/config.py` |
| `src/hermes_satellite_adapter/models.py` | `src/satellite_core/models.py` |
| `src/hermes_satellite_adapter/registry.py` | `src/satellite_core/registry.py` |
| `src/hermes_satellite_adapter/management.py` | `src/satellite_core/management/service.py` + `management/app.py` |
| `src/hermes_satellite_adapter/logsink.py` | `src/satellite_core/logsink.py` |
| `src/hermes_satellite_adapter/signaling.py` | `src/satellite_core/webrtc/signaling.py` |
| `src/hermes_satellite_adapter/session.py` | `src/satellite_core/webrtc/session.py` |
| `src/hermes_satellite_adapter/media.py` | `src/satellite_core/webrtc/media.py` |
| `src/hermes_satellite_adapter/streamasm.py` | `src/satellite_core/webrtc/streamasm.py` |
| `src/hermes_satellite_adapter/hermes_bridge.py` | `src/satellite_core/platforms/hermes/bridge.py` |
| `src/hermes_satellite_adapter/textseg.py` | `src/satellite_core/platforms/hermes/textseg.py` |
| `src/hermes_satellite_adapter/turnlatency.py` | `src/satellite_core/turnlatency.py` (platform-neutral instrumentation) |

A compatibility shim (`src/hermes_satellite_adapter/__init__.py` that re-
exports from `satellite_core` with a `DeprecationWarning`) is kept for one
release so the running Hermes gateway's adapter registration does not
break mid-migration. The shim is itself a tracked deletion in this
feature's tasks.

## Complexity Tracking

> No constitution violations → no complexity to justify. The package
> rename + new plugin seam are *enablers* of the v2.0.0 amendment, not
> deviations from it.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| — | — | — |
