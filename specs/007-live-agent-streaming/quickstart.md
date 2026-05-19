# Quickstart: End-to-End Streaming Conversation — verify & ship

Goal: prove the answer begins while the agent is still composing, barge-in
cancels generation, ship via the existing gated path, run the live test.

## 0. Preconditions

- Feature 007 code: `streamasm.py`, `_SatellitePlatformAdapter` draft-stream
  opt-in + interrupt-on-barge-in, the incremental reply bridging, FR-005
  fallback. Feature 006 deployed; STT `medium`; `local/electron-test-1`
  pairing approved.

## 1. Local: provable logic green (SC-007 / FR-009)

```bash
cd /Users/yashwant.singh/coderepo/hermes-voice-gateway
.venv/bin/python -m pytest -q
```

Expect: new `test_streamasm.py` passes **and** feature 001's fake-transport
suite still 100% green with **no test edits** (fake bridge → 006 fallback,
identical turn semantics). Streaming itself is host-only (constitution V).

## 2. Implement-time host API verification (constitution V)

Before/while implementing, read the **running host** to pin the residuals
(research.md): in `~/.hermes/hermes-agent/gateway/platforms/base.py` the exact
`supports_draft_streaming` partner update method + `edit_message(...,
finalize=)` signature; and the Hermes interrupt entrypoint for an in-flight
turn. Same host-verification discipline that fixed the `send()`/`Platform`/
`MessageEvent` APIs in features 003/005.

## 3. Gated redeploy (reuse 003/004 — FR-010)

```bash
deploy/deploy-to-hermes.sh --preflight                 # read-only
yes yes | deploy/deploy-to-hermes.sh                    # 🔒 HOST-MUTATING (gate quirk)
```

Backup → rsync → ~2-min restart drain → post-verify (no embedded engine,
plugin import/register, 0 pre-existing platforms removed, both ports
LISTENING). Confirm 5 pre-existing platforms intact (SC-008).

## 4. Live spoken test (US1/US2) — LAN-direct client

Reload the Electron app (`192.168.4.140` defaults), Connect.

1. **SC-001/SC-002** — ask a question whose full answer takes the agent ≥10 s
   (e.g. *"Explain how a four-stroke engine works, step by step."*). The
   **first sentence is heard within ~3 s** of the turn answering — far before
   the agent could finish; compare time-to-first-word vs feature 006 on the
   same prompt (expect ≥60% faster).
2. **SC-003/SC-006** — the answer continues as the agent generates: no
   >~1.5 s gaps while it's producing steadily; the whole answer is coherent,
   no missing/duplicated sentences.
3. **SC-004** — ask another long question; **while it's still speaking AND
   the agent is still generating, talk over it**: audio stops ≤300 ms, no
   later sentence is spoken, and agent generation ceases within ~1 s (verify
   in `~/.hermes/logs/gateway.log` — no continued response/streaming lines
   for that turn after the interrupt).
4. **SC-005** — a one-liner + an empty/tool-only case: no regression vs 006.

## 5. Reversibility (SC-008)

```bash
yes | deploy/rollback.sh        # 🔒 HOST-MUTATING — restores prior state
```

Config byte-identical to backup, plugin removed, 5 pre-existing platforms ==
pre-state, < 5 min; then redeploy to leave streaming live (operator choice).

## Done when

SC-001…SC-008 observed: first sentence ≤3 s for a ≥10 s answer, ≥60% faster
TTFW vs 006, ≤1.5 s gaps, barge-in ≤300 ms + gen-stop ≤1 s with zero orphans,
coherent long answer, no short/empty regression, fake suite green, 0 platform
regression / <5 min rollback.
