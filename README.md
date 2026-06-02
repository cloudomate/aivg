# AIVG — AI Voice Gateway

**AIVG** is a platform-neutral voice satellite system: a thin, realtime
voice transport (WebRTC / Opus) bridged into whichever **agent platform
plugin** is configured (v1 canonical: **Hermes**; planned: OpenClaw).
Satellites capture audio and play it back; STT, the agent loop, TTS,
and end-of-utterance detection live in the upstream agent platform.

## Install (PyPI)

```bash
pip install aivg
```

**Supported**: Python 3.11+ on Linux x86_64/aarch64, macOS arm64/x86_64.

**⚠ Install into your existing Hermes virtualenv, not a fresh venv.** The
`aivg-satellite` entry point is only discoverable by Hermes's plugin loader
if AIVG lives in the same venv Hermes runs from:

```bash
uv pip install --python ~/.hermes/hermes-agent/venv/bin/python aivg
```

Then add `aivg-satellite` under `plugins.enabled:` in `~/.hermes/config.yaml`
and restart the gateway. Full setup flow: see [docs/](docs/) or run
`aivg setup --help`.

Repo: <https://github.com/cloudomate/aivg> · Changelog:
[CHANGELOG.md](CHANGELOG.md) · License: MIT.

## Status

| Layer | State |
|---|---|
| Voice plane (WebRTC, Opus, server-side endpointing) | Implemented (features 001/005/006/008/010) |
| Management plane (registry, adoption, control WS, SSE logs) | Implemented (feature 011 Phases 1–4) |
| `aivg` CLI + Hermes agent skill | Implemented (feature 011 Phase 3+4) |

## Quickstart

```bash
pip install -e .          # picks up the renamed entry point
aivg --version            # JSON envelope, contract_version 0.3.0
aivg list                 # see the fleet
aivg device get kitchen   # full state of one device
aivg logs kitchen --follow
aivg onboard --ssid "MyWiFi" --password "..." --name "bedroom"
```

## Repo layout

```text
src/aivg_core/           # platform-neutral management plane
  platforms/hermes/        # v1 Hermes plugin (Hermes-platform agent skill, bridge)
  platforms/openclaw/      # planned plugin (stub)
  webrtc/                  # voice plane (WebRTC)
  transports/              # additive non-WebRTC transports
    esphome/                 # ESPHome native API (feature 017)
    grpc/                    # gRPC bidi streaming (feature 021)
  management/              # App. A REST + SSE + control WS
src/aivg_cli/            # `aivg` Typer CLI
proto/                   # canonical cross-language wire schemas (gRPC transport)
skills/hermes-agent/     # Hermes-platform agent skill (invokes `aivg` CLI)
specs/                   # Spec Kit features 001–021
docs/                    # design notes, data-dir reference, rebrand allow-list
```

## Transports

A satellite's audio plane can run over any of three transports; the gateway
selects the best one each satellite advertises (no flag-day, no per-device
branching):

| Transport | For | Notes |
|---|---|---|
| **WebRTC** | browser-tab satellites; legacy native | Opus, ICE/DTLS/SRTP. The only option a browser can open. |
| **ESPHome native API** | ESPHome voice devices (feature 017) | Additive; off by default. |
| **gRPC** | native satellites — RPi/ESP32 class (feature 021) | Bidi `Audio.Stream` (mic up, audio+transcripts+events down); optional `Management` service for the control plane. No ICE/DTLS to stall. |

The gRPC transport is **off by default**. Opt in via the `satellite:` block in
`~/.hermes/config.yaml`:

```yaml
satellite:
  enabled: true
  transports:
    grpc:
      enabled: true
      port: 8645              # audio plane (distinct from management 8643 / webrtc 8644)
      tls: insecure           # trusted-LAN default; "mtls" for fleet
      downstream_codec: pcm   # or "opus"
      management_over_grpc: false   # true => also serve the control plane over gRPC
```

The canonical wire schema lives at
[`proto/aivg/satellite/v1/`](proto/aivg/satellite/v1/) — the single source of
truth shared by the Python gateway and native C++ clients (in the companion
[`aivg-devices`](https://github.com/cloudomate/aivg-devices) repo). Regenerate
the Python stubs with `scripts/gen_proto.sh`.

## Hermes vs AIVG

| Use this | When you mean |
|---|---|
| **AIVG** | the product, the repo, the system as a whole |
| **Hermes** | the v1 agent-platform plugin (one of several AIVG supports) |
| **`aivg`** | the CLI binary |
| **`aivg_core`** | the platform-neutral Python package |
| **`~/.aivg/`** | AIVG's operator data (state, firmware manifests) |
| **`~/.hermes/`** | the Hermes plugin's data (provider config, secrets) |


## Development

```bash
# Editable install with all dev deps (pytest, ruff, black, etc.)
pip install -e ".[dev]"
# or with uv:
uv pip install -e ".[dev]"

# Run the suite
pytest -q                 # 300+ tests
```

Runtime + dev deps are declared in `pyproject.toml` under
`[project]` and `[project.optional-dependencies]` respectively.
(The legacy `requirements-dev.txt` was removed in feature 018 —
single source of truth is the `pyproject.toml` extras now.)

See [`specs/`](specs/) for the design history and the active feature
(currently [018-aivg-pypi-distribution](specs/018-aivg-pypi-distribution/)).
