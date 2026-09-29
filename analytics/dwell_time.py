"""Dwell time analytics for zones and kiosks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class DwellTimeAnalytics:
    average_seconds: float | None = None
    peak_seconds: float | None = None
    samples: List[float] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.samples:
            self.average_seconds = sum(self.samples) / len(self.samples)
            self.peak_seconds = max(self.samples)

    def record(self, seconds: float) -> None:
        if seconds < 0:
            raise ValueError("dwell time cannot be negative")
        self.samples.append(float(seconds))
        self.average_seconds = sum(self.samples) / len(self.samples)
        self.peak_seconds = max(self.peak_seconds, seconds)

    def snapshot(self) -> Dict[str, float]:
        return {"average_seconds": self.average_seconds, "peak_seconds": self.peak_seconds,
                "status": "AVAILABLE" if self.samples else "UNAVAILABLE"}
