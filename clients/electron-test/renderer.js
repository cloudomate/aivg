/* Satellite #3 test client (design §5). Two connections (constitution III):
 *  - always-on control WS  (register/heartbeat)
 *  - per-call RTCPeerConnection, client = offerer, FULL ICE GATHER → offer
 * Chromium AEC3 handles local echo (browser_aec3). No STT/TTS/agent here. */
const $ = (id) => document.getElementById(id);
const log = (m) => { $("log").textContent += m + "\n"; $("log").scrollTop = 1e9; };
const setState = (s) => ($("state").textContent = s);

const DEVICE_ID = "electron-test-1";
let pc, ws, micStream, speaking = false, eosAt = 0;

async function fullGatherOffer(pc) {
  await pc.setLocalDescription(await pc.createOffer());
  if (pc.iceGatheringState === "complete") return pc.localDescription;
  return new Promise((res) => {
    const chk = () => { if (pc.iceGatheringState === "complete") {
      pc.removeEventListener("icegatheringstatechange", chk); res(pc.localDescription); } };
    pc.addEventListener("icegatheringstatechange", chk);
  });
}

async function connect() {
  const mgmt = $("mgmt").value, webrtc = $("webrtc").value, wsUrl = $("ws").value;

  // 1) Control plane (always-on, independent of any call).
  ws = new WebSocket(wsUrl);
  ws.onopen = () => { ws.send(JSON.stringify({ type: "register",
    device_id: DEVICE_ID, device_type: "browser", firmware_version: "0.1.0" }));
    log("control WS open; registered"); };
  ws.onmessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch { return; }
    if (m.type === "state") setState(m.state);
    else if (m.type === "partial_transcript") $("tx").textContent = m.text;
    else if (m.type === "barge_in") log("server: barge-in");
  };
  ws.onclose = () => log("control WS closed (will need reconnect)");
  setInterval(() => ws?.readyState === 1 &&
    ws.send(JSON.stringify({ type: "heartbeat", device_id: DEVICE_ID })), 30000);

  // 2) Mic (Chromium AEC/NS/AGC ON — handles echo on-device).
  try {
    micStream = await navigator.mediaDevices.getUserMedia({ audio: {
      echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      channelCount: 1, sampleRate: 48000 } });
  } catch (err) {
    log("MIC DENIED: " + err +
      "\n→ macOS: System Settings ▸ Privacy & Security ▸ Microphone. Test cannot pass without mic.");
    return;
  }

  // 3) Voice PC — client is the offerer.
  pc = new RTCPeerConnection();
  micStream.getTracks().forEach((t) => { t.enabled = false; pc.addTrack(t, micStream); });
  pc.ontrack = (ev) => {
    $("far").srcObject = ev.streams[0];
    ev.track.onunmute = () => { if (eosAt) {
      $("lat").textContent = Math.round(performance.now() - eosAt); eosAt = 0; } };
  };
  const offer = await fullGatherOffer(pc);
  const r = await fetch(webrtc + "/webrtc/offer", { method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ sdp: offer.sdp, type: "offer", device_id: DEVICE_ID }) });
  const ans = await r.json();
  await pc.setRemoteDescription(ans);
  log("WebRTC connected (offer full-gathered, answer applied)");
  $("ptt").disabled = false;
}

// Push-to-talk (v1, no wake word). Releasing marks end-of-speech for latency.
function talk(on) {
  if (!micStream) return;
  speaking = on;
  micStream.getAudioTracks().forEach((t) => (t.enabled = on));
  if (on) { setState("listening (PTT)"); }
  else { eosAt = performance.now(); setState("thinking"); }
}
$("connect").onclick = () => connect().catch((e) => log("ERR " + e));
const ptt = $("ptt");
ptt.onmousedown = () => talk(true);
ptt.onmouseup = () => talk(false);
ptt.onmouseleave = () => speaking && talk(false);
