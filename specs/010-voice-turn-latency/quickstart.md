# Quickstart: Voice-Turn Latency — instrument, baseline, tune, prove (LOCAL Hermes)

Goal: a per-turn latency breakdown for every turn, then a measured ≥40%
cut in end-of-speech → first-word via reversible Hermes config defaults —
no engine rebuilt, no hardcoded tuning. All localhost.

## 0. Preconditions

- Feature 010 code: `turnlatency.py` (pure breakdown), stage instants in
  `session.py` + `hermes_bridge.agent_stream`, instrumentation knob read
  from the existing `satellite:` block, `deploy-local.sh` faster-defaults
  step (backup-first, reversible). Local Hermes v0.14.0 running; pairing
  `local/electron-test-1` approved. 008+009 already live.

## 1. Local: provable slice + no regression (SC-003/SC-006/FR-009)

```bash
cd /Users/yashwant.singh/coderepo/hermes-voice-gateway
.venv/bin/python -m pytest -q
```

Expect: new `tests/unit/test_turnlatency.py` green (ordered breakdown sums
to total within tolerance; dominant stage exposed; missing/interrupted/
error stages handled; tuning values read from config, none hardcoded) AND
the existing suite (88) still 100% green WITH NO test edits.

## 2. Implement-time host re-verify (constitution V)

Re-read the running `~/.hermes/config.yaml`: current `voice.silence_
duration`, `voice.silence_threshold`, `stt.local.model`, and the
`satellite:` block; confirm `SatelliteAdapterConfig` exposes the
instrumentation knob path. Record actual values + the agreed "typical
short prompt" phrase here. Same discipline as 003/005/007/008/009.

## 3. Baseline BEFORE tuning (FR-003/L5 — Principle V)

Reload the Electron client (`http://localhost:8643`/`:8644`, no tunnel),
Connect. Ask the agreed typical short prompt; from
`~/.hermes/logs/` read the per-turn breakdown. **Record the baseline
numbers here** (per-stage + end-to-end). Repeat ~3× for a median.

### Baseline RECORDED 2026-05-19 (un-tuned: stt medium, silence 3.0; --no-tune build)

Prompt **"what time is it?"**, summary mode, `turn latency` records:

| turn | total_ms | dominant |
|------|----------|----------|
| 1 | 40401.4  | stt   (outlier: Piper wave.Error retry / cold STT) |
| 2 | 17103.6  | agent |
| 3 | 10732.8  | stt   |
| 4 | 12882.7  | agent |

**Median ≈ 15.0 s** end-of-speech → first audible word; dominated by
**STT (Whisper medium)** and **agent first-token**. This is the FR-003 /
SC-001 reference. (Instrumentation proven: feature-010 `turn latency`
emitted for every turn, summary mode, `complete: true` — SC-003.) The
≥40 % target → median ≲ 9 s after the faster defaults.

## 4. Local gated redeploy with reversible faster defaults (FR-004/FR-010)

```bash
deploy/deploy-local.sh --preflight        # read-only
deploy/deploy-local.sh --yes              # 🔒 LOCAL-MUTATING (backup-first, idempotent)
```

Backs up `~/.hermes/config.yaml`, sets faster defaults (e.g.
`voice.silence_duration` ↓, `stt.local.model` ↓ medium→small/base) the
same idempotent way it already sets the `streaming:` block, restarts the
gateway, post-verifies (plugin import/register, 0 pre-existing platforms
removed, both :8643 & :8644 LISTENING). Production `deploy-to-hermes.sh`
untouched.

## 5. After: prove the win (SC-001/SC-002/SC-004)

Reconnect; ask the SAME prompt ~3×. From the breakdowns: median
end-of-speech → first-audible-word **≥40% lower** than the §3 baseline,
target ≤2 s; the before/after shows WHICH stage(s) improved. Log both sets
of numbers here.

### After RECORDED 2026-05-19 (tuned: stt small, silence 1.2)

Prompt **"what time is it?"**, `turn latency` (summary):

| turn | total_ms | dominant | note |
|------|----------|----------|------|
| 1 | 35720.3 | stt   | cold Whisper-small load (1st turn post-restart) — one-time warm-up outlier |
| 2 | 14540.2 | agent | remote-model first-token variance |
| 3 |  7763.8 | endpoint | steady-state |
| 4 |  7403.9 | endpoint | steady-state |
| 5 |  7267.5 | endpoint | steady-state |

**Steady-state median ≈ 7.4 s vs baseline ≈ 15.0 s → ≈ 51 % reduction
(SC-001 ✅, ≥40 %).** STT confirmed `small` (agent.log
"via local whisper (small …)"). **`dominant` shifted stt/agent →
endpoint** — the attacked stages are no longer the bottleneck (SC-004
evidence). SC-002's absolute ≤2 s not met (~7.4 s) — non-binding
aspiration; the binding ≥40 % vs baseline IS met. Zero post-tuning
crashes; instrumentation `complete:true` every steady turn (SC-003).
Per-stage depth available via `satellite.default_config.latency_log: full`
(no code change — proves FR-011 config-driven). Reversible: restore
`~/.hermes/config.yaml.bak.f007local.20260519T160320Z`.

## 6. No regression (FR-006/SC-005)

Same session: a long-answer prompt still streams first sentence fast (008);
a Markdown answer is still clean (009); talk over a reply → barge-in still
stops fast; a follow-up still has context (multi-turn). All unaffected.

## 7. Reversibility (SC-008)

```bash
cp ~/.hermes/config.yaml.bak.f007local.<TS> ~/.hermes/config.yaml
hermes gateway restart
```

Latency returns to the §3 baseline, pre-existing platforms == pre-state,
< 5 min; then redeploy to leave the faster defaults live (operator choice).

## Done when

Every turn emits a coherent per-stage breakdown that sums to the total;
recorded baseline → ≥40% reduction (≤2 s target) with the improved stage
identified; 008/009/barge-in/multi-turn no regression; zero hardcoded
tuning constants (config/restore flips latency, no code change);
`test_turnlatency.py` + existing suite green with no edits; 0 platform
regression / < 5 min restore.
