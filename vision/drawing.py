"""Utility functions for drawing overlays on a Tk canvas."""
from __future__ import annotations

from typing import Sequence, Tuple


def draw_zone(canvas, points: Sequence[Tuple[int, int]], color: str = "#3ddc97", outline: str = "#ffffff") -> None:
    if not points:
        return
    canvas.create_polygon(*sum(points, ()), fill=color, outline=outline, stipple="gray25")


def draw_line(canvas, start: Tuple[int, int], end: Tuple[int, int], color: str = "#ffb703") -> None:
    canvas.create_line(start, end, fill=color, width=2)


def draw_bounding_box(canvas, x1: int, y1: int, x2: int, y2: int, color: str = "#ffffff") -> None:
    canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
