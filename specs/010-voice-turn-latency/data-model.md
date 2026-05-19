# Phase 1 Data Model: Voice-Turn Latency

No persistence/schema. Transient per-turn timing only; the record is
emitted through the existing `LogSink` (not stored). Pure assembly lives
in the new `turnlatency.py`.

## Entities (transient, in-process)

| Entity | Definition | Rules |
|---|---|---|
| **Turn Stage** | A named, timed segment with a start instant and an end instant (monotonic clock). | Stages are contiguous; the end of stage *n* is the start of stage *n+1*. A stage may be **absent** (turn errored/interrupted/empty before it ran) — absence is recorded, never faked. |
| **Latency Breakdown** | The ordered list of completed Turn Stages for one turn + the end-to-end total (end_of_speech → first_audio_delivered). | Ordered by the canonical stage sequence (D1). Sum of present stage durations equals the end-to-end span within a small tolerance (SC-003). Exposes the single dominant stage. Built by `turnlatency.py` (pure). |
| **Voice Turn** | One exchange (reused from 001/005/006/008). | Carries the stage instants; on completion `session.py` builds the Breakdown and emits it once. |
| **Baseline Record** | The Latency Breakdown for the agreed typical short prompt, captured BEFORE any tuning. | The reference for FR-004/SC-001/SC-004; recorded via the same instrumentation (Principle V). |
| **Tuning Parameter** | A value affecting the speed/quality trade-off. | FR-011/SC-009: every one is config-driven — a Hermes `~/.hermes/config.yaml` key (inherited/read) or the existing `satellite:` block (existing loader). NEVER a hardcoded code constant. |
| **Instrumentation Setting** | Verbosity/enable of the breakdown. | Lives in the existing `satellite:` block; default **on** (lightweight always produced — FR-012); only detail level/enable is tunable. |

## Canonical stage sequence (the only ordering)

```
end_of_speech
  └─[1 endpoint]→ endpoint_detected
       └─[2 stt]→ stt_done
            └─[3 agent]→ agent_first_output
                 └─[4 assemble]→ first_unit_ready
                      └─[5 synth]→ first_audio_synth
                           └─[6 playback]→ first_audio_delivered  (= end-to-end end)
```

- Stage 1 owner: `session.py` (`detect_endpoint` → end_of_utterance);
  `end_of_speech` ≈ `endpoint_detected − voice.silence_duration` (config
  value, read not hardcoded).
- Stages 2 & 6 owner: `session.py` (`stt_transcribe` span; first
  `send_audio`).
- Stages 3–5 owner: `hermes_bridge.agent_stream` (first delta / first
  assembled unit / first `tts_synthesize` return) → recorded onto the turn.

## State / lifecycle

None beyond the turn's own lifecycle. Instants are stamped as the turn
already progresses through existing seams; on turn end (success, error,
barge-in, or empty) `turnlatency.py` assembles whatever instants exist
into an ordered Breakdown (missing tail stages simply omitted, never
hung/faked — FR-008) and `session.py` emits it once via `self._log`.
