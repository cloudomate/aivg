/* Living integration test for @aivg/sat-sdk (feature 014 / US4).
 *
 * PTT model: long-lived voice session, toggle the mic track on
 * press/release. Tearing down the PC on every mouseup races the
 * gateway-side silence detector (~3 s window) and means STT never
 * runs. Mirrors the legacy electron-test's pattern. */
import { Satellite } from "@aivg/sat-sdk";

const $ = (id) => document.getElementById(id);
const log = (m) => ($("log").textContent += m + "\n", $("log").scrollTop = 1e9);

const DEVICE_ID = "electron-test-1";
let sat = null;
let eosAt = 0;

function start() {
  sat = new Satellite({
    gatewayUrl: $("mgmt").value,
    deviceId: DEVICE_ID, deviceName: DEVICE_ID,
    deviceType: "electron", firmwareVersion: "0.2.0",
  });
  sat.on("adoption", (e) => {
    log(`adoption: ${e.state}${e.firstApproval ? " ✓" : ""}`);
    if (e.state === "adopted" && !sat._sessionStarting) {
      // Open the voice session ONCE on first adoption. PTT will mute/unmute
      // the mic track inside this long-lived session.
      sat._sessionStarting = true;
      sat.mute(); // start muted — mic only goes live during PTT press
      sat.beginSession().then(
        () => { log(`voice session ready; press & hold PTT to talk`); $("ptt").disabled = false; },
        (err) => log(`beginSession failed: ${err.code ?? "?"}: ${err.message}`),
      );
    }
  });
  sat.on("state", (e) => {
    $("state").textContent = e.current;
    if (e.previous === "listening" && e.current === "speaking" && eosAt) {
      $("lat").textContent = Math.round(performance.now() - eosAt); eosAt = 0;
    }
  });
  sat.on("gateway_state", (g) => log(`gw: ${g.state}`));
  sat.on("transcript", (d) =>
    $(d.speaker === "user" ? "tx" : "rep").textContent = d.text);
  sat.on("log", (e) => log(`[${e.level}] ${e.source}: ${e.message}`));
  sat.on("error", (e) => log(`! ${e.code}: ${e.message}`));
  sat.on("transient_error", (e) => log(`~ ${e.code}: ${e.message}`));
  sat.on("session_ended", (r) => { log(`session ended: ${r.reason}`); sat._sessionStarting = false; });
  sat.on("barge_in", () => log("barge-in"));
  sat.connect().then(
    () => log(`connected — run: aivg device adopt ${DEVICE_ID}`),
    (err) => log(`connect failed: ${err.code ?? "?"}: ${err.message}`),
  );
}

$("connect").onclick = start;
// PTT toggles the mic track inside the long-lived voice session.
// Mark end-of-speech on release for latency measurement.
$("ptt").onmousedown = () => { sat?.unmute(); $("state").textContent = "listening (PTT)"; };
$("ptt").onmouseup = () => { sat?.mute(); eosAt = performance.now(); $("state").textContent = "thinking"; };
$("ptt").onmouseleave = () => { if (sat?.isMicLive) { sat.mute(); eosAt = performance.now(); } };
$("stats").onclick = () => log(sat
  ? `state=${sat.state} adopted=${sat.isAdopted} mic=${sat.isMicLive ? "live" : "muted"}`
  : "not connected");
