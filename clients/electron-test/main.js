// Minimal Electron host for the satellite-#3 test client.
// Connects to the deployed adapter via SSH-forwarded localhost ports.
// Constitution I: this process does NO STT/TTS/agent — only window + mic perms.
const { app, BrowserWindow, session } = require("electron");
const path = require("path");

function createWindow() {
  const win = new BrowserWindow({
    width: 520,
    height: 560,
    title: "Hermes Satellite Test",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      // Keep the always-listening pipeline + control WS off the throttler.
      backgroundThrottling: false,
      contextIsolation: true,
    },
  });

  // Auto-grant mic to our own renderer only (FR-007). Denials are surfaced
  // in-renderer with the OS settings path.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, cb) => {
    cb(permission === "media");
  });

  win.loadFile("renderer.html");
  // Auto-open DevTools so the operator sees any renderer-side JS error
  // immediately. Comment out for non-dev builds.
  win.webContents.openDevTools({ mode: "right" });
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => app.quit());
