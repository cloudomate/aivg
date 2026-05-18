# Phase 0 Research: Real WebRTC Media Transport

All decisions below are forced by feature 001's design contract,
`HermesV013Bridge`/`session.py` as they already exist, and the spec's
Assumptions. No open `NEEDS CLARIFICATION` remain.

## D1 — Inbound: Opus track → PCM the bridge expects

- **Decision**: aiortc gives the caller's audio as a `MediaStreamTrack`
  (kind `audio`); `await track.recv()` yields an `av.AudioFrame`. Reformat
  each frame to **signed 16-bit little-endian, mono, 48 000 Hz** via an
  `av.AudioResampler(format="s16", layout="mono", rate=48000)`, then run the
  bytes through `PcmFramer` to emit fixed **20 ms = 1920-byte** frames from
  `receive()`.
- **Rationale**: `HermesV013Bridge` writes STT WAVs at `sampwidth=2`,
  `nchannels=1`, `framerate=48000` and computes RMS/endpoint over s16 mono
  with `frame_seconds=0.02`. Matching exactly means **no transport-induced
  degradation** (SC-001) and the existing server-side endpointing fires on
  real audio unchanged (FR-001, US1 scenario 4). Opus on the wire is already
  48 kHz, so this is a format/layout conversion, not a quality-lossy
  resample.
- **Alternatives considered**: passing native frame sizes straight through
  (rejected — endpoint accounting assumes uniform 20 ms frames; jitter in
  frame size would skew the silence-duration math); converting to 16 kHz
  (rejected — bridge default is 48 kHz; changing it is out of scope and risks
  the unchanged-logic guarantee FR-008/FR-012).

## D2 — Outbound: Hermes TTS bytes → Opus track

- **Decision**: `send_audio(pcm)` receives whatever
  `HermesBridge.tts_synthesize` returned — raw provider file bytes of
  *unknown* container/codec/rate. Decode with `av.open(io.BytesIO(data))`,
  resample every decoded frame to 48 kHz mono s16, and enqueue onto a custom
  outbound `MediaStreamTrack` whose `recv()` paces 20 ms Opus frames to the
  peer (aiortc encodes Opus).
- **Rationale**: The spec Assumptions mandate "format reconciliation uses the
  media library already on the host"; `av` sniffs the container so we are
  robust to whichever provider Hermes is configured with (WAV/MP3/etc.) —
  satisfies FR-004 and the chipmunk/slow-motion edge case directly.
- **Alternatives considered**: assuming WAV/PCM and slicing manually
  (rejected — couples us to one TTS provider, violates constitution IV
  inheritance of Hermes's provider choice); SDP munging to negotiate a
  non-Opus codec (rejected — feature 001 contract pins Opus 48 kHz, "no SDP
  munging").

## D3 — Non-audio sentinels (empty reply / providers-unavailable)

- **Decision**: `send_audio` first guards: empty/very-short bytes or bytes
  that `av` cannot open as audio (e.g. the session's
  `b"__PROVIDERS_UNAVAILABLE__"` failure sentinel, or a fake-suite
  `b"AUDIO:"` marker) are logged and **dropped** — never raised.
- **Rationale**: Edge cases "agent reply empty/tool-only → no broken/zero-
  length audio" and "outbound send before ready → never an error that kills
  the session". Keeps the session loop alive and returning to listening.
- **Alternatives considered**: synthesizing a beep locally (rejected —
  constitution I forbids the transport generating audio content).

## D4 — Barge-in / `stop_playback()`

- **Decision**: The outbound track pulls from an `asyncio.Queue` of 20 ms
  frames. `stop_playback()` drains the queue and sets a "flushed" flag so
  the in-flight clip stops; the track keeps producing **silence** frames so
  RTP timing/sender stay healthy and the transport is immediately reusable
  for the next turn.
- **Rationale**: `session.py` already cancels the reply pipeline and calls
  `await self._transport.stop_playback()` within `BARGE_IN_DEADLINE_S` (0.3);
  draining a queue is O(1)-ish and well inside SC-004's 300 ms. Continuing
  silence (vs stopping the track) avoids a wedged transceiver for the next
  turn (FR-005, last edge case).
- **Alternatives considered**: closing/recreating the track per turn
  (rejected — renegotiation latency, risk of a wedged PC); stopping `recv()`
  entirely (rejected — aiortc sender expects continuous frames; gaps cause
  desync, fails SC-006).

## D5 — Connection state & teardown

- **Decision**: `connection_state` returns `pc.connectionState`
  (`"new"|"connecting"|"connected"|"disconnected"|"failed"|"closed"`).
  On a `connectionstatechange` to `failed`/`closed` (or inbound
  `recv()` raising `MediaStreamError`), `receive()` returns `None` so the
  `session.py` loop ends cleanly; `close()` stops both tracks and
  `await pc.close()`, is idempotent, and cancels any internal reader task —
  no orphaned media tasks (FR-006). A fresh `/webrtc/offer` builds a new
  `RTCPeerConnection`/session with no gateway restart.
- **Rationale**: `session.run()`'s `finally` already calls
  `transport.close()`; `SignalingService.drop()` cancels the task. We only
  need honest state mapping + None-on-end so existing teardown works
  unchanged.
- **Alternatives considered**: raising on drop (rejected — `session.py`
  treats `receive()==None` as the clean end signal; raising would hit the
  defensive `except` and log a crash).

## D6 — "No inbound audio track in the offer"

- **Decision**: After `setRemoteDescription`, if the offer negotiates no
  receivable audio track within a short bounded wait, `aiortc_transport_factory`
  raises a clear `RuntimeError` (surfaced by the signaling site as a failed
  offer) instead of returning a transport that would hang in `receive()`.
- **Rationale**: Edge case "no inbound audio track → fail clearly, not a
  hang"; FR-007 requires the offer to *succeed end-to-end* for a valid voice
  offer and fail loudly otherwise.

## D7 — Local testability boundary (constitution V)

- **Decision**: Extract the deterministic, media-stack-free logic — splitting
  an arbitrary PCM byte stream into uniform 20 ms frames, buffering partial
  remainders, and tail-padding with silence — into `media.py::PcmFramer`,
  unit-tested in `tests/unit/test_media_framer.py`. aiortc/av glue stays in
  `signaling.py` behind a lazy import and is proven by the host live spoken
  test.
- **Rationale**: Honest verification (constitution V): test what can be
  tested deterministically without the real stack; prove the rest on the
  host before relying on it. Keeps the fake-transport suite untouched
  (FR-012/SC-008) while still giving FR-004 real local coverage.
- **Alternatives considered**: mocking aiortc/av wholesale (rejected — a mock
  of the very thing under test proves nothing; would be theatre, not
  verification).

## D8 — Deploy/redeploy mechanism

- **Decision**: Reuse `deploy/deploy-to-hermes.sh` + `rollback.sh` from
  features 003/004 **unchanged**. Existing post-verify (constitution-I no
  embedded engines, plugin import/register, zero pre-existing-platform
  regression, both ports listening) remains the gate; media correctness is
  the live spoken test (US4), not a new automated deploy check.
- **Rationale**: Spec FR-009 / Assumptions explicitly forbid a new deploy
  mechanism and reuse the gated, backup-first, one-step-reversible path.
- **Alternatives considered**: adding an automated offer/answer media probe
  to post-verify (rejected — requires a real WebRTC peer with a mic on the
  host; that *is* US4's human-driven test, not a deploy script step).
