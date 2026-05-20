# Hermes-platform satellite management skill

v1 canonical agent-platform skill (constitution v2.0.0 Principle IV).
Drives the platform-neutral `sat-cli` binary on the operator's host.

## Install

Hermes installs skills from `~/.hermes/skills/<skill-name>/SKILL.md`.

```bash
mkdir -p ~/.hermes/skills/satellite-management
cp -R ./SKILL.md ~/.hermes/skills/satellite-management/
```

The Hermes agent will pick up the skill on its next config reload.

## Prerequisites

- `sat-cli` is installed and on `PATH`. From this repo:
  ```bash
  pip install -e .
  sat-cli --contract-version   # expect 1.0.0
  ```
- A satellite gateway is reachable (default `http://localhost:8643`).
  Override via `SAT_GATEWAY_URL` or `sat-cli --gateway ...`.
- For onboarding: a BLE-capable host (macOS or Linux). Install the BLE
  extra: `pip install -e '.[ble]'`.

## What this skill does NOT do

- Talk to the gateway over REST itself — it shells out to `sat-cli`.
- Embed any Hermes-specific transport — the same `sat-cli` is used by
  the OpenClaw-platform skill (planned) without modification.
- Auto-confirm destructive actions; the agent must ask the user first.

## Versioning

This skill tracks `cli-contract.md` v1.0.0. Upgrade in lock-step when the
CLI contract bumps.
