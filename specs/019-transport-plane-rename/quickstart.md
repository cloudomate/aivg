# Quickstart — Verify the `satellite_webrtc` → `aivg_satellite` rename

**Feature**: 019-transport-plane-rename · **Date**: 2026-05-21

The "did we land it" checklist. Exercises every binding success
criterion from [spec.md](./spec.md#success-criteria) using the
smallest possible set of commands. Run after implementation
completes; every step should pass without manual fix-ups.

Repo root for all commands: `/Users/yashwant.singh/coderepo/aivg`.
Hermes venv path: `~/.hermes/hermes-agent/venv/`.

---

## 1. Static checks (under 5 seconds)

### 1.1 No remaining `satellite_webrtc` literals in shipping code (SC-001)

```bash
rg --no-heading -n '"satellite_webrtc"|satellite_webrtc' \
  src/aivg_core/ \
  --glob '!*test*' --glob '!*setup.py'
```

**Expected**: ZERO matches outside `setup.py` (which keeps
`LEGACY_PLUGIN_NAME = "satellite_webrtc"` for feature 013's
legacy-cleanup paths).

### 1.2 Canonical name in the entry-point shim (SC-001)

```bash
grep -n 'name="aivg_satellite"' \
  src/aivg_core/platforms/hermes/plugin_entrypoint/adapter.py
```

**Expected**: one match on the `ctx.register_platform(name=…)`
call.

### 1.3 Back-compat alias present (R-3 / data-model § 3)

```bash
grep -nE 'SatelliteWebRTCAdapter = AivgSatelliteAdapter' \
  src/aivg_core/adapter.py
```

**Expected**: one match. The alias keeps any external
`from aivg_core.adapter import SatelliteWebRTCAdapter` import
working.

### 1.4 Constitution-binding files untouched (SC-002, Principle II)

```bash
git diff main..019-transport-plane-rename -- \
  src/aivg_core/management/service.py \
  src/aivg_core/webrtc/session.py \
  src/aivg_core/config.py \
  src/aivg_core/models.py | wc -l
```

**Expected**: `0`. The wire surfaces and the contract-version
machinery are untouched.

---

## 2. Unit tests (under 10 seconds)

```bash
PYENV_VERSION=3.11.9 PYTHONPATH=src:tests pytest \
  tests/unit/test_plugin_registration_name.py \
  tests/unit/test_conflict_detector.py \
  tests/unit/test_no_conflict_quiet_path.py \
  tests/unit/test_adapter_sites.py \
  -v
```

**Expected**: all pass. The three new tests assert the rename
landed, the detector fires loudly on conflict, and the detector
stays silent on the common case. The existing
`test_adapter_sites.py` continues to pass against the back-compat
alias.

---

## 3. Full suite regression (SC-004)

```bash
for i in 1 2 3; do
  PYENV_VERSION=3.11.9 PYTHONPATH=src:tests pytest tests/ -q --tb=line 2>&1 | tail -3
  echo "---"
done
```

**Expected**: 3/3 consecutive runs at **329 + N passed, 0 failed**
(329 from feature 017 + N new tests). No flakes.

---

## 4. Wire-surface byte-diff (SC-002, Principle II)

The binding gate for the "constitution-neutral" promise. Capture
the wire surface from the pre-019 gateway, capture it again from
the post-019 gateway over the same scripted flow, and diff.

### 4.1 Pre-019 capture (run BEFORE applying 019)

```bash
# Restart the gateway on the pre-019 build (main HEAD).
~/.hermes/hermes-agent/venv/bin/hermes gateway restart

# Wait for both ports to bind.
until [ "$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null \
  | grep -Eo ':(8643|8644)\b' | sort -u | wc -l)" = "2" ]; do
  sleep 1
done

# Capture each REST surface.
mkdir -p /tmp/aivg-019-baseline/pre
curl -s 'http://localhost:8643/satellite/list?state=all' \
  > /tmp/aivg-019-baseline/pre/list.json
~/.hermes/hermes-agent/venv/bin/aivg --contract-version \
  > /tmp/aivg-019-baseline/pre/contract-version.json

# Capture a WS register exchange.
python3 - <<'PY' > /tmp/aivg-019-baseline/pre/ws-register.txt
import asyncio, aiohttp
async def main():
    async with aiohttp.ClientSession() as s:
        async with s.ws_connect(
            "ws://localhost:8643/satellite/ws?device_id=diff-probe"
        ) as ws:
            await ws.send_json({
                "type":"register","device_id":"diff-probe",
                "device_type":"probe","firmware_version":"0.0.0",
                "contract_version":"1.1.0"})
            for _ in range(2):
                try: msg = await asyncio.wait_for(ws.receive(), timeout=3)
                except asyncio.TimeoutError: break
                print(msg.data)
asyncio.run(main())
PY
```

### 4.2 Post-019 capture (run AFTER applying 019)

```bash
~/.hermes/hermes-agent/venv/bin/hermes gateway restart
until [ "$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null \
  | grep -Eo ':(8643|8644)\b' | sort -u | wc -l)" = "2" ]; do
  sleep 1
done

mkdir -p /tmp/aivg-019-baseline/post
curl -s 'http://localhost:8643/satellite/list?state=all' \
  > /tmp/aivg-019-baseline/post/list.json
~/.hermes/hermes-agent/venv/bin/aivg --contract-version \
  > /tmp/aivg-019-baseline/post/contract-version.json
# (same WS register script as above)
```

### 4.3 Diff

```bash
diff -u /tmp/aivg-019-baseline/pre/list.json \
        /tmp/aivg-019-baseline/post/list.json
diff -u /tmp/aivg-019-baseline/pre/contract-version.json \
        /tmp/aivg-019-baseline/post/contract-version.json
diff -u /tmp/aivg-019-baseline/pre/ws-register.txt \
        /tmp/aivg-019-baseline/post/ws-register.txt
```

**Expected**: ZERO diff on all three. Wire surfaces are
byte-identical. This is the binding constitution-II gate.

---

## 5. Gateway log assertion (SC-001)

```bash
~/.hermes/hermes-agent/venv/bin/hermes gateway restart
sleep 5
grep -E 'aivg_satellite|satellite_webrtc' ~/.hermes/logs/gateway.log \
  | tail -10
```

**Expected**: lines containing `aivg_satellite` (e.g.,
`Connecting to aivg_satellite...`, `✓ aivg_satellite connected`).
ZERO lines containing `satellite_webrtc` from the post-019
restart timestamp onward.

---

## 6. Conflict detector — loud failure (SC-003)

Simulate the silent-shadow trap we hit during the 2026-05-21
deploy session. Place a pre-rebrand vendored plugin AND enable
the post-019 entry-point plugin, then restart.

### 6.1 Setup the conflict

```bash
# Restore the pre-rebrand bundled plugin from today's deploy backup.
cp -R ~/.hermes/backups/satellite_webrtc.pre-aivg-redeploy.*.bak \
      ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc

# Confirm both plugins are visible to Hermes.
~/.hermes/hermes-agent/venv/bin/python -c "
from hermes_cli.plugins import discover_plugins, get_plugin_manager
discover_plugins(force=True)
m = get_plugin_manager()
for p in m.list_plugins():
    n = p.get('name','?')
    if 'satel' in n.lower() or 'aivg' in n.lower():
        print(f'{n!r} source={p.get(\"source\")} enabled={p.get(\"enabled\")}')
"
```

**Expected**: two rows — the legacy `satellite-webrtc-platform`
(source=bundled, enabled=True) AND the new `aivg-satellite`
(source=entrypoint, enabled=True).

### 6.2 Restart and verify loud failure

```bash
~/.hermes/hermes-agent/venv/bin/hermes gateway restart
sleep 5

# The entry-point plugin should refuse to register with a clear error.
grep -E 'satellite-webrtc-platform|aivg_satellite' \
  ~/.hermes/logs/gateway.log | tail -20
```

**Expected** (since the new error fires on the post-019 plugin's
`register()`):

- A clear ERROR-level log line naming the conflict, naming the
  directory (`~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc/`),
  and naming the cleanup verb (`mv …` or `rm -rf …`).
- The gateway boots, but `aivg-satellite` shows as
  `error="<conflict text>"` in `hermes plugins list`.
- Other Hermes platforms (IRC, etc.) load normally — the
  satellite-plugin failure does NOT cascade.

### 6.3 Clean up and recover

```bash
mv ~/.hermes/hermes-agent/plugins/platforms/satellite_webrtc \
   ~/.hermes/backups/satellite_webrtc.requickstart-test.bak
~/.hermes/hermes-agent/venv/bin/hermes gateway restart
sleep 5
grep -E 'aivg_satellite' ~/.hermes/logs/gateway.log | tail -5
```

**Expected**: gateway boots cleanly, log shows
`✓ aivg_satellite connected`, no conflict error.

---

## 7. Pre-019 client compatibility (SC-005)

The binding "no operator-side change" check.

### 7.1 Unchanged @aivg/sat-sdk 0.1.4 electron-test

```bash
cd clients/electron-test
npm start
# (in the renderer:)
# 1. Connect → adopt → press-and-hold PTT → speak → release
# 2. Confirm a voice turn completes end-to-end exactly as it did pre-019
```

**Expected**: full register → adopt → voice-turn flow completes.
The renderer's log shows `adoption: adopted ✓`, the PTT button
enables, a voice turn produces audio playback. ZERO renderer-side
change required.

### 7.2 (Optional) Unchanged ESPHome voice satellite

If a Home Assistant Voice PE or M5Stack Atom Echo flashed against
the pre-019 gateway is available on the LAN:

1. Power-cycle the device.
2. Wait for it to re-register with the post-019 gateway over the
   ESPHome native API (port 6053).
3. Trigger a voice turn via wake-word or hardware button.
4. Confirm round-trip audio playback.

**Expected**: zero device-side change needed. The ESPHome
transport's wire format is upstream-defined and untouched by 019.

---

## 8. CHANGELOG entry

`CHANGELOG.md` MUST contain a 019 entry along these lines:

```markdown
## [0.3.1] — 2026-MM-DD

### Changed

- Internal Hermes plugin registration name renamed from
  `satellite_webrtc` to `aivg_satellite`. Gateway log lines now
  carry the new name. **No wire-surface change** — REST paths
  under `/satellite/*`, the `satellite:` config block, the
  `SATELLITE_*` env vars, and the contract version (`1.1.0`)
  are unchanged. (Feature 019.)
- `aivg_core.adapter.SatelliteWebRTCAdapter` renamed to
  `AivgSatelliteAdapter`. The old name remains importable as
  a back-compat alias for one release. (Feature 019.)

### Added

- The post-019 plugin entry-point's `register()` detects a
  still-installed pre-rebrand vendored `satellite_webrtc/`
  bundled plugin and refuses to register, with a clear error
  naming the cleanup verb. Eliminates the silent-shadow trap
  that affected pre-019 fresh installs over the rebrand cutover.
  (Feature 019.)
```

**Expected**: the entry exists, the version number matches the
released artifact, the prose names the spec section / FRs the
entry maps to.

---

## Cleanup

After verification, the test-injection setup from step 6.1 left
a re-injected legacy plugin; step 6.3 moved it out. No persistent
state to clean.

If step 4 produced `/tmp/aivg-019-baseline/` artifacts and you're
done with them:

```bash
rm -rf /tmp/aivg-019-baseline/
```
