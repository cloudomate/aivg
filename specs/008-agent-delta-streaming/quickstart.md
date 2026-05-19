# Quickstart: Agent Text-Delta Streaming — verify & ship (LOCAL Hermes)

Goal: prove the answer begins while the Hermes agent is still composing it,
via the agent text-delta seam (cli.py pattern), barge-in aborts generation,
ship via the local reversible deploy, run the live test. **All localhost** —
no ssh, no LAN, no tunnel (so WebRTC media works).

## 0. Preconditions

- Feature 008 code: `hermes_bridge.agent_stream` rewritten to run
  `run_agent.AIAgent` with a delta callback → feature-007
  `IncrementalUnitAssembler` → feature-006 per-sentence Hermes-Piper TTS →
  WebRTC; barge-in → `AIAgent.interrupt()`; FR-005 fallback to 006. Feature
  007 draft-hook glue removed. Local Hermes v0.14.0 running; pairing
  `local/electron-test-1` approved.

## 1. Local: provable logic green (SC-007 / FR-009)

```bash
cd /Users/yashwant.singh/coderepo/hermes-voice-gateway
.venv/bin/python -m pytest -q
```

Expect: feature 007's `test_streamasm.py` still passes **unchanged** AND
feature 001's fake-transport suite still 100% green with **no test edits**
(fake bridge → 006 fallback). Streaming itself is host-only (constitution V).

## 2. Implement-time host API verification (constitution V)

Before/while implementing, read the **running local** host to pin the
residuals (research.md D2/D5): in `~/.hermes/hermes-agent`, `run_agent.py`
`AIAgent.__init__` + `run_conversation(..., stream_callback=…)` +
`interrupt()`, and `cli.py`'s `AIAgent(...)` construction (model/toolsets/
session args) + its voice `stream_callback` wiring. Same host-verification
discipline used in 003/005/007.

## 3. Local gated redeploy (reuse deploy-local.sh — FR-010)

```bash
deploy/deploy-local.sh --preflight        # read-only
deploy/deploy-local.sh --yes              # 🔒 LOCAL-MUTATING (backup-first, idempotent)
```

Backup config → vendor plugin → restart local gateway → post-verify (no
embedded engine, plugin import/register, 0 pre-existing platforms removed,
both :8643 & :8644 LISTENING). Production `deploy-to-hermes.sh` untouched.

## 4. Live spoken test (US1/US2) — localhost client

Reload the Electron app (defaults `http://localhost:8643` / `:8644`),
Connect. (Re-approve pairing if the gateway was restarted:
`hermes pairing approve local <CODE>`.)

1. **SC-001/SC-002** — FIRST record the feature-006 time-to-first-word for a
   ≥10 s-answer prompt (e.g. *"tell me a 40 line story"*); then on the 008
   build ask the SAME prompt — first sentence heard within ~3 s, ≥60% faster
   TTFW than the 006 baseline. Log both numbers here.
2. **SC-003/SC-006** — answer continues as the agent generates: no >~1.5 s
   gaps while producing; coherent, no missing/duplicated sentences.
3. **SC-004** — while it's still speaking AND the agent is still generating,
   talk over it: audio stops ≤300 ms, no later sentence spoken, agent
   generation ceases ≤1 s (verify in `~/.hermes/logs/agent.log`: no further
   `chat_completion_stream`/turn lines for that turn after the interrupt).
4. **SC-005** — a one-liner + an empty/tool-only case: no regression vs 006;
   if a turn doesn't stream, behaviour == 006.

Decisive log check (instrumentation may be re-added for this): the agent
delta callback fires repeatedly DURING generation (agent.log
`chat_completion_stream_request` open while sentences already playing), and
first TTS audio precedes the agent's `response ready time=Xs` — the opposite
of features 006/007 where first audio came only after the full reply.

## 5. Reversibility (SC-008)

```bash
cp ~/.hermes/config.yaml.bak.f007local.<TS> ~/.hermes/config.yaml   # restore backup
hermes gateway restart
```

Config restored, pre-existing platforms == pre-state, < 5 min; then redeploy
to leave streaming live (operator choice).

## Done when

SC-001…SC-008 observed: first sentence ≤3 s for a ≥10 s answer, ≥60% faster
TTFW vs 006, ≤1.5 s gaps, barge-in ≤300 ms + gen-stop ≤1 s with zero orphans,
coherent long answer, no short/empty regression, `test_streamasm.py` +
fake suite green with no edits, 0 platform regression / <5 min restore.
