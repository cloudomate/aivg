# Quickstart: TTS Markdown Strip — verify & ship (LOCAL Hermes)

Goal: the satellite speaks clean prose (no "asterisk asterisk", no
spelled-out URLs) by reusing Hermes's own `_strip_markdown_for_tts`,
exactly as Hermes's CLI/gateway voice already do. All localhost — no ssh,
no LAN, no tunnel.

## 0. Preconditions

- `HermesV013Bridge.tts_synthesize` strips via
  `tools.tts_tool._strip_markdown_for_tts` before
  `text_to_speech_tool` (one site; covers 008 + 006). FR-008 raw-fallback
  in place. Local Hermes v0.14.0 running; pairing
  `local/electron-test-1` approved.

## 1. Local: provable wiring + no regression (SC-006 / FR-010)

```bash
cd /Users/yashwant.singh/coderepo/hermes-voice-gateway
.venv/bin/python -m pytest -q
```

Expect: the existing suite (82) still green **with no test edits**, plus
the new `tests/unit/test_tts_strip.py` green — it injects a fake
`tools.tts_tool` and asserts `tts_synthesize` feeds the **stripped** text
to synth (H1/H2/H3 wiring + parity + order) and that a raising strip stub
⇒ raw text is synthesised (H6/FR-008). Real strip semantics are
Hermes-owned (host-proven below).

## 2. Implement-time host re-verification (constitution V)

In `~/.hermes/hermes-agent`, re-confirm on the running build:
`tools/tts_tool.py` exposes `_strip_markdown_for_tts` and
`text_to_speech_tool` (the latter does NOT self-strip), and Hermes's own
`gateway/run.py:_send_voice_reply` still calls
`_strip_markdown_for_tts(...)` before `text_to_speech_tool` (the pattern
we mirror). Same discipline as 003/005/007/008.

## 3. Local gated redeploy (reuse deploy-local.sh — FR-011)

```bash
deploy/deploy-local.sh --preflight        # read-only
deploy/deploy-local.sh --yes              # 🔒 LOCAL-MUTATING (backup-first, idempotent)
```

Backup config → vendor plugin → restart local gateway → post-verify
(plugin import/register, 0 pre-existing platforms removed, both :8643 &
:8644 LISTENING). Production `deploy-to-hermes.sh` untouched.

## 4. Live spoken test (US1/US2) — localhost client

Reload the Electron app (`http://localhost:8643` / `:8644`), Connect
(re-approve pairing if the gateway restarted:
`hermes pairing approve local <CODE>`).

1. **SC-001/SC-002/US1** — ask something that yields a Markdown-rich
   answer (e.g. *"give me a bulleted summary with a bold title and a
   link"*). Heard: natural prose + plainly-read list; **no** "asterisk",
   "hash", "backtick", or spelled-out URL. Compare to the same text in
   Hermes CLI voice — should sound the same (parity).
2. **SC-004/US2** — ask for an answer containing a fenced code block and a
   long URL. Heard: code and URL are simply not spoken; surrounding prose
   intact (no stand-in phrase — that's expected, clarify Q4).
3. **US2 edge / FR-007** — ask for *only* a code block. Heard: clean
   return to listening (no symbols, no zero-length audio, no hang).
4. **SC-003** — ask a plain, already-conversational question. Heard:
   unchanged vs before (stripper is a no-op) — no wording/timing change.
5. **SC-005** — confirm the on-screen/answer text + transcript for those
   prompts still show the original Markdown (only audio changed).

Decisive check: spoken audio for a Markdown answer is byte-equivalent in
content to `_strip_markdown_for_tts(reply)`; first-word latency for the
008 streaming path is unchanged (SC-008 — the strip is one cheap regex
pass Hermes already runs in its own voice).

## 5. Reversibility (SC-007)

```bash
cp ~/.hermes/config.yaml.bak.f007local.<TS> ~/.hermes/config.yaml
hermes gateway restart
```

Config restored, pre-existing platforms == pre-state, < 5 min; redeploy
to leave the fix live (operator choice).

## Done when

SC-001…SC-008 observed: zero vocalized Markdown / spelled URLs, parity
with Hermes CLI voice, code/URL not spoken, code-only → clean
return-to-listening, plain text unchanged, display/transcript unchanged,
new wiring test + existing suite green with no edits, 0 platform
regression / < 5 min restore, no added TTFW.
