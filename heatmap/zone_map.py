"""Heatmap zone map metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class ZoneMap:
    zones: Dict[str, List[tuple]] = field(default_factory=lambda: {
        "entry": [(0, 0), (8, 0), (8, 6), (0, 6)],
        "checkout": [(10, 0), (15, 0), (15, 6), (10, 6)],
    })
