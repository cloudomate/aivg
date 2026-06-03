"""Feature 023 live proof (light): drive one gRPC voice turn through the REAL
fixed code path (GrpcMediaAdapter.send_audio -> run_outbound_pump) and capture
the downstream 16 kHz AudioChunks.

Also renders the PRE-023 behavior (raw container bytes downsampled 48->16 as if
they were 48 kHz PCM) so you can A/B: out_fixed.wav = words, out_buggy.wav = noise.

Run on iva:  PYTHONPATH=src python specs/023-grpc-tts-pcm-decode/live_proof.py
Then:        aplay -D plughw:0,0 out_fixed.wav   # the XVF3800
             aplay -D plughw:0,0 out_buggy.wav
"""

from __future__ import annotations

import asyncio
import audioop
import struct
import wave

import grpc

from aivg_core.transports.grpc._generated import audio_pb2, audio_pb2_grpc
from aivg_core.transports.grpc.codec import CODEC_PCM_S16LE_16K
from aivg_core.transports.grpc.media_adapter import GrpcMediaAdapter

WORDS = open("words.wav", "rb").read()  # 22.05 kHz mono WAV of real speech


class Audio(audio_pb2_grpc.AudioServicer):
    async def Stream(self, request_iterator, context):
        adapter = GrpcMediaAdapter(downstream_codec=CODEC_PCM_S16LE_16K)
        pump = asyncio.create_task(adapter.run_outbound_pump())

        async def drive():
            async for f in request_iterator:
                if (f.WhichOneof("body") == "event"
                        and f.event.kind == audio_pb2.ClientEvent.END_OF_UTTERANCE):
                    await adapter.send_audio(WORDS)  # <-- THE FEATURE-023 CODE UNDER TEST
                    await adapter.close()
                    return

        driver = asyncio.create_task(drive())
        try:
            while True:
                sf = await adapter.next_server_frame()
                if sf is None:
                    break
                yield sf
        finally:
            await driver
            await pump


async def _run_turn() -> bytes:
    server = grpc.aio.server()
    audio_pb2_grpc.add_AudioServicer_to_server(Audio(), server)
    port = server.add_insecure_port("127.0.0.1:0")
    await server.start()

    async def client_frames():
        yield audio_pb2.ClientFrame(session=audio_pb2.SessionHeader(
            session_id="iva-1",
            downstream_codec_pref=[audio_pb2.Codec.Value("CODEC_PCM_S16LE_16K")]))
        for _ in range(3):  # a little mic PCM up (realism)
            yield audio_pb2.ClientFrame(pcm=audio_pb2.PcmChunk(samples=b"\x00\x00" * 320))
            await asyncio.sleep(0)
        yield audio_pb2.ClientFrame(event=audio_pb2.ClientEvent(
            kind=audio_pb2.ClientEvent.END_OF_UTTERANCE))

    payload = bytearray()
    async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as ch:
        stub = audio_pb2_grpc.AudioStub(ch)
        async for sf in stub.Stream(client_frames()):
            if sf.WhichOneof("body") == "audio":
                payload += sf.audio.payload
    await server.stop(None)
    return bytes(payload)


def _write_wav(path: str, pcm16: bytes, rate: int = 16000) -> None:
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm16)


def _peak(b: bytes) -> int:
    a = struct.unpack("<%dh" % (len(b) // 2), b[: len(b) // 2 * 2])
    return max((abs(x) for x in a), default=0)


async def main() -> None:
    fixed = await _run_turn()
    _write_wav("out_fixed.wav", fixed)
    # PRE-023: old send_audio queued the raw container, the pump downsampled it
    # 48000->16000 as if it were 48 kHz PCM. Reproduce that to A/B against.
    buggy, _ = audioop.ratecv(WORDS, 2, 1, 48000, 16000, None)
    _write_wav("out_buggy.wav", buggy)
    print(f"FIXED  out_fixed.wav: {len(fixed):>7} B  {len(fixed)/2/16000:5.2f}s  peak {_peak(fixed)}")
    print(f"BUGGY  out_buggy.wav: {len(buggy):>7} B  {len(buggy)/2/16000:5.2f}s  peak {_peak(buggy)}")
    print("FIXED should ~match the 5.33s source; BUGGY is shorter garbled noise.")


if __name__ == "__main__":
    asyncio.run(main())
