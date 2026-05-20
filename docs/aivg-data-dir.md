# `~/.aivg/` — AIVG data directory

**Owned by**: feature 012 (AIVG rebrand). Renamed from `~/.satellite/`
in this feature (previously introduced in feature 011 under
constitution v2.0.0). Distinct from any agent platform's own data
directory (e.g. `~/.hermes/`, which the Hermes plugin reuses for *its*
provider config — Principle IV).

## Layout

```text
~/.aivg/
├── config.yaml                       # AIVG-system config (platform selection, ports, limits)
├── state.json                        # adopted-device registry snapshot
└── firmware/
    ├── rpi/manifest.json             # per-device-type OTA manifests
    └── esp32/manifest.json
```

> **No `browser/`** under `firmware/` — browser devices are explicitly
> not OTA-eligible (constitution II sanctioned divergence).

## `~/.aivg/config.yaml` (sample)

```yaml
# Which agent platform plugin to load (constitution v2.0.0 Principle IV).
platform: hermes        # or "openclaw" (stub) once that plugin ships.

satellite:
  enabled: true
  management_port: 8643
  webrtc_port: 8644
  heartbeat_interval: 30
  mdns_advertise: true
  device_limit: 10
  auto_adopt_on_register: false   # Feature 011 US2 onboarding gate
  default_config:
    wake_word: "Hey Jarvis"
    routing_mode: "preferred"
    log_level: "INFO"

ota:
  firmware_dir: "~/.aivg/firmware"
```

## First-run migration from `~/.satellite/`

On the first start of the rebranded gateway, if `~/.satellite/state.
json` exists (from a feature-011-era deployment) and `~/.aivg/state.
json` either does not exist or is older, AIVG runs an atomic migration:

1. Loads `~/.satellite/state.json`.
2. Writes the content to `~/.aivg/state.json` via the existing atomic
   `tmp+rename` helper.
3. Renames the old file in place to
   `~/.satellite/state.json.pre-aivg-rebrand.bak` — never deleted (so
   you have a rollback rope).

Subsequent starts are idempotent: the migration only fires if the new
location is empty or older than the old. See
[specs/012-aivg-branding/research.md R-3](../specs/012-aivg-branding/research.md#r-3-data-directory-migration--first-run-atomic-leave-bak).

## Predecessor doc

[`docs/satellite-data-dir.md`](satellite-data-dir.md) describes the
predecessor layout under `~/.satellite/` and is retained for reference;
it is superseded by this file for new installs.

## Why not under `~/.hermes/`?

Under constitution v2.0.0 the satellite system is platform-agnostic;
writing satellite-owned state into a single platform's home directory
would couple operator state to that platform. The **Hermes plugin**
still reads `~/.hermes/config.yaml` and `~/.hermes/.env` for *its own*
provider config — that's the plugin's reuse of upstream assets per
Principle IV.
