"""Footfall analytics based on entrance and exit events."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class FootfallAnalytics:
    entries: List[Dict[str, Any]] = field(default_factory=list)
    exits: List[Dict[str, Any]] = field(default_factory=list)

    def record(self, direction: str, count: int = 1) -> None:
        if direction not in {"entry", "exit"} or count < 0:
            raise ValueError("direction must be entry or exit and count non-negative")
        (self.entries if direction == "entry" else self.exits).append({"count": count})

    def snapshot(self) -> Dict[str, Any]:
        visits = sum(item["count"] for item in self.entries)
        departures = sum(item["count"] for item in self.exits)
        return {
            "visits": visits,
            "departures": departures,
            "occupancy": max(visits - departures, 0),
            "peak_traffic": None,
            "status": "AVAILABLE" if self.entries or self.exits else "UNAVAILABLE",
        }
