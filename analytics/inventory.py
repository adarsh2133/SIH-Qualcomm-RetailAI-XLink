"""Shelf inventory estimates with explicit provenance and configured thresholds."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Dict, List


@dataclass
class InventoryAnalytics:
    items: List[Dict[str, Any]] = field(default_factory=list)

    def snapshot(self) -> Dict[str, Any]:
        configured_items = [
            item for item in self.items
            if item.get("low_stock_threshold") is not None
        ]
        total_units = sum(item["quantity"] for item in self.items)
        low_stock = sum(item["status"] == "low" for item in configured_items)
        return {
            "total_units": None if not self.items else total_units,
            "low_stock": None if not configured_items else low_stock,
            "items": [item.copy() for item in self.items],
            "status": "UNAVAILABLE" if not self.items else "AVAILABLE",
        }

    def update(
        self,
        sku: str,
        count: int,
        *,
        camera_id: str | None = None,
        shelf_id: str | None = None,
        section_id: str | None = None,
        confidence: float | None = None,
        low_stock_threshold: int | None = None,
        timestamp: str | None = None,
    ) -> None:
        if not isinstance(sku, str) or not sku.strip():
            raise ValueError("sku cannot be empty")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("quantity must be a non-negative integer")
        if low_stock_threshold is not None and (
            not isinstance(low_stock_threshold, int)
            or isinstance(low_stock_threshold, bool)
            or low_stock_threshold < 1
        ):
            raise ValueError("low_stock_threshold must be positive")

        item = next(
            (
                current for current in self.items
                if (
                    current["sku"],
                    current.get("camera_id"),
                    current.get("shelf_id"),
                    current.get("section_id"),
                ) == (sku, camera_id, shelf_id, section_id)
            ),
            None,
        )
        if confidence is not None and (
            not isinstance(confidence, (int, float))
            or isinstance(confidence, bool)
            or not isfinite(confidence)
            or not 0.0 <= confidence <= 1.0
        ):
            raise ValueError("confidence must be finite and between 0 and 1")
        threshold = (
            low_stock_threshold
            if low_stock_threshold is not None
            else item.get("low_stock_threshold") if item is not None
            else None
        )
        status = (
            "unclassified" if threshold is None
            else "low" if count < threshold
            else "healthy"
        )
        updated = {
            "sku": sku,
            "quantity": count,
            "status": status,
            "low_stock_threshold": threshold,
            "camera_id": camera_id,
            "shelf_id": shelf_id,
            "section_id": section_id,
            "confidence": confidence,
            "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        }
        if item is None:
            self.items.append(updated)
        else:
            item.update(updated)
