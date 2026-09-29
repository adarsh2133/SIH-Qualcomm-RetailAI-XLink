"""Validation for opt-in, single-product shelf alert regions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite

from vision.zones import Zone

from .inventory_alerts import InventoryAlertRule


@dataclass(frozen=True)
class ShelfAlertConfig:
    rule: InventoryAlertRule
    class_id: int
    region: Zone


def parse_shelf_alert_rules(raw: str) -> list[ShelfAlertConfig]:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("PORTAL_INVENTORY_ALERT_RULES_JSON must be valid JSON") from exc
    if not isinstance(values, list):
        raise ValueError("PORTAL_INVENTORY_ALERT_RULES_JSON must be a JSON array")

    rules: list[ShelfAlertConfig] = []
    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise ValueError(f"inventory alert rule {index} must be an object")
        try:
            points = value["region"]
            if value.get("dedicated_sku_region") is not True:
                raise ValueError(
                    "dedicated_sku_region must be true; mixed-product regions cannot identify SKUs"
                )
            if not isinstance(points, list):
                raise ValueError("region must be a list of normalized points")
            coordinates_list = []
            for point in points:
                if (
                    not isinstance(point, (list, tuple))
                    or len(point) != 2
                    or any(
                        not isinstance(value, (int, float))
                        or isinstance(value, bool)
                        or not isfinite(value)
                        or not 0 <= value <= 1
                        for value in point
                    )
                ):
                    raise ValueError(
                        "region coordinates must be finite numeric pairs normalized to [0, 1]"
                    )
                coordinates_list.append((float(point[0]), float(point[1])))
            coordinates = tuple(coordinates_list)
            class_id = value.get("class_id", 0)
            if not isinstance(class_id, int) or isinstance(class_id, bool) or class_id < 0:
                raise ValueError("class_id must be a non-negative integer")
            rule = InventoryAlertRule(
                camera_id=value["camera_id"],
                sku_id=value["sku_id"],
                product=value["product"],
                shelf_id=value["shelf_id"],
                section=value["section"],
                low_stock_threshold=value["low_stock_threshold"],
                critical_stock_threshold=value["critical_stock_threshold"],
                confirmation_s=value.get("confirmation_s", 2.0),
                cooldown_s=value.get("cooldown_s", 60.0),
                min_confidence=value.get("min_confidence", 0.7),
                stable_samples=value.get("stable_samples", 3),
                max_quantity_spread=value.get("max_quantity_spread", 0),
                message_template=value.get(
                    "message_template",
                    "{product} has limited availability in {section}, shelf {shelf_id}.",
                ),
                uncertain_message_template=value.get(
                    "uncertain_message_template",
                    "Availability could not be verified for {product} at {shelf_id}.",
                ),
                out_of_stock_message_template=value.get(
                    "out_of_stock_message_template",
                    "{product} is currently unavailable at {shelf_id}.",
                ),
            )
            region = Zone(
                f"{rule.shelf_id}:{rule.section}",
                coordinates,
            )
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            raise ValueError(f"invalid inventory alert rule {index}: {exc}") from exc
        rules.append(ShelfAlertConfig(rule, class_id, region))

    identities = [
        (item.rule.camera_id, item.rule.sku_id, item.rule.shelf_id)
        for item in rules
    ]
    if len(identities) != len(set(identities)):
        raise ValueError("shelf alert rules must have unique camera/SKU/shelf keys")
    return rules


def load_shelf_alert_rules() -> list[ShelfAlertConfig]:
    import os

    raw = os.getenv("PORTAL_INVENTORY_ALERT_RULES_JSON", "").strip()
    return parse_shelf_alert_rules(raw) if raw else []
