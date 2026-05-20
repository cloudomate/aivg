# Contract: `AgentPlatform` Plugin Interface

**Feature**: `011-satellite-management` · **Plan**: [../plan.md](../plan.md) ·
**Version**: 1.0.0 · **Constitution**: v2.0.0 Principle IV

`AgentPlatform` is the seam that makes the satellite system
**agent-platform-agnostic** (constitution v2.0.0). The satellite core never
imports a specific platform; it loads one `AgentPlatform` implementation by
name from `~/.satellite/config.yaml`'s `platform:` key and uses only this
interface.

## Location

```text
src/satellite_core/platforms/
├── base.py                  # the AgentPlatform Protocol + PluginRegistry
├── hermes/                  # v1 canonical implementation
│   └── __init__.py          # exposes PLATFORM: AgentPlatform
└── openclaw/                # stub (planned)
    └── __init__.py          # exposes PLATFORM: AgentPlatform — methods raise NotImplementedError
```

## Interface (Python `Protocol`)

```python
from typing import AsyncIterator, Protocol, Optional

class AgentPlatform(Protocol):
    """Pluggable agent-platform integration. v2.0.0 Principle IV.

    Implementations MUST NOT leak provider/SDK types across this boundary —
    only the Python primitives below cross it.
    """

    name: str
    """Stable lowercase identifier, e.g. 'hermes', 'openclaw'."""

    async def startup(self, *, gateway_config: dict) -> None:
        """Called once when the satellite adapter starts.
        Implementations open whatever long-lived resources the platform
        requires (e.g. Hermes provider warm-up). MUST NOT raise on a
        recoverable startup error — return; the next call will retry.
        """

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        """ASR: PCM16 mono → text. Sample rates: 16000 or 48000."""

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        """Agent loop: user text → streaming reply text deltas.
        Implementations stream as soon as the platform produces tokens
        (feature 008 streaming seam). Implementations MUST yield clean
        prose suitable for TTS — markdown stripping etc. is the
        platform's responsibility (constitution I), NOT the core's.
        """

    async def synthesize(self, text: str) -> bytes:
        """TTS: text → Opus or PCM (negotiated at startup)."""

    async def endpoint(self, frame: bytes) -> bool:
        """Server-side end-of-utterance for one incoming frame.
        Returns True at the moment EOU is reached. Implementations
        delegate to the platform's existing silence algorithm
        (constitution I rule).
        """

    async def shutdown(self) -> None:
        """Called on adapter teardown. MUST be idempotent."""
```

## Loading

Selected in `~/.satellite/config.yaml`:

```yaml
platform: hermes        # or "openclaw" once implemented
satellite:
  management_port: 8643
  webrtc_port: 8644
  device_limit: 10
  heartbeat_interval: 30
```

`satellite_core.config.load_config()` reads `platform`, imports
`satellite_core.platforms.<name>` dynamically, and exposes
`module.PLATFORM` as the singleton `AgentPlatform` instance used by the
voice/management code. **No fallback / no auto-discovery** in v1 — an
unknown `platform:` value is a fatal startup error with a clear message.

## Plugin contract (rules the satellite core enforces)

1. **Module exposure**: `satellite_core.platforms.<name>` MUST expose a
   module-level attribute `PLATFORM: AgentPlatform`. Asserted in
   `tests/unit/test_agent_platform_contract.py`.
2. **Name attribute**: `PLATFORM.name == "<name>"` MUST hold.
3. **No cross-platform imports**: a platform plugin MUST NOT import
   another plugin. Asserted by static check in
   `tests/unit/test_no_platform_branching.py`.
4. **No platform imports from the core**: `satellite_core/` (excluding
   `satellite_core/platforms/`) MUST NOT contain any
   `import satellite_core.platforms.hermes` or
   `import satellite_core.platforms.openclaw` (or any other concrete
   plugin). Asserted by the same static check.
5. **Type independence**: a plugin's return types are stdlib primitives
   (`bytes`, `str`, `AsyncIterator[str]`, `bool`). Plugin-internal types
   stay inside the plugin.

## v1 implementations

| Plugin | Status | Source | Configures |
|---|---|---|---|
| `hermes` | **shipping** | Migrated from current `hermes_bridge.py` | `~/.hermes/config.yaml`, `~/.hermes/.env`, Hermes STT/TTS providers |
| `openclaw` | **stub** | New `__init__.py` raises NotImplementedError | (TBD — separate feature) |

## Test gate

`tests/integration/test_agent_platform_seam.py` registers a **fake
`EchoPlatform`** (placed under `tests/fixtures/platforms/echo/` and
selected via a test-only `platform: echo` config) that returns
deterministic strings, runs the full voice loop end-to-end through it
*without any Hermes-specific module ever being imported*, and asserts
`sys.modules` has no `satellite_core.platforms.hermes*` entries.

This is the binding gate for constitution v2.0.0 Principle IV.

## Versioning

This contract shares the v1.0.0 semver of `management-api.yaml`,
`management-ws.md`, and `cli-contract.md` (R-13). Adding optional methods
or kwargs is minor; removing/renaming methods is major.
