from __future__ import annotations

import unittest

from analytics.inventory_alerts import InventoryAlertEngine, InventoryAlertRule
from analytics.shelf_alert_config import parse_shelf_alert_rules


def rule(**overrides: object) -> InventoryAlertRule:
    values: dict[str, object] = {
        "camera_id": "shelf-01",
        "sku_id": "sku-cola",
        "product": "Cola",
        "shelf_id": "A-03",
        "section": "Drinks",
        "low_stock_threshold": 5,
        "critical_stock_threshold": 2,
        "confirmation_s": 2.0,
        "cooldown_s": 10.0,
        "stable_samples": 3,
    }
    values.update(overrides)
    return InventoryAlertRule(**values)  # type: ignore[arg-type]


class InventoryAlertEngineTests(unittest.TestCase):
    def test_no_alert_from_single_observation(self) -> None:
        engine = InventoryAlertEngine([rule()])
        self.assertIsNone(
            engine.observe("shelf-01", "sku-cola", "A-03", 3, 0.95, now=0)
        )
        self.assertEqual(engine.snapshot()["alerts"], [])

    def test_low_stock_is_debounced_and_does_not_repeat_each_observation(self) -> None:
        engine = InventoryAlertEngine([rule()])
        for moment in (0, 1, 2):
            engine.observe("shelf-01", "sku-cola", "A-03", 8, 0.95, now=moment)
        for moment in (3, 4, 5):
            event = engine.observe(
                "shelf-01", "sku-cola", "A-03", 4, 0.95, now=moment
            )
            self.assertIsNone(event)
        event = engine.observe("shelf-01", "sku-cola", "A-03", 4, 0.95, now=7)
        self.assertEqual(event["type"], "LOW_STOCK")
        self.assertEqual(event["quantity"], 4)
        self.assertEqual(event["threshold"], 5)
        self.assertEqual(event["product"], "Cola")
        for moment in (8, 9, 10):
            self.assertIsNone(
                engine.observe("shelf-01", "sku-cola", "A-03", 4, 0.95, now=moment)
            )
        self.assertEqual(len(engine.snapshot()["alert_events"]), 1)

    def test_replenishment_resolves_then_later_low_stock_emits_again(self) -> None:
        engine = InventoryAlertEngine([rule(confirmation_s=0, cooldown_s=0)])
        for moment in (0, 1, 2):
            engine.observe("shelf-01", "sku-cola", "A-03", 4, 0.95, now=moment)
        alert = engine.observe("shelf-01", "sku-cola", "A-03", 4, 0.95, now=3)
        self.assertEqual(alert["type"], "LOW_STOCK")
        acknowledged = engine.acknowledge(alert["id"])
        self.assertTrue(acknowledged["acknowledged"])

        for moment in (4, 5, 6):
            engine.observe("shelf-01", "sku-cola", "A-03", 10, 0.95, now=moment)
        resolved = engine.observe(
            "shelf-01", "sku-cola", "A-03", 10, 0.95, now=7
        )
        self.assertEqual(resolved["type"], "RESOLVED")
        self.assertEqual(engine.snapshot()["alerts"], [])

        for moment in (8, 9, 10):
            engine.observe("shelf-01", "sku-cola", "A-03", 2, 0.95, now=moment)
        again = engine.observe("shelf-01", "sku-cola", "A-03", 2, 0.95, now=11)
        self.assertEqual(again["type"], "CRITICAL_STOCK")
        self.assertEqual(
            [event["type"] for event in engine.snapshot()["alert_events"]],
            ["LOW_STOCK", "RESOLVED", "CRITICAL_STOCK"],
        )

    def test_low_confidence_creates_uncertain_not_out_of_stock(self) -> None:
        engine = InventoryAlertEngine([
            rule(confirmation_s=0, stable_samples=1)
        ])
        engine.observe("shelf-01", "sku-cola", "A-03", 0, 0.1, now=0)
        event = engine.observe("shelf-01", "sku-cola", "A-03", 0, 0.1, now=1)
        self.assertEqual(event["type"], "INVENTORY_UNCERTAIN")
        self.assertIsNone(event["quantity"])
        self.assertNotEqual(event["type"], "OUT_OF_STOCK")

    def test_cooldown_suppresses_reactivation_then_allows_notification(self) -> None:
        engine = InventoryAlertEngine([
            rule(confirmation_s=0, cooldown_s=10, stable_samples=1)
        ])
        engine.observe("shelf-01", "sku-cola", "A-03", 4, 0.95, now=0)
        first = engine.observe(
            "shelf-01", "sku-cola", "A-03", 4, 0.95, now=1
        )
        self.assertEqual(first["type"], "LOW_STOCK")

        engine.observe("shelf-01", "sku-cola", "A-03", 10, 0.95, now=2)
        engine.observe("shelf-01", "sku-cola", "A-03", 10, 0.95, now=3)
        engine.observe("shelf-01", "sku-cola", "A-03", 4, 0.95, now=4)
        suppressed = engine.observe(
            "shelf-01", "sku-cola", "A-03", 4, 0.95, now=5
        )
        self.assertTrue(suppressed["notification_suppressed"])
        self.assertEqual(
            [event["type"] for event in engine.snapshot()["alert_events"]],
            ["LOW_STOCK", "RESOLVED"],
        )
        repeated = engine.observe(
            "shelf-01", "sku-cola", "A-03", 4, 0.95, now=11
        )
        self.assertFalse(repeated["notification_suppressed"])
        self.assertEqual(
            [event["type"] for event in engine.snapshot()["alert_events"]],
            ["LOW_STOCK", "RESOLVED", "LOW_STOCK"],
        )

    def test_thresholds_and_rule_identity_are_validated(self) -> None:
        with self.assertRaisesRegex(ValueError, "below"):
            rule(critical_stock_threshold=5)
        with self.assertRaisesRegex(ValueError, "unsupported placeholder"):
            rule(message_template="{missing}")


class ShelfRuleConfigTests(unittest.TestCase):
    def test_requires_dedicated_sku_region_and_normalized_polygon(self) -> None:
        valid = (
            '[{"camera_id":"shelf-01","sku_id":"sku-cola","product":"Cola",'
            '"shelf_id":"A-03","section":"Drinks","class_id":0,'
            '"low_stock_threshold":5,"critical_stock_threshold":2,'
            '"dedicated_sku_region":true,"region":[[0,0],[1,0],[1,1],[0,1]]}]'
        )
        parsed = parse_shelf_alert_rules(valid)
        self.assertEqual(parsed[0].rule.product, "Cola")
        self.assertEqual(parsed[0].class_id, 0)

        invalid = valid.replace('"dedicated_sku_region":true,', "")
        with self.assertRaisesRegex(ValueError, "dedicated_sku_region"):
            parse_shelf_alert_rules(invalid)

        outside = valid.replace("[[0,0]", "[[2,0]")
        with self.assertRaisesRegex(ValueError, "normalized"):
            parse_shelf_alert_rules(outside)


if __name__ == "__main__":
    unittest.main()
