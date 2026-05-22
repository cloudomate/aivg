# libaivg-sat — API reference & RPi (PipeWire + seeed) integration

`libaivg-sat` is a thin C++17 satellite-client SDK for AIVG. It owns the
**protocol** (control plane + WebRTC voice plane); **you own the audio
hardware**. On a Raspberry Pi the natural way to drive the SDK's audio
callbacks is **PipeWire** capturing/playing the **seeed ReSpeaker** HAT.

> Contract: PCM16 **mono @ 48 kHz** at the callback boundary. The SDK does
> Opus encode/decode and DTLS-SRTP internally (Constitution Principle I —
> no STT/TTS/agent in the SDK). The gateway and wire contract are unchanged.

---

## 1. Public API

All headers are under `#include <aivg/sat/...>`; everything is in namespace
`aivg::sat`.

### `SatelliteOptions` — `<aivg/sat/satellite.hpp>`

| Field | Type | Meaning |
|-------|------|---------|
| `gateway_url` | `std::string` | Management base, e.g. `ws://gw:8643` (control WS). |
| `signaling_url` | `std::optional<std::string>` | Voice-plane base, e.g. `http://gw:8644`. Derived from `gateway_url` if unset. |
| `device_id` | `std::string` | Stable unique id. |
| `device_name` / `device_type` / `firmware_version` | `std::string` | Identity sent at register. |
| `reconnect` | `ReconnectPolicy` | `{base_delay_ms, max_delay_ms, jitter}` (exp backoff + jitter). |
| `timeouts` | `Timeouts` | `{ice_gather_ms, media_first_audio_ms, signaling_ms}`. |
| `audio_input` | `AudioInputCallback` | You fill PCM16 mono frames (mic). |
| `audio_output` | `AudioOutputCallback` | You consume PCM16 mono frames (speaker). |
| `on_event` | `EventHandler` | Receives `SatEvent`. |

### Callbacks — `<aivg/sat/audio.hpp>`

```cpp
// Fill up to `frames` PCM16 mono samples; return how many you produced.
// Return 0 only to end the stream — a live satellite streams continuously
// (silence when idle) so the gateway VAD can endpoint utterances.
using AudioInputCallback  = std::function<std::size_t(int16_t* buf, std::size_t frames)>;

// Consume exactly `frames` PCM16 mono reply samples for playback.
using AudioOutputCallback = std::function<void(const int16_t* buf, std::size_t frames)>;
```

### `Satellite` — `<aivg/sat/satellite.hpp>`

```cpp
aivg::sat::Satellite sat(std::move(options));
sat.connect().get();        // control WS + register + heartbeat (auto-reconnect)
// wait for adoption (operator runs `aivg device adopt`, or auto-adopt):
while (!sat.isAdopted()) { /* sleep */ }
sat.beginSession().get();   // WebRTC offer/answer + DTLS-SRTP, media starts
sat.unmute();               // PTT: open the mic
// ... speak; sat.isMicLive() == true ...
sat.mute();                 // PTT release (does NOT tear down the PeerConnection)
sat.endSession().get();     // close the voice plane; control WS stays up
sat.disconnect().get();
```

`SatelliteState state()` → `Idle | Listening | Speaking | Error`.
`bool isAdopted()`, `bool isMicLive()`.

### Events — `<aivg/sat/events.hpp>`

`on_event` receives a `SatEvent` (`std::variant`). Match with `std::get_if`:

```cpp
opts.on_event = [](const aivg::sat::SatEvent& ev) {
  using namespace aivg::sat;
  if (auto* a = std::get_if<AdoptionEvent>(&ev))      /* a->previous -> a->current */;
  else if (auto* g = std::get_if<GatewayStatePayload>(&ev)) /* idle/listening/thinking/speaking */;
  else if (auto* t = std::get_if<TranscriptDelta>(&ev))     /* t->text, t->is_final */;
  else if (auto* e = std::get_if<SatError>(&ev))            /* e->code, e->message */;
};
```

Full set (mirrors `@aivg/sat-sdk`): `state`, `gateway_state`, `adoption`,
`config_changed`, `command`, `log`, `ota_manifest`, `ota_progress`,
`transcript`, `tool_call`, `skill`, `barge_in`, `remote_stream`,
`session_started`, `session_ended`, `error`, `transient_error`.

Errors (`<aivg/sat/errors.hpp>`) carry a stable code string
(`ice_failed`, `signaling_failed`, `not_adopted`, …).

---

## 2. Supported boards (Linux tier)

All are aarch64 Linux running PipeWire (Raspberry Pi OS Bookworm/Trixie);
the **same SDK + same integration code** runs on each — only headroom and
the HAT model differ.

| Board | CPU / RAM | Notes |
|-------|-----------|-------|
| **RPi Zero 2 W** | 4×A53 @1 GHz / 512 MB | The constrained floor. WebRTC + Opus + DTLS-SRTP fit; keep other load light. |
| **RPi 3B / 3B+** | 4×A53 @1.2 GHz / 1 GB | Comfortable. |
| **RPi 5** | 4×A76 @2.4 GHz / 4–8 GB | Ample; lowest latency. |

Audio HAT: **seeed ReSpeaker 2-Mic / 4-Mic** (`seeed-voicecard`). The HAT's
mic is often native 16 kHz — PipeWire resamples to the SDK's 48 kHz mono.

---

## 3. Audio: seeed ReSpeaker via PipeWire

1. Install the HAT driver (seeed-voicecard overlay) so it appears as an
   ALSA card; PipeWire auto-wraps ALSA devices as nodes.
2. Confirm the nodes:
   ```bash
   pw-cli ls Node | grep -iE "seeed|respeaker|capture|playback"
   wpctl status            # find the seeed source/sink ids
   ```
3. Either set the seeed nodes as the PipeWire **default** source/sink
   (`wpctl set-default <id>`), or target them explicitly in the app via the
   `PIPEWIRE_NODE` env / a `target.object` stream property.

The SDK never touches ALSA/PipeWire — it only sees the PCM you hand it.

---

## 4. Example: PipeWire + openWakeWord satellite

A complete, buildable reference lives in
[`examples/rpi_pipewire/`](../examples/rpi_pipewire/) (compiles against
libpipewire-0.3). Shape:

- Two `pw_stream`s on a `pw_thread_loop`: a **capture** stream (seeed mic →
  `mic_ring`) and a **playback** stream (`spk_ring` → speaker), both
  S16/mono/48000.
- `audio_input` drains `mic_ring` (returns silence when empty — keep
  streaming!); `audio_output` fills `spk_ring`.
- **openWakeWord** runs on the capture frames and *gates* the upstream:
  the voice session is long-lived, mic muted by default; on wake → `unmute()`;
  when the gateway finishes (`gateway_state` → `idle`) → `mute()`.

```cpp
// --- wiring the SDK to PipeWire ring buffers (see examples/rpi_pipewire/main.cpp) ---
opts.audio_input = [&](int16_t* buf, std::size_t frames) -> std::size_t {
  std::size_t got = mic_ring.read(buf, frames);     // PipeWire capture fills mic_ring
  if (got < frames) std::memset(buf + got, 0, (frames - got) * 2);  // pad w/ silence
  return frames;                                    // always stream (silence when idle)
};
opts.audio_output = [&](const int16_t* buf, std::size_t frames) {
  spk_ring.write(buf, frames);                      // PipeWire playback drains spk_ring
};
```

> **Why always return `frames` (silence when idle)?** The gateway runs
> server-side VAD/endpointing; it needs a continuous stream to detect the
> speech→silence transition that ends an utterance. A satellite that stops
> sending when idle never gets endpointed. (This is exactly what the WAV
> smoke learned — see `docs`/`research.md` R10.)

### Build

```cmake
# examples/rpi_pipewire/CMakeLists.txt links the SDK + libpipewire
find_package(PkgConfig REQUIRED)
pkg_check_modules(PIPEWIRE REQUIRED libpipewire-0.3)
target_link_libraries(rpi_pipewire PRIVATE aivg::sat ${PIPEWIRE_LIBRARIES})
```

```bash
# On the Pi (or cross-built — see rpi-builder/):
cmake -B build -DAIVG_SAT_BUILD_EXAMPLES=ON -DAIVG_SAT_ENABLE_VOICE=ON \
      -DAIVG_SAT_LIBPEER_ROOT=/path/to/libpeer
cmake --build build
./build/examples/rpi_pipewire/rpi_pipewire ws://<gw>:8643 http://<gw>:8644 rpi-livingroom
```

### openWakeWord gating

Constitution Principle I lets a device wake word **gate** the upstream
(save bandwidth / privacy) while the **gateway still owns endpointing/STT**.
The example wires this as:

```text
seeed mic --PipeWire--> capture frames --> openWakeWord (16 kHz)
                                       \--> mic_ring (only streamed when unmuted)
  on wake: sat.unmute()  →  stream the utterance
  gateway_state == "idle" (turn done)  →  sat.mute()
```

The voice session is **long-lived** (one `beginSession()`); the wake word
only toggles `unmute()/mute()` (FR-010 — never tear the PeerConnection down
per activation).

**Plugging in real openWakeWord** (the example ships a placeholder energy
gate in `WakeWordDetector::detect()`):

1. Add `onnxruntime` and the three openWakeWord ONNX models
   (`melspectrogram`, `embedding`, and your `<wakeword>.onnx`).
2. Downsample the 48 kHz capture frames to **16 kHz mono** (openWakeWord's
   rate) — e.g. via `libsamplerate` or `audioop`-style decimation.
3. Run melspectrogram → embedding → wakeword; return `true` when the score
   crosses your threshold (≈0.5), with a short refractory period.

openWakeWord is Apache-2.0; its prebuilt models are downloadable. Models +
the runner belong in the **device app** (this example / `aivg-devices`),
never in the SDK.

### Run / verify

Say the wake word, speak, then stop; the reply plays out the HAT speaker.
A real turn (whisper STT + agent + TTS) can take **30 s+** on a CPU-only
gateway — the SDK streams continuously and surfaces `gateway_state`
(`listening → thinking → speaking`) and `transcript` events meanwhile.

---

## 5. Notes / caveats

- **libpeer patch required**: the voice plane needs libpeer built with the
  offerer→DTLS-client patch (`rpi-builder/patches/0001-offerer-dtls-client.patch`),
  otherwise the DTLS-SRTP handshake fails against aiortc. See `research.md` R10.
- **Latency**: server STT + model + TTS dominate (tens of seconds on
  CPU-only hosts); the SDK transport adds little.
- Production device firmware/rigs live in the companion repo
  [`cloudomate/aivg-devices`](https://github.com/cloudomate/aivg-devices);
  this example is the SDK's reference integration (the role `electron-test`
  plays for `@aivg/sat-sdk`).
