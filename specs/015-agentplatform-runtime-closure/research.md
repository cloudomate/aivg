# Research — AgentPlatform Runtime Closure (Phase 0)

**Feature**: 015-agentplatform-runtime-closure · **Date**: 2026-05-20

The spec was clarification-free (the user pre-resolved the two open
questions in the spec prompt: canonical verb names + keep `agent_stream`
as an optional extension). What's left for Phase 0 is two ADRs that
arise from the implementation work itself:

- **R-1** — `endpoint()` return type: bare `bool` (constitution literal) vs richer `EndpointResult` dataclass.
- **R-2** — `agent_step()` empty-reply convention.

Plus three smaller "pattern" decisions that pin down implementation
mechanics so the next phase doesn't re-litigate them.

---

## R-1. `endpoint()` return type

**Question**: The constitution's Principle IV declares
`endpoint(audio_frame) → end_of_utterance?` — a predicate-style bool.
But the loop today uses BOTH `sig.end_of_utterance` AND
`sig.speech_started` from the Hermes-side `EndpointSignal` dataclass.
If we narrow the return to bare `bool`, the loop loses
`speech_started`. What do we adopt?

**Code reality** (today):

```python
# webrtc/session.py:208 — uses sig.end_of_utterance
if sig.end_of_utterance: ...

# webrtc/session.py:336 — uses sig.speech_started
if sig.speech_started: ...

# platforms/hermes/bridge.py:61 — the Hermes-side dataclass
@dataclass
class EndpointSignal:
    end_of_utterance: bool
    speech_started: bool = False
```

So `speech_started` is *genuinely consumed* by the loop's
barge-in watcher path. Dropping it would require duplicating VAD
logic at the satellite layer (constitutional Principle I forbids
satellite-side VAD: "Authoritative end-of-utterance is the platform's
existing server-side silence algorithm, reused unchanged").

**Options considered**:

1. **Bare `bool` (constitution literal, drop `speech_started`).**
   *Rejected*: violates Principle I (forces VAD logic onto the
   satellite) and constitutes a behavioural regression.
2. **Two separate Protocol verbs** (`is_end_of_utterance` +
   `is_speech_active`). *Rejected*: noisy API; every plugin
   implements both; couples two checks that platforms naturally
   compute in a single pass.
3. **Lift `EndpointSignal` → `EndpointResult` into `platforms/base.py`.**
   ✅ *Selected*. The constitution's wording (`endpoint(audio_frame)
   → end_of_utterance?`) describes the *predicate semantic* of the
   return value; a struct whose primary field is
   `end_of_utterance: bool` satisfies that semantic exactly, and
   carrying `speech_started` alongside is a strict superset that
   no plugin is forced to use.

**Decision (R-1)**: introduce
`@dataclass class EndpointResult { end_of_utterance: bool;
speech_started: bool = False }` in `src/aivg_core/platforms/base.py`.
The Protocol's `endpoint` verb returns it. Hermes's
`HermesAgentPlatform.endpoint(frame)` delegates to the existing
`HermesV013Bridge.detect_endpoint(stream, ctx)` and re-shapes the
returned `EndpointSignal` to `EndpointResult` (one-for-one field
mapping). The bridge keeps `EndpointSignal` internally for
backwards-compatible plugin code; nothing outside the plugin
sees it.

**Constitution check**: this is a structural refinement that
preserves Principle IV's literal wording (`end_of_utterance?` is
the result's primary field) and rescues Principle I (no satellite
VAD). NOT a v2.0.x bump — the principle text doesn't change.

---

## R-2. `agent_step()` empty-reply convention

**Question**: Hermes's existing `agent_turn(text, ctx)` returns
`AgentReply { text: str, is_empty: bool }` so the loop can detect
"empty / tool-only reply" without inspecting `text`. The constitution's
`agent_step(text, session) → reply_stream` is an `AsyncIterator[str]`
(text deltas). What signals an empty reply?

**Code reality** (today):

```python
# webrtc/session.py:313
reply: AgentReply = await self._bridge.agent_turn(turn.user_text, ctx=self._ctx)
# ... later:
if reply.is_empty or not (reply.text or "").strip():
    return  # empty / tool-only turn → back to listening
```

So the existing logic ALREADY checks "is_empty OR text-after-strip
is empty". The `is_empty` flag is informational; the empty-string
check is the load-bearing branch.

**Options considered**:

1. **Add `is_empty` to the Protocol** (some plugins might emit
   tool-only replies as zero deltas but want to signal an
   intentional empty turn). *Rejected*: muddies the streaming
   contract. The natural signal "no deltas yielded" is sufficient.
2. **Empty-string convention** (loop accumulates `"".join(deltas)`
   and checks `.strip() == ""`). ✅ *Selected*. Matches what the
   existing code path already does post-strip. No protocol
   surface change.

**Decision (R-2)**: `agent_step()`'s contract is "yield text deltas
in order; yield zero deltas (or only whitespace) for an empty /
tool-only turn." The loop accumulates and checks
`accumulated.strip() == ""`. Hermes's `HermesAgentPlatform.agent_step`
maps onto its existing delta-callback path (`run_conversation`'s
`stream_callback`), yielding the same deltas the existing
`agent_stream` path collects internally.

**Edge case**: the existing `HermesBridge` raises
`AllProvidersUnavailable` from `agent_turn` when STT/TTS providers
are all down. The Protocol surface has no such typed exception.
Resolution: `HermesAgentPlatform` keeps raising
`AllProvidersUnavailable` (it's a `RuntimeError` subclass, fully
platform-neutral as a base-class type). The loop's existing
`except AllProvidersUnavailable` clause stays.

---

## R-3. Where the platform instance is constructed

**Question**: today the `_SatellitePlatformAdapter` factory in
`adapter.py:127` constructs a `HermesV013Bridge` directly. After
the refactor, who constructs the `AgentPlatform` and when?

**Decision (R-3)**: the platform is constructed at adapter startup
via `PluginRegistry.load(self.cfg.platform)` — the platform name
comes from the satellite-side `aivg_core` config
(`SatelliteAdapterConfig.platform`, default `"hermes"`). The
factory function holds the loaded `AgentPlatform` instance and
passes it into both the voice session and the signaling service
on construction.

Concretely:

```python
# adapter.py — after refactor
class _SatellitePlatformAdapter(BasePlatformAdapter):
    def __init__(self, config):
        super().__init__(config, Platform.LOCAL)
        # Was: self._bridge = HermesV013Bridge(...)
        from .platforms.base import PluginRegistry
        self._platform = PluginRegistry.load(self.cfg.platform)
        self._impl = SatelliteWebRTCAdapter(platform=self._platform)
```

`SatelliteWebRTCAdapter` propagates the platform to the
`SignalingService` and the per-session voice loop.

---

## R-4. Fail-fast protocol validation at adapter startup

**Question**: spec FR-007 — "fail fast at startup with a clear
error listing missing required protocol verbs when a platform
plugin omits any of `transcribe`, `agent_step`, `synthesize`,
`endpoint`." How is this enforced?

**Decision (R-4)**: `AgentPlatform` is already a `@runtime_checkable`
Protocol, but `isinstance(plat, AgentPlatform)` only checks
*shape* (method presence) — not signatures. We add an explicit
`_validate_agent_platform(plat)` helper called from
`SatelliteWebRTCAdapter.__init__` that asserts each of the four
required verbs is present and is callable:

```python
def _validate_agent_platform(plat: AgentPlatform) -> None:
    required = ("transcribe", "agent_step", "synthesize", "endpoint")
    missing = [v for v in required if not callable(getattr(plat, v, None))]
    if missing:
        raise RuntimeError(
            f"AgentPlatform {plat.name!r} is missing required verb(s): "
            f"{', '.join(missing)}. See specs/015-agentplatform-runtime-closure/"
            f"contracts/agent-platform.md."
        )
```

Optional methods (`agent_stream`) are not validated — they're
shape-detected at first use in the loop.

---

## R-5. Test-fixture migration path

**Question**: how many existing tests directly hold a `HermesBridge`
reference and need their fixtures migrated to `HermesAgentPlatform`
or `FakeAgentPlatform`?

**Survey**:

```
$ grep -rln 'HermesBridge\|UnboundHermesBridge\|HermesV013Bridge' tests/ | wc -l
~12 files
```

The majority are inside `tests/unit/` testing Hermes-bridge internals
(streaming, normalisation, latency seams) — those tests stay
intact because they're testing the Hermes plugin's internals
(now plugin-internal symbols, still importable as
`from aivg_core.platforms.hermes.bridge import ...` from tests).

A smaller subset of tests construct the voice session against a
`FakeHermesBridge`. Those tests are migrated to construct a
`FakeAgentPlatform` (a tiny test helper) and pass it where the
session previously took the bridge.

**Decision (R-5)**: add a `tests/helpers/fake_agent_platform.py`
that implements `AgentPlatform` with configurable canned responses
per verb. Migrate the ~3-4 session-construction sites that today
build a `FakeHermesBridge` directly. Bridge-internal tests are
untouched.

---

## R-6. Latency parity verification

**Question**: SC-003 requires post-refactor latency within ±10 %
of feature-010's baseline. How is this measured?

**Decision (R-6)**: re-run the existing
`tests/integration/test_voice_turn_latency.py` suite before and
after the refactor on the same machine, same config (`aivg setup
--legacy-hermes --force --yes`), same Electron client. The test
emits the latency breakdown (`endpoint_detected →
agent_first_output → first_unit_ready → first_audio_synth →
first_audio_delivered`) per turn; median across N=10 turns is
the SC-003 measurement.

If the median post-refactor turn is more than 10 % slower than
the pre-refactor median, the refactor reverts to the next-most-
conservative implementation choice (smallest delta from current
code) until parity is achieved.

---

## Out of scope (recorded for clarity)

The following appear adjacent to this feature but are deliberately
DEFERRED (matches spec OOS-001 … OOS-005):

- Shipping an actual OpenClaw platform plugin. The seam is closed
  here; OpenClaw is its own future feature.
- Changes to the public WS/REST wire surface, the JSON message
  shapes, or the management plane contract version. `aivg
  --contract-version` stays `1.0.0`.
- Changes to the TypeScript SDK (`@aivg/sat-sdk`). The SDK is a
  wire-only consumer.
- The C++ SDK (`libaivg-sat`) — that is feature 016.
- Constitutional amendment. Principle IV stays at v2.0.1 / current
  text; this feature *closes* the principle's runtime obligation
  rather than redefining it.
