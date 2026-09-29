"""Explicit live metric values with freshness and provenance."""
from __future__ import annotations

import time
from typing import Any


def metric(value: Any = None, *, source: str = "live", timestamp: float | None = None,
           status: str = "AVAILABLE", reason: str = "") -> dict[str, Any]:
    """Create the wire/display shape used by live dashboards."""
    valid = status == "AVAILABLE" and value is not None
    return {"valid": valid, "value": value if valid else None, "source": source,
            "timestamp": timestamp if timestamp is not None else time.time(),
            "status": status, "reason": reason}


def expire(value: dict[str, Any], timeout_s: float, now: float | None = None) -> dict[str, Any]:
    """Invalidate a metric once its timestamp is older than the freshness window."""
    now = time.time() if now is None else now
    timestamp = value.get("timestamp")
    if timestamp is None or now - float(timestamp) > timeout_s:
        return metric(source=value.get("source", "live"), timestamp=timestamp,
                      status="STALE", reason="metric freshness timeout")
    return value
