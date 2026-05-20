# `@aivg/sat-sdk`

> The official **TypeScript SDK** for the AIVG satellite contract — register,
> stream voice (WebRTC), get config pushes, surface agent telemetry,
> receive OTA notifications. Browser, Electron, Node. No native deps.

[![npm](https://img.shields.io/npm/v/@aivg/sat-sdk.svg)](https://www.npmjs.com/package/@aivg/sat-sdk)

## Install

```bash
npm install @aivg/sat-sdk
```

## 30-line example (browser, push-to-talk)

```ts
import { Satellite } from "@aivg/sat-sdk";

const sat = new Satellite({
  gatewayUrl: "http://localhost:8643",
  deviceId:   localStorage.getItem("devId") ?? crypto.randomUUID(),
  deviceName: "browser-ptt-demo",
  deviceType: "browser",
});
localStorage.setItem("devId", sat.options.deviceId);

sat.on("adoption",  (e) => console.log("adoption:", e.state));
sat.on("state",     (e) => console.log("state:", e.previous, "→", e.current));
sat.on("transcript",(d) => console.log(`${d.speaker}: ${d.text}`));
sat.on("error",     (e) => console.error("ERR", e.code, e.message));

await sat.connect();
document.querySelector("#ptt")!.addEventListener("mousedown", () => sat.beginSession());
document.querySelector("#ptt")!.addEventListener("mouseup",   () => sat.endSession());
```

Then run `aivg device adopt <device-id>` on the operator's machine and
you're live.

## Targets

| Runtime           | WebRTC                       | Audio sink                       |
|-------------------|------------------------------|----------------------------------|
| Browser           | `globalThis.RTCPeerConnection` (built-in) | managed `<audio>` element (default) |
| Electron renderer | same as browser              | same as browser                  |
| Electron main     | inject (e.g. `@roamhq/wrtc`) | consumer-provided                |
| Node 20+          | inject (e.g. `@roamhq/wrtc`) | consumer-provided                |

The SDK never bundles a WebRTC binary — Node users `npm install @roamhq/wrtc`
in their own project and pass it via `webrtcFactory:`. See
[contracts/webrtc-injection.md](../../specs/014-aivg-sat-sdk-ts/contracts/webrtc-injection.md).

## Architecture

The SDK is the satellite-side of the four-plane AIVG contract:

- **Control plane** — long-lived WebSocket against `/satellite/ws`
  (register, heartbeat, config, commands, logs, OTA)
- **Voice plane** — per-session `RTCPeerConnection` (offerer; full-gather
  then offer)
- **State machine** — `idle | listening | speaking | error`
- **Event surface** — typed `on(event, handler)` + async-iterator sugar

For the full spec → [spec.md](../../specs/014-aivg-sat-sdk-ts/spec.md).
For the API contract → [contracts/satellite-api.md](../../specs/014-aivg-sat-sdk-ts/contracts/satellite-api.md).
For the wire protocol → [contracts/wire-protocol.md](../../specs/014-aivg-sat-sdk-ts/contracts/wire-protocol.md).

## Development

```bash
npm install
npm run build       # tsup → dist/{index.mjs,index.cjs,index.d.ts}
npm test            # vitest run
npm run typecheck   # tsc --noEmit
npm run lint        # eslint
```

Live integration tests need a running AIVG gateway:

```bash
GATEWAY_URL=http://localhost:8643 npm test
```

## License

MIT
