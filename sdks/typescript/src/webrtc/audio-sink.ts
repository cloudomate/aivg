// Stub — real defaultAudioSinkFactory lands in T026 (Phase 3 / US1).
import { sdkError } from "../errors";
import type { AudioSink, AudioSinkFactory } from "./injectable";

export const defaultAudioSinkFactory: AudioSinkFactory = () => {
  // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
  if (typeof document === "undefined") {
    throw sdkError(
      "no_microphone_api",
      "No DOM — pass audioSinkFactory to Satellite constructor for Node",
    );
  }
  const el = document.createElement("audio");
  el.autoplay = true;
  document.body.appendChild(el);
  const sink: AudioSink = {
    attach(stream: MediaStream): void {
      el.srcObject = stream;
    },
    detach(): void {
      el.srcObject = null;
      el.remove();
    },
  };
  return sink;
};
