// Minimal Electron renderer that imports @aivg/sat-sdk and prints state.
// The full Electron client refactor (US4) is the canonical Electron
// example — this file is just a starter skeleton.
import { Satellite } from "@aivg/sat-sdk";

const sat = new Satellite({
  gatewayUrl: "http://localhost:8643",
  deviceId: "electron-mini-example",
  deviceType: "electron",
});

sat.on("state", (e) => console.log("state:", e.previous, "→", e.current));
sat.on("adoption", (e) => console.log("adoption:", e.state));
sat.on("transcript", (d) => console.log(`${d.speaker}:`, d.text));

sat.connect().then(
  () => console.log("connected"),
  (e) => console.error("connect failed", e),
);

window.beginSession = () => sat.beginSession();
window.endSession = () => sat.endSession();
