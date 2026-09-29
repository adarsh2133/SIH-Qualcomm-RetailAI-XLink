from __future__ import annotations

import unittest

from vision.line_crossing import LineCrossingDetector
from vision.tracker import ObjectTracker
from vision.zones import Zone, ZoneSet


def detection(left: float, top: float, right: float, bottom: float,
             class_id: int = 0) -> dict[str, object]:
    return {
        "bbox": [left, top, right, bottom],
        "class_id": class_id,
        "confidence": 0.9,
    }


class ObjectTrackerTests(unittest.TestCase):
    def test_repeated_frames_keep_one_track_and_use_foot_point(self) -> None:
        tracker = ObjectTracker()
        track_ids = []
        for frame in range(20):
            tracked = tracker.update_detections([
                detection(10 + frame, 20, 30 + frame, 80)
            ])
            track_ids.append(tracked[0]["track_id"])
        self.assertEqual(len(set(track_ids)), 1)
        self.assertEqual(tracked[0]["x"], 20 + 19)
        self.assertEqual(tracked[0]["y"], 80)

    def test_each_detection_gets_at_most_one_existing_track(self) -> None:
        tracker = ObjectTracker(max_distance=100)
        first = tracker.update_detections([
            detection(0, 0, 20, 20),
            detection(90, 0, 110, 20),
        ])
        second = tracker.update_detections([
            detection(40, 0, 60, 20),
            detection(45, 0, 65, 20),
        ])
        self.assertEqual(len({item["track_id"] for item in first}), 2)
        self.assertEqual(len({item["track_id"] for item in second}), 2)

    def test_short_detection_loss_is_tolerated_then_track_expires(self) -> None:
        tracker = ObjectTracker(max_missed_frames=2)
        initial = tracker.update_detections([detection(0, 0, 20, 20)])[0]["track_id"]
        tracker.update_detections([])
        tracker.update_detections([])
        reacquired = tracker.update_detections([detection(1, 0, 21, 20)])[0]["track_id"]
        self.assertEqual(initial, reacquired)
        tracker.update_detections([])
        tracker.update_detections([])
        tracker.update_detections([])
        expired = tracker.update_detections([detection(1, 0, 21, 20)])[0]["track_id"]
        self.assertNotEqual(initial, expired)

    def test_class_changes_do_not_reuse_a_track(self) -> None:
        tracker = ObjectTracker()
        first = tracker.update_detections([detection(0, 0, 20, 20, class_id=0)])[0]
        second = tracker.update_detections([detection(0, 0, 20, 20, class_id=1)])[0]
        self.assertNotEqual(first["track_id"], second["track_id"])

    def test_capacity_exposes_untracked_detections_without_reusing_live_ids(self) -> None:
        tracker = ObjectTracker(max_tracks=1)
        results = tracker.update_detections([
            detection(0, 0, 20, 20),
            detection(100, 0, 120, 20),
        ])
        self.assertTrue(results[0]["tracked"])
        self.assertFalse(results[1]["tracked"])
        self.assertEqual(len(tracker.active_tracks), 1)

        tracker = ObjectTracker(max_tracks=1)
        original = tracker.update_detections([detection(0, 0, 20, 20)])[0]
        results = tracker.update_detections([
            detection(1, 0, 21, 20),
            detection(100, 0, 120, 20),
        ])
        self.assertEqual(results[0]["track_id"], original["track_id"])
        self.assertIsNone(results[1]["track_id"])
        self.assertFalse(results[1]["tracked"])

    def test_malformed_detection_is_rejected(self) -> None:
        tracker = ObjectTracker()
        with self.assertRaisesRegex(ValueError, "four-coordinate bbox"):
            tracker.update_detections([{"bbox": [0, 1, 2]}])


class LineCrossingTests(unittest.TestCase):
    def test_direction_is_reported_once_per_actual_crossing(self) -> None:
        detector = LineCrossingDetector(line=(0, 0, 100, 0), deadband=1)
        self.assertIsNone(detector.evaluate_crossing(1, (50, -5)))
        self.assertIsNone(detector.evaluate_crossing(1, (50, 0)))
        self.assertEqual(detector.evaluate_crossing(1, (50, 5)), "positive")
        self.assertIsNone(detector.evaluate_crossing(1, (50, 6)))
        self.assertEqual(detector.evaluate_crossing(1, (50, -5)), "negative")

    def test_unconfigured_line_does_not_generate_crossings(self) -> None:
        self.assertIsNone(LineCrossingDetector().evaluate_crossing(1, (5, 5)))


class ZoneTests(unittest.TestCase):
    def test_zones_are_not_assumed_without_configuration(self) -> None:
        self.assertEqual(ZoneSet().list_zones(), [])

    def test_polygon_contains_inside_and_boundary_points(self) -> None:
        zones = ZoneSet()
        zones.add_zone(Zone("queue", ((0, 0), (10, 0), (10, 10), (0, 10))))
        self.assertTrue(zones.contains("queue", (5, 5)))
        self.assertTrue(zones.contains("queue", (0, 5)))
        self.assertFalse(zones.contains("queue", (11, 5)))

    def test_invalid_polygon_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "at least three"):
            Zone("invalid", ((0, 0), (1, 1)))
        with self.assertRaisesRegex(ValueError, "non-zero area"):
            Zone("flat", ((0, 0), (1, 0), (2, 0)))


if __name__ == "__main__":
    unittest.main()
