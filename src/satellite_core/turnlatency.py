"""Voice-turn latency breakdown — pure, stdlib-only (feature 010).

Constitution I/V: this is **timing arithmetic only**. It performs NO ASR,
TTS, agent, endpointing, or I/O. It turns a set of recorded stage instants
(monotonic seconds; any may be absent because a turn errored / was
barged-in / was empty) into an ordered, contiguous `LatencyBreakdown`
whose stage durations sum to the measured span and whose dominant stage is
unambiguous. Deterministic and dependency-free so it is the locally
unit-testable slice of feature 010 (mirrors `streamasm.py`/`textseg.py`);
real wall-clock reductions are host-proven (constitution V).

The canonical instant order is the ONLY ordering; segments are formed
between *consecutive present* instants, so a missing middle instant simply
widens the neighbouring segment rather than corrupting the sum.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping, Optional, Tuple

__all__ = [
    "INSTANTS",
    "STAGES",
    "Stage",
    "LatencyBreakdown",
    "build_breakdown",
]

# Canonical instant order (data-model.md). end_of_speech is derived by the
# caller (= endpoint_detected − voice.silence_duration, read from config —
# never hardcoded here; this module only does arithmetic on what it is given).
INSTANTS: Tuple[str, ...] = (
    "end_of_speech",
    "endpoint_detected",
    "stt_done",
    "agent_first_output",
    "first_unit_ready",
    "first_audio_synth",
    "first_audio_delivered",
)

# Human-facing label for the gap that *starts* at each instant (the last
# instant has no following gap).
STAGES: Tuple[Tuple[str, str], ...] = (
    ("endpoint", "end_of_speech"),
    ("stt", "endpoint_detected"),
    ("agent", "stt_done"),
    ("assemble", "agent_first_output"),
    ("synth", "first_unit_ready"),
    ("playback", "first_audio_synth"),
)
_LABEL_BY_START = {start: label for label, start in STAGES}


@dataclass(frozen=True)
class Stage:
    """One contiguous timed segment of a turn."""

    name: str          # human label (endpoint/stt/agent/assemble/synth/playback)
    start: str          # canonical instant name the segment starts at
    end: str            # canonical instant name the segment ends at
    seconds: float      # duration, clamped to >= 0.0 (never negative)


@dataclass(frozen=True)
class LatencyBreakdown:
    """Ordered per-stage durations + the end-to-end total for one turn."""

    stages: Tuple[Stage, ...]
    total_s: float                 # first present instant → last present instant
    dominant: Optional[str]        # name of the longest stage, or None if no stages
    complete: bool                 # True iff all 7 canonical instants present

    def as_log_fields(self) -> dict:
        """Flat dict for the LogSink (one coherent record — FR-002)."""
        fields = {"total_ms": round(self.total_s * 1000.0, 1)}
        for st in self.stages:
            fields[st.name + "_ms"] = round(st.seconds * 1000.0, 1)
        if self.dominant is not None:
            fields["dominant"] = self.dominant
        fields["complete"] = self.complete
        return fields


def build_breakdown(instants: "Mapping[str, float] | None") -> LatencyBreakdown:
    """Assemble the ordered breakdown from recorded instants.

    - Absent instants are skipped; a segment spans the two *consecutive
      present* canonical instants, so the stage durations always sum
      exactly to ``total_s`` (last present − first present) regardless of
      which middle instants are missing (SC-003 / contract L2).
    - Out-of-order/negative gaps are clamped to ``0.0`` (a starved clock or
      a barge-in can yield these) — never raises, never hangs (FR-008/L3).
    - Empty / None / single-instant input → no stages, total 0.0, dominant
      None, complete False (no raise).
    """
    present: List[Tuple[str, float]] = []
    if instants:
        for name in INSTANTS:
            v = instants.get(name)
            if v is not None:
                present.append((name, float(v)))

    if len(present) < 2:
        return LatencyBreakdown(
            stages=(), total_s=0.0, dominant=None,
            complete=bool(instants) and len(present) == len(INSTANTS),
        )

    stages: List[Stage] = []
    for (start_name, t0), (end_name, t1) in zip(present, present[1:]):
        dur = t1 - t0
        if dur < 0.0:
            dur = 0.0  # clamp: starved clock / interrupted ordering
        # Label by the canonical START instant of the gap; if a middle
        # instant was missing the merged gap keeps the earlier label
        # (still attributable to where the time began accumulating).
        label = _LABEL_BY_START.get(start_name, start_name)
        stages.append(Stage(name=label, start=start_name, end=end_name,
                             seconds=dur))

    total = present[-1][1] - present[0][1]
    if total < 0.0:
        total = 0.0
    dominant = max(stages, key=lambda s: s.seconds).name if stages else None
    return LatencyBreakdown(
        stages=tuple(stages),
        total_s=total,
        dominant=dominant,
        complete=len(present) == len(INSTANTS),
    )
