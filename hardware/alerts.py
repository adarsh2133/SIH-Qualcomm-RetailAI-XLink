"""Alert manager writing to the application log."""
from __future__ import annotations

import logging
from typing import Any


class AlertManager:
    def __init__(self, logger: logging.Logger | None = None) -> None:
        self.logger = logger or logging.getLogger("PORTAL-XLINK")
        self.history: list[dict[str, Any]] = []

    def emit(self, message: str, **context: Any) -> None:
        self.logger.warning("%s | %s", message, context)
        self.history.append({"message": message, "context": context})

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.history[-limit:]
