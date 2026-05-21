# Data Model — AgentPlatform Runtime Closure (Phase 1)

**Feature**: 015-agentplatform-runtime-closure · **Date**: 2026-05-20

This document defines every type signature the refactor introduces or
modifies. It is the binding reference for the contract tests in
[contracts/agent-platform.md](./contracts/agent-platform.md).

## 1. `AgentPlatform` Protocol (canonical surface)

The canonical Protocol exposed by every agent-platform plugin. Lives
in `src/aivg_core/platforms/base.py`. Already exists today; this
feature aligns one return type (R-1) and pins the empty-reply
convention (R-2).

```python
from typing import AsyncIterator, Optional, Protocol, runtime_checkable

@runtime_checkable
class AgentPlatform(Protocol):
    """Platform-neutral integration surface (constitution v2.0.0+ IV)."""

    name: str
    """Stable lowercase identifier (e.g. 'hermes', 'openclaw')."""

    async def startup(self, *, gateway_config: dict) -> None: ...
    """Open long-lived resources. MUST NOT raise on recoverable errors."""

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str: ...
    """ASR: PCM16 mono → text. Sample rates: 16000 or 48000."""

    def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]: ...
    """User text → streaming reply text deltas.

    Empty / tool-only turn: yield zero deltas (or only whitespace).
    The loop accumulates and skips synthesis when accumulated.strip()
    == "" — R-2 convention.
    """

    async def synthesize(self, text: str) -> bytes: ...
    """TTS: text → Opus or PCM (negotiated at startup)."""

    async def endpoint(self, frame: bytes) -> "EndpointResult": ...
    """Server-side end-of-utterance + speech-start signal for one
    PCM frame. Returns the dataclass below (R-1)."""

    async def shutdown(self) -> None: ...
    """Idempotent teardown."""
```

### Optional extension — `agent_stream`

A delta-capable platform MAY expose:

```python
async def agent_stream(
    self,
    text: str,
    session_id: str,
    *,
    history: Optional[list[dict]] = None,
    turn: Optional["ConversationTurn"] = None,
) -> AsyncIterator[bytes]: ...
"""User text → streaming AUDIO PCM/Opus chunks (sub-sentence latency).

Feature 008 seam. Shape-detected by the loop via
`hasattr(platform, "agent_stream")`. NOT part of the required
Protocol; plugins without it fall through to the assemble-from-
agent_step + synthesize-per-sentence path.
"""
```

The loop tests for `agent_stream` at session-construction time and
caches the result; per-turn it skips the hasattr check.

## 2. `EndpointResult` (lifted from `EndpointSignal`) — R-1

Lives in `src/aivg_core/platforms/base.py` alongside `AgentPlatform`.

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class EndpointResult:
    """Per-frame endpoint detection signal.

    Returned by `AgentPlatform.endpoint(frame)`. Carries both
    `end_of_utterance` (the constitutional primary field) and
    `speech_started` (consumed by the voice loop's barge-in
    watcher to detect first-non-silent-frame within the current
    turn). Frozen so the Protocol implementation can construct
    and return literals cheaply.
    """
    end_of_utterance: bool
    speech_started: bool = False
```

**Migration note**: Hermes's existing
`aivg_core/platforms/hermes/bridge.py::EndpointSignal` is structurally
identical to `EndpointResult`. The Hermes plugin's
`HermesAgentPlatform.endpoint()` converts internally (one-line):

```python
sig = await self._bridge.detect_endpoint(stream, ctx=ctx)
return EndpointResult(
    end_of_utterance=sig.end_of_utterance,
    speech_started=sig.speech_started,
)
```

`EndpointSignal` stays in `bridge.py` as a plugin-internal type;
nothing outside the Hermes plugin imports it.

## 3. `HermesAgentPlatform` (plugin-internal)

Lives in NEW file `src/aivg_core/platforms/hermes/platform.py`.
This is the wrapper that satisfies `AgentPlatform` by delegating
to `HermesV013Bridge`.

```python
from typing import AsyncIterator, Optional
from ..base import AgentPlatform, EndpointResult
from .bridge import HermesV013Bridge, SessionCtx

class HermesAgentPlatform:
    """Hermes plugin's AgentPlatform implementation.

    Wraps HermesV013Bridge (low-level Hermes provider calls) and
    exposes the canonical Protocol verbs. The bridge stays
    plugin-internal; the satellite voice loop sees only this class
    via the loaded PLATFORM symbol.
    """

    name: str = "hermes"

    def __init__(self, bridge: Optional[HermesV013Bridge] = None) -> None:
        self._bridge = bridge or HermesV013Bridge(agent_runner=None)
        # session_id → SessionCtx cache (replaces the loop-side ctx
        # threading that the bridge expected). Built at first call
        # per session; trimmed at session_ended.
        self._ctx_cache: dict[str, SessionCtx] = {}

    async def startup(self, *, gateway_config: dict) -> None:
        # Bridge construction is lazy + side-effect-free; warm-up
        # happens on first verb call. Provider readiness is checked
        # by the existing _venv_has() probe inside the bridge.
        pass

    async def transcribe(self, audio: bytes, *, sample_rate: int) -> str:
        ctx = self._mint_ctx(session_id="transcribe-once", sample_rate=sample_rate)
        return await self._bridge.stt_transcribe(audio, ctx=ctx)

    async def agent_step(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
    ) -> AsyncIterator[str]:
        # The bridge's stream_callback path collects text deltas;
        # expose them through this AsyncIterator. Empty / tool-only
        # turn → yields nothing (R-2 convention).
        async for delta in self._bridge.agent_text_deltas(text, session_id, history=history):
            yield delta

    async def synthesize(self, text: str) -> bytes:
        ctx = self._mint_ctx(session_id="synth-once")
        return await self._bridge.tts_synthesize(text, ctx=ctx)

    async def endpoint(self, frame: bytes) -> EndpointResult:
        # The bridge's detect_endpoint consumes a stream; we feed
        # one-frame-at-a-time and re-shape the EndpointSignal.
        ctx = self._mint_ctx(session_id="endpoint-once")
        sig = await self._bridge.detect_endpoint_frame(frame, ctx=ctx)
        return EndpointResult(
            end_of_utterance=sig.end_of_utterance,
            speech_started=sig.speech_started,
        )

    async def shutdown(self) -> None:
        self._ctx_cache.clear()

    # ---- Optional extension (feature 008 streaming) ------------------
    async def agent_stream(
        self,
        text: str,
        session_id: str,
        *,
        history: Optional[list[dict]] = None,
        turn=None,
    ) -> AsyncIterator[bytes]:
        ctx = self._mint_ctx(session_id=session_id)
        async for audio in self._bridge.agent_stream(text, ctx=ctx, turn=turn):
            yield audio
```

Two implementation notes worth flagging:

1. **`agent_text_deltas`** is a new helper on `HermesV013Bridge`
   that exposes the existing `_cb` text-delta path as an
   `AsyncIterator[str]`. The bridge today uses this callback
   internally; the helper just wraps it in an async queue. Tiny
   addition (~20 LoC).
2. **`detect_endpoint_frame`** wraps the bridge's existing
   `detect_endpoint(stream, ctx)` (which takes an async stream)
   into a single-frame call. One-frame-stream wrapper, ~10 LoC.

Both are private to `bridge.py`. The new file `platform.py` only
sees them through the bridge's plugin-internal API.

## 4. Plugin export surface

`src/aivg_core/platforms/hermes/__init__.py` — public exports:

```python
from .platform import HermesAgentPlatform
from .setup import SETUP, HermesSetupCapability  # feature 013

# THIS is the symbol PluginRegistry.load("hermes") returns.
PLATFORM = HermesAgentPlatform()

__all__ = ["PLATFORM", "SETUP", "HermesSetupCapability"]
# NOT exported: HermesBridge, HermesV013Bridge, UnboundHermesBridge,
# EndpointSignal, AgentReply, SessionCtx. All plugin-internal.
```

After this change:

- `from aivg_core.platforms.hermes import PLATFORM` works.
- `from aivg_core.platforms.hermes import HermesBridge` works **only**
  inside the plugin (for the bridge's own tests + the wrapper); it
  is NOT in `__all__` and is grep-flagged when imported from
  outside the plugin directory (FR-011 / SC-006).

## 5. Adapter / Session / Signaling constructor changes

### `src/aivg_core/adapter.py`

```python
# BEFORE — lines 18, 127
from .platforms.hermes.bridge import HermesBridge, UnboundHermesBridge  # AgentPlatform-coupling-TODO
# ...
from .platforms.hermes.bridge import HermesV013Bridge, SessionCtx  # AgentPlatform-coupling-TODO
# ...
self._bridge = HermesV013Bridge(agent_runner=_run_agent)
self._impl = SatelliteWebRTCAdapter(bridge=self._bridge)

# AFTER
from .platforms.base import AgentPlatform, PluginRegistry, _validate_agent_platform
# ...
class _SatellitePlatformAdapter(BasePlatformAdapter):
    def __init__(self, config) -> None:
        super().__init__(config, Platform.LOCAL)
        # Resolve the active platform (default "hermes" from satellite cfg).
        self._platform: AgentPlatform = PluginRegistry.load(self.cfg.platform)
        _validate_agent_platform(self._platform)
        self._impl = SatelliteWebRTCAdapter(platform=self._platform)
```

The `_run_agent` callback that previously threaded through the
bridge is now folded inside the Hermes plugin's
`HermesAgentPlatform` initialization (it was Hermes-specific anyway
— it routes the gateway's `handle_message` async path).

### `src/aivg_core/webrtc/session.py`

```python
# BEFORE — line 23
from ..platforms.hermes.bridge import (  # AgentPlatform-coupling-TODO
    HermesBridge, SessionCtx, AgentReply, AllProvidersUnavailable,
)

# AFTER
from ..platforms.base import AgentPlatform, EndpointResult
from ..platforms.hermes.bridge import AllProvidersUnavailable  # base-class exception, plugin-neutral
```

`SessionCtx` becomes a local-to-`session.py` dataclass (it was
already mostly used here; the bridge's use was an artefact of the
old coupling). `AgentReply` is no longer needed — the loop
accumulates text via `agent_step` (R-2).

Session class signature change:

```python
class Session:
    def __init__(
        self,
        *,
        platform: AgentPlatform,        # was: bridge: HermesBridge
        transport: Transport,
        sink: LogSink,
        # ... other params unchanged ...
    ) -> None:
        self._platform = platform
        # Cache the optional agent_stream method once.
        self._agent_stream = getattr(platform, "agent_stream", None)
```

Five call-site changes (all in `session.py`):

| Old call | New call |
|---|---|
| `await bridge.tts_synthesize(text, ctx=ctx)` | `await platform.synthesize(text)` |
| `await self._bridge.detect_endpoint(stream, ctx=self._ctx)` | per-frame: `await platform.endpoint(frame)` |
| `await self._bridge.stt_transcribe(utterance, ctx=self._ctx)` | `await platform.transcribe(utterance, sample_rate=self._sr)` |
| `await self._bridge.agent_turn(text, ctx=ctx) → AgentReply` | accumulate `async for delta in platform.agent_step(text, sid, history=history)` |
| `getattr(self._bridge, "agent_stream", None)` | `self._agent_stream` (cached at construction) |

### `src/aivg_core/webrtc/signaling.py`

```python
# BEFORE — line 17
from ..platforms.hermes.bridge import HermesBridge  # AgentPlatform-coupling-TODO

# AFTER
from ..platforms.base import AgentPlatform
```

`SignalingService.__init__` takes `platform: AgentPlatform` instead
of `bridge: HermesBridge`. Internal use of the platform reference
is minimal — it's passed through to per-session `Session` instances.

## 6. Validation helper

New helper in `src/aivg_core/platforms/base.py`:

```python
def _validate_agent_platform(plat: AgentPlatform) -> None:
    """Fail fast if the loaded platform is missing a required verb.

    Called from SatelliteWebRTCAdapter.__init__ (FR-007). Raises a
    clear RuntimeError listing the missing verbs; the adapter
    refuses to start.
    """
    required = ("transcribe", "agent_step", "synthesize", "endpoint")
    missing = [v for v in required if not callable(getattr(plat, v, None))]
    if missing:
        raise RuntimeError(
            f"AgentPlatform {getattr(plat, 'name', '<unknown>')!r} is "
            f"missing required verb(s): {', '.join(missing)}. See "
            f"specs/015-agentplatform-runtime-closure/contracts/agent-platform.md."
        )
```

## 7. Entity reference table

| Entity | Where | Status after this feature |
|---|---|---|
| `AgentPlatform` Protocol | `aivg_core/platforms/base.py` | Aligned (R-1 return type) |
| `EndpointResult` dataclass | `aivg_core/platforms/base.py` | NEW (lifted from Hermes-side) |
| `PluginRegistry.load` | `aivg_core/platforms/base.py` | Unchanged |
| `_validate_agent_platform` helper | `aivg_core/platforms/base.py` | NEW |
| `HermesAgentPlatform` | `aivg_core/platforms/hermes/platform.py` | NEW |
| `HermesBridge` Protocol | `aivg_core/platforms/hermes/bridge.py` | Plugin-internal only (removed from `__all__`) |
| `HermesV013Bridge` impl | `aivg_core/platforms/hermes/bridge.py` | Plugin-internal only |
| `UnboundHermesBridge` test stub | `aivg_core/platforms/hermes/bridge.py` | Plugin-internal only |
| `EndpointSignal` Hermes dataclass | `aivg_core/platforms/hermes/bridge.py` | Plugin-internal only |
| `AgentReply` Hermes dataclass | `aivg_core/platforms/hermes/bridge.py` | Plugin-internal only |
| `SessionCtx` | moves from `bridge.py` → `webrtc/session.py` | Local to webrtc layer |
| `Session` (voice session) | `aivg_core/webrtc/session.py` | Constructor: `bridge=…` → `platform=…` |
| `SignalingService` | `aivg_core/webrtc/signaling.py` | Constructor: `bridge=…` → `platform=…` |
| `SatelliteWebRTCAdapter` | `aivg_core/adapter.py` | Holds `AgentPlatform`, validates at startup |
