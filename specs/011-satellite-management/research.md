# Phase 0 Research: Satellite Management — Onboard, Configure & OTA

**Feature**: `011-satellite-management` · **Plan**: [plan.md](./plan.md) ·
**Spec**: [spec.md](./spec.md) · **Date**: 2026-05-20

Each item below resolves a planning-blocker by stating a **decision**, its
**rationale** (tied to a binding constraint from the spec / constitution /
design doc), and the **alternatives considered**. No `NEEDS CLARIFICATION`
markers remain after this phase.

---

## R-1. CLI framework: Typer

**Decision**: Use [Typer](https://typer.tiangolo.com) (≥0.12) for the
`hermes-sat` binary.

**Rationale**:

- Type-hint-driven command tree maps cleanly onto the App. A REST surface
  (one subcommand per resource: `sat list`, `sat device get`, `sat device
  config`, `sat ota apply`, …) and gives free help/usage.
- First-class support for both human (Rich) and machine output — `--json`
  toggles a stable JSON formatter (FR-006, SC-006).
- Async-friendly via `asyncio.run()` in command entrypoints — needed for SSE
  follow modes (httpx async iterator) and for the `bleak` Improv flow.
- Already widely used in Python CLI tooling; low new-dependency risk.

**Alternatives considered**:

- **Click** — Typer's parent. Works, but loses the type-hint ergonomics and
  forces more boilerplate for the stable-output contract.
- **argparse stdlib** — zero deps, but the spec's "stable, documented
  contract with JSON output" (FR-006) is easier to keep consistent with a
  framework that already encourages a single source of help/usage truth.
- **A Click-on-top-of-`hermes` plugin** — explicitly rejected by the
  2026-05-20 clarification (the CLI must NOT be a subcommand of `hermes`).

---

## R-2. Cross-platform BLE central for Improv-Wifi: bleak

**Decision**: Use [`bleak`](https://bleak.readthedocs.io) (≥0.22) directly,
speaking the Improv-Wifi GATT service UUIDs by hand inside
`sat_cli/onboard/improv_ble.py`.

**Rationale**:

- The operator host is macOS or Linux (plan Target Platform); `bleak` is the
  one Python BLE central library that supports both via a unified asyncio
  API (CoreBluetooth on macOS, BlueZ on Linux).
- The Improv-Wifi spec (https://www.improv-wifi.com/ble/) is a small, fixed
  set of characteristics (state, error, RPC command, RPC result). Hand-
  rolling the framing is ~150 LOC and avoids depending on
  Home-Assistant-coupled libraries.
- A failed/timeout BLE attempt must produce a **specific reason** (FR-012);
  a thin in-repo implementation lets us surface real GATT errors instead of
  hiding them behind a higher-level library's exceptions.

**Alternatives considered**:

- **`aioimprov` / community improv libraries** — most are server-side
  (ESP32) or HA-coupled. None we surveyed maintain a clean Python-central
  release on PyPI.
- **Reusing the browser Improv flow (`improv-wifi.com`)** — the user is
  required to be at a browser; loses the CLI-driven goal of the 2026-05-19
  clarification. Documented as the manual fallback for hosts without BLE.

---

## R-3. Live log transport: Server-Sent Events (SSE) over HTTP

**Decision**: Per-device live log tail is delivered as **SSE** at
`GET /satellite/{id}/logs?follow=true` (and `GET /satellite/logs?follow=true`
for the aggregate fleet log). The control WebSocket (`WS /satellite/ws`)
already used by devices fans out `log_entry` events from `LogSink._broadcast`
internally; the CLI consumes them via SSE on the operator side.

**Rationale**:

- SSE is one-way server→client text, exactly the shape of a log tail; the
  CLI's `httpx` SSE line-iterator is two-call setup.
- Constitution III draws the line at "durable control on WS, call-scoped
  low-latency on datachannel". The operator's log tail is neither durable
  state nor call-scoped — it is a read-only stream — and SSE keeps it off
  the device control channel that already carries register/heartbeat.
- The existing design Appendix A already specifies SSE for `/satellite/
  {id}/logs`. No new transport invented.
- OTA progress is delivered via the same SSE stream (`source=ota`,
  structured `metadata`), so the CLI's one `follow` implementation covers
  both log-tail and OTA-progress watch (FR-023, FR-026).

**Alternatives considered**:

- **Reuse the device WS for operator log tail** — would couple operator
  liveness to the device control channel and require a second client of
  that WS; SSE is cleaner.
- **Plain JSON-lines over HTTP chunked** — works, but SSE's `event:` and
  reconnect-id semantics give us cheap resume on transient drops and the
  framing is what aiohttp already supports via `aiohttp-sse`.
- **WebSocket for everything operator-facing** — operator surface is REST
  per the 2026-05-19 clarification; restricting WS/SSE to "live streams
  only" is the spec rule (FR-008).

---

## R-4. Data models: keep stdlib `dataclasses` (no `pydantic`)

**Decision**: New models (`AdoptionState`, `OtaJob`, `CommandRequest`,
`OtaManifest`, `PendingDevice`) extend the existing stdlib `@dataclass`
style already used in [src/hermes_satellite_adapter/models.py](src/hermes_satellite_adapter/models.py)
(rename target: `src/satellite_core/models.py`).
**Do not** introduce `pydantic`. Request/response validation lives in
contract tests against `contracts/management-api.yaml`.

**Rationale**:

- The existing `models.py` (constitution II / Appendix B) is plain
  dataclasses + `Enum`s. Adding `pydantic` to *some* models splits the
  data layer and forces every reader to learn which models validate where.
- Validation is already covered upstream: the OpenAPI contract gates the
  REST surface in `tests/contract/`, and `Registry` enforces invariants in
  Python (`tests/unit/test_models_config_registry.py`).
- Smaller dependency surface; faster `pytest` cold start.

**Alternatives considered**:

- **Adopt `pydantic` for all models** — bigger blast radius than this
  feature's scope warrants; can be revisited as a separate refactor.
- **Adopt `pydantic` for *new* models only** — explicitly rejected per the
  rationale above (split data layer).

---

## R-5. Registry persistence: atomic JSON dump to `~/.hermes/satellite.json`

**Decision**: Adopted devices, names, and per-device persisted configs are
written to `~/.satellite/state.json` after every mutating operation, using
an atomic `tmp+rename` write inside `persistence.py`. On `ManagementService`
startup the file is loaded into `Registry`. Pending/unclaimed devices are
in-memory only (they re-arrive on register).

**Rationale**:

- Spec FR-015 requires config to survive reboot; FR-027 requires concurrent
  writes to converge. A file + atomic write is the smallest thing that
  satisfies both without introducing a database (constitution IV: no new
  store).
- `~/.satellite/` is the satellite system's own data directory. Under
  constitution v2.0.0 the satellite core is platform-agnostic, so we MUST
  NOT write satellite state into any single platform's data directory
  (e.g. `~/.hermes/`). The Hermes platform plugin separately reads
  `~/.hermes/config.yaml` for *its* provider config (constitution IV v2.0.0
  — the plugin reuses Hermes's assets; the core does not).
- Pending devices are by definition transient — losing them on restart is
  acceptable; the device's next register repopulates them.
- A single-file write is safe for the 1–10 device scale; no concurrency
  beyond an `asyncio.Lock` is required.

**Alternatives considered**:

- **SQLite** — overkill for ≤10 rows; adds a binary file format and a dep.
- **YAML in `~/.hermes/config.yaml`** — that file is Hermes's config, not
  runtime state; mixing causes config-vs-state confusion.
- **No persistence** — fails FR-015 / SC-003 on gateway restart.

---

## R-6. OTA flow: per-device-type adapter, browser explicitly exempted

**Decision**: `satellite_core/management/ota.py` exposes one `OtaService`
API (`check(device_id) -> CheckResult`, `apply(device_id, version) ->
OtaJob`, `manifest(device_type) -> OtaManifest`) and dispatches internally
by `device_type` from the `Registry`. **The dispatch is the one sanctioned
per-type divergence (browser = no OTA), and is asserted in tests not to
leak into any other endpoint or into the CLI/skill surface.** Manifests are
static `manifest.json` files under `~/.satellite/firmware/<device_type>/`
(per design Appendix D) with `version`, `url`, `sha256`, `signature`,
`changelog`. Apply returns a job id; progress is pushed onto the existing
`LogSink` with `source="ota"`, consumed by the CLI via the SSE log stream
(R-3) — no separate transport.

**Rationale**:

- Constitution II permits exactly two per-type divergences (browser-no-OTA
  and `echo_strategy`). Confining the dispatch to `ota.py` and proving
  with a test that no other code path branches on `device_type` is the
  cleanest way to keep the boundary visible.
- Rolling progress through `LogSink` reuses one streaming substrate (R-3)
  for both log tail and OTA progress — one `follow` implementation in the
  CLI.
- ESP32 dual-partition rollback and RPi `curl + systemctl restart` are
  device-firmware concerns (out of scope here); the management plane only
  records `result: success | rolled_back | failed`.

**Alternatives considered**:

- **A separate OTA stream endpoint** — duplicates the log infrastructure
  for no behavioral gain.
- **One OTA implementation, `device_type`-blind** — impossible: browser
  has no firmware at all; the divergence is real and must be modeled.

---

## R-7. Adoption flow: explicit `PendingDevice` lifecycle

**Decision**: A device that posts `/satellite/register` for the first time
is stored as a `PendingDevice` (NOT yet a `ConnectedClient`) until an
operator calls `POST /satellite/{id}/adopt { name, config_overrides? }`.
Adoption promotes the entry to `ConnectedClient`, persists it (R-5), and
returns the resolved default config. `DELETE /satellite/{id}` returns the
device to "not present" (and a future re-register starts a new
`PendingDevice`, per spec edge cases). Re-registration of an adopted device
is **not** demoted; the existing record's `last_seen` is updated.

**Rationale**:

- Spec FR-011 and US2 require pending → adopted as a visible operator step.
- Keeping `PendingDevice` separate from `ConnectedClient` matches the
  existing `Registry` shape (one dict of clients, one of sessions) — we
  add one dict (`_pending`) rather than nullable fields on every client.
- Edge case "Re-register after factory reset" — a factory-reset device
  re-registers with its prior `device_id`. If we treated that as already-
  adopted we'd silently restore stale state (which the spec edge case
  forbids). Resolution: factory-reset is detected by a `factory_reset=true`
  flag in the register payload (set by the device after wiping NVS); when
  present, the gateway moves the device back to `PendingDevice` and
  discards its persisted config.

**Alternatives considered**:

- **Auto-adopt on first register** — violates FR-011 and spec edge case
  "Unclaimed device never named".
- **Promote on first heartbeat** — same problem; an operator never gets a
  chance to name the device.

---

## R-8. CLI JSON output: a frozen v1 contract

**Decision**: `--json` (or `HERMES_SAT_JSON=1`) switches every command to
emit a single newline-terminated JSON document on stdout with shape
`{ "ok": bool, "data": <command-specific>, "error": null | { code, message } }`.
Streaming commands (`logs follow`, `watch`) emit one such object per line
(NDJSON). The contract is documented in
[contracts/cli-contract.md](./contracts/cli-contract.md); the shape of
`data` per command is **versioned as v1** and any backward-incompatible
change requires a `--json-version` flag or a new top-level field.

**Rationale**:

- Spec FR-006 + SC-006: "non-Hermes agent or script that can execute the
  CLI MUST be able to reproduce every management action with no additional
  integration code, using the CLI's machine-readable output." That requires
  a stable, parsable shape — not Rich-formatted prose.
- A two-mode CLI (human/JSON) is standard (`gh`, `kubectl`, `aws`).
- `tests/unit/test_cli_json_output.py` golden-files the v1 schema per
  command; any change there is a deliberate contract bump.

**Alternatives considered**:

- **YAML output** — humans prefer it, agents prefer JSON; pick one (JSON).
- **Per-command output without a wrapping envelope** — error reporting
  becomes ambiguous (is it a row, or a failure?). The `ok/data/error`
  envelope is the smallest reliable shape.

---

## R-9. Exit codes

**Decision**: Documented in `cli-contract.md`. Categories:

- `0` success
- `1` user input error (bad flag, unknown device, validation)
- `2` device offline / unreachable for an action that requires online
- `3` gateway unreachable
- `4` BLE/Improv provisioning failure (host-side)
- `5` OTA failure (device-reported `failed` or `rolled_back`)
- `64+` reserved

**Rationale**: Agents (Hermes skill, scripts) read exit codes for control
flow; collapsing all failures to `1` makes "device offline" indistinguishable
from "bad command", which fails FR-016's edge case requirement.

---

## R-10. Per-agent-platform skill packaging

**Decision**: Ship one skill folder per supported agent platform under
`skills/<platform>/`. v1: `skills/hermes-agent/SKILL.md` (canonical, uses
the Hermes skill schema observed in the vendored
`.claude/skills/hermes-agent/SKILL.md` — feature 002 pinned a verbatim
copy at commit `98db898…` so the schema is concrete) plus
`skills/openclaw/SKILL.md` (stub — same contract, body is "not yet
implemented; planned"). Each skill's **body is examples + a contract:
invoke `sat-cli --json ...` and parse the envelope from R-8**. The Hermes
skill installs to the operator's `~/.hermes/skills/satellite-management/`
per Hermes skill conventions (documented in
`skills/hermes-agent/README.md`); other platforms ship to their own
analogous install paths. No Python in any skill — they are thin policy
wrappers over the platform-neutral CLI.

**Rationale**:

- The 2026-05-20 clarification fixes the skill as a wrapper around the CLI
  — the skill is policy + examples, not a parallel implementation.
- Reusing the documented Hermes skill folder convention (constitution IV)
  avoids inventing a new skill plumbing.

**Alternatives considered**:

- **Skill calls REST directly** — explicitly rejected by the 2026-05-20
  clarification (the skill must go through the CLI as its single execution
  surface).

---

## R-11. Concurrent config writes — last-writer-wins with version stamps

**Decision**: Each persisted `SatelliteConfig` carries a monotonically
incrementing `version: int` and a `updated_at: float`. `POST
/satellite/{id}/config` accepts the new config + an optional `If-Match:
version` header. With the header: a stale version returns 409 and the
caller refetches. Without the header (CLI/skill convenience): the gateway
applies the write, bumps `version`, and broadcasts the new running config
on the device WS (FR-027 — predictable convergence).

**Rationale**:

- Spec FR-027: concurrent writes from different surfaces must converge
  deterministically. Version-stamped last-writer-wins is the smallest
  scheme that gives a clear "what won" answer and surfaces conflicts when
  the caller asks for them.
- Devices already process `config_changed` over the WS (existing
  `_broadcast`); we extend the payload with `version`.

**Alternatives considered**:

- **Field-level CRDT** — overkill for a flat config of ≤20 fields.
- **Lock per device for the duration of an edit** — UI/skill latency
  becomes unpredictable; agents can deadlock each other.

---

## R-12. Device-limit enforcement

**Decision**: `satellite.device_limit` defaults to **10** in
`~/.hermes/config.yaml`, configurable. Enforced at `POST
/satellite/{id}/adopt` (not at `register`, so registrations that don't yet
result in adoption can pile up harmlessly in `PendingDevice`). On refusal
the response is `409 { error: "device_limit_reached", current, limit }` and
the CLI maps it to exit code `1` with a specific message pointing to
unpair-then-retry.

**Rationale**:

- Spec assumption (limit is a configurable gateway setting, not fixed by
  spec). 10 matches the referenced UI mockup's example.
- Limit at `adopt` (not at `register`) keeps pending discovery cheap and
  doesn't accidentally lock the fleet by drowning the limit with
  re-registers.

---

## R-13. Stable contract surface: where versioning lives

**Decision**: Three contract artifacts, each independently versioned:

1. **REST**: `contracts/management-api.yaml` — OpenAPI 3.1, `info.version
   = 1.0.0`. Breaking changes bump major; additive bump minor.
2. **Device WS**: `contracts/management-ws.md` — table of message types
   with shapes; same semver.
3. **CLI**: `contracts/cli-contract.md` — commands, flags, exit codes,
   JSON-envelope shape; same semver. CLI binary prints
   `--contract-version` for agents.

All three are required to stay in lock-step with one another (an FR change
that crosses surfaces is a coordinated bump). Verified by
`tests/contract/` which loads `management-api.yaml` and the CLI's
`--contract-version` and asserts they agree.

**Rationale**: FR-006/FR-008/SC-006 require a stable agent-consumable
surface; without versioned artifacts the "stable contract" claim is
unprovable.

---

## R-14. Identify-LED, mute, unmute — encoded as commands

**Decision**: Mute, unmute, identify, reboot, restart_voice,
restart_manager, reset_config, factory_reset are all `POST /satellite/{id}/
command { command: <verb> }` (already the App. A shape). The full enum is
fixed in `models.py::CommandVerb` and asserted in `tests/contract/
test_command.py`. Anything destructive (factory_reset, the registry-
removing `DELETE /satellite/{id}`) requires the CLI/skill to prompt the
operator unless `--yes` is passed; the management API itself does not
prompt — gating destructive actions is a *client* responsibility (FR-019),
not a server one.

**Rationale**:

- Keeping one endpoint and one enum makes the constitution-II "no protocol
  branching" claim provable.
- Destructive-confirmation belongs in the surface a human/agent drives, not
  in the wire protocol — otherwise scripted callers can never automate
  safe sequences.

**Alternatives considered**:

- **A REST verb per command** — proliferates endpoints; nothing gained.

---

## R-15. Agent platform plugin seam (constitution v2.0.0 enabler)

**Decision**: Define `satellite_core/platforms/base.py::AgentPlatform`
as a Python `Protocol` (PEP 544) with these required methods:

```python
class AgentPlatform(Protocol):
    name: str

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str: ...
    async def agent_step(self, text: str, session_id: str) -> "AsyncIterator[str]": ...
    async def synthesize(self, text: str) -> bytes: ...
    async def endpoint(self, frame: bytes) -> bool: ...
    async def shutdown(self) -> None: ...
```

Platform plugins live under `satellite_core/platforms/<name>/` with an
`__init__.py` that exposes a module-level `PLATFORM: AgentPlatform`
instance (or factory). Plugin discovery is **explicit config**: the
satellite config (`~/.satellite/config.yaml`) names the active plugin as
`platform: hermes` (or `openclaw`, etc.); `satellite_core.config` imports
`satellite_core.platforms.<name>` dynamically. No entry-point magic in v1
(that can come later if third parties package external plugins).

A test (`tests/integration/test_agent_platform_seam.py`) registers a
**fake `EchoPlatform`** that returns deterministic strings and proves the
voice loop runs end-to-end without any Hermes-specific code being imported
— this is the binding gate that v2.0.0 Principle IV is honored.

**Rationale**:

- `Protocol` gives a structural-typing contract — third-party plugins
  don't need to inherit from a base class, they just need to expose the
  named methods. Smaller coupling.
- Explicit config (no entry-point auto-discovery) keeps the loader
  predictable for v1; entry-points can be a follow-up.
- The fake-platform test is the only reliable way to prove "no Hermes
  leakage" — mocking individual imports is too fragile.

**Alternatives considered**:

- **Abstract base class (`abc.ABC`)** — works, but forces inheritance and
  is more boilerplate than `Protocol`. Reject.
- **Setuptools entry-points** — convenient for third parties, but adds
  packaging surface for v1 where we control both plugins. Defer.
- **Subprocess-based plugins** (each platform is its own process) —
  overkill; Python in-process import is fine for the scale.

---

## Open questions deferred to `/speckit-tasks`

None for Phase 0. Two minor scoping points belong in `/speckit-tasks`:

- Exact OpenAPI operation IDs vs Python handler names (mechanical).
- Whether to split `test_command.py` per verb or keep one parametrized file
  (style; pick one in tasks).
