# Phase 0 Research: Instrument & Reduce Voice-Turn Latency

Grounded in this session's live debugging of the local hermes-agent
v0.14.0 install and read of the satellite turn loop. Measure-first
(constitution V): the dominant stage is to be **confirmed by the new
instrumentation + a recorded baseline**, not assumed; the levers below are
what the architecture permits.

## D1 — The stage map (where the time goes; where to time it)

- **Decision**: Instrument these contiguous stages of one turn:
  1. `end_of_speech` → `endpoint_detected` (Hermes silence rule;
     ≈ `voice.silence_duration` of trailing silence — the satellite knows
     the detected instant; the true end-of-speech is `silence_duration`
     earlier and is derivable since that value is read from config).
  2. `endpoint_detected` → `stt_done` (Hermes STT, `stt_transcribe`).
  3. `stt_done` → `agent_first_output` (agent first text delta).
  4. `agent_first_output` → `first_unit_ready` (sentence assembled).
  5. `first_unit_ready` → `first_audio_synth` (Hermes Piper TTS).
  6. `first_audio_synth` → `first_audio_delivered` (transport playback).
- **Evidence (verified seams)**: `session.py::_collect_utterance` returns
  exactly when `bridge.detect_endpoint(...).end_of_utterance` (the
  endpoint_detected instant); `_handle_turn` then calls
  `bridge.stt_transcribe(...)` (stt span) then `_respond` →
  `agent_stream`; the `async for audio in streamer(...)` first iteration =
  first unit synthesized; the subsequent `send_audio` = first audio
  delivered. Stages 3–5 live inside `hermes_bridge.agent_stream` (it alone
  sees the first `stream_callback` delta, first assembled unit, first
  `tts_synthesize` return) → it records those three instants onto the
  turn; `session.py` records 1, 2, 6 and emits the consolidated record.
- **Rationale**: These are the existing seams; no new control flow. The
  consolidated record is emitted once at the existing `"turn complete"`
  `self._log` (LogSink) so it is one coherent line (FR-002).

## D2 — Likely dominant costs (to confirm, not assume)

- **Observed this session (feature 009 live test, not yet
  instrumented)**: a ~10 s gap between Whisper transcription completing and
  the agent turn starting, plus a fixed `voice.silence_duration: 3.0` s
  trailing-silence wait before the endpoint even fires, plus Whisper
  `medium` STT on multi-second utterances. These are the prime suspects;
  the instrumentation will quantify each per FR-003.
- **Rationale for measuring first**: without per-stage numbers any tuning
  is guesswork (Principle V); the baseline record is the gate to FR-004.

## D3 — The permitted levers (config-only; nothing hardcoded — FR-011)

- **Decision / Evidence (verified in `~/.hermes/config.yaml`)**:
  - `voice.silence_duration` (currently `3.0`) and
    `voice.silence_threshold` (`200`) — endpoint silence behaviour;
    lowering `silence_duration` (e.g. → ~1.0–1.5 s) directly cuts stage 1.
    Endpointing stays Hermes's algorithm — only its exposed value changes.
  - `stt.local.model` (currently `medium`) — lowering to `small`/`base`
    materially cuts stage 2 on CPU; it is a Hermes config value, not an
    engine swap in our code.
  - `streaming` block (already `enabled:true, transport:auto` from feature
    008's deploy) — keeps stage 4/5 overlapped; verify nothing in the
    satellite adds avoidable buffering before the first unit.
- **Config homes (constitution IV; verified)**: engine/endpoint knobs are
  the existing Hermes keys above (inherited & read — the satellite already
  reads `voice_mode` silence values via `HermesV013Bridge._load_silence_
  rule`; STT model is Hermes-internal to `transcribe_audio`). Any
  satellite-side knob (instrumentation verbosity/enable) goes in the
  EXISTING `satellite:` block via the EXISTING `SatelliteAdapterConfig`
  (`default_config`/extra). **No new file, loader, or secret store. No
  tuning value is a hardcoded constant** (FR-011/SC-009).
- **Delivery (clarify Q1)**: `deploy/deploy-local.sh` adds an idempotent,
  **backup-first, reversible** step that sets the faster defaults in
  `~/.hermes/config.yaml` — the same mechanism it already uses for the
  `streaming:` block. Operator overrides via config or restores the
  timestamped backup to revert latency exactly (FR-004/FR-010/SC-008).
- **Alternatives considered**: device/satellite-side VAD to shortcut the
  endpoint — REJECTED (constitution I: authoritative endpoint is Hermes's
  algorithm; device VAD may only *gate* upstream, not replace endpointing).
  Streaming STT — REJECTED (would reimplement/replace Hermes STT). A new
  `satellite.latency` config schema/loader — REJECTED (constitution IV: no
  new loader; reuse the existing block).

## D4 — Local testability boundary (constitution V)

- **Decision**: The deterministic, locally unit-tested slice is
  `turnlatency.py`: given recorded stage instants (some possibly missing
  due to error/barge-in/empty), produce an **ordered** `LatencyBreakdown`
  whose stage durations sum (within tolerance) to the end-to-end total and
  expose the dominant stage — pure, stdlib, no I/O (mirrors
  `streamasm.py`/`textseg.py`). Tests also assert tuning values are READ
  from config, not hardcoded (SC-009/FR-011).
- **Host-only / host-proven**: the real wall-clock reductions, the Hermes
  STT-model swap effect, and "feels snappy" are proven by the live spoken
  before/after on the local install (same discipline as 005/006/008/009);
  the fake-transport suite stays green with no edits (instrumentation is
  additive; the fake path is unaffected).

## D5 — No-regression guard

- **Decision**: 008 (first-sentence-while-generating), 009 (clean speech),
  barge-in stop, multi-turn continuity must all still pass after the
  config changes. The instrumentation is emit-only (no behaviour change,
  FR-007); the only behavioural change is faster Hermes config values,
  which the before/after + the live 008/009/barge-in checks cover (FR-006/
  SC-005). `deploy-local.sh` stays backup-first so any regression is a
  one-command restore.

## T002 — RESOLVED at implement time (host v0.14.0, 2026-05-19)

- `~/.hermes/config.yaml`: `stt.local.model: medium`,
  `stt.provider: local`; `voice.silence_duration: 3.0`,
  `voice.silence_threshold: 200`. These are the faster-defaults targets
  for `deploy-local.sh` (T009): e.g. `stt.local.model` → `small`/`base`,
  `voice.silence_duration` 3.0 → ~1.0–1.5 (operator-overridable,
  backup-restorable — clarify Q1).
- The satellite already INHERITS the silence rule (constitution IV/FR-011):
  `HermesV013Bridge._load_silence_rule()` reads
  `tools.voice_mode.SILENCE_RMS_THRESHOLD/SILENCE_DURATION_SECONDS`
  (module-level fallback constants apply ONLY if the Hermes import fails on
  a non-host env) — so endpoint timing is config-derived, not an adapter
  hardcode. STT model is internal to Hermes `transcribe_audio` (config).
- `satellite:` block has `default_config: {wake_word, routing_mode,
  log_level}`; `SatelliteAdapterConfig.from_mapping` loads
  `default_config=dict(block.get("default_config", {}))` — the
  instrumentation knob (T007) goes here (e.g. `default_config.
  latency_log: full|summary|off`, default summary/on), no new loader.
- Seams confirmed: `session.py::_collect_utterance` (endpoint),
  `::_handle_turn` `stt_transcribe` span + first `send_audio`;
  `hermes_bridge.agent_stream` has `turn` in scope for the 3 agent/synth
  instants. "Typical short prompt" fixed = **"what time is it?"** (one
  sentence, short answer) — used for baseline & after.

## Residual (re-verify at implement time, not blockers)

- Exact current values + key paths in the running `~/.hermes/config.yaml`
  (`voice.silence_duration`, `stt.local.model`) and the
  `SatelliteAdapterConfig` field used for the instrumentation knob — re-read
  at implement time (same discipline as 003/005/007/008/009).
- Whether `agent_stream` already exposes a clean point for the three
  agent/synth instants without disturbing the 008/009 logic — confirm the
  minimal touch when implementing (it has `turn` in scope already).
- The agreed "typical short prompt" phrase + the post-baseline final
  numeric targets (Assumptions) — fixed at implement time and recorded.
