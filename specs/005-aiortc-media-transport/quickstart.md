# Quickstart: Real WebRTC Media Transport — verify & ship

Goal: prove the real `AiortcTransport` works, ship it via the existing gated
reversible path, and finally run the long-blocked end-to-end spoken test.

## 0. Preconditions

- Feature 005 code in place: `media.py`, real `AiortcTransport` +
  `aiortc_transport_factory` body in `signaling.py`, `tests/unit/test_media_framer.py`.
- Adapter currently deployed (features 003/004); both ports verified LISTENING.
- aiortc/aiohttp/av present on the host (feature 003 preflight — re-checked by
  the deploy script).

## 1. Local: locally-provable logic green (SC-008, FR-012)

```bash
cd /Users/yashwant.singh/coderepo/hermes-voice-gateway
.venv/bin/python -m pytest -q
```

Expect: feature-001 fake-transport suite still 100% green **and** the new
`test_media_framer.py` passing. The real media path is *not* exercised here
(aiortc/av are not local deps) — that is intentional (constitution V).

## 2. Gated redeploy (reuse 003/004 — no new mechanism, FR-009)

```bash
deploy/deploy-to-hermes.sh --preflight        # read-only
deploy/deploy-to-hermes.sh                     # 🔒 HOST-MUTATING — confirm each step
```

The script backs up `~/.hermes/config.yaml`, rsyncs the media-complete plugin,
restarts the gateway, and post-verifies: no embedded speech engine, plugin
imports/registers, **0** pre-existing platforms removed, **both** :8643 and
:8644 LISTENING. Any failure → `ROLLBACK REQUIRED`.

Confirm on host: `ss -ltn` shows 8643 + 8644; `curl /satellite/list` ok; the
5 pre-existing platforms intact (SC-007).

## 3. Live spoken test — the long-blocked payoff (US1/US2/US4)

```bash
ssh -N -L 8643:localhost:8643 -L 8644:localhost:8644 hermes
# then, in clients/electron-test:  npm start
```

With a human at the microphone:

1. **US1 / FR-007 / SC-005**: push-to-talk, speak a short phrase → the offer
   succeeds (no "not implemented"), the gateway transcribes it, and an
   **audible** agent reply plays in the client.
2. **SC-003**: reply audio begins ≤1.5 s after you stop speaking.
3. **SC-001/SC-002**: transcription matches what you said; reply is
   understandable on first listen.
4. **US2 / SC-004**: while the reply is playing, talk over it → playback
   stops promptly (≤300 ms) and your interruption becomes the next turn.
5. **SC-006**: hold ≥3 alternating turns — audio stays intact both ways, no
   progressive desync or dropout.
6. **FR-006**: drop the call (close client) and re-offer → audio
   re-establishes with **no** gateway restart.

## 4. Reversibility drill (SC-007)

```bash
deploy/rollback.sh                  # 🔒 HOST-MUTATING — restores prior state
```

Verify config is byte-identical to the backup, plugin removed, the 5
pre-existing platforms == pre-state, all in <5 minutes. Then redeploy to leave
the media-complete adapter live (operator-confirmed).

## Done when

SC-001…SC-008 all observed: parity transcription, intelligible reply,
≤1.5 s onset, ≤300 ms barge-in, 100% offer success, ≥3 clean turns, 0
regression / <5 min rollback, fake suite green. The feature-003/004
human-driven spoken exchange is no longer blocked.
