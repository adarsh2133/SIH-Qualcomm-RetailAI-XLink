"""Direction-aware line crossing for camera-local tracks."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Dict, Tuple


@dataclass
class LineCrossingDetector:
    line: Tuple[float, float, float, float] | None = None
    deadband: float = 1.0
    crossed: Dict[int, bool] = field(default_factory=dict)
    previous_side: Dict[int, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.deadband < 0:
            raise ValueError("deadband cannot be negative")
        if self.line is not None:
            if len(self.line) != 4:
                raise ValueError("line must contain four coordinates")
            x1, y1, x2, y2 = self.line
            if hypot(x2 - x1, y2 - y1) == 0:
                raise ValueError("line endpoints must be different")

    def evaluate_crossing(
        self, track_id: int, position: Tuple[float, float]
    ) -> str | None:
        if self.line is None:
            return None
        x1, y1, x2, y2 = self.line
        line_length = hypot(x2 - x1, y2 - y1)
        side = (
            (x2 - x1) * (position[1] - y1)
            - (y2 - y1) * (position[0] - x1)
        ) / line_length
        if abs(side) <= self.deadband:
            return None
        previous = self.previous_side.get(track_id)
        self.previous_side[track_id] = side
        if previous is None or previous * side >= 0:
            return None
        self.crossed[track_id] = True
        return "positive" if side > 0 else "negative"

    def evaluate(self, track_id: int, position: Tuple[float, float]) -> bool:
        return self.evaluate_crossing(track_id, position) is not None

    def forget(self, track_id: int) -> None:
        self.previous_side.pop(track_id, None)
        self.crossed.pop(track_id, None)
