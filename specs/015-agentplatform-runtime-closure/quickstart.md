# Quickstart — Verify AgentPlatform Runtime Closure

**Feature**: 015-agentplatform-runtime-closure · **Date**: 2026-05-20

This is the "did we land it" checklist. It exercises every binding
success criterion from [spec.md](./spec.md#success-criteria) using
the smallest possible set of commands. Run after implementation
completes; every step should pass without manual fix-ups.

Repo root for all commands: `/Users/ys/coderepo/hermes-voice`.

---

## 1. Static checks (under 5 seconds)

### 1.1 Zero coupling-TODO markers (SC-006a)

```bash
rg --no-heading -n '# AgentPlatform-coupling-TODO' src/aivg_core/
```

**Expected**: no output (exit code 1 from ripgrep — the absence of
matches IS the success).

### 1.2 Zero plugin imports outside the plugin (SC-006b)

```bash
rg --no-heading -n 'from .platforms.hermes\.|from \.\.platforms\.hermes\.|from aivg_core\.platforms\.hermes\.' \
   src/aivg_core/ \
   | grep -v '^src/aivg_core/platforms/hermes/'
```

**Expected**: no output. Imports of `aivg_core.platforms.hermes`
must live ONLY inside that plugin directory (the plugin's own
internal cross-file imports are fine).

### 1.3 Plugin export surface clean (FR-011)

```bash
python -c "from aivg_core.platforms.hermes import PLATFORM; \
print(type(PLATFORM).__name__, PLATFORM.name)"
```

**Expected**: `HermesAgentPlatform hermes`.

```bash
python -c "import aivg_core.platforms.hermes as h; \
print('HermesBridge' in dir(h), 'HermesV013Bridge' in dir(h))"
```

**Expected**: `False False` — bridge symbols are plugin-internal.

---

## 2. Contract tests (under 10 seconds)

```bash
pytest -x tests/contract/test_agent_platform_contract.py -v
```

**Expected**: all 13 tests pass. Both the Hermes plugin AND the
echo fixture plugin satisfy the contract.

---

## 3. Echo-plugin integration test (US4, SC-008)

```bash
pytest -x tests/integration/test_voice_loop_echo_platform.py -v
```

The echo platform is loaded via `PluginRegistry.load("echo")`; the
voice loop runs end-to-end without importing anything from
`aivg_core.platforms.hermes`. **Expected**: PASS.

---

## 4. Hermes parity tests (US2, SC-001, SC-002)

```bash
pytest -x \
  tests/integration/test_signaling_offer_answer.py \
  tests/integration/test_voice_session_basic.py \
  tests/integration/test_voice_session_barge_in.py \
  -v
```

**Expected**: every test that passed on `main` before the refactor
still passes. ZERO test edits beyond the bridge-→-platform
constructor signature change in the test fixtures.

---

## 5. Latency parity (US3, SC-003)

Re-run the feature-010 measurement harness against a freshly
restarted gateway:

```bash
# In one terminal — gateway
hermes config set voice.silence_duration 1.2
hermes gateway run --port 8643

# In another terminal — measurement
pytest -x tests/perf/test_voice_turn_latency.py::test_first_audio_p50 -v --runs 10
```

**Expected**: median first-audio delivered ≤ 110% of `main`
baseline (from feature 010: ~720ms). I.e. budget ≤ 792ms.

If a real human turn beats the budget on the electron-test smoke
(US4 manual), that is the binding signal — the synthetic test is a
guard rail, not the bar.

---

## 6. Live smoke (US4, the binding human check)

```bash
cd clients/electron-test
npm install
npm start
```

Then in the app:

1. Click **Connect** — wait for `connected — run: aivg device adopt …`.
2. In a shell: `aivg device adopt electron-test-1`.
3. App: state goes `provisioned → adopted → idle → ready`.
4. Hold **PTT**, say "Hello, can you hear me?", release.
5. State transitions: `listening (PTT) → thinking → speaking → idle`.
6. Reply audio plays through speakers; transcript boxes populate.

**Expected**: identical behaviour to pre-refactor. The TS SDK
build (`@aivg/sat-sdk` 0.1.3) is NOT rebuilt — same package binary
drives the new platform-keyed loop.

If any step regresses, the wire-surface invariance gate (FR-014)
has failed; revert the offending commit.

---

## 7. Optional — drop in a fake non-Hermes plugin

Drop the `tests/fixtures/platforms/echo/` plugin (already on disk)
into the satellite config at runtime:

```bash
aivg config set adapter.platform echo
aivg gateway run --port 8643
```

The voice loop runs against echo (echoes back the user transcript
as synthesized speech). Confirms US1: a non-Hermes plugin drives
the same code path. No `aivg_core` change required.

---

## Cleanup

```bash
aivg config set adapter.platform hermes  # restore default
```
