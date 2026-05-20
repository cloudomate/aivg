/**
 * Dependency-injection contracts for WebRTC + audio I/O.
 *
 * Binding doc: `specs/014-aivg-sat-sdk-ts/contracts/webrtc-injection.md`.
 *
 * The SDK NEVER bundles a WebRTC implementation (FR-024, SC-005).
 * Browser/Electron consumers get a built-in default; Node consumers pass
 * their own (typically `@roamhq/wrtc`) via `webrtcFactory:`.
 */

/** Factory that returns a fresh peer connection per `VoiceSession`. */
export type WebrtcFactory = () => RTCPeerConnection;

/**
 * Audio sink — attaches an inbound remote `MediaStream` to a host-
 * appropriate output. Default in browser/Electron is a managed `<audio>`
 * element; Node consumers supply a writer / pulseaudio sink / /dev/null.
 */
export interface AudioSink {
  attach(stream: MediaStream): void;
  detach(): void;
}

export type AudioSinkFactory = () => AudioSink;

/**
 * Reserved extension point for Node test environments that want to
 * inject a pre-recorded PCM file as the "microphone" source. NOT in v1
 * (push-to-talk only; consumers who need this for CI write their own
 * session orchestration). Declared here as the future hook so consumers
 * don't accidentally pick a name we'll want.
 */
export type MicSourceFactory = () => Promise<MediaStreamTrack>;
