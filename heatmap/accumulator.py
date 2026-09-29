"""Collects motion intensity data into a grid."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class HeatmapAccumulator:
    width: int = 16
    height: int = 16
    values: List[List[int]] = field(default_factory=lambda: [[0 for _ in range(16)] for _ in range(16)])

    def record(self, x: int, y: int, weight: int = 1) -> None:
        if weight < 0:
            raise ValueError("weight must be non-negative")
        x_index = min(max(x, 0), self.width - 1)
        y_index = min(max(y, 0), self.height - 1)
        self.values[y_index][x_index] += weight

    def clear(self) -> None:
        self.values = [[0 for _ in range(self.width)] for _ in range(self.height)]

    def normalized(self) -> List[List[float]]:
        peak = max((max(row) for row in self.values), default=0)
        return [[value / peak if peak else 0.0 for value in row] for row in self.values]

    def matrix(self) -> List[List[int]]:
        return [row[:] for row in self.values]
