# Contract: Real `MediaTransport` Realisation (`AiortcTransport`)

**Status**: authoritative for feature 005.
**Interface owner**: feature 001 — `session.MediaTransport` Protocol.
**This feature**: provides a real backer; the Protocol itself is **unchanged**.

The realisation MUST be substitutable for `FakeTransport` with **zero** change
to `session.py`, `hermes_bridge.py`, the signaling/control wiring, or the
fake-transport test suite (FR-003/FR-008/FR-012).

## Interface (unchanged — restated for the conformance target)

```python
class MediaTransport(Protocol):
    async def receive(self) -> Optional[bytes]: ...      # next inbound PCM, None on end
    async def send_audio(self, pcm: bytes) -> None: ...   # one outbound clip
    async def stop_playback(self) -> None: ...            # barge-in flush
    @property
    def connection_state(self) -> str: ...
    async def close(self) -> None: ...
```

## Factory contract

`aiortc_transport_factory(offer_sdp: str, device_id: str) -> tuple[str, MediaTransport]`

| # | Requirement | Spec ref |
|---|-------------|----------|
| F1 | Build an answerer `RTCPeerConnection`, `setRemoteDescription(offer)`, attach an outbound audio track, `createAnswer` + `setLocalDescription`, return `(local_sdp, AiortcTransport)`. No SDP munging; Opus 48 kHz mono as negotiated. | FR-007 |
| F2 | If the offer yields **no receivable inbound audio track** within a bounded wait, raise a clear error (offer fails loudly) — never return a transport that hangs in `receive()`. | Edge: no inbound track |
| F3 | Lazy-import aiortc/av inside the factory so the package imports and the fake suite runs without them. | FR-012 / constitution V |

## Behavioural conformance

| # | Requirement | Spec ref |
|---|-------------|----------|
| C1 | `receive()` returns 16-bit LE **mono 48 kHz** PCM in uniform **20 ms (1920 B)** frames; quality equivalent to feeding the same audio to Hermes STT directly. | FR-001, SC-001 |
| C2 | `receive()` returns `None` (no exception) when the inbound track ends or the PC is `failed`/`closed`. | FR-006, Edge: track ends |
| C3 | `send_audio()` reconciles **any** TTS container/sample-rate (decode+resample via `av` → 48 kHz mono) so playback is intelligible — no chipmunk/slow-motion. | FR-002, FR-004, SC-002 |
| C4 | `send_audio()` with empty / undecodable / sentinel bytes logs and drops; never raises, never emits zero-length/broken audio. | Edge: empty/tool-only, send-before-ready |
| C5 | `stop_playback()` drops queued/in-flight outbound audio so output stops **≤300 ms** after detected caller speech, leaving the transport reusable for the next turn. | FR-005, SC-004, Edge: barge-in mid-reply |
| C6 | `connection_state` reflects the live `RTCPeerConnection.connectionState`. | FR-006 |
| C7 | `close()` is idempotent, stops both tracks, closes the PC, and leaves **no orphaned media tasks**; a fresh offer re-establishes audio with no gateway restart. | FR-006 |
| C8 | The transport performs **no** STT/TTS/agent/endpointing/VAD — audio plumbing only. | FR-008, FR-011, constitution I |

## Conformance tests

**Locally testable (must be green in `.venv`, SC-008 unaffected):**

- `tests/unit/test_media_framer.py` — `PcmFramer`: exact framing at the
  boundary, remainder carry-over across pushes, tail `flush()` zero-pads to a
  full frame, odd `frame_bytes` rejected, no partial frame ever returned
  (covers the locally-provable slice of C1/C3/FR-004).
- Existing feature-001 fake-transport suite remains untouched and green
  (FR-012/SC-008) — proves `session.py` still drives the unchanged Protocol.

**Host-proven (constitution V — live spoken test, US4 / quickstart):**

- C1–C2, C5–C7 over a real `RTCPeerConnection` from the Electron client:
  spoken phrase transcribed with parity (SC-001), reply heard intelligibly
  (SC-002), reply onset ≤1.5 s (SC-003), barge-in ≤300 ms (SC-004), ≥3 clean
  turns (SC-006), offer success 100% (SC-005), clean drop/re-offer (FR-006).

## Out of scope (unchanged by this feature)

Signaling routes, control plane, conversation/turn logic, the `HermesBridge`
seam and Hermes STT/agent/TTS integration, shared models, and the
deploy/rollback scripts (reused as-is, FR-009/FR-010).
