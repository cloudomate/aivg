# Feature Specification: Speak Clean Prose — Reuse Hermes's TTS Markdown Stripper

**Feature Branch**: `009-tts-text-normalization`
**Created**: 2026-05-19
**Status**: Draft
**Input**: User description: "today while reading the model responds with md
decorators emojis and exclamation and the tts reads this — this is not how a
conversation should look like, let's fix it" (+ clarify hint: "do research,
see how Hermes handles it — prompt, config and soul")

## Overview

When the voice satellite speaks the agent's answer, the agent often writes
the answer as **written text for a screen** — Markdown emphasis (`**bold**`,
`# headings`, `` `code` ``), bullet/numbered list markers, link syntax, and
runs of punctuation. Today the speech engine vocalizes those literally
("asterisk asterisk", "hash", "backtick", spelled-out URLs), so the result
sounds like someone reading raw Markdown aloud, not a person talking.

Research into the running Hermes install (recorded in Clarifications)
established that Hermes **already owns** the fix: `tools.tts_tool.`
`_strip_markdown_for_tts()` is Hermes's canonical "remove markdown that
shouldn't be spoken" helper, and Hermes's own voice paths (the gateway
`_send_voice_reply`, the CLI streaming speaker) call it themselves before
synthesis. The satellite bridge regressed by calling Hermes's synthesis
entrypoint (`text_to_speech_tool`) **without** that sibling helper call —
in Hermes, markdown-stripping is a *caller* responsibility, not built into
the synth entrypoint.

This feature therefore does **exactly what Hermes's own voice does**: call
`tools.tts_tool._strip_markdown_for_tts()` on the text immediately before
`tools.tts_tool.text_to_speech_tool()`, at the satellite's existing
reply→speech seam, on **both** the feature-008 streaming path and the
feature-006 fallback. No bespoke normalizer, no new config, no agent-prompt
change, no engine — pure reuse of the Hermes function Hermes's voice modes
use (constitution I/IV). The agent's output, the displayed text, and the
transcript are unchanged; only the audio differs.

## Clarifications

### Session 2026-05-19

- Q: Primary mechanism — agent prompt/soul lever, vs reuse Hermes's
  `_strip_markdown_for_tts`, vs both? → A: **Reuse
  `tools.tts_tool._strip_markdown_for_tts` at the bridge seam only**
  (mirror Hermes's own `_send_voice_reply`; no hand-rolled normalizer, no
  agent system-prompt change).
- Q: Hermes's stripper has no emoji handling anywhere — add emoji removal,
  or match Hermes voice exactly? → A: **Exact Hermes parity — no emoji
  code.** Emojis are left exactly as Hermes's own voice leaves them
  (whatever Piper does with them); the only transform is Hermes's
  `_strip_markdown_for_tts`.
- Q: User typed `max_length: 300` — cap spoken text? → A: **No cap (Hermes
  parity).** The 300-char idea is dropped (it would truncate long answers
  and contradict feature 008's long-answer streaming); behave like Hermes
  voice (no real spoken-length limit).
- Q: Spec wanted "brief spoken stand-in" for code/URLs, but reuse just
  removes them — reconcile? → A: **Accept Hermes removal behavior.** Code
  blocks and URLs are simply removed from speech (no spoken "code
  sample"/"a link" phrase); requirements relaxed from "stand-in" to "not
  vocalized", matching `_strip_markdown_for_tts` exactly.
- Decided (no question needed — resolved by the pure-reuse decision):
  the user's proposed `voice: { tts_enabled, restrict_special_chars,
  max_length }` keys are NOT added — Hermes has no such keys and
  constitution IV forbids inventing adapter config; `restrict_special_chars`
  is already what `_strip_markdown_for_tts` does, and the voice satellite
  always synthesizes (no `tts_enabled` toggle needed).

## User Scenarios & Testing *(mandatory)*

### User Story 1 - The spoken answer is clean prose, not read-aloud Markdown (Priority: P1)

A person asks a question whose answer the agent formats with bold text,
headings, a bulleted list, inline code, and a link. Instead of hearing
"asterisk asterisk important asterisk asterisk … hash hash summary … dash …
h-t-t-p-colon-slash-slash…", they hear the natural sentence and the list
read as plain spoken words — identical to how Hermes's own CLI/gateway
voice modes already sound.

**Why this priority**: This is the entire complaint — the spoken output is
not conversational because the satellite bypassed the markdown-strip step
Hermes's own voice uses.

**Independent Test**: Ask a question that reliably yields a Markdown-rich
answer (emphasis + a list + inline code + a link); confirm by listening
that no Markdown decoration character or URL is audible and the underlying
words are spoken in order — and that this matches Hermes CLI voice for the
same text.

**Acceptance Scenarios**:

1. **Given** an agent reply containing Markdown emphasis, headings, inline
   code, list markers, links, and horizontal rules, **When** it is spoken,
   **Then** none of those Markdown decoration characters are vocalized and
   the underlying words are spoken in the same order — identical to
   applying Hermes's `_strip_markdown_for_tts` to that text.
2. **Given** a bulleted or numbered list, **When** it is spoken, **Then**
   the leading list/bullet markers are not vocalized (the items are spoken
   as plain text), exactly as Hermes's stripper produces.
3. **Given** a reply emitted incrementally (feature 008) AND the same reply
   produced as a completed string (feature 006 fallback), **When** each is
   spoken, **Then** both have the markdown-strip applied — behaviour is
   consistent across both paths.
4. **Given** a plain, already-conversational reply with no Markdown,
   **When** it is spoken, **Then** it is spoken exactly as before (the
   stripper is a no-op on clean text) — no regression in words or timing.

---

### User Story 2 - Code and URLs are not spelled out (Priority: P2)

A person asks something whose answer includes a fenced code block and a
long URL. Instead of the engine reading the code character-by-character or
spelling a 90-character link, those segments are simply not vocalized and
the surrounding answer continues normally — exactly Hermes's own voice
behaviour.

**Why this priority**: These are the worst offenders for "not a
conversation", but the resolution is the same single reused helper as US1;
no extra mechanism.

**Independent Test**: Ask for something containing a fenced code block and
a long URL; confirm neither is read aloud (both are removed from speech by
Hermes's stripper) and the prose around them is intact.

**Acceptance Scenarios**:

1. **Given** a reply containing a fenced (```) or long inline code block,
   **When** it is spoken, **Then** the code content is not vocalized (it is
   removed by `_strip_markdown_for_tts`); no spoken stand-in phrase is
   expected.
2. **Given** a reply containing a bare URL or a `[text](url)` link, **When**
   it is spoken, **Then** the raw URL is not spelled out (URL removed; link
   text preserved), exactly as Hermes's stripper does.
3. **Given** a reply that is *only* a code block (nothing speakable after
   stripping), **When** the turn is spoken, **Then** it ends cleanly (no
   audio / clean return to listening per the existing empty-unit handling),
   not a stream of symbols.

---

### User Story 3 - Display, transcript, and other platforms unaffected; reversible local deploy (Priority: P3)

The fix changes only what is heard. The on-screen/answer text, stored
transcript, the agent's actual output, and every pre-existing gateway
platform are exactly as before, and the change ships through the existing
local, backed-up, reversible deploy path.

**Why this priority**: Established safety posture; the change must not alter
the written answer/record or any other platform and must be reversible.

**Independent Test**: For the same prompt, the displayed answer and stored
transcript are byte-identical before and after; pre-existing platforms
untouched; restoring the prior backup returns the previous state.

**Acceptance Scenarios**:

1. **Given** the fix is active, **When** an answer is produced, **Then**
   the displayed answer text and the stored transcript are identical to
   what they would have been without this feature (only audio differs —
   the strip is applied to a copy on the way to synthesis).
2. **Given** the local deploy runs, **Then** the host-mutating step is
   confirmed and backed up first, no pre-existing platform is degraded, and
   restoring the backup returns to the prior state.

### Edge Cases

- Reply is empty / whitespace-only, or becomes empty only after stripping
  (e.g., only a code block or only `---`) → no empty/whitespace text is
  sent to synthesis; the turn ends cleanly via the existing empty-unit
  handling (no zero-length audio, no hang) — consistent with feature 008's
  empty-unit guard.
- Markdown spanning a streamed-chunk or sentence boundary (e.g., `**bold`
  then `text**` in the next delta) → because stripping is applied to the
  assembled speakable unit (the same text Hermes would strip), behaviour
  matches Hermes's stripper on that text; spoken order preserved.
- Genuine content containing symbol characters (decimals `3.14`,
  abbreviations `e.g.`, currency `$5`, version `v0.14.0`) → behaves exactly
  as Hermes's `_strip_markdown_for_tts` (its regexes are scoped to Markdown
  constructs); no over-stripping beyond Hermes's own behaviour.
- Emojis present → behave exactly as in Hermes's own voice modes (Hermes
  applies no emoji processing); this feature deliberately adds none.
- `_strip_markdown_for_tts` import/call fails on the host → fall back to
  speaking the un-stripped text (never worse than today; no hang) — the
  existing per-unit synth error handling already covers this.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The satellite MUST apply Hermes's own
  `tools.tts_tool._strip_markdown_for_tts()` to the reply text immediately
  before `tools.tts_tool.text_to_speech_tool()`, at the existing
  reply→speech seam, mirroring Hermes's own `_send_voice_reply`.
- **FR-002**: The strip MUST be applied on BOTH the feature-008 streaming
  path (per assembled speakable unit, before per-unit synthesis) and the
  feature-006 non-streaming fallback, so spoken output is consistent
  regardless of how the reply was produced.
- **FR-003**: Behaviour MUST equal Hermes's `_strip_markdown_for_tts`
  output for the same input — no additional, custom, or different text
  transformation is added (no bespoke normalizer, no emoji handling, no
  punctuation collapsing beyond what that function does).
- **FR-004**: No new configuration keys are introduced (no
  `tts_enabled` / `restrict_special_chars` / `max_length`); provider,
  voice, and behaviour remain inherited from Hermes config (constitution
  IV). No spoken-length cap is added.
- **FR-005**: Code blocks and URLs MUST NOT be vocalized; they are removed
  by the reused helper (no spoken stand-in phrase is produced or required).
- **FR-006**: The agent's output, the displayed/answer text, and the
  stored transcript MUST be unchanged — the strip is applied only to the
  text on its way to synthesis, never to what is shown or recorded.
- **FR-007**: If stripping yields nothing speakable (empty/whitespace),
  no synthesis call is made for that unit; the turn ends cleanly using the
  existing empty-unit handling (no zero-length/broken audio, no hang).
- **FR-008**: If `_strip_markdown_for_tts` is unavailable or raises on the
  host, the system MUST fall back to speaking the un-stripped text and MUST
  never be worse than today (perceptible, non-hanging).
- **FR-009**: Speech recognition, the agent, and speech synthesis remain
  Hermes-owned and unmodified; this feature only inserts a call to an
  existing Hermes helper at the existing seam (no engine reimplemented).
- **FR-010**: Media transport, signaling, control plane, turn/state-machine
  semantics, and the existing automated conversation suite MUST remain
  behaviourally compatible with no test edits.
- **FR-011**: Redeployment MUST use the existing local, backup-first,
  reversible deploy path and MUST NOT degrade any pre-existing gateway
  platform; the production deploy script remains unchanged.

### Key Entities *(include if feature involves data)*

- **Raw Reply Text**: the agent's answer exactly as produced — the source
  for display, transcript, and (via a stripped copy) speech; never altered
  for display/record.
- **Spoken Text**: the result of `_strip_markdown_for_tts(raw)` — the
  Hermes-defined, decoration-free text actually sent to synthesis.
- **Reused Hermes Helper**: `tools.tts_tool._strip_markdown_for_tts` — the
  single, Hermes-owned transform; its behaviour is the spec (this feature
  adds no transform of its own).
- **Speakable Unit**: reused from features 006/008 — the per-sentence chunk;
  the strip is applied to each unit before synthesis; unit boundaries are
  unchanged.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a deliberately Markdown-rich answer, the spoken output
  contains **zero** vocalized Markdown decoration characters/markers and no
  spelled-out URLs — and is byte-equivalent to
  `_strip_markdown_for_tts(reply)` for that text.
- **SC-002**: For the same prompt, the satellite's spoken text exactly
  equals what Hermes's own voice path would speak (parity with
  `_strip_markdown_for_tts`); no added/dropped/reordered words beyond what
  that function does.
- **SC-003**: For a plain, already-conversational answer, the spoken output
  is unchanged versus today (stripper is a no-op) — no regression in
  wording, timing, or time-to-first-word on the streaming path.
- **SC-004**: For an answer containing a code block and a long URL, neither
  is vocalized (both removed by the reused helper); the surrounding prose
  is intact.
- **SC-005**: The displayed answer text and stored transcript for any
  prompt are byte-identical with and without this feature (only audio
  differs).
- **SC-006**: The existing automated conversation suite remains 100% green
  with no test edits; a small test asserts the bridge applies
  `_strip_markdown_for_tts` (parity) on representative input.
- **SC-007**: 0 regressions to pre-existing gateway platforms after the
  local redeploy; restoring the backup returns the gateway to its prior
  state in under 5 minutes.
- **SC-008**: No perceptible added latency or time-to-first-word increase
  on the streaming path (the strip is a cheap per-unit regex pass, the same
  Hermes already runs in its own voice modes).

## Assumptions

- The fix is pure reuse of `tools.tts_tool._strip_markdown_for_tts`, called
  exactly where/how Hermes's own `_send_voice_reply` calls it; the spec's
  behaviour IS that function's behaviour (no independent normalization
  semantics to define).
- Emojis and any non-Markdown symbols are left exactly as Hermes's own
  voice modes leave them — this feature adds no emoji/symbol handling.
- No spoken-length cap and no new adapter config keys (the user's
  `tts_enabled`/`restrict_special_chars`/`max_length:300` are intentionally
  not implemented — they don't exist in Hermes and constitution IV forbids
  inventing adapter config; `_strip_markdown_for_tts` already covers the
  "restrict special chars" intent).
- Applied at the existing satellite reply→speech seam for both feature-008
  (per speakable unit) and feature-006 (completed reply) paths; sentence
  assembly, media transport (005), and the Hermes-owned engines are reused
  unchanged.
- The deploy/test target is the local Hermes install via the existing
  reversible local deploy; the production deploy path is untouched.
- Conversational quality is confirmed by a human listening test
  (consistent with prior features); parity with `_strip_markdown_for_tts`
  is asserted by a small unit test plus the unchanged automated suite.
- STT model choice and the agent's formatting behaviour (the prompt/soul
  lever) remain explicitly out of scope — the chosen approach is stripper
  reuse only, not changing what the agent writes.
