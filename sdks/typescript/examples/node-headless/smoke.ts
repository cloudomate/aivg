/**
 * Headless Node smoke test — registers, makes one voice call, prints
 * the assistant's transcript. Used as the CI smoke against a live
 * AIVG gateway when GATEWAY_URL is set.
 *
 * Pre-requisites in your own project:
 *   npm install @aivg/sat-sdk @roamhq/wrtc
 *
 * Run:
 *   GATEWAY_URL=http://localhost:8643 npx tsx smoke.ts
 */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
import type { Satellite as _SatelliteType } from "../../src/index";
import { Satellite } from "../../src/index";

const GATEWAY = process.env.GATEWAY_URL;
if (!GATEWAY) {
  // eslint-disable-next-line no-console
  console.error("GATEWAY_URL env var required");
  process.exit(2);
}

// `@roamhq/wrtc` is the consumer's choice — declared here as a dynamic
// import so the smoke script itself works without it (will error at
// session start if it's not installed in the consumer's project).
async function main(): Promise<void> {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let wrtc: any = null;
  try {
    // eslint-disable-next-line @typescript-eslint/no-unsafe-assignment
    wrtc = await import("@roamhq/wrtc" as string);
  } catch {
    // eslint-disable-next-line no-console
    console.error("`@roamhq/wrtc` is required for the Node smoke. Run:");
    // eslint-disable-next-line no-console
    console.error("  npm install @roamhq/wrtc");
    process.exit(2);
  }

  const transcripts: string[] = [];
  const sat = new Satellite({
    gatewayUrl: GATEWAY!,
    deviceId: "ci-smoke-node",
    deviceName: "ci-smoke-node",
    deviceType: "node",
    // eslint-disable-next-line @typescript-eslint/no-unsafe-call, @typescript-eslint/no-unsafe-member-access
    webrtcFactory: () => new wrtc.RTCPeerConnection({ iceServers: [] }) as RTCPeerConnection,
    audioSinkFactory: () => ({
      attach: () => {
        // In CI we drop the audio on the floor. A real Node client would
        // pipe to a file writer or pulseaudio sink here.
      },
      detach: () => {},
    }),
  });

  sat.on("transcript", (d) => {
    if (d.speaker === "assistant") transcripts.push(d.text);
  });
  sat.on("error", (e) => {
    // eslint-disable-next-line no-console
    console.error("error", e.code, e.message);
  });

  await sat.connect();
  // Wait for adoption — in CI, we expect this to be done out-of-band
  // (a pre-step `aivg device adopt ci-smoke-node`).
  for (let i = 0; i < 60 && !sat.isAdopted; i++) {
    await new Promise((r) => setTimeout(r, 500));
  }
  if (!sat.isAdopted) {
    // eslint-disable-next-line no-console
    console.error("device not adopted after 30 s");
    process.exit(3);
  }

  await sat.beginSession();
  // No mic in Node by default — the test relies on the gateway
  // generating SOMETHING the SDK can transcribe. For a real test
  // you'd inject a MicSourceFactory (post-v1, R-9 follow-up).
  await new Promise((r) => setTimeout(r, 10_000));
  await sat.endSession();
  await sat.disconnect();

  // eslint-disable-next-line no-console
  console.log("assistant reply:", transcripts.join(""));
  process.exit(transcripts.length > 0 ? 0 : 1);
}

main().catch((e: unknown) => {
  // eslint-disable-next-line no-console
  console.error(e);
  process.exit(99);
});
