"""Heatmap service facade for dashboard panels."""
from __future__ import annotations

from typing import Dict, List

from heatmap.accumulator import HeatmapAccumulator


class HeatmapService:
    def __init__(self) -> None:
        self.accumulator = HeatmapAccumulator(12, 12)

    def snapshot(self) -> Dict[str, List[List[int]]]:
        matrix = self.accumulator.matrix()
        return {"matrix": matrix, "status": "UNAVAILABLE" if not any(any(row) for row in matrix) else "AVAILABLE"}
