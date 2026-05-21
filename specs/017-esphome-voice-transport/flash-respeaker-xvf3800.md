# Flashing the ReSpeaker XVF3800 against AIVG (feature 017)

**Target hardware**: ReSpeaker XVF3800 + ESP32-S3 (the device used in
[formatBCE/Respeaker-XVF3800-ESPHome-integration](https://github.com/formatBCE/Respeaker-XVF3800-ESPHome-integration)).

This recipe adapts the upstream YAML at
`config/respeaker-xvf-satellite-example.yaml` to point at AIVG instead
of Home Assistant Assist. Total time: ~10 minutes (most is ESPHome
compile-time).

---

## Step 1 — AIVG side: per-device API key

Already done in this session. The keystore now contains:

```text
device_id : respeaker-xvf-1
api_key   : G_NAR9VvpTZyH2ihBZWGfGaDlDmhLSP2
keystore  : ~/.aivg/devices/keys.json (mode 0600)
```

If you need to regenerate the key (e.g. you flashed with a different
one), re-run:

```bash
/Users/ys/.hermes/hermes-agent/venv/bin/python -c "
import sys
sys.path.insert(0, '/Users/ys/coderepo/hermes-voice/src')
from aivg_core.transports.esphome.auth import KeystoreResolver
ks = KeystoreResolver()
new_key = ks.add_device('respeaker-xvf-1')
print('new key:', new_key)
"
```

---

## Step 2 — Clone the upstream YAML

```bash
cd ~/projects   # or wherever you keep firmware sources
git clone https://github.com/formatBCE/Respeaker-XVF3800-ESPHome-integration.git
cd Respeaker-XVF3800-ESPHome-integration/config
```

The reference file is `respeaker-xvf-satellite-example.yaml`. Copy it
to a working file you'll customize:

```bash
cp respeaker-xvf-satellite-example.yaml aivg-respeaker.yaml
```

---

## Step 3 — Patch the YAML to point at AIVG

Two edits required, both small:

### 3a. Add `password:` to the `api:` block

The upstream YAML's `api:` block has no `password:` — leaving it open
to any LAN client. AIVG requires the device to authenticate against
the per-device key from step 1. Add **one line** to the `api:` block:

```yaml
api:
  id: api_id
  password: !secret aivg_api_key   # ← ADD THIS LINE
  actions:
    - action: set_led_color
    # … rest unchanged …
```

### 3b. Set the device's `name:` to match the keystore entry

The upstream `name:` template should be set so the device identifies
as `respeaker-xvf-1` (matching the keystore key from step 1). In the
`esphome:` block:

```yaml
esphome:
  name: respeaker-xvf-1   # ← MUST match the device_id in step 1
  friendly_name: "AIVG ReSpeaker"
  # … rest unchanged …
```

---

## Step 4 — Add the AIVG key to `secrets.yaml`

ESPHome reads `!secret` references from a `secrets.yaml` adjacent to
your YAML. Add:

```yaml
# secrets.yaml (in the same directory as aivg-respeaker.yaml)
wifi_ssid: "YourWiFiSSID"
wifi_password: "YourWiFiPassword"
aivg_api_key: "G_NAR9VvpTZyH2ihBZWGfGaDlDmhLSP2"
```

Use the **exact** key from step 1. Replace SSID + password with yours
if not already set.

---

## Step 5 — Configure AIVG to dial the device

The device is the **API server** (listens on port 6053; advertises
`_esphomelib._tcp` via mDNS). AIVG is the **client** (dials out to
each configured device). This is the standard ESPHome flow, same as
how Home Assistant connects to ESPHome devices.

Find the device's LAN IP — easiest path: after first boot, the
device's serial console prints it, or check your router's DHCP
table, or use `arp-scan` / `nmap`:

```bash
# Find the device on the LAN (replace 192.168.1.0 with your subnet):
sudo arp-scan -l 192.168.1.0/24 | grep -i espressif
```

Assume the device's IP is `192.168.1.42`. Add the device entry to
the AIVG gateway config (`~/.hermes/config.yaml`):

```yaml
satellite:
  # … existing block …
  transports:
    esphome_api:
      enabled: true        # server mode (optional; for linux-voice-assistant)
      port: 6053
      devices:             # client mode — dial these devices
        - host: 192.168.1.42
          port: 6053
          device_id: respeaker-xvf-1
          api_key: G_NAR9VvpTZyH2ihBZWGfGaDlDmhLSP2  # from step 1
```

Then restart the gateway. The dialer starts one `asyncio.Task` per
configured device, dials it with exponential backoff, and runs the
full ESPHome native-API client handshake on connect (HelloRequest →
HelloResponse → ConnectRequest → ConnectResponse →
SubscribeVoiceAssistantRequest). On any disconnect (device reboot,
WiFi flap), the dialer reconnects automatically.

---

## Step 6 — Compile + upload

```bash
cd /path/to/Respeaker-XVF3800-ESPHome-integration/config

# If ESPHome CLI is installed:
esphome compile aivg-respeaker.yaml
esphome upload aivg-respeaker.yaml

# Or use the ESPHome Builder web UI / Dashboard if you have HA installed
# locally (just point it at the YAML).
```

First compile takes 5-10 minutes (downloads esp-idf, the external
components, compiles micro_wake_word model, etc.).

---

## Step 7 — Boot + observe

1. After upload, the device reboots and connects to your WiFi.
2. Watch the gateway log: `tail -f ~/.hermes/logs/gateway.log`
3. You should see (if our direction model is correct):
   ```
   esphome: device_adopted device_id='respeaker-xvf-1'
   ```
4. Or — if the direction is REVERSED — you'll need to update step 5's
   guidance to make AIVG connect to the device, and we'd add a small
   "client mode" patch as a v1.0.1.

5. Confirm via `aivg list`:

   ```bash
   /Users/ys/.hermes/hermes-agent/venv/bin/aivg list
   ```

   You should see `respeaker-xvf-1` with `transport: esphome_api`,
   `status: online`.

6. Trigger a voice turn (wake-word "Hey Jarvis" or the device's
   configured wake-word, or press the device's central button if
   that's a manual-trigger build):

   - Say: "What time is it?"
   - Watch the gateway log for `session opened → transcribed → turn complete`
   - The device should play back the agent's reply through its speaker.

---

## What to do if it doesn't work

Most likely failure modes + their fixes:

| Symptom | Likely cause | Fix |
|---|---|---|
| Device boots but never appears in `aivg list` | Gateway not dialing the device | Verify the `devices:` entry in step 5 has the right LAN IP. Check `tail ~/.hermes/logs/gateway.log` for `esphome dialer:` lines — these show dial attempts + backoff |
| `esphome: auth_failed device_id='respeaker-xvf-1'` in gateway log | API key mismatch | Re-run step 1 and re-set `aivg_api_key` in secrets.yaml |
| Device connects but no voice pipeline starts on wake-word | `use_wake_word: false` + AIVG doesn't push wake events | Likely a v1.1 follow-up — device YAML may need `use_wake_word: true` to delegate |
| Transcript appears but no reply audio | TTS chain broken (or audioop ratecv stalled) | Check gateway log for `send_audio` lines + media_adapter resampling errors |
| Device disconnects after 30 s | ESPHome keepalive timeout | Verify `PingResponse` lines in gateway log; should be fine but signal if not |
