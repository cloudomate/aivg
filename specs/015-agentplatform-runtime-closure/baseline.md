# Pre-Refactor Baseline (feature 015)

**Date captured**: 2026-05-20 (pre-implementation)
**Reference branch**: `main` @ 71db568 ("feat(010): instrument + reduce voice-turn latency").

## SC-001 / SC-006 — coupling counts

```bash
rg -n '# AgentPlatform-coupling-TODO' src/aivg_core/
```

**Pre-refactor count**: **4 lines / 3 distinct markers** (one is a multi-line tuple import in `session.py` matched on line 23). The three coupling sites:

- `src/aivg_core/adapter.py:18`  (top-level `HermesBridge, UnboundHermesBridge`)
- `src/aivg_core/adapter.py:127` (lazy `HermesV013Bridge, SessionCtx`)
- `src/aivg_core/webrtc/signaling.py:17` (top-level `HermesBridge`)
- `src/aivg_core/webrtc/session.py:23` (multi-line `HermesBridge, SessionCtx, AgentReply, AllProvidersUnavailable`)

```bash
rg -n 'from .*\.platforms\.hermes\.' src/aivg_core/ | grep -v '^src/aivg_core/platforms/hermes/'
```

**Pre-refactor count**: **4** (same files as above — these are the gated imports).

Target post-refactor: **0 / 0** (SC-001 / SC-006).

## SC-002 — live electron-test smoke

Last live-proven on `main` per feature 014 commit history (TS SDK v0.1.3 mute/unmute PTT model). Recorded by the user as working in feature 014 closure. Treated as the SC-002 reference baseline; not re-run pre-refactor in this session.

## SC-003 — first-audio latency

**Pre-refactor median (feature 010 live-proven baseline)**: as recorded in commit `71db568` — feature 010 measured ~51% improvement over its own pre-instrumentation baseline. Treating the post-feature-010 median as the SC-003 reference; the synthetic pytest harness was not re-run in this session per implementation-time decision (will be evaluated by the manual electron-test smoke at T033).

Target post-refactor: |post − pre| / pre ≤ 0.10 (±10 %).

## SC-007 — wire surface

```bash
aivg --contract-version
```

**Pre-refactor**: `1.0.0` (frozen since feature 011). MUST remain `1.0.0` post-refactor.

## Post-refactor measurements

- **Post-refactor TODO count**: **0** (was 4 lines / 3 markers) — verified by `tests/unit/test_no_coupling_todo_markers.py` ✓
- **Post-refactor hermes-import-in-core count**: **0** outside `src/aivg_core/platforms/hermes/` (was 4) — verified by `tests/unit/test_no_hermes_imports_in_core.py` ✓
- **Post-refactor fake-bridge/fake-platform test suite**: **266 passed, 1 xpassed, 0 failed** across 4 consecutive full-suite runs ✓
- **Post-refactor electron-test smoke (T033)**: _DEFERRED to host_ — requires the user to run on a machine with the Hermes gateway + electron-test client. Procedure documented in [quickstart.md § 6](./quickstart.md).
- **Post-refactor latency median (T034)**: _DEFERRED to host_ — feature 010's `tests/integration/test_voice_turn_latency.py` requires the real Hermes runtime. Manual electron-test smoke (T033) is the binding human check per [quickstart.md § 5](./quickstart.md).
- **Post-refactor `aivg --contract-version` (T049)**: _DEFERRED to host_ — should print `1.0.0` unchanged (SC-007). Verified by inspection: this feature touched no WS/REST handlers (FR-014 / contracts/agent-platform.md § 6 wire-surface invariance).
