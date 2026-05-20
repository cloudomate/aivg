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


# Feature 011 — adoption / OTA / commands -----------------------------------


class AdoptionState(str, Enum):
    """Lifecycle of a device in the registry (data-model.md §2.1)."""

    PENDING = "pending"
    ADOPTED = "adopted"


class OtaState(str, Enum):
    """Per-device OTA progress (data-model.md §2.4)."""

    IDLE = "idle"
    CHECKING = "checking"
    DOWNLOADING = "downloading"
    FLASHING = "flashing"
    REBOOTING = "rebooting"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class CommandVerb(str, Enum):
    """Closed enum of operator commands (R-14)."""

    REBOOT = "reboot"
    RESTART_VOICE = "restart_voice"
    RESTART_MANAGER = "restart_manager"
    RESET_CONFIG = "reset_config"
    FACTORY_RESET = "factory_reset"
    MUTE = "mute"
    UNMUTE = "unmute"
    IDENTIFY = "identify"


@dataclass
class PendingDevice:
    """A device that has registered but not yet been adopted.

    In-memory only — survives across registers but not across gateway
    restarts (the device's next register repopulates it). Feature 011 R-7.
    """

    device_id: str
    device_type: str  # rpi | esp32 | browser
    firmware_version: str = ""
    ip_address: str = ""
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)

    def touch(self) -> None:
        self.last_seen = time.time()


@dataclass
class OtaJob:
    """An OTA in flight or just finished (data-model.md §2.5)."""

    job_id: str
    device_id: str
    target_version: str
    state: OtaState = OtaState.IDLE
    started_at: float = field(default_factory=time.time)
    ended_at: Optional[float] = None
    result: Optional[str] = None  # success | rolled_back | failed
    failure_reason: Optional[str] = None


@dataclass
class OtaManifest:
    """Per-device-type firmware manifest under ~/.satellite/firmware/."""

    device_type: str  # rpi | esp32 — NOT browser (constitution II)
    version: str
    url: str
    sha256: str
    signature: Optional[str] = None
    changelog: str = ""

    def __post_init__(self) -> None:
        if self.device_type == "browser":
            raise ValueError(
                "OTA manifest for 'browser' device_type rejected: "
                "browser is explicitly not OTA-eligible (constitution II)."
            )
        if not (len(self.sha256) == 64 and all(c in "0123456789abcdef" for c in self.sha256)):
            raise ValueError(
                f"OtaManifest.sha256 must be 64 lowercase hex chars; got {self.sha256!r}"
            )


@dataclass
class CommandRequest:
    command: CommandVerb
    args: dict[str, Any] = field(default_factory=dict)


@dataclass
class CommandResponse:
    accepted: bool
    scheduled_at: float = field(default_factory=time.time)
    reason: Optional[str] = None


@dataclass
class RegistrySnapshot:
    """Atomic-written persistence record (R-5, ~/.satellite/state.json)."""

    schema_version: int = 1
    saved_at: float = field(default_factory=time.time)
    clients: list[dict[str, Any]] = field(default_factory=list)  # ConnectedClient.to_dict
    device_limit: int = 10


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

    # Feature 011 — adoption + persistence + OTA tracking
    name: Optional[str] = None  # human-set during adopt; required once adopted
    adoption_state: AdoptionState = AdoptionState.ADOPTED  # entries here are adopted
    config_version: int = 0  # monotonic (R-11)
    config_updated_at: float = field(default_factory=time.time)
    ota_state: OtaState = OtaState.IDLE
    ota_version: Optional[str] = None
    ota_job_id: Optional[str] = None

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
