# Phase 0 Research: Agent Text-Delta Streaming Seam

Grounded in live debugging of feature 007 + read-only recon of the running
**local** hermes-agent **v0.14.0** (`~/.hermes/hermes-agent`, 2026-05-19).
The central feasibility question is answered; exact entrypoints are pinned
below and re-verified at implement time (constitution V), with FR-005 as the
safety net.

## D1 — Feature 007's draft-hook seam is a confirmed dead end (why 008 exists)

- **Decision**: Abandon the platform draft-streaming hook for the
  satellite/voice path.
- **Evidence (live `-vv` DEBUG, instrumented adapter)**: our 007 code is
  correct & fully exercised (`F007 agent_stream ENTER` → `send (FINAL)` →
  `feed_final … saw_draft=False` every turn), but Hermes **never** probes
  `supports_draft_streaming` / calls `send_draft`, and
  `GatewayStreamConsumer` is **never instantiated** (0 occurrences in the
  full `-vv` log, satellite *and* TUI). The draft/stream consumer is the
  text-messaging-platform delivery path; it is not attached to a programmatic
  adapter that drives the agent via `handle_message` and returns the reply
  through a `send()`-future.
- **Rationale**: config gates were all satisfied (`streaming.enabled:true`,
  `transport:auto`, `display.platforms.cli.streaming:true`) and it still
  never engaged → architectural, not configuration.

## D2 — The sanctioned seam: run Hermes's `AIAgent` with a delta callback

- **Decision**: Obtain the incremental reply the way Hermes's **own CLI and
  Discord voice modes** do — construct/run the Hermes `AIAgent` directly with
  a text-delta callback; consume the deltas into feature 007's
  `IncrementalUnitAssembler` → feature 006 per-sentence Hermes-TTS → WebRTC.
- **Evidence (host recon, verified v0.14.0)**:
  - `cli.py:673` `from run_agent import AIAgent`.
  - `cli.py:4516+` constructs `AIAgent(model=…, fallback_model=…,
    enabled_toolsets=…, disabled_toolsets=…, ephemeral_system_prompt=…,
    session_id=…, session_db=…, stream_delta_callback=… , …)`.
  - `cli.py:11108+` voice path: `text_queue=queue.Queue()`,
    `stop_event=threading.Event()`, thread →
    `tools.tts_tool.stream_tts_to_speaker(text_queue, stop_event, done)`,
    `def stream_callback(delta): text_queue.put(delta)`, then
    `self.agent.run_conversation(msg, …, stream_callback=stream_callback)`.
  - `run_agent.py:326` `class AIAgent`; `:349 def __init__(… ,
    stream_delta_callback: callable = None, …)`; `:3867 def
    run_conversation(self, user_message, system_message=None,
    conversation_history=None, task_id=None, stream_callback=None,
    persist_user_message=None) -> dict` (forwards to
    `agent.conversation_loop.run_conversation`); both
    `stream_delta_callback` and per-call `stream_callback` receive text
    deltas (`run_agent.py:2923/2937/3027`).
  - Discord voice mode = the **Discord adapter itself** orchestrates
    join/capture/STT/agent/`play_tts` (`gateway/platforms/discord.py`) — i.e.
    adapter-side voice orchestration calling Hermes engines is the
    **sanctioned Hermes pattern**, not a constitution violation.
- **Rationale**: This is the *only* path that actually streams to a
  programmatic consumer, and it is Hermes-native (constitution IV). We run
  Hermes's agent, not a reimplementation.
- **Alternatives considered**: 007 draft hook — rejected (D1, proven dead).
  Hermes API-server SSE (`/v1/chat/completions` stream) — rejected for now
  (separate service/auth surface; a heavier dependency than running the
  in-process `AIAgent` the way the CLI already does).

## D3 — TTS: keep our per-sentence Hermes-Piper path, NOT `stream_tts_to_speaker`

- **Decision**: Reuse the existing `bridge.tts_synthesize` (Hermes
  `tts_tool`/Piper) per assembled sentence + feature 006 pipeline. Do **not**
  use `tools.tts_tool.stream_tts_to_speaker`.
- **Evidence**: `tools/tts_tool.py:1981` "Streaming TTS: sentence-by-sentence
  pipeline **for ElevenLabs**"; `:2014 stream_tts_to_speaker` writes to the
  **local machine speaker** (sounddevice) and is ElevenLabs-locked. Unusable
  for a remote WebRTC client and provider-locked.
- **Rationale**: We only need the *agent delta seam* from the CLI pattern;
  the audio sink is already solved by features 005/006 (Piper via the bridge
  → WebRTC). Reusing it keeps provider choice = Hermes config (constitution
  I/IV) and the fake suite byte-identical.

## D4 — STT unchanged

- **Decision**: Keep `transcription_tools.transcribe_audio(file_path,
  model=None)` via the existing `bridge.stt_transcribe` (verified
  `tools/transcription_tools.py:814`; provider/fallback from Hermes config).
  No change.

## D5 — Barge-in cancels generation via `AIAgent.interrupt()`

- **Decision**: On barge-in, call `AIAgent.interrupt(message=None)`
  (`run_agent.py:1585`, designed to be called cross-thread) on the in-flight
  agent, in addition to feature 006 stop_playback + abandoning the unit
  queue. `AIAgent.is_interrupted()` (`:2146`) guards the loop.
- **Rationale**: Hermes-owned cancellation (constitution I); replaces
  feature 007's `interrupt_session_activity` (that was for the dead
  handle_message path). No orphan generation (FR-004/SC-004).

## D6 — Mandatory fallback to feature 006 (FR-005)

- **Decision**: If `AIAgent` cannot be constructed/run for a turn (host
  import/seam failure) or the bridge is the fake test double, resolve the
  reply exactly as feature 006 (`agent_turn`/`tts_stream` over the completed
  reply). `session._respond` already branches on `getattr(bridge,
  'agent_stream', None)`; the fake bridge exposes none → 006 verbatim →
  fake-transport suite byte-identical, no test edits (SC-007).

## D7 — Local testability boundary (constitution V)

- **Decision**: The deterministic slice (cumulative/append deltas → ordered
  complete units, buffered tail, idempotent flush, immutable prefix) is
  feature 007's `IncrementalUnitAssembler`, reused with its unit suite
  **unchanged** (FR-011). Running the real `AIAgent`, the delta wiring, and
  barge-in are host-only and host-proven (local live spoken test).

## D8 — Deploy

- **Decision**: Reuse `deploy/deploy-local.sh` unchanged (local Hermes,
  backup-first, idempotent, reversible). Production `deploy-to-hermes.sh`
  untouched (FR-010). End-to-end cadence + barge-in are the local live
  spoken test.

## T002 — RESOLVED at implement time (local host recon, v0.14.0, 2026-05-19)

- **Construct**: `from run_agent import AIAgent`. All `__init__` params have
  defaults; minimal headless set = `AIAgent(model, api_key, base_url,
  provider, api_mode, session_id, session_db, platform="satellite",
  stream_delta_callback=cb, fallback_model=…, max_iterations=…)`. No TTY /
  prompt_toolkit / stdin requirement in `__init__` (cli.py only optionally
  sets `agent._print_fn` afterwards) → **headless construction feasible**
  (M2 de-risked).
- **Model/provider runtime** (constitution IV — inherit Hermes config, do
  NOT hardcode the `model:` block): `from hermes_cli.runtime_provider import
  resolve_runtime_provider`; `runtime = resolve_runtime_provider()` →
  api_key/base_url/provider/api_mode; model from Hermes config default.
- **Session/history (FR-012)**: `from hermes_state import SessionDB`;
  cli.py constructs ONE `SessionDB()` + a stable `session_id` and passes
  both to `AIAgent`; `agent/conversation_loop.run_conversation`
  (run_agent.py:3867 → conversation_loop.py:187,
  `conversation_history`/`session_db`) persists+restores history. **Decision:
  construct ONE persistent `AIAgent` per voice session (cached by
  `ctx.session_id`) with a stable `session_id` + a shared `SessionDB()`, and
  reuse it across turns** → multi-turn continuity at cli.py parity, no
  per-turn history bookkeeping in the adapter.
- **run_conversation**: `agent.run_conversation(user_text,
  stream_callback=cb)` (blocking; runs in a worker thread →
  `asyncio.to_thread` / queue handoff like feature 006 `tts_stream`); `cb`
  receives text deltas (same as ctor `stream_delta_callback`).
- **Barge-in**: `agent.interrupt(message=None)` (cross-thread safe);
  `agent.is_interrupted()` guards.
- **STT/TTS unchanged**: `transcription_tools.transcribe_audio` /
  `tts_tool` Piper via the existing bridge.

## Live host findings 2026-05-19 (constitution V — fixes applied)

Logs from the local gateway (`~/.hermes/logs/agent.log`,`errors.log`)
confirmed the 008 seam is genuinely live: `agent.conversation_loop:
conversation turn: session=satellite_<sid> platform=satellite
model=MiniMaxAI/MiniMax-M2.7 provider=custom` with
`chat_completion_stream_request` on a worker thread + per-sentence Piper
TTS — the cli.py delta seam, model/runtime inherited from Hermes config
(constitution IV). Three defects surfaced and were fixed:

- **B1 `_on_done` CancelledError leak**: on barge-in/teardown the worker
  task is cancelled; `_on_done` did `t.exception()` (re-raises
  `CancelledError`) → caught → fell to `t.result()` → re-raised uncaught
  → `ERROR asyncio: Exception in callback …_on_done`. Fix: `if
  t.cancelled(): return` first (deliver nothing — consumer already gone).
  Verified: zero recurrences after the fix redeploy.
- **B2 empty-unit Piper `wave.Error: # channels not specified`**: a
  whitespace/empty speakable unit reached Hermes `text_to_speech_tool` →
  0-frame WAV. Was swallowed by the per-unit `except Exception: continue`
  (FR-007 held) but dropped a sentence + spammed `errors.log`. Fix: skip
  empty/whitespace units before TTS (FR-003). Zero recurrences after fix.
- **B4 sticky interrupt → "doesn't talk back"** (most user-visible):
  after any barge-in, every subsequent turn ended
  `reason=interrupted_by_user api_calls=0 response_len=0` → no reply →
  no TTS → silence. Root cause: barge-in calls `agent.interrupt()`
  (`_interrupt_requested=True`); the cached `AIAgent` is REUSED across
  turns (FR-012 design); `agent/conversation_loop` at turn start
  **deliberately preserves** a pending interrupt (comment: "If an
  interrupt arrived before startup finished, preserve it") and does NOT
  auto-clear — it expects the caller to clear it once handled, exactly as
  cli.py does (`agent.clear_interrupt()`). We never cleared it → stale
  flag bled into the next turn → instant abort. Fix: call
  `agent.clear_interrupt()` at the start of `_run` (before
  `run_conversation`) — the new user utterance is the fresh-start signal.
  Log evidence: first turn on a fresh agent worked (`response_len=23`),
  every reused-agent turn after a barge-in was `response_len=0
  interrupted_by_user`. Re-verify live after redeploy.
- **B3 FR-012 continuity broke (`history=0` every turn)**: 7 turns in one
  `satellite_<sid>` session all logged `history=0`. Root cause:
  `agent/conversation_loop.run_conversation` logs `history=%d` from the
  `conversation_history` **arg** and DOES NOT auto-restore from
  `session_db`; the **caller** must restore it (cli.py does:
  `restored = self._session_db.get_messages_as_conversation(self.session_id)`
  → passed as `conversation_history`). `_persist_session` →
  `_flush_messages_to_session_db` already auto-persists every turn keyed
  by `agent.session_id`. Fix: before each `run_conversation`, restore
  `self._session_db.get_messages_as_conversation(agent.session_id)` and
  pass it as `conversation_history=` (best-effort; restore failure → a
  stateless turn, never worse). This is the missing half of the
  persistent-`AIAgent`+shared-`SessionDB` design — now at cli.py parity.
  **Re-verify in T020** (the live "my name is Yash" → "what's my name?"
  two-turn proof must show non-zero `history=` on the follow-up).

## T003 — IMPLEMENT-TIME DEVIATION (recorded, constitution V / T023)

- **What**: `tasks.md` T003 wording says feed deltas as
  `IncrementalUnitAssembler.push(delta)`. The agent `stream_callback`
  emits **append** deltas (fragments), not cumulative snapshots. Feeding
  raw fragments is **incorrect** with the reused (feature-007, unchanged)
  assembler: `_absorb` decides cumulative-vs-append against the
  *already-consumed* prefix, and while nothing is consumed yet every
  fragment satisfies `draft.startswith("")` → the cumulative branch
  (`self._acc = draft`), so each new fragment **discards** the prior
  buffered fragments. Verified live against the real `streamasm.py`:
  deltas `["Hello"," there",". How"," are you","? Bye."]` →
  raw-delta feed yields `['.', 'How are you?', 'Bye.']` (first sentence
  corrupted), cumulative feed yields the correct
  `['Hello there.', 'How are you?', 'Bye.']`.
- **Decision**: The bridge accumulates the deltas into a running
  cumulative reply string and calls `assembler.push(cumulative)` (and
  `assembler.flush(final or cumulative)`), i.e. drives the assembler on
  its **well-tested cumulative path** (the path the A1–A5 suite proves).
  The reused assembler + its test suite stay **byte-unchanged** (FR-011);
  only the bridge's call shape differs from T003's literal phrasing.
- **Why this is faithful**: identical observable behaviour, uses the
  proven path, no assembler/test edits, no new logic. Honest deviation
  from literal task wording, same intent (deltas → ordered complete units
  → per-sentence Hermes TTS). To re-confirm in T023.

## Residual (re-verify at implement time, not blockers)

- Exact `AIAgent` constructor argument set required for a minimal voice turn
  on v0.14.0 (model/toolset/session args) — mirror `cli.py`'s construction;
  read the running `run_agent.py`/`cli.py` again at implement time (same
  discipline as 003/005/007). FR-005 covers the negative case.
- Whether `run_conversation` must run in a worker thread (it is blocking /
  thread-pool in cli.py) and how its `stream_callback` thread interleaves
  with the asyncio transport — confirmed pattern: producer thread →
  `asyncio.Queue`/threadsafe handoff → async consumer (mirrors feature 006
  `tts_stream`).
- Conversation history/session persistence parity with the prior
  `handle_message` path (cosmetic; turn bookkeeping unchanged — FR-009).
