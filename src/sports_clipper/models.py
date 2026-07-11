from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TimelinePoint:
    second: int
    audio_score: float = 0.0
    motion_score: float = 0.0
    combined_score: float = 0.0


@dataclass
class ClipCandidate:
    start_time: float
    end_time: float
    mean_audio: float
    peak_audio: float
    mean_motion: float
    peak_motion: float
    mean_combined: float
    peak_combined: float
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["duration"] = self.duration
        return result
