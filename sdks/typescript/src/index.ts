/**
 * `@aivg/sat-sdk` — TypeScript SDK for the AIVG satellite contract.
 *
 * Public surface binding doc:
 *   specs/014-aivg-sat-sdk-ts/contracts/satellite-api.md
 *
 * Phase 2 ships type-only foundations. The `Satellite` class (Phase 3
 * = US1) is the runtime entrypoint and lands in `src/satellite.ts`.
 */

// Version constants
export { CONTRACT_VERSION, SDK_VERSION } from "./proto/version";

// Closed-set error codes + class
export { SdkError, sdkError, isSdkError } from "./errors";
export type { SdkErrorCode, TransientErrorCode, TransientError } from "./errors";

// Lifecycle state machine
export type { SatelliteState } from "./state";

// Typed event surface
export type {
  SatelliteEvents,
  StateChangePayload,
  AdoptionEvent,
  SatelliteConfig,
  CommandEvent,
  CommandResult,
  LogEntry,
  OtaManifest,
  OtaProgress,
  TranscriptDelta,
  ToolCallEvent,
  SkillEvent,
  RemoteStreamEvent,
  VoiceSession,
  VoiceSessionResult,
} from "./events";

// WebRTC DI contracts
export type {
  WebrtcFactory,
  AudioSink,
  AudioSinkFactory,
  MicSourceFactory,
} from "./webrtc/injectable";

// US1 entrypoints — the runtime surface.
export { Satellite } from "./satellite";
export type { SatelliteOptions, ReconnectPolicy } from "./satellite";
export { defaultWebrtcFactory } from "./webrtc/browser";
export { defaultAudioSinkFactory } from "./webrtc/audio-sink";
