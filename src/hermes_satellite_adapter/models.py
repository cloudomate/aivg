"""Shared data models (design Appendix B / data-model.md).

Used UNCHANGED for every device type (constitution Principle II). The only
sanctioned per-type divergence is ``echo_strategy`` (an enum, not a global
ducking flag) and ``browser`` having no OTA.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class ClientStatus(str, Enum):
    ONLINE = "online"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ERROR = "error"


class SessionState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    ERROR = "error"


class TurnOutcome(str, Enum):
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"


class EchoStrategy(str, Enum):
    HARDWARE_XMOS = "hardware_xmos"
    SOFTWARE_SPEEX = "software_speex"
    HALF_DUPLEX = "half_duplex"
    BROWSER_AEC3 = "browser_aec3"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class LogSource(str, Enum):
    VAD = "vad"
    WAKEWORD = "wakeword"
    ASR = "asr"
    TTS = "tts"
    WEBRTC = "webrtc"
    SYSTEM = "system"
    OTA = "ota"


@dataclass
class SatelliteConfig:
    """Persisted device + server config (Appendix B defaults)."""

    wake_word: str = "Hey Jarvis"
    wake_word_engine: str = "openwakeword"
    vad_threshold: float = 0.5
    vad_mode: str = "adaptive"
    routing_mode: str = "preferred"
    input_volume: float = 1.0
    output_volume: float = 1.0
    echo_strategy: Optional[str] = None  # per-device, set on register (§2.5)
    webrtc_enabled: bool = True
    log_level: str = "INFO"
    heartbeat_interval: int = 30

    def merged(self, overrides: dict[str, Any]) -> "SatelliteConfig":
        data = {**self.__dict__, **{k: v for k, v in overrides.items() if k in self.__dict__}}
        return SatelliteConfig(**data)


@dataclass
class ConnectedClient:
    device_id: str
    device_type: str  # rpi | esp32 | browser  -- informational ONLY
    firmware_version: str = ""
    ip_address: str = ""
    status: ClientStatus = ClientStatus.CONNECTING
    last_seen: float = field(default_factory=time.time)
    active_session_id: Optional[str] = None
    config: SatelliteConfig = field(default_factory=SatelliteConfig)
    last_error: Optional[str] = None

    def touch(self) -> None:
        self.last_seen = time.time()


@dataclass
class ConversationTurn:
    turn_id: str
    session_id: str
    user_text: str = ""
    agent_text: Optional[str] = None
    outcome: Optional[TurnOutcome] = None
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    # Feature 010: per-stage monotonic instants (seconds) for the
    # voice-turn latency breakdown — keys per turnlatency.INSTANTS.
    # Filled by session.py + hermes_bridge.agent_stream; consumed once on
    # turn completion. Absent keys are tolerated (FR-008).
    lat_instants: dict = field(default_factory=dict)

    @property
    def latency_ms(self) -> Optional[float]:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0


@dataclass
class VoiceSession:
    session_id: str
    device_id: str
    state: SessionState = SessionState.IDLE
    started_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    current_turn: Optional[ConversationTurn] = None
    webrtc_state: str = "new"
    bitrate_tx: int = 0
    bitrate_rx: int = 0
    last_error: Optional[str] = None

    def touch(self) -> None:
        self.last_activity = time.time()


@dataclass
class LogEntry:
    device_id: str
    level: LogLevel
    source: LogSource
    message: str
    timestamp: float = field(default_factory=time.time)
    metadata: Optional[dict[str, Any]] = None
