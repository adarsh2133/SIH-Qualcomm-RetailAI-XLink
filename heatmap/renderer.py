"""Renders a heatmap matrix to a simplified wireframe."""
from __future__ import annotations

from typing import List


class HeatmapRenderer:
    @staticmethod
    def render(matrix: List[List[int]]) -> List[List[int]]:
        return [[cell for cell in row] for row in matrix]

    @staticmethod
    def colors(matrix: List[List[int]]) -> List[List[str]]:
        peak = max((max(row) for row in matrix), default=0)
        return [[f"#{int(255 * value / peak if peak else 0):02x}2030" for value in row] for row in matrix]
