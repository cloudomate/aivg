# Contract: Hermes Bridge (internal seam)

`hermes_bridge.py` is the **only** module permitted to touch Hermes
intelligence (constitution I). It contains delegation only — no Whisper, no
Piper, no engine objects, no agent loop, no silence algorithm of its own. The
rest of the package depends on this Protocol, not on the concrete Hermes API,
so the running-build verification gates (research VG-1..VG-4) change only this
file + the registration shim.

## Interface (Protocol)

```python
class HermesBridge(Protocol):
    async def stt_transcribe(self, pcm: AudioBuffer, *, ctx: SessionCtx) -> str:
        """Delegate to Hermes's configured STT provider (+ its fallback order).
        MUST NOT instantiate any recognizer."""

    async def detect_endpoint(self, pcm_stream) -> EndpointSignal:
        """Delegate to Hermes's authoritative server-side silence/end-of-
        utterance algorithm. Device VAD never substitutes for this."""

    async def agent_turn(self, user_text: str, *, ctx: SessionCtx) -> AgentReply:
        """Invoke the Hermes agent as an entity via the SAME path the
        telegram/discord adapters use. One in-flight call per session."""

    async def tts_synthesize(self, text: str, *, ctx: SessionCtx) -> AudioBuffer:
        """Delegate to Hermes's configured TTS provider (+ its fallback)."""
```

`SessionCtx` carries `device_id`, `session_id`, conversation/agent context,
and configured-provider selection — all sourced from Hermes config, never
re-specified here.

## Guarantees / rules

- **No engine instantiation** anywhere in the package outside this Protocol's
  Hermes-backed implementation (enforced by a unit/lint test that fails on
  `whisper`/`piper`/engine imports outside `hermes_bridge`).
- Provider selection + fallback are **inherited** from Hermes config; the
  adapter exposes no provider config (FR-006).
- Endpointing authority is `detect_endpoint` only (FR-005, constitution I).
- All four calls are async and cancellable — barge-in cancels the in-flight
  `agent_turn`/`tts_synthesize` within ≤300 ms (SC-003).
- On all-providers-unavailable, calls raise a typed error → session emits a
  perceptible failure, not silence/hang (FR-015).

## Test double (`FakeHermesBridge`, tests/)

Deterministic implementation for the whole test suite (no live Hermes / no
hardware): scripted transcripts, configurable latency, injectable
provider-failure, controllable endpoint signal. Lets P1 loop, barge-in,
reconnect, fallback, and 10× concurrency be validated against the fake while
the real implementation is wired behind the verification gates.

## Verification gates (from research.md)

| Gate | Confirm in running Hermes build | Touches |
|------|---------------------------------|---------|
| VG-1 | STT/TTS provider interface names + signatures | real bridge impl |
| VG-2 | Silence/end-of-utterance entrypoint + config thresholds | `detect_endpoint` |
| VG-3 | Shared adapter→agent entrypoint + session ctx object | `agent_turn` |
| VG-4 | Adapter registration hook + enable/restart CLI | registration shim |
