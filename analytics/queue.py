"""Queue analytics for line waits and backlog."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class QueueAnalytics:
    queue_length: int | None = None
    avg_wait_s: float | None = None
    service_rate_per_min: float | None = None

    def snapshot(self) -> Dict[str, Any]:
        return {
            "queue_length": self.queue_length,
            "avg_wait_s": self.avg_wait_s,
            "service_rate_per_min": self.service_rate_per_min,
            "stalled": self.queue_length is not None and self.queue_length > 15,
            "status": "UNAVAILABLE" if self.queue_length is None else "AVAILABLE",
        }

    def update(self, queue_length: int, avg_wait_s: float | None = None) -> None:
        if queue_length < 0:
            raise ValueError("queue length cannot be negative")
        self.queue_length = queue_length
        if avg_wait_s is not None:
            self.avg_wait_s = max(0.0, float(avg_wait_s))
