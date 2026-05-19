# Quickstart: Streaming Spoken Replies — verify & ship

Goal: prove sentence-by-sentence streaming + intact barge-in, ship via the
existing gated reversible path, run the live spoken test.

## 0. Preconditions

- Feature 006 code in place: `textseg.py`, `HermesV013Bridge.tts_stream`,
  the `session._respond`/`_reply_audio` change, `tests/unit/test_textseg.py`.
- Feature 005 adapter currently deployed; Hermes STT model = `medium`
  (set 2026-05-19); pairing `local/electron-test-1` approved.

## 1. Local: provable logic green (SC-006 / FR-008)

```bash
cd /Users/yashwant.singh/coderepo/hermes-voice-gateway
.venv/bin/python -m pytest -q
```

Expect: new `test_textseg.py` passes **and** feature 001's fake-transport
suite still 100% green with **no test edits** (the fake bridge has no
`tts_stream` → single-chunk fallback → identical turn behaviour). Streaming
cadence itself is not locally exercisable (host-proven below) — intentional
(constitution V).

## 2. Gated redeploy (reuse 003/004 — no new mechanism, FR-009)

```bash
deploy/deploy-to-hermes.sh --preflight                 # read-only
yes yes | deploy/deploy-to-hermes.sh                    # 🔒 HOST-MUTATING (gate quirk: feed 'yes')
```

Backup → rsync the streaming package → ~2-min restart drain → post-verify
(no embedded speech engine, plugin import/register, 0 pre-existing platforms
removed, both :8643 & :8644 LISTENING). Confirm 5 pre-existing platforms
intact (SC-007).

## 3. Live spoken test (US1/US2)

Client connects LAN-direct (no SSH tunnel): fields default to
`http://192.168.4.140:8643`, `:8644`, `ws://192.168.4.140:8643/satellite/ws`.

1. Reload the Electron app, **Connect**.
2. Ask a **multi-sentence** question (e.g. *"Give me three tips for better
   sleep, one sentence each."*).
   - **SC-001**: first words heard within ~1.5 s of the reply being ready
     (not after the whole answer is synthesized).
   - **SC-002**: sentences follow with natural pacing, no >~1 s mid-reply
     gap, no overlap/garble.
   - **SC-004**: a 5+-sentence reply is intelligible/natural end to end.
3. Ask another multi-sentence question; **while it is speaking, hold PTT and
   talk over it**.
   - **SC-003**: audio stops within ~300 ms; **no** later sentence is spoken
     after the interruption; your new utterance becomes the next turn.
4. Ask something with a **one-line** answer and an empty/tool-only case.
   - **SC-005**: no latency/correctness regression vs feature 005.

## 4. Reversibility (SC-007)

```bash
yes | deploy/rollback.sh        # 🔒 HOST-MUTATING — restores prior state
```

Verify config byte-identical to backup, plugin removed, 5 pre-existing
platforms == pre-state, < 5 min; then redeploy to leave streaming live
(operator-confirmed).

## Done when

SC-001…SC-007 observed: first words ≤1.5 s, ≤1 s inter-sentence gaps, barge-in
≤300 ms with zero orphan sentences, 5+-sentence intelligibility, no short/empty
regression, fake suite green, 0 platform regression / <5 min rollback.
