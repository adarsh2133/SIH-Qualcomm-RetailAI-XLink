from __future__ import annotations

import unittest

from analytics.inventory import InventoryAnalytics
from hardware.realtime_alerts import RealtimeAlertManager


class RealtimeAlertTests(unittest.TestCase):
    def test_raw_detection_count_does_not_create_stock_alerts(self) -> None:
        alerts = RealtimeAlertManager(detection_rearm_s=0)
        alerts.update_detections(
            "shelf-camera",
            [{"class_id": 0, "confidence": 0.9}],
            valid=True,
        )
        categories = {item["category"] for item in alerts.snapshot()["alerts"]}
        self.assertEqual(categories, {"detection"})

        alerts.update_detections("shelf-camera", [], valid=True)
        categories = {item["category"] for item in alerts.snapshot()["alerts"]}
        self.assertEqual(categories, set())


class InventoryAnalyticsTests(unittest.TestCase):
    def test_no_stock_threshold_is_invented(self) -> None:
        inventory = InventoryAnalytics()
        inventory.update("sku-a", 4)
        snapshot = inventory.snapshot()
        self.assertIsNone(snapshot["low_stock"])
        self.assertEqual(snapshot["items"][0]["status"], "unclassified")

    def test_configured_shelf_threshold_and_camera_metadata_are_preserved(self) -> None:
        inventory = InventoryAnalytics()
        inventory.update(
            "sku-a",
            4,
            camera_id="shelf-camera-1",
            shelf_id="shelf-01",
            section_id="section-a",
            confidence=0.87,
            low_stock_threshold=5,
            timestamp="2026-09-28T10:00:00+00:00",
        )
        snapshot = inventory.snapshot()
        self.assertEqual(snapshot["low_stock"], 1)
        self.assertEqual(snapshot["total_units"], 4)
        self.assertEqual(
            snapshot["items"][0],
            {
                "sku": "sku-a",
                "quantity": 4,
                "status": "low",
                "low_stock_threshold": 5,
                "camera_id": "shelf-camera-1",
                "shelf_id": "shelf-01",
                "section_id": "section-a",
                "confidence": 0.87,
                "timestamp": "2026-09-28T10:00:00+00:00",
            },
        )

    def test_inventory_updates_are_scoped_to_shelf_and_section(self) -> None:
        inventory = InventoryAnalytics()
        inventory.update("sku-a", 4, shelf_id="shelf-01", section_id="a")
        inventory.update("sku-a", 8, shelf_id="shelf-02", section_id="a")
        self.assertEqual(inventory.snapshot()["total_units"], 12)
        self.assertEqual(len(inventory.snapshot()["items"]), 2)

    def test_configured_threshold_is_retained_across_updates(self) -> None:
        inventory = InventoryAnalytics()
        inventory.update("sku-a", 7, low_stock_threshold=5)
        inventory.update("sku-a", 4)
        self.assertEqual(inventory.snapshot()["items"][0]["status"], "low")
        self.assertEqual(inventory.snapshot()["low_stock"], 1)


if __name__ == "__main__":
    unittest.main()
