# Hermes-platform AIVG satellite-management skill

v1 canonical agent-platform skill for **AIVG (AI Voice Gateway)**
(constitution v2.0.1 Principle IV). Drives the platform-neutral `aivg`
binary on the operator's host.

## Install

Hermes installs skills from `~/.hermes/skills/<skill-name>/SKILL.md`.

```bash
mkdir -p ~/.hermes/skills/satellite-management
cp -R ./SKILL.md ~/.hermes/skills/satellite-management/
```

The Hermes agent will pick up the skill on its next config reload.

## Prerequisites

- `aivg` is installed and on `PATH`. From this repo:
  ```bash
  pip install -e .
  aivg --contract-version   # expect 1.0.0
  ```
- An AIVG gateway is reachable (default `http://localhost:8643`).
  Override via `SAT_GATEWAY_URL` or `aivg --gateway ...`.
- For onboarding: a BLE-capable host (macOS or Linux). Install the BLE
  extra: `pip install -e '.[ble]'`.

The legacy binary `sat-cli` still works for one release as a
deprecation-warned alias; new automation should use `aivg`.

## What this skill does NOT do

- Talk to the gateway over REST itself — it shells out to `aivg`.
- Embed any Hermes-specific transport — the same `aivg` is used by
  the OpenClaw-platform skill (planned) without modification.
- Auto-confirm destructive actions; the agent must ask the user first.

## Versioning

This skill tracks `cli-contract.md` v1.0.0. Upgrade in lock-step when the
CLI contract bumps.
