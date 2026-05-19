# Phase 0 Research: Reuse Hermes's TTS Markdown Stripper

Host recon of the running local **hermes-agent v0.14.0**
(`~/.hermes/hermes-agent`), performed during `/speckit-clarify`
(2026-05-19). No NEEDS CLARIFICATION remained after the clarify session;
this consolidates the findings that decided the approach.

## D1 — Hermes already owns the fix; the satellite bypassed it

- **Decision**: Reuse `tools.tts_tool._strip_markdown_for_tts(text)`; do
  not build any normalizer.
- **Evidence (verified, v0.14.0)**:
  - `tools/tts_tool.py:1999 def _strip_markdown_for_tts(text)` — Hermes's
    canonical "remove markdown that shouldn't be spoken" helper. Strips
    (regexes `tts_tool.py:1987–1996`): fenced code blocks ```` ``` ````→
    space, `[text](url)`→`text`, bare `https?://…`→removed, `**bold**`/
    `*italic*`/`` `code` ``→inner text, `#` headers, `-`/`*` list markers,
    `---` HR, collapses 3+ newlines. `.strip()`-ed result.
  - It is a **caller** responsibility, NOT built into synthesis: the synth
    entrypoint `tools.tts_tool.text_to_speech_tool()` (what our bridge's
    `tts_synthesize` calls) does **not** call it — it passes raw `text`
    straight to `_generate_piper_tts`.
  - Hermes's OWN voice callers strip first: `gateway/run.py`
    `_send_voice_reply` → `_strip_markdown_for_tts(text[:4000])` before
    `text_to_speech_tool`; the CLI `stream_tts_to_speaker` →
    `_strip_markdown_for_tts(sentence)` per sentence.
  - Conclusion: the satellite regressed only by omitting that sibling
    call; the fix is to do exactly what Hermes's own voice does.
- **Rationale**: Constitution IV (reuse, don't rebuild) — a forked
  normalizer would diverge from Hermes voice behaviour and need
  maintenance. The function IS the spec.
- **Alternatives considered**:
  - Bespoke normalizer in the adapter — rejected (constitution IV; clarify
    Q1 chose stripper-only).
  - Agent system-prompt / "soul" lever (add a `satellite`/`voice` key to
    `agent/prompt_builder.py`'s per-platform guidance like `sms`/
    `api_server` "plain text, no markdown, conversational") — viable and
    Hermes-native, but **out of scope** per clarify Q1 (stripper-only;
    fixes the symptom deterministically without changing what the agent
    writes). Recorded here as the documented not-taken option.
  - `display.final_response_markdown: strip` (config, line 249) — that is
    a CLI *display* stripper, not the TTS path; not applicable.

## D2 — Emoji gap accepted (exact Hermes parity)

- **Decision**: Add no emoji/symbol handling. Behaviour == Hermes voice.
- **Evidence**: no emoji regex anywhere in Hermes (`grep` of tts_tool /
  gateway / agent found none); `_strip_markdown_for_tts` does not touch
  emoji. Clarify Q2 chose exact parity.
- **Rationale**: "no worse than Hermes's own voice; add nothing custom"
  (constitution I/IV). Whatever Piper does with emoji is what Hermes users
  already get.

## D3 — No length cap, no new config

- **Decision**: No spoken-length limit; no `tts_enabled` /
  `restrict_special_chars` / `max_length` keys.
- **Evidence**: Hermes `voice:` block (config.yaml:298) has
  `record_key/max_recording_seconds/auto_tts/beep_enabled/silence_*` —
  none for spoken-text restriction; `_send_voice_reply` uses a coarse
  `text[:4000]` only. The user's proposed keys do not exist in Hermes.
- **Rationale**: Constitution IV forbids inventing adapter config;
  `_strip_markdown_for_tts` already realises the "restrict special chars"
  intent; a 300-char cap would truncate long answers and contradict
  feature 008 streaming (clarify Q3).

## D4 — Single insertion point covers both speech paths

- **Decision**: Apply the strip inside
  `HermesV013Bridge.tts_synthesize._work()`, between
  `from tools.tts_tool import …` and `text_to_speech_tool(text)`
  (`src/hermes_satellite_adapter/hermes_bridge.py` ~L259–264).
- **Evidence**: feature 008 `agent_stream` synthesises each unit via
  `self.tts_synthesize(unit, ctx=ctx)`; feature 006 `tts_stream` likewise
  via `self.tts_synthesize`. Both funnel through this one method →
  one change satisfies FR-001/FR-002 with no path-specific code.
- **Failure handling**: import or strip raises → fall back to the raw
  `text` (FR-008, never worse than today). Stripped text empty/whitespace
  → raise a generic (non-`AllProvidersUnavailable`) error so the existing
  per-unit `except Exception: continue` skips it (FR-007) — feature 008
  already also guards empty units upstream; no new handler added.

## D5 — Local testability boundary (constitution V)

- **Decision**: The locally-provable slice is the **wiring**: a unit test
  injects a fake `tools.tts_tool` module (`_strip_markdown_for_tts` +
  `text_to_speech_tool` recording their inputs) and asserts
  `tts_synthesize` feeds the **stripped** text to synth (order + parity)
  and that an import/strip failure falls back to raw text (FR-008). The
  real `_strip_markdown_for_tts` semantics are Hermes-owned and
  host-proven by the live spoken test (same discipline as 005/006/008 —
  the fake suite proves wiring; the host proves real engine behaviour).
- **Rationale**: `_strip_markdown_for_tts` cannot be imported without the
  Hermes package; re-deriving its regexes locally would violate
  constitution IV. Testing the wiring (not re-testing Hermes's function)
  is the correct, non-forking boundary.

## Live host finding 2026-05-19 (constitution V — fix applied)

First live test ("say 100 lines of a story") spoke only the intro, then
nothing. Logs: intro unit synth OK; the next unit hit Hermes Piper
`wave.Error: # channels not specified`; Hermes's `text_to_speech_tool`
**catches** that and returns `success:false` (it does not raise). Our
`tts_synthesize._work` mapped **any** `success:false` →
`AllProvidersUnavailable`, which `agent_stream` treats as fatal
(`except AllProvidersUnavailable: raise`) → the whole stream aborted after
the intro. A single Piper-unspeakable line (markdown-stripped story/list
fragment) killed the entire answer — violates FR-007.

**Fix**: classify `success:false` by the Hermes error text — genuine
provider/dependency OUTAGE ("not installed" / "no tts provider" /
"dependency missing" / "not available") stays fatal
`AllProvidersUnavailable` (FR-008, perceptible); everything else (per-text
render failure: "# channels not specified" / "produced no output" /
"generation failed") raises the new skippable `_UnitSynthFailed`, caught
by callers' existing `except Exception: continue` → that unit is skipped,
the rest of the answer keeps speaking (FR-007). 2 regression tests added
(`test_per_unit_render_failure_is_skippable_not_fatal`,
`test_genuine_provider_outage_is_still_fatal`); `pytest -q` = 88.
Pre-existing 006/008 mis-classification surfaced by 009's stripping.

NOT in scope (recorded, separate concern): perceived slowness is
endpoint silence wait (`voice.silence_duration: 3.0`) + Whisper `medium`
STT on long utterances + model first-token time — Hermes-owned VAD/STT,
explicitly out of scope per spec 009 Assumptions; warrants its own spec.

## Residual (re-verify at implement time, not blockers)

- Exact line numbers in `tts_tool.py` / `hermes_bridge.py` shift between
  versions — re-read the running host at implement time (same discipline
  as 003/005/007/008). The seam (lazy import in `tts_synthesize._work`)
  and the function names are verified for v0.14.0.
- Whether any unit becomes empty *only* after stripping in practice (e.g.
  a sentence that was purely a URL) — handled by FR-007 skip; observe in
  the live test.
