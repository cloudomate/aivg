# Contract: Bridge ↔ Hermes TTS-Strip Seam

The single behavioural contract for feature 009. "Parity" everywhere means
*byte-equal to `tools.tts_tool._strip_markdown_for_tts(input)` for the same
input* — this feature defines no transform of its own.

## H1 — Strip-before-synth (FR-001)

`HermesV013Bridge.tts_synthesize(text)` MUST call
`tools.tts_tool._strip_markdown_for_tts(text)` and pass **its return
value** to `tools.tts_tool.text_to_speech_tool(...)`. The raw `text` MUST
NOT be passed to `text_to_speech_tool` on the success path.

## H2 — Both speech paths covered (FR-002)

The strip MUST occur inside `tts_synthesize` (not in `agent_stream` or
`tts_stream` individually), so the feature-008 streaming path and the
feature-006 fallback — both of which synthesise via `tts_synthesize` —
are covered by the one site with no path-specific code.

## H3 — Exact parity, nothing added (FR-003/FR-005)

No transformation other than `_strip_markdown_for_tts` is applied: no
emoji handling, no punctuation collapsing, no length cap, no stand-in
phrases for removed code/URLs. Output == the Hermes function's output.

## H4 — Display/transcript untouched (FR-006)

Only the value handed to synthesis is the stripped copy. The agent's
output object, the displayed text, and the stored transcript MUST be
byte-identical to the no-feature behaviour.

## H5 — Empty-after-strip → skip, not fail (FR-007)

If the stripped text is empty/whitespace, no `text_to_speech_tool` call is
made for that unit; the unit is skipped via the **existing** per-unit
`except Exception: continue` (008/006), producing no audio for it — no new
handler, no zero-length/broken audio, no hang.

## H6 — Failure fallback (FR-008)

If importing or calling `_strip_markdown_for_tts` raises, the bridge MUST
fall back to synthesising the **raw** (un-stripped) text — never worse
than today, never a hang. (A genuine TTS failure still surfaces via the
existing `AllProvidersUnavailable` turn-level path, unchanged.)

## H7 — No new surface (FR-004/FR-009/FR-010/FR-011)

No new config key, no engine, no new dependency; transport/signaling/
control-plane/turn semantics and the existing automated suite unchanged
with no test edits; ships via the reused `deploy/deploy-local.sh`;
production deploy script untouched.

## Verification

- **Local (wiring/parity/order/fallback — H1/H2/H3/H6)**: a unit test
  injects a fake `tools.tts_tool` exposing recording stubs for
  `_strip_markdown_for_tts` and `text_to_speech_tool`; asserts the stub
  synth received exactly the stub strip's output, that raw was not used on
  success, and that a raising strip stub ⇒ raw text synthesised (H6).
- **Local (regression — H4/H7)**: full `pytest -q` stays green with no
  test edits (fake-transport suite never reaches `HermesV013Bridge`, so it
  is inherently unaffected — proves no behavioural contract change).
- **Host (real semantics — H1/H3/H5 end-to-end)**: live spoken test on the
  local gateway — a Markdown+code+URL answer is heard as clean prose
  matching Hermes CLI voice; a code-only reply yields clean
  return-to-listening (quickstart).
