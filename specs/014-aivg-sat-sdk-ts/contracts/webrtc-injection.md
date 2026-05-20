# Contract — WebRTC dependency injection

**Feature**: 014-aivg-sat-sdk-ts · **Binds research decision R-1**.

The SDK never bundles a WebRTC implementation. Hosts that don't have one
built in (Node.js, headless workers) MUST provide one at construction time.

## `webrtcFactory` contract

```ts
type WebrtcFactory = () => RTCPeerConnection;
```

The factory is called once per `VoiceSession`. The returned instance MUST
conform to the W3C [`RTCPeerConnection` interface][rtc-spec] — specifically
the subset the SDK uses:

| Member                                | Used by                                           |
|---------------------------------------|---------------------------------------------------|
| `addTrack(track, ...streams)`         | `beginSession()` — to attach the mic track       |
| `addTransceiver(kind, init?)`         | `beginSession()` (for receive-only tracks)       |
| `createOffer(options?)`               | `beginSession()` — generate the SDP offer        |
| `setLocalDescription(desc)`           | `beginSession()` — apply the local SDP           |
| `setRemoteDescription(desc)`          | `beginSession()` — apply the answer              |
| `iceGatheringState`                   | `beginSession()` — wait for `"complete"`         |
| `iceConnectionState`                  | session lifecycle — listen for `"failed"`        |
| `connectionState`                     | session lifecycle — listen for `"connected"`     |
| `ontrack` (or `addEventListener("track")`) | hand the remote `MediaStream` to the audio sink |
| `onicegatheringstatechange`           | resolve the full-gather wait                     |
| `oniceconnectionstatechange`          | detect ICE failure                               |
| `onconnectionstatechange`             | detect transport failure                         |
| `close()`                             | `endSession()`                                   |
| `addEventListener("datachannel", …)`  | live UI events sub-channel (optional)            |

The SDK does NOT use:

- ICE restart
- SCTP data channels for durable traffic (constitution III)
- Renegotiation mid-session (each session is one offer/answer)
- DTLS fingerprint introspection
- `getStats()` (consumers can call it on the instance themselves)

## Reference factory (browser/Electron — default)

```ts
// sdks/typescript/src/webrtc/browser.ts
export const defaultWebrtcFactory: WebrtcFactory = () => {
  if (typeof globalThis.RTCPeerConnection !== "function") {
    throw new SdkError("no_webrtc_impl",
      "No RTCPeerConnection in this runtime — pass webrtcFactory to Satellite constructor");
  }
  return new globalThis.RTCPeerConnection({
    iceServers: [],   // LAN-only by default; consumer override via opts (post-v1)
  });
};
```

## Node.js usage (`@roamhq/wrtc`)

```ts
import wrtc from "@roamhq/wrtc";
import { Satellite } from "@aivg/sat-sdk";

const sat = new Satellite({
  // … other opts …
  webrtcFactory: () => new wrtc.RTCPeerConnection({ iceServers: [] }),
});
```

`@roamhq/wrtc` is a prebuilt Node binding that ships pre-compiled binaries
for the major platforms (no `node-gyp` step). The SDK does NOT list it as
a `peerDependency` (would force install-time resolution); it's a documented
optional dependency the consumer installs in their own project.

## Test-time fake

The SDK's own test suite (`tests/contract/`, `tests/unit/`) uses an
in-process fake factory that mirrors the relevant subset of
`RTCPeerConnection` and lets tests drive `connectionState` transitions
deterministically:

```ts
// tests/helpers/fake-webrtc.ts
export const fakeWebrtcFactory: WebrtcFactory = () => new FakePC();
```

The fake is NOT exported publicly. Third-party tests can build their own,
using the W3C spec as the binding contract.

## `audioSinkFactory` contract

```ts
export interface AudioSink {
  attach(stream: MediaStream): void;
  detach(): void;
}

type AudioSinkFactory = () => AudioSink;
```

The factory is called once per `VoiceSession`. `attach` is called when
the remote audio track arrives; `detach` is called on `endSession()`.

### Default browser sink

```ts
// sdks/typescript/src/webrtc/audio-sink.ts
export const defaultAudioSinkFactory: AudioSinkFactory = () => {
  if (typeof document === "undefined") {
    throw new SdkError("no_microphone_api",
      "No DOM — pass audioSinkFactory to Satellite constructor for Node");
  }
  const el = document.createElement("audio");
  el.autoplay = true;
  document.body.appendChild(el);
  return {
    attach: (stream) => { el.srcObject = stream; },
    detach: () => { el.srcObject = null; el.remove(); },
  };
};
```

### Node sink (consumer-provided)

For headless flows, the consumer typically attaches the stream to:

- A file writer (for CI smoke tests recording the assistant's audio).
- A pulseaudio / coreaudio sink (Linux/macOS).
- `/dev/null` (drop on the floor, just verify the protocol).

```ts
const sat = new Satellite({
  // …
  audioSinkFactory: () => ({
    attach: (stream) => {
      const writer = new WaveFileWriter("./assistant.wav");
      pipeStreamToWriter(stream, writer);  // consumer-defined
    },
    detach: () => { /* close writer */ },
  }),
});
```

## Microphone source override (post-v1)

For Node test environments that want to inject a pre-recorded PCM file
as the "microphone" source, the SDK exposes
`micSourceFactory?: () => Promise<MediaStreamTrack>` in the options.
Default factory calls `getUserMedia()`. NOT IN V1 (PTT only; consumers
who need this for CI write their own session orchestration); documented
here as the reserved extension point.

[rtc-spec]: https://w3c.github.io/webrtc-pc/#dom-rtcpeerconnection
