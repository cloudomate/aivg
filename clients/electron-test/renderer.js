/* Living integration test for @aivg/sat-sdk (feature 014 / US4).
 * Two-connections invariant + Chromium AEC3 + full-gather ICE live
 * in the SDK now. This file is the SDK's first consumer (SC-002). */
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
    // Belt-and-suspenders: the button is also enabled on connect()
    // resolve below, but the first adoption event is the strictly-stronger
    // signal that the gateway has us registered.
    if (e.state === "adopted") $("ptt").disabled = false;
  });
  sat.on("state", (e) => {
    $("state").textContent = e.current;
    if (e.previous === "listening" && e.current === "speaking" && eosAt) {
      $("lat").textContent = Math.round(performance.now() - eosAt); eosAt = 0;
    }
  });
  sat.on("transcript", (d) =>
    $(d.speaker === "user" ? "tx" : "rep").textContent = d.text);
  sat.on("log", (e) => log(`[${e.level}] ${e.source}: ${e.message}`));
  sat.on("error", (e) => log(`! ${e.code}: ${e.message}`));
  sat.on("transient_error", (e) => log(`~ ${e.code}: ${e.message}`));
  sat.on("session_ended", (r) => log(`session ended: ${r.reason}`));
  sat.connect().then(
    () => { log(`connected — adopt with: aivg device adopt ${DEVICE_ID}`); $("ptt").disabled = false; },
    (err) => log(`connect failed: ${err.code ?? "?"}: ${err.message}`),
  );
}

$("connect").onclick = start;
$("ptt").onmousedown = () => { $("state").textContent = "listening (PTT)"; sat?.beginSession().catch((e) => log(`begin: ${e.code}: ${e.message}`)); };
$("ptt").onmouseup = () => { eosAt = performance.now(); $("state").textContent = "thinking"; sat?.endSession(); };
$("ptt").onmouseleave = () => { if (sat?.state === "listening") { eosAt = performance.now(); sat.endSession(); } };
$("stats").onclick = () => log(sat ? `state=${sat.state} adopted=${sat.isAdopted}` : "not connected");
