# Contract — `AgentPlatform` Protocol

**Feature**: 015-agentplatform-runtime-closure · **Phase**: 1 · **Date**: 2026-05-20

This is the binding contract every agent-platform plugin MUST satisfy
so the satellite voice loop can drive it without importing
plugin-internal symbols. The satellite layer in `aivg_core` consumes
**only** the verbs defined here, plus the optional `agent_stream`
extension (§ 7).

Type signatures and dataclass shapes are normative; see
[../data-model.md](../data-model.md) for the canonical Python source.

---

## 1. Plugin discovery contract

A platform plugin is a Python package under
`src/aivg_core/platforms/<name>/` exposing a module-level constant:

```python
PLATFORM: AgentPlatform
```

`PluginRegistry.load(name: str) -> AgentPlatform` imports
`aivg_core.platforms.<name>` and returns the `PLATFORM` attribute.
Any plugin that fails this contract — missing `PLATFORM`, or
`PLATFORM` failing `_validate_agent_platform` — MUST cause adapter
startup to fail with a clear `RuntimeError` (FR-007).

The plugin MAY also expose a `SETUP` constant satisfying the feature
013 `SetupCapability` Protocol, but that is out of scope for this
contract.

---

## 2. Required verbs

All four verbs below MUST be present as `callable` attributes on the
plugin's `PLATFORM` instance. `_validate_agent_platform` checks for
exactly this set (R-4).

### 2.1 `transcribe(audio, *, sample_rate) -> str`

```python
async def transcribe(self, audio: bytes, *, sample_rate: int) -> str
```

**Inputs**:
- `audio` — PCM16 mono little-endian bytes for one captured utterance.
- `sample_rate` — Hertz. The voice loop today sends `16000` (downsampled
  upstream) and MAY send `48000` (WebRTC default). Plugins MUST accept
  both; resampling internally is acceptable.

**Output**: UTF-8 text. Empty string is legal — represents "could not
transcribe / silence". The loop treats empty as "skip the agent turn"
(US2 edge case).

**Error policy**: A platform-internal STT failure SHOULD raise
`AllProvidersUnavailable` (already imported by the satellite as a
plugin-neutral, base-class exception). The loop catches this and
emits a `transient_error` event; the user can re-press PTT.

### 2.2 `agent_step(text, session_id, *, history=None) -> AsyncIterator[str]`

```python
def agent_step(
    self,
    text: str,
    session_id: str,
    *,
    history: Optional[list[dict]] = None,
) -> AsyncIterator[str]
```

**Inputs**:
- `text` — user utterance text (output of `transcribe`).
- `session_id` — opaque stable string identifying the conversation;
  the platform MAY use it to key its own conversation memory.
- `history` — optional list of `{role, content}` dicts (OpenAI-style).
  The loop populates this from the assembled user/agent turns of the
  current voice session.

**Output**: Async iterator yielding **text deltas**. The loop
accumulates deltas into a per-turn buffer; downstream behaviour is:
- accumulated text `.strip() != ""` → call `synthesize(accumulated)`
- accumulated text `.strip() == ""` → skip TTS (R-2 empty-reply
  convention; tool-only turns hit this path)

**Cancellation**: The loop MUST be able to `aclose()` the iterator on
barge-in. Plugins MUST treat `GeneratorExit` as a normal cancellation
and release any provider resources promptly (<200ms — SC-009 budget).

### 2.3 `synthesize(text) -> bytes`

```python
async def synthesize(self, text: str) -> bytes
```

**Inputs**:
- `text` — UTF-8 reply text. The loop does NOT strip markdown
  upstream — plugins that emit markdown deltas SHOULD strip before
  synthesis (Hermes plugin reuses feature 009 `_strip_markdown_for_tts`).

**Output**: Audio bytes — either Opus or PCM16, format negotiated at
`startup` via `gateway_config`. The default is PCM16 mono @ 48000 Hz
(matches the satellite's RTP sender).

**Latency**: Feature 010 budget — median <600ms first-audio for short
replies. Plugins that cannot meet this SHOULD also expose `agent_stream`
(§ 7).

### 2.4 `endpoint(frame) -> EndpointResult`

```python
async def endpoint(self, frame: bytes) -> EndpointResult
```

**Inputs**: `frame` — single PCM16 mono frame, 20ms @ 16000Hz
(640 bytes). The loop calls this once per inbound frame during the
listening state.

**Output**: `EndpointResult` dataclass (frozen):

```python
@dataclass(frozen=True)
class EndpointResult:
    end_of_utterance: bool   # True → loop transitions to thinking
    speech_started: bool = False  # True on first non-silent frame in turn
```

**Statefulness**: The platform MAY hold per-session VAD state internally
keyed by the most recent `startup` / by ambient session context. The
satellite contract does NOT pass `session_id` into `endpoint` — plugins
that need it SHOULD key off the calling task identity or use a single
global VAD (Hermes does the latter).

---

## 3. Lifecycle verbs

### 3.1 `startup(*, gateway_config) -> None`

Called once at adapter startup, after plugin load and before any
session is accepted.

`gateway_config` is the satellite's resolved YAML config dict (passed
by reference, plugins MUST treat as read-only). Plugins use it to
pick up: TTS audio format, target sample rates, optional API keys
that the user mirrors into the gateway config.

MUST NOT raise on recoverable errors (e.g. provider not yet warm) —
log + continue. MUST raise only on misconfiguration that makes
operation impossible (e.g. required API key missing).

### 3.2 `shutdown() -> None`

Idempotent. Called from adapter shutdown. MUST release all
long-lived resources (HTTP clients, subprocesses, model handles).

---

## 4. Optional extension — `agent_stream`

```python
async def agent_stream(
    self,
    text: str,
    session_id: str,
    *,
    history: Optional[list[dict]] = None,
    turn: Optional["ConversationTurn"] = None,
) -> AsyncIterator[bytes]
```

A delta-capable platform MAY expose `agent_stream` to short-circuit
the `agent_step → accumulate → synthesize` path. Output is **audio
bytes** in the same format as `synthesize`.

The loop detects this method via `hasattr(platform, "agent_stream")`
at `Session.__init__` and caches the bound method. Per-turn:

- `agent_stream` present → use it; fall back to step+synthesize on
  exception or empty iterator.
- absent → use `agent_step` + `synthesize` per accumulated sentence.

The Hermes plugin exposes `agent_stream` (feature 008). Future
plugins are NOT required to.

---

## 5. Validation contract

Adapter startup invokes:

```python
_validate_agent_platform(self._platform)
```

This MUST succeed before any session is accepted. It checks:

1. The four required verbs (`transcribe`, `agent_step`, `synthesize`,
   `endpoint`) are present and callable on the instance.
2. The `name` attribute is a non-empty lowercase string.

Failure raises `RuntimeError` with the list of missing verbs and a
pointer to this contract document.

`_validate_agent_platform` does NOT runtime-check the optional
`agent_stream` extension.

---

## 6. Wire-surface invariance (FR-014)

This contract changes NO bytes on:
- The HTTP `/webrtc/offer` request/response shape.
- WebSocket frame schemas to/from the satellite.
- The `@aivg/sat-sdk` TypeScript SDK public API.

A working v0.1.x SDK build MUST continue to drive the gateway over a
live WebRTC session through every code path touched by this feature.
This is enforced by re-running the electron-test smoke (US4) after
the refactor.

---

## 7. Contract tests (binding)

Each test below MUST exist in `tests/contract/test_agent_platform_contract.py`
and run against TWO fixtures: `HermesAgentPlatform` (real provider
stack with the Hermes bridge mocked) AND `tests/fixtures/platforms/echo/`
(the echo plugin already on disk).

| Test | What it asserts | Source FR |
|---|---|---|
| `test_protocol_runtime_check` | `isinstance(PLATFORM, AgentPlatform)` (PEP 544 `@runtime_checkable`) | FR-001 |
| `test_required_verbs_present` | All four verbs callable | FR-001, FR-007 |
| `test_validate_helper_accepts` | `_validate_agent_platform(PLATFORM)` returns `None` | FR-007 |
| `test_validate_helper_rejects_partial` | Stripping `transcribe` raises `RuntimeError` | FR-007 |
| `test_transcribe_returns_str` | `await PLATFORM.transcribe(silence_frame, sample_rate=16000)` returns `str` | FR-002 |
| `test_agent_step_yields_str_deltas` | `agent_step` returns async iter of `str`; iterator closes cleanly on `aclose()` | FR-003 |
| `test_agent_step_empty_turn` | Tool-only turn → zero deltas; accumulated `.strip() == ""` | FR-003, edge |
| `test_synthesize_returns_bytes` | `await PLATFORM.synthesize("hi")` returns non-empty `bytes` | FR-004 |
| `test_endpoint_returns_result` | `await PLATFORM.endpoint(frame)` returns `EndpointResult` with both fields | FR-005 |
| `test_lifecycle_idempotent` | `startup` then `shutdown` then `shutdown` does not raise | FR-006 |
| `test_no_hermes_imports_outside_plugin` | Greps `src/aivg_core/` for `from .platforms.hermes.` imports outside `src/aivg_core/platforms/hermes/`; expects zero matches | FR-011, SC-006 |
| `test_no_coupling_todo_markers` | Greps `src/aivg_core/` for `# AgentPlatform-coupling-TODO`; expects zero matches | FR-012, SC-006 |
| `test_wire_surface_unchanged` | Re-runs `tests/integration/test_signaling_offer_answer.py` and `tests/sdk/test_ws_frame_shapes.py` (read-only — no diff allowed in fixtures) | FR-014 |

---

## 8. Out of scope for this contract

- TLS / authentication concerns (handled by the gateway, not the
  platform).
- Multi-platform routing within a single satellite (one platform
  per adapter instance).
- C++ SDK (feature 016).
- OpenClaw plugin (separate feature). This contract is the seam it
  will be written against.
