"""Voice-pipeline message helpers for the ESPHome transport.

ESPHome's voice-assistant protocol (server-to-client direction
swapped vs. typical RPCs because the *device* requests the pipeline
run):

- Device → us: ``SubscribeVoiceAssistantRequest`` (subscribe to pipelines).
- Device → us: ``VoiceAssistantRequest(start=True, ...)`` (start a pipeline).
- Us → device: ``VoiceAssistantResponse(port=0, error=False)`` (pipeline accepted).
- Device → us: ``VoiceAssistantAudio`` frames carrying PCM16 mono @ 16 kHz.
- Us → device: ``VoiceAssistantEventResponse`` events (STT_START, STT_END, etc.).
- Us → device: ``VoiceAssistantAudio`` frames carrying TTS audio.
- Us → device: ``VoiceAssistantEventResponse(VOICE_ASSISTANT_RUN_END)``.

Per [research.md R-4](../../../specs/017-esphome-voice-transport/research.md#r-4--voice-assistant-pipeline-event-mapping-implementation-note).

Constitutional Principle I: the device's STT_END signal is
informational only — the **gateway's** server-side endpoint detector
(``AgentPlatform.endpoint(frame)``) is authoritative. We emit STT_END
when the platform reports end-of-utterance, NOT when the device tells
us to.
"""

from __future__ import annotations

import aioesphomeapi.api_pb2 as pb

__all__ = [
    "make_hello_response",
    "make_device_info_response",
    "make_voice_assistant_response",
    "make_voice_assistant_configuration_response",
    "make_voice_assistant_event_response",
    "make_voice_assistant_audio",
    "Event",
]


# Re-export the event-type constants as a thin namespace so callers
# don't need to import from aioesphomeapi.api_pb2 directly.
class Event:
    RUN_START = pb.VOICE_ASSISTANT_RUN_START
    RUN_END = pb.VOICE_ASSISTANT_RUN_END
    STT_START = pb.VOICE_ASSISTANT_STT_START
    STT_END = pb.VOICE_ASSISTANT_STT_END
    INTENT_START = pb.VOICE_ASSISTANT_INTENT_START
    INTENT_END = pb.VOICE_ASSISTANT_INTENT_END
    TTS_START = pb.VOICE_ASSISTANT_TTS_START
    TTS_END = pb.VOICE_ASSISTANT_TTS_END
    WAKE_WORD_START = pb.VOICE_ASSISTANT_WAKE_WORD_START
    WAKE_WORD_END = pb.VOICE_ASSISTANT_WAKE_WORD_END
    ERROR = pb.VOICE_ASSISTANT_ERROR


def make_hello_response(*, server_name: str = "aivg-gateway") -> pb.HelloResponse:
    """Initial response to the device's HelloRequest. Advertises a
    recent API version (matches what current ESPHome devices expect)."""
    return pb.HelloResponse(
        api_version_major=1,
        api_version_minor=10,
        server_info=server_name,
        name=server_name,
    )


def make_device_info_response(
    *,
    name: str = "aivg-gateway",
    friendly_name: str = "AIVG Gateway",
    uses_password: bool = True,
) -> pb.DeviceInfoResponse:
    """Reply to the device's DeviceInfoRequest. The device reads this
    to display the gateway's friendly name in its logs / status."""
    return pb.DeviceInfoResponse(
        name=name,
        friendly_name=friendly_name,
        uses_password=uses_password,
        esphome_version="aivg-1.1.0",
        manufacturer="AIVG",
        model="AIVG Voice Gateway",
        legacy_voice_assistant_version=2,
    )


def make_voice_assistant_response(
    *,
    port: int = 0,
    error: bool = False,
) -> pb.VoiceAssistantResponse:
    """Reply to the device's VoiceAssistantRequest(start=True).
    ``port=0`` tells the device to send audio on the same connection
    (not a separate UDP socket — UDP audio is the alternative ESPHome
    transport flavour and is OOS for v1)."""
    return pb.VoiceAssistantResponse(port=port, error=error)


def make_voice_assistant_configuration_response() -> (
    pb.VoiceAssistantConfigurationResponse
):
    """Reply to a VoiceAssistantConfigurationRequest. We advertise no
    wake-words (the device runs its own) and no maximums."""
    return pb.VoiceAssistantConfigurationResponse(
        available_wake_words=[],
        active_wake_words=[],
        max_active_wake_words=0,
    )


def make_voice_assistant_event_response(
    event_type: int,
    *,
    data: list[tuple[str, str]] | None = None,
) -> pb.VoiceAssistantEventResponse:
    """Build a lifecycle event. ``data`` is a list of (name, value)
    tuples carried as ``VoiceAssistantEventData`` repeated entries —
    used for ``STT_END`` to deliver the transcript text, ``TTS_START``
    to deliver the reply text, etc."""
    msg = pb.VoiceAssistantEventResponse(event_type=event_type)
    if data:
        for name, value in data:
            msg.data.add(name=name, value=value)
    return msg


def make_voice_assistant_audio(
    pcm: bytes,
    *,
    end: bool = False,
) -> pb.VoiceAssistantAudio:
    """Wrap a raw PCM16 mono @ 16 kHz chunk for the wire."""
    return pb.VoiceAssistantAudio(data=pcm, end=end)
