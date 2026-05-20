# Quickstart — `@aivg/sat-sdk`

**Feature**: 014-aivg-sat-sdk-ts · **Date**: 2026-05-20

Three runnable flows: browser PTT, Electron, and headless Node. All
three target a locally-installed AIVG gateway (the one this repo's
`aivg setup` brings up). Same `Satellite` class, same events.

---

## Prerequisites

1. **AIVG gateway running**. From this repo:
   ```bash
   PYTHONPATH=src python -m aivg_cli.cli setup --yes        # one-time, feature 013
   hermes gateway run > /tmp/hermes-gateway.log 2>&1 &      # start the gateway
   curl -s http://localhost:8643/satellite/list             # confirm it answers
   ```
   See [specs/013-aivg-setup-cli/quickstart.md](../013-aivg-setup-cli/quickstart.md).
2. **Node 20+** for any of the JS flows.
3. **`@aivg/sat-sdk`** built locally during feature 014:
   ```bash
   cd sdks/typescript
   npm install
   npm run build         # produces dist/{index.mjs,index.cjs,index.d.ts}
   npm link              # makes the package linkable into consumers
   ```

---

## Flow 1 — Browser PTT (30 LoC) — the SC-001 reference

`sdks/typescript/examples/browser-ptt/index.html`:

```html
<!doctype html>
<html>
<body>
  <button id="ptt">Hold to talk</button>
  <pre id="log"></pre>
  <script type="module">
    import { Satellite } from "https://localhost:5173/@aivg/sat-sdk/dist/index.mjs";

    const sat = new Satellite({
      gatewayUrl: "http://localhost:8643",
      deviceId:   localStorage.getItem("devId") ?? crypto.randomUUID(),
      deviceName: "browser-ptt-demo",
      deviceType: "browser",
    });
    localStorage.setItem("devId", sat.options.deviceId);

    sat.on("adoption", (e) => log(`adoption: ${e.state}`));
    sat.on("state",     (e) => log(`state: ${e.previous} → ${e.current}`));
    sat.on("transcript",(d) => log(`${d.speaker}: ${d.text}`));
    sat.on("error",     (e) => log(`ERROR ${e.code}: ${e.message}`));

    await sat.connect();
    const btn = document.getElementById("ptt");
    btn.onmousedown  = () => sat.beginSession();
    btn.onmouseup    = () => sat.endSession();
    function log(s) { document.getElementById("log").textContent += s + "\n"; }
  </script>
</body>
</html>
```

**Adopt the device** (one-time, on the operator's machine):

```bash
aivg list                                          # find the device id
aivg device adopt <device-id>
```

You're now under 50 LoC of application code (excluding HTML markup —
matches SC-001).

---

## Flow 2 — Electron (existing test client, refactored)

The existing `clients/electron-test/` is the canonical Electron
example. After feature 014 lands, its `renderer.js` shrinks ≥ 30 %
(SC-009) because all the WebRTC + WebSocket protocol code moves
into the SDK. Operator workflow is unchanged: `npm start` in
`clients/electron-test/`, then `aivg device adopt <id>`.

Refactored skeleton (`renderer.js` after feature 014):

```js
import { Satellite } from "@aivg/sat-sdk";

const sat = new Satellite({
  gatewayUrl: document.getElementById("mgmt").value,
  deviceId:   "electron-test-1",
  deviceName: "electron-test-1",
  deviceType: "electron",
});

const log = (msg) => (document.getElementById("log").textContent += msg + "\n");
sat.on("state",      (e) => log(`state: ${e.previous} → ${e.current}`));
sat.on("transcript", (d) => log(`${d.speaker}: ${d.text}`));
sat.on("log",        (e) => log(`[${e.level}] ${e.source}: ${e.message}`));
sat.on("error",      (e) => log(`! ${e.code}: ${e.message}`));

document.getElementById("connect").onclick = () => sat.connect();
document.getElementById("ptt-start").onmousedown = () => sat.beginSession();
document.getElementById("ptt-end").onmouseup     = () => sat.endSession();
```

That's the entire protocol-level body of the test client after the
refactor — every direct `new RTCPeerConnection`, `new WebSocket`,
`fetch("/webrtc/offer")`, `getUserMedia` call disappears.

---

## Flow 3 — Headless Node smoke test

`sdks/typescript/examples/node-headless/smoke.ts`:

```ts
import wrtc from "@roamhq/wrtc";                       // consumer-installed
import { Satellite } from "@aivg/sat-sdk";
import { readFileSync } from "node:fs";

const sat = new Satellite({
  gatewayUrl: process.env.GATEWAY_URL!,                // e.g. http://localhost:8643
  deviceId:   "ci-smoke-node",
  deviceType: "node",
  webrtcFactory: () => new wrtc.RTCPeerConnection(),   // R-1 DI hole
  audioSinkFactory: () => ({
    attach: (stream) => { /* in CI we drop the audio on the floor */ },
    detach: () => {},
  }),
});

await sat.connect();

const transcripts: string[] = [];
sat.on("transcript", (d) => { if (d.speaker === "assistant") transcripts.push(d.text); });

await sat.beginSession();
// (in a real test you'd inject a pre-recorded PCM via a custom audio source —
// see tests/integration/node-live.spec.ts for the full setup)
await new Promise((r) => setTimeout(r, 8000));
await sat.endSession();
await sat.disconnect();

console.log("agent reply:", transcripts.join(""));
process.exit(transcripts.length ? 0 : 1);
```

Run:

```bash
GATEWAY_URL=http://localhost:8643 \
  npx tsx sdks/typescript/examples/node-headless/smoke.ts
```

---

## What the SDK does for you

| You write                  | SDK does                                                     |
|----------------------------|--------------------------------------------------------------|
| `new Satellite(opts)`      | nothing yet — pure construction                              |
| `await sat.connect()`      | opens WS, sends `register`, starts heartbeat loop            |
| `await sat.beginSession()` | requests mic, builds PC, ICE gather, POST `/webrtc/offer`, applies answer |
| `sat.on("transcript", …)`  | subscribes to streaming agent text deltas over WS            |
| `sat.on("config_changed", …)` | subscribes to operator-pushed config updates              |
| `await sat.endSession()`   | closes PC, releases mic tracks, returns to `idle`            |
| `await sat.disconnect()`   | closes WS, cancels heartbeat                                 |

## Where to go next

- **API surface (full)** → [contracts/satellite-api.md](contracts/satellite-api.md)
- **WebRTC DI contract** → [contracts/webrtc-injection.md](contracts/webrtc-injection.md)
- **Wire shapes the SDK consumes** → [contracts/wire-protocol.md](contracts/wire-protocol.md)
- **Type reference** → [data-model.md](data-model.md)
- **All ADRs** → [research.md](research.md) (R-1 … R-14)
