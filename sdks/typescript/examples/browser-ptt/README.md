# Browser PTT demo

Push-to-talk against a local AIVG gateway. Reference for SC-001
(< 50 LoC consumer code).

## Run

```bash
# 1. Build the SDK once (from sdks/typescript/)
npm run build

# 2. Serve this directory with any static server (one of):
npx http-server -p 5173 .
#   OR: python -m http.server 5173

# 3. Open in a browser:
open http://localhost:5173/examples/browser-ptt/

# 4. On the operator's machine (where the gateway runs):
aivg list           # find the device id assigned to the browser
aivg device adopt <id>
```

Hold the "▼ Hold to talk" button, speak, release. The agent's reply
streams back through the page's audio output.
