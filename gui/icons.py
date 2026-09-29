"""Offline, dependency-free vector icons for the CustomTkinter UI.

Icons are drawn on a small Tk canvas from centralized line primitives. This
keeps the dashboard offline and avoids emoji, remote assets, and extra UI
dependencies.
"""
from __future__ import annotations

import logging
import tkinter as tk
from typing import Callable


ICON_NAMES = {
    "overview", "cameras", "analytics", "queue", "footfall", "inventory",
    "dwell", "heatmap", "alerts", "reports", "system", "settings", "refresh",
    "connection", "ai", "gpu", "users", "timer", "package", "bell",
    "check", "warning", "offline", "connecting", "not-configured", "unavailable",
    "na", "camera",
}


def _line(canvas: tk.Canvas, points: tuple[float, ...], color: str, width: int) -> None:
    canvas.create_line(*points, fill=color, width=width, capstyle=tk.ROUND,
                       joinstyle=tk.ROUND)


def _circle(canvas: tk.Canvas, box: tuple[float, float, float, float],
            color: str, width: int = 1, fill: str = "") -> None:
    canvas.create_oval(*box, outline=color, width=width, fill=fill)


def _draw_icon(canvas: tk.Canvas, name: str, size: int, color: str) -> None:
    s = float(size)
    p = max(1, round(s / 12))
    a, b, c = s * .18, s * .50, s * .82
    if name in {"check", "online"}:
        _circle(canvas, (a, a, c, c), color, p)
        _line(canvas, (s*.34, s*.51, s*.46, s*.64, s*.70, s*.36), color, p)
    elif name in {"warning", "degraded"}:
        _line(canvas, (b, a, c, c, a, c, b, a), color, p)
        _line(canvas, (b, s*.38, b, s*.60), color, p)
        _circle(canvas, (b-.5, s*.70, b+.5, s*.71), color, 1, color)
    elif name in {"offline", "unavailable"}:
        _circle(canvas, (a, a, c, c), color, p)
        _line(canvas, (s*.36, s*.36, s*.64, s*.64), color, p)
        _line(canvas, (s*.64, s*.36, s*.36, s*.64), color, p)
    elif name == "connecting":
        _circle(canvas, (a, a, c, c), color, p)
        _line(canvas, (b, a, b, b, s*.70, b), color, p)
    elif name in {"not-configured", "na"}:
        _circle(canvas, (a, a, c, c), color, p)
        _line(canvas, (s*.35, b, s*.65, b), color, p)
    elif name in {"camera", "cameras"}:
        canvas.create_rectangle(s*.16, s*.30, s*.67, s*.70,
                                outline=color, width=p)
        _line(canvas, (s*.67, s*.42, s*.84, s*.32, s*.84, s*.68, s*.67, s*.58), color, p)
        _circle(canvas, (s*.32, s*.40, s*.52, s*.60), color, p)
    elif name in {"overview", "analytics"}:
        canvas.create_rectangle(a, a, c, c, outline=color, width=p)
        _line(canvas, (b, a, b, c), color, p)
        _line(canvas, (a, b, c, b), color, p)
    elif name in {"queue", "users", "footfall"}:
        _circle(canvas, (s*.38, a, s*.62, s*.38), color, p)
        _line(canvas, (s*.28, s*.78, s*.72, s*.78), color, p)
        _circle(canvas, (s*.10, s*.28, s*.29, s*.47), color, p)
        _circle(canvas, (s*.71, s*.28, s*.90, s*.47), color, p)
    elif name in {"inventory", "package"}:
        _line(canvas, (a, s*.30, b, a, c, s*.30, c, s*.70, b, c, a, s*.70, a, s*.30), color, p)
        _line(canvas, (b, c, b, s*.70), color, p)
    elif name in {"dwell", "timer"}:
        _circle(canvas, (a, a, c, c), color, p)
        _line(canvas, (b, b, b, s*.30, s*.67, s*.58), color, p)
    elif name == "heatmap":
        _circle(canvas, (a, a, c, c), color, p)
        _circle(canvas, (s*.34, s*.34, s*.66, s*.66), color, p)
    elif name in {"alerts", "bell"}:
        _line(canvas, (s*.28, s*.68, s*.72, s*.68), color, p)
        _line(canvas, (s*.34, s*.68, s*.38, s*.30, s*.62, s*.30, s*.66, s*.68), color, p)
        _circle(canvas, (s*.46, s*.72, s*.54, s*.80), color, p, fill=color)
    elif name == "reports":
        canvas.create_rectangle(s*.25, a, s*.75, c, outline=color, width=p)
        _line(canvas, (s*.37, s*.37, s*.63, s*.37, s*.37, s*.50, s*.63, s*.50,
                       s*.37, s*.63, s*.56, s*.63), color, p)
    elif name in {"system", "settings"}:
        _circle(canvas, (s*.28, s*.28, s*.72, s*.72), color, p)
        _circle(canvas, (s*.44, s*.44, s*.56, s*.56), color, p, fill=color)
        for angle in range(0, 360, 45):
            import math
            x1 = b + s*.25*math.cos(math.radians(angle))
            y1 = b + s*.25*math.sin(math.radians(angle))
            x2 = b + s*.42*math.cos(math.radians(angle))
            y2 = b + s*.42*math.sin(math.radians(angle))
            _line(canvas, (x1, y1, x2, y2), color, p)
    elif name in {"ai", "gpu"}:
        canvas.create_rectangle(s*.25, s*.25, s*.75, s*.75, outline=color, width=p)
        for offset in (s*.34, s*.50, s*.66):
            _line(canvas, (offset, a, offset, s*.25), color, p)
            _line(canvas, (offset, s*.75, offset, c), color, p)
            _line(canvas, (a, offset, s*.25, offset), color, p)
            _line(canvas, (s*.75, offset, c, offset), color, p)
        _circle(canvas, (s*.42, s*.42, s*.58, s*.58), color, p)
    elif name == "refresh":
        _circle(canvas, (a, a, c, c), color, p)
        _line(canvas, (s*.64, a, c, a, c, s*.36), color, p)
    elif name == "connection":
        _line(canvas, (a, s*.65, s*.38, s*.42, s*.62, s*.58, c, s*.35), color, p)
        _circle(canvas, (a-.03*s, s*.58, a+.14*s, s*.74), color, p)
        _circle(canvas, (c-.14*s, s*.26, c+.03*s, s*.42), color, p)
    else:
        _circle(canvas, (a, a, c, c), color, p)


class Icon(tk.Canvas):
    """Reusable local vector icon widget with a neutral fallback."""

    def __init__(self, master, name: str, size: int = 18, color: str = "#8da1b5",
                 **kwargs):
        self.icon_name = name if name in ICON_NAMES else "na"
        self.icon_size = size
        self.icon_color = color
        super().__init__(master, width=size, height=size, bg=kwargs.pop("bg", "#121c27"),
                         highlightthickness=0, borderwidth=0, **kwargs)
        try:
            _draw_icon(self, self.icon_name, size, color)
        except (tk.TclError, ValueError, TypeError) as exc:
            logging.getLogger(__name__).warning("Icon %s failed: %s", name, exc)
            self.create_oval(2, 2, size-2, size-2, outline=color, width=1)


def status_icon_name(state: str) -> str:
    return {
        "ONLINE": "check", "AVAILABLE": "check", "RUNNING": "check",
        "DEGRADED": "warning", "CONNECTING": "connecting",
        "OFFLINE": "offline", "NOT CONFIGURED": "not-configured",
        "UNAVAILABLE": "unavailable", "N/A": "na",
    }.get(state, "na")
