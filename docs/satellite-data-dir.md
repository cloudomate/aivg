# `~/.satellite/` — satellite-system data directory

**Owned by**: feature 011 (constitution v2.0.0). Distinct from any agent
platform's own data directory (e.g. `~/.hermes/`, which the Hermes plugin
reuses for *its* provider config — Principle IV).

## Layout

```text
~/.satellite/
├── config.yaml                       # satellite-system config (platform selection, ports, limits)
├── state.json                        # adopted-device registry snapshot (R-5)
└── firmware/
    ├── rpi/manifest.json             # per-device-type OTA manifests (R-6)
    └── esp32/manifest.json
```

> **No `browser/`** under `firmware/` — browser devices are explicitly
> not OTA-eligible (constitution II sanctioned divergence).

## `~/.satellite/config.yaml` (sample)

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
  default_config:
    wake_word: "Hey Jarvis"
    routing_mode: "preferred"
    log_level: "INFO"

ota:
  firmware_dir: "~/.satellite/firmware"
```

## `~/.satellite/state.json` (atomic-written by the management plane)

`RegistrySnapshot` per [data-model.md](../specs/011-satellite-management/data-model.md§5);
written via `tmp+rename` on every mutating operation (adopt / delete /
post_config / OTA terminal transition).

## Why not under `~/.hermes/`?

Under constitution v2.0.0 the satellite system is platform-agnostic;
writing satellite-owned state into a single platform's home directory
would couple operator state to that platform. The **Hermes plugin** still
reads `~/.hermes/config.yaml` and `~/.hermes/.env` for *its own* provider
config — that's the plugin's reuse of upstream assets per Principle IV.
