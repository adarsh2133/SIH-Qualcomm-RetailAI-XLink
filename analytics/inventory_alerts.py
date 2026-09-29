"""Debounced, transition-based alerts for stabilized shelf observations."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite
from string import Formatter
import time
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class InventoryAlertRule:
    camera_id: str
    sku_id: str
    product: str
    shelf_id: str
    section: str
    low_stock_threshold: int
    critical_stock_threshold: int
    confirmation_s: float = 2.0
    cooldown_s: float = 60.0
    min_confidence: float = 0.7
    stable_samples: int = 3
    max_quantity_spread: int = 0
    message_template: str = (
        "{product} has limited availability in {section}, shelf {shelf_id}."
    )
    uncertain_message_template: str = (
        "Availability could not be verified for {product} at {shelf_id}."
    )
    out_of_stock_message_template: str = (
        "{product} is currently unavailable at {shelf_id}."
    )

    def __post_init__(self) -> None:
        for name in ("camera_id", "sku_id", "product", "shelf_id", "section"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} cannot be empty")
        if (
            not isinstance(self.low_stock_threshold, int)
            or isinstance(self.low_stock_threshold, bool)
            or self.low_stock_threshold < 1
        ):
            raise ValueError("low_stock_threshold must be positive")
        if (
            not isinstance(self.critical_stock_threshold, int)
            or isinstance(self.critical_stock_threshold, bool)
            or not 0 <= self.critical_stock_threshold < self.low_stock_threshold
        ):
            raise ValueError(
                "critical_stock_threshold must be non-negative and below low_stock_threshold"
            )
        if not isfinite(self.confirmation_s) or self.confirmation_s < 0:
            raise ValueError("confirmation_s must be finite and non-negative")
        if not isfinite(self.cooldown_s) or self.cooldown_s < 0:
            raise ValueError("cooldown_s must be finite and non-negative")
        if (
            not isinstance(self.min_confidence, (int, float))
            or isinstance(self.min_confidence, bool)
            or not isfinite(self.min_confidence)
            or not 0.0 <= self.min_confidence <= 1.0
        ):
            raise ValueError("min_confidence must be between 0 and 1")
        if (
            not isinstance(self.stable_samples, int)
            or isinstance(self.stable_samples, bool)
            or self.stable_samples < 1
        ):
            raise ValueError("stable_samples must be positive")
        if (
            not isinstance(self.max_quantity_spread, int)
            or isinstance(self.max_quantity_spread, bool)
            or self.max_quantity_spread < 0
        ):
            raise ValueError("max_quantity_spread cannot be negative")
        placeholders = {
            field_name
            for template in (
                self.message_template,
                self.uncertain_message_template,
                self.out_of_stock_message_template,
            )
            for _, field_name, _, _ in Formatter().parse(template)
            if field_name is not None
        }
        if placeholders - {"product", "shelf_id", "section", "quantity"}:
            raise ValueError("alert message template contains an unsupported placeholder")


class InventoryAlertEngine:
    """Requires repeated stable observations before alerting on stock level."""

    def __init__(self, rules: list[InventoryAlertRule], history_limit: int = 100):
        keys = [(rule.camera_id, rule.sku_id, rule.shelf_id) for rule in rules]
        if len(set(keys)) != len(keys):
            raise ValueError("inventory alert rules must have unique camera/SKU/shelf keys")
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        self.rules = {key: rule for key, rule in zip(keys, rules)}
        self._observations: dict[tuple[str, str, str], deque[tuple[int, float]]] = {
            key: deque(maxlen=rule.stable_samples)
            for key, rule in self.rules.items()
        }
        self._candidate: dict[tuple[str, str, str], tuple[str, float]] = {}
        self._state: dict[tuple[str, str, str], str] = {}
        self._active: dict[str, dict[str, Any]] = {}
        self._last_emitted: dict[tuple[tuple[str, str, str], str], float] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=history_limit)

    def observe(
        self,
        camera_id: str,
        sku_id: str,
        shelf_id: str,
        quantity: int | None,
        confidence: float,
        *,
        observed_at: str | None = None,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        key = (camera_id, sku_id, shelf_id)
        rule = self.rules.get(key)
        if rule is None:
            raise KeyError(f"no inventory alert rule configured for {key!r}")
        if quantity is not None and (
            not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 0
        ):
            raise ValueError("quantity must be a non-negative integer or None")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise ValueError("confidence must be numeric")
        if not isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("confidence must be finite and between 0 and 1")

        moment = time.monotonic() if now is None else now
        if not isfinite(moment):
            raise ValueError("now must be finite")
        timestamp = observed_at or datetime.now(timezone.utc).isoformat()
        observations = self._observations[key]
        if quantity is not None and confidence >= rule.min_confidence:
            observations.append((quantity, float(confidence)))
        else:
            observations.clear()

        if quantity is None or confidence < rule.min_confidence:
            candidate = "INVENTORY_UNCERTAIN"
        elif len(observations) < rule.stable_samples:
            return None
        else:
            quantities = [item[0] for item in observations]
            if max(quantities) - min(quantities) > rule.max_quantity_spread:
                return None
            else:
                estimate = sorted(quantities)[len(quantities) // 2]
                candidate = self._stock_level(estimate, rule)

        previous_candidate = self._candidate.get(key)
        if previous_candidate is None or previous_candidate[0] != candidate:
            self._candidate[key] = (candidate, moment)
            return None
        if moment - previous_candidate[1] < rule.confirmation_s:
            return None
        if self._state.get(key) == candidate:
            active = self._active_for(key)
            if active is not None:
                active["quantity"] = quantity
                active["timestamp"] = timestamp
                last_emitted = self._last_emitted.get((key, candidate))
                if (
                    active["notification_suppressed"]
                    and last_emitted is not None
                    and moment - last_emitted >= rule.cooldown_s
                ):
                    active["notification_suppressed"] = False
                    self._events.append(active.copy())
                    self._last_emitted[(key, candidate)] = moment
                    return active.copy()
            return None

        old_state = self._state.get(key, "NORMAL")
        self._state[key] = candidate
        if candidate == "NORMAL":
            resolved = self._resolve(key, timestamp)
            if resolved is not None:
                return resolved
            return None

        if old_state != "NORMAL":
            self._resolve(key, timestamp)
        return self._activate(
            key,
            candidate,
            None if candidate == "INVENTORY_UNCERTAIN" else quantity,
            confidence,
            timestamp,
            moment,
            rule,
        )

    @staticmethod
    def _stock_level(quantity: int, rule: InventoryAlertRule) -> str:
        if quantity == 0:
            return "OUT_OF_STOCK"
        if quantity <= rule.critical_stock_threshold:
            return "CRITICAL_STOCK"
        if quantity <= rule.low_stock_threshold:
            return "LOW_STOCK"
        return "NORMAL"

    def _activate(
        self,
        key: tuple[str, str, str],
        alert_type: str,
        quantity: int | None,
        confidence: float,
        timestamp: str,
        moment: float,
        rule: InventoryAlertRule,
    ) -> dict[str, Any]:
        template = (
            rule.uncertain_message_template
            if alert_type == "INVENTORY_UNCERTAIN"
            else rule.out_of_stock_message_template
            if alert_type == "OUT_OF_STOCK"
            else rule.message_template
        )
        message = template.format(
            product=rule.product,
            shelf_id=rule.shelf_id,
            section=rule.section,
            quantity="unknown" if quantity is None else quantity,
        )
        payload = {
            "id": str(uuid4()),
            "type": alert_type,
            "severity": {
                "LOW_STOCK": "warning",
                "CRITICAL_STOCK": "critical",
                "OUT_OF_STOCK": "critical",
                "INVENTORY_UNCERTAIN": "warning",
            }[alert_type],
            "product": rule.product,
            "sku_id": rule.sku_id,
            "shelf_id": rule.shelf_id,
            "section": rule.section,
            "quantity": quantity,
            "threshold": (
                rule.low_stock_threshold if alert_type == "LOW_STOCK"
                else rule.critical_stock_threshold
                if alert_type in {"CRITICAL_STOCK", "OUT_OF_STOCK"}
                else None
            ),
            "confidence": confidence,
            "timestamp": timestamp,
            "camera_id": rule.camera_id,
            "message": message,
            "acknowledged": False,
            "resolved": False,
        }
        last_emitted = self._last_emitted.get((key, alert_type))
        payload["notification_suppressed"] = (
            last_emitted is not None and moment - last_emitted < rule.cooldown_s
        )
        self._active[payload["id"]] = payload
        if not payload["notification_suppressed"]:
            self._events.append(payload.copy())
            self._last_emitted[(key, alert_type)] = moment
        return payload.copy()

    def _active_for(self, key: tuple[str, str, str]) -> dict[str, Any] | None:
        for alert in self._active.values():
            if (
                alert["camera_id"],
                alert["sku_id"],
                alert["shelf_id"],
            ) == key:
                return alert
        return None

    def _resolve(
        self, key: tuple[str, str, str], timestamp: str
    ) -> dict[str, Any] | None:
        active = self._active_for(key)
        if active is None:
            return None
        resolved = {
            "id": str(uuid4()),
            "type": "RESOLVED",
            "severity": "info",
            "product": active["product"],
            "sku_id": active["sku_id"],
            "shelf_id": active["shelf_id"],
            "section": active["section"],
            "quantity": active["quantity"],
            "threshold": active["threshold"],
            "timestamp": timestamp,
            "camera_id": active["camera_id"],
            "resolved_alert_id": active["id"],
        }
        self._active.pop(active["id"], None)
        self._events.append(resolved.copy())
        return resolved

    def acknowledge(self, alert_id: str) -> dict[str, Any]:
        alert = self._active.get(alert_id)
        if alert is None:
            raise KeyError(f"active alert not found: {alert_id}")
        alert["acknowledged"] = True
        return alert.copy()

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "alerts": [item.copy() for item in self._active.values()],
            "alert_events": [item.copy() for item in self._events],
        }
