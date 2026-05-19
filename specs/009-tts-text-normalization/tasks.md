---
description: "Task list for Speak Clean Prose — reuse Hermes's _strip_markdown_for_tts at the TTS seam"
---

# Tasks: Speak Clean Prose — Reuse Hermes's TTS Markdown Stripper

**Input**: Design documents from `/specs/009-tts-text-normalization/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: One NEW local unit test is requested (spec SC-006 / quickstart
§1): `tests/unit/test_tts_strip.py` asserts the strip→synth **wiring**
via an injected fake `tools.tts_tool` (real `_strip_markdown_for_tts`
semantics are Hermes-owned, host-proven). The existing fake-transport
suite (82) stays 100% green WITH NO EDITS (it never reaches
`HermesV013Bridge`, so it is inherently unaffected — FR-010/SC-006).

**⚠️ PRODUCTION SAFETY**: redeploy is `🔒 LOCAL-MUTATING` — explicit
confirmation + prior backup; reuse `deploy/deploy-local.sh` unchanged; the
production ssh `deploy-to-hermes.sh` stays untouched (FR-011).

**Organization**: US1 P1 clean prose at the seam · US2 P2 code/URLs not
spelled out · US3 P3 display/transcript unaffected + reversible local
redeploy. The ENTIRE implementation is ONE site in
`hermes_bridge.py::tts_synthesize` (covers feature-008 streaming AND
feature-006 fallback because both synthesize through it) — pure reuse of
Hermes's `_strip_markdown_for_tts` (constitution I/IV; clarify-decided).

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

- [X] T001 Baseline: run `.venv/bin/python -m pytest -q` from repo root and record the existing suite (82) is green — regression baseline for FR-010/SC-006

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pin the exact host seam before editing (constitution V).

**⚠️ CRITICAL**: Blocks US1, US2, US3

- [X] T002 Host re-verify (read-only, constitution V): in the running local `~/.hermes/hermes-agent` confirm `tools/tts_tool.py` still exposes `_strip_markdown_for_tts(text)` and `text_to_speech_tool(text)` (the latter does NOT self-strip), and that Hermes's own `gateway/run.py:_send_voice_reply` still calls `_strip_markdown_for_tts(...)` before `text_to_speech_tool` (the pattern we mirror); record any line-number drift in `specs/009-tts-text-normalization/research.md` "Residual" — same discipline as 003/005/007/008

**Checkpoint**: Seam + helper names confirmed for v0.14.0; nothing changed

---

## Phase 3: User Story 1 - Clean prose, not read-aloud Markdown (Priority: P1) 🎯 MVP

**Goal**: The text sent to synthesis is `_strip_markdown_for_tts(text)`,
applied once in `tts_synthesize` so both the 008 streaming path and the
006 fallback are covered; display/transcript unchanged; raw-text fallback
on failure.

**Independent Test**: new `test_tts_strip.py` green (stripped text reaches
synth, parity, order, raw not used on success, raise→raw) + existing 82
green with no edits; real prose quality host-proven in Phase 6.

- [X] T003 [US1] In `src/hermes_satellite_adapter/hermes_bridge.py`, inside `HermesV013Bridge.tts_synthesize._work()`, lazily import `_strip_markdown_for_tts` alongside `text_to_speech_tool` and apply it to `text` BEFORE `text_to_speech_tool(...)`; on import/strip exception fall back to the raw `text` (FR-008/H6); if the stripped text is empty/whitespace raise a generic (NON-`AllProvidersUnavailable`) error so the existing per-unit `except Exception: continue` in `agent_stream`/`tts_stream` skips it (FR-007/H5) — no new handler, no other file touched (FR-001/FR-002/FR-003/FR-006, contracts H1–H3)
- [X] T004 [US1] Create `tests/unit/test_tts_strip.py`: inject a fake `tools.tts_tool` module (recording stubs `_strip_markdown_for_tts` → returns a sentinel-transformed string, `text_to_speech_tool` → records its input, returns a valid JSON pointing at a temp wav); assert `await HermesV013Bridge().tts_synthesize(raw, ctx=...)` calls strip with `raw` AND feeds `text_to_speech_tool` exactly the strip output (parity + order; raw NOT used on success) — contracts H1/H2/H3
- [X] T005 [US1] Add to `tests/unit/test_tts_strip.py` the FR-008 case: a `_strip_markdown_for_tts` stub that raises ⇒ `text_to_speech_tool` receives the RAW text (raw-fallback, never worse than today) — contract H6
- [X] T006 [US1] Run `.venv/bin/python -m pytest -q`: new `test_tts_strip.py` passes AND the existing fake-transport suite (82) still 100% green WITHOUT test edits (FR-010/SC-006)
- [X] T007 [US1] Static self-review vs contracts H1–H7 + constitution I/IV/V: only `hermes_bridge.py` changed (+ the new unit test); strip occurs in `tts_synthesize` so feature-008 `agent_stream` and feature-006 `tts_stream` are both covered by the one site; no engine/normalizer/config/agent-prompt added; agent output/display/transcript path untouched (FR-009)

**Checkpoint**: MVP — markdown-strip wired at the single seam, locally
proven where provable; real prose quality host-proven in Phase 6

---

## Phase 4: User Story 2 - Code and URLs are not spelled out (Priority: P2)

**Goal**: Code blocks and URLs are removed (not vocalized, no stand-in) —
delivered by the SAME reused helper from US1; no extra code.

**Independent Test**: `test_tts_strip.py` covers code-block/URL/empty
inputs (wiring + skip); host-proven in Phase 6.

- [X] T008 [US2] Extend `tests/unit/test_tts_strip.py`: with the fake whose `_strip_markdown_for_tts` returns `""` for a code-only/url-only input, assert `text_to_speech_tool` is NOT called for that unit and the unit is skipped via the generic-exception path (no zero-length audio) — FR-005/FR-007, contracts H3/H5 (no production code change — US2 is satisfied by the US1 single-site reuse)
- [X] T009 [US2] Re-run `.venv/bin/python -m pytest -q`: full suite still green after the US2 cases (no regression — FR-010/SC-006)

**Checkpoint**: Code/URL + empty-after-strip behaviour locked by tests;
end-to-end host-proven in Phase 6

---

## Phase 5: User Story 3 - Display/transcript unaffected; reversible local redeploy (Priority: P3)

**Goal**: The strip changes only audio; ship via the reused gated,
backed-up, reversible local deploy; zero pre-existing-platform regression.

**Independent Test**: post-redeploy both ports listen + 5 pre-existing
platforms intact; displayed/transcript text byte-identical; backup restore
< 5 min.

- [X] T010 [US3] Run `deploy/deploy-local.sh --preflight` (read-only): local host reachable, deps present, snapshot pre-existing platforms (script reused unchanged, FR-011)
- [X] T011 [US3] 🔒 LOCAL-MUTATING Execute `deploy/deploy-local.sh --yes` (gated, backup-first, idempotent): backup config → vendor the package → restart local gateway → post-verify (plugin import/register, 0 pre-existing platforms removed, both :8643 & :8644 LISTENING)
- [ ] T012 [US3] Confirm on the local host: for a Markdown-rich prompt the displayed answer text + stored transcript are byte-identical to pre-deploy (only audio differs — FR-006/SC-005), `lsof` shows :8643 & :8644 LISTEN, the 5 pre-existing platforms intact (SC-007); re-approve pairing if needed (`hermes pairing approve local <CODE>`)
- [ ] T013 [US3] 🔒 LOCAL-MUTATING Reversibility drill: restore the latest `~/.hermes/config.yaml.bak.f007local.*` backup + `hermes gateway restart`; verify config matches backup + pre-existing platforms == pre-state < 5 min (SC-007); then redeploy to leave the fix live for Phase 6 (operator-confirmed)

**Checkpoint**: Fix deployed locally; reversibility re-proven; zero
regression; written answer/record provably unchanged

---

## Phase 6: Live validation — US1 & US2 host-proof (Priority: P1/P2)

**Goal**: Real spoken quality that cannot be exercised locally is proven
on the local gateway with a human.

**Independent Test**: localhost Electron client (`127.0.0.1:8643/8644`, no
ssh/LAN/tunnel), real spoken exchange.

- [ ] T014 [US1] Live (SC-001/SC-002/SC-003): ask a Markdown-rich prompt (bold title + bulleted list + a link) — heard as natural prose + plainly-read list, NO "asterisk"/"hash"/"backtick"/spelled-out URL, sounding the same as Hermes CLI voice for that text (parity); then a plain conversational prompt — spoken output unchanged vs before (stripper no-op, no wording/timing change)
- [ ] T015 [US2] Live (SC-004 / FR-005 / FR-007): an answer containing a fenced code block + a long URL — neither is vocalized, surrounding prose intact, no stand-in phrase (expected per clarify Q4); a code-only reply — clean return to listening (no symbols, no zero-length audio, no hang)
- [ ] T016 [US1] Live (SC-008): on the feature-008 streaming path, confirm no perceptible added time-to-first-word vs the 008 build (the strip is one cheap per-sentence regex Hermes already runs in its own voice)

**Checkpoint**: Clean conversational speech, code/URL not spoken,
code-only graceful, no latency regression — proven on the local gateway

---

## Phase 7: Polish & Cross-Cutting

- [ ] T017 [P] Confirm scope discipline once more: only `src/hermes_satellite_adapter/hermes_bridge.py` changed + new `tests/unit/test_tts_strip.py`; `streamasm.py`/`adapter.py`/`session.py`/transport/contracts/`deploy/*` untouched; existing suite green with NO edits (FR-009/FR-010/FR-011)
- [ ] T018 [P] Update `specs/009-tts-text-normalization/quickstart.md` + `research.md` if the verified host names/seam differed from plan; record the live-test result + any deviation with justifying evidence (constitution V / Governance); update memory ([[feature-007-superseded]] chain → note 009 landed) and leave the host per operator choice

---

## Dependencies & Execution Order

- **Setup (T001)** → **Foundational (T002)** = baseline + host seam pinned; BLOCKS all
- T002 (host re-verify) BEFORE T003 (implements against the verified seam)
- **US1 (T003–T007)**: the only production change (T003) + its wiring tests; no host
- **US2 (T008–T009)**: test-only increment (no new code — US1's single-site reuse already delivers it); depends on T003/T004
- **US3 (T010–T013)**: redeploys locally (needs US1/US2 green); 🔒 local-mutating
- **Phase 6 (T014–T016)**: needs US3 deployed + a human at a mic — host-proof
- **Polish (T017–T018)** last
- T017 ∥ T018

## Parallel Opportunities

- T017 ∥ T018 (scope re-check vs doc/memory update — different files)
- Within US1, T004 and T005 edit the same new file → sequential (no [P]);
  T003 (production) precedes both.
- (No `[P]` across stories: there is a single production site, US2 depends
  on the US1 change, US3 depends on both.)

## Implementation Strategy

**MVP = Setup + Foundational + US1**: pin the host seam (T002), add the
one strip call in `tts_synthesize` with raw-fallback + empty-skip (T003),
prove the wiring + raw-fallback locally (T004–T006) and that the existing
82-suite stays green with no edits, self-review vs the H-contract (T007).
US2 is a pure test increment (the same single reuse already removes
code/URLs — no extra code). US3 ships it via the reused gated/reversible
local deploy and proves display/transcript are byte-unchanged. Phase 6 is
the human host-proof of real spoken quality + no latency regression.
Smallest possible change; pure constitution-IV reuse; fully reversible;
never worse than today (FR-008).

## Notes

- 🔒 LOCAL-MUTATING: T011, T013 — explicit confirmation + backup; reuse
  `deploy/deploy-local.sh` unchanged (FR-011); production ssh
  `deploy-to-hermes.sh` NOT touched.
- The whole feature is one call to Hermes's own `_strip_markdown_for_tts`
  at the existing `tts_synthesize` seam (research D1/D4) — Hermes's own
  voice (`_send_voice_reply`, CLI `stream_tts_to_speaker`) does the same.
  No bespoke normalizer, no emoji code (exact Hermes parity — clarify Q2),
  no length cap (clarify Q3), no new config (clarify Q4/constitution IV).
- Local-testability boundary (constitution V): the WIRING is unit-tested
  with a fake `tools.tts_tool`; the real `_strip_markdown_for_tts`
  semantics are Hermes-owned and host-proven by the live spoken test —
  not re-derived locally (would fork behaviour, violating IV).
- Constitution: I/IV exemplary (defer entirely to a Hermes helper, no
  engine); V satisfied (host researched in clarify + re-verified T002;
  wiring locally proven; real behaviour host-proven). II/III untouched;
  transport/turn semantics behaviourally unchanged, fake suite green with
  no edits (FR-009/FR-010). Complexity Tracking: none (feature removes
  complexity).
