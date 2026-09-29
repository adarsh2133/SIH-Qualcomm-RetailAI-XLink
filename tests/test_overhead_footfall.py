import tempfile
import unittest
from pathlib import Path

from analytics.daily_footfall import DailyFootfallStore
from vision.overhead_footfall import (
    OverheadFootfallCounter,
    create_footfall_counter_from_env,
    select_person_detections,
)


def box_at(y):
    return {
        "bbox": [40, y - 5, 60, y + 5],
        "class_id": 0,
        "confidence": 1.0,
    }


def box_at_x(x):
    return {
        "bbox": [x - 5, 40, x + 5, 60],
        "class_id": 0,
        "confidence": 1.0,
    }


def hold_at(counter, y, frames=3):
    events = []
    for _ in range(frames):
        events.extend(counter.update_tracks([box_at(y)], 100, 100)[1])
    return events


class FakeHOG:
    def __init__(self, centers):
        self.centers = iter(centers)
        self.calls = 0

    def detectMultiScale(self, image, *args):
        self.calls += 1
        center_y = next(self.centers)
        if center_y is None:
            return [], ()
        return [(40, center_y - 10, 20, 20)], [2.0]


class OverheadFootfallTests(unittest.TestCase):
    def test_footfall_environment_defaults_to_configured_doorway_direction(self):
        from unittest.mock import patch

        with patch.dict("os.environ", {}, clear=True):
            counter = create_footfall_counter_from_env()

        self.assertEqual(counter.line_axis, "horizontal")
        self.assertEqual(counter.entry_side, "negative")

    def test_horizontal_line_counts_both_directions(self):
        counter = OverheadFootfallCounter(
            line_axis="horizontal",
            entry_side="negative",
            crossing_cooldown_frames=1,
            crossing_confirm_frames=1,
            min_track_frames=1,
            min_track_motion=0,
        )
        self.assertEqual(counter.update_tracks([box_at(75)], 100, 100)[1], [])
        entry = counter.update_tracks([box_at(25)], 100, 100)[1]
        exit_events = counter.update_tracks([box_at(75)], 100, 100)[1]

        self.assertEqual([event["direction"] for event in entry], ["entry"])
        self.assertEqual([event["direction"] for event in exit_events], ["exit"])

    def test_vertical_line_counts_right_to_left_as_entry_and_reverse_as_exit(self):
        counter = OverheadFootfallCounter(
            line_axis="vertical",
            entry_side="negative",
            crossing_cooldown_frames=1,
            crossing_confirm_frames=1,
            min_track_frames=1,
            min_track_motion=0,
        )
        self.assertEqual(counter.update_tracks([box_at_x(75)], 100, 100)[1], [])
        entry = counter.update_tracks([box_at_x(25)], 100, 100)[1]
        exit_events = counter.update_tracks([box_at_x(75)], 100, 100)[1]

        self.assertEqual([event["direction"] for event in entry], ["entry"])
        self.assertEqual([event["direction"] for event in exit_events], ["exit"])

    def test_detection_labels_do_not_overlap_each_other_or_the_count_banner(self):
        import cv2
        import numpy as np

        counter = OverheadFootfallCounter()
        image = np.zeros((120, 240, 3), dtype=np.uint8)
        occupied = [(0, 0, 240, 34)]
        counter._draw_box_label(
            image, "PERSON #1", (20, 35, 80, 90), (0, 200, 255), occupied
        )
        counter._draw_box_label(
            image, "PERSON #2", (25, 40, 85, 95), (0, 200, 255), occupied
        )

        self.assertGreater(len(occupied), 2)
        for index, first in enumerate(occupied):
            for second in occupied[index + 1:]:
                self.assertFalse(
                    first[0] < second[2]
                    and first[2] > second[0]
                    and first[1] < second[3]
                    and first[3] > second[1]
                )
        self.assertEqual(image.shape, (120, 240, 3))

    def test_selects_only_person_class_above_confidence(self):
        detections = [
            {"class_id": 0, "confidence": 0.8, "bbox": [1, 1, 20, 30]},
            {"class_id": 1, "confidence": 0.9, "bbox": [30, 1, 50, 30]},
            {"class_id": 0, "confidence": 0.2, "bbox": [60, 1, 80, 30]},
        ]

        self.assertEqual(
            select_person_detections(detections, 0, 0.25),
            [detections[0]],
        )

    def test_counts_two_simultaneous_tracked_person_crossings(self):
        counter = OverheadFootfallCounter(
            min_track_frames=1,
            min_track_motion=0,
            crossing_confirm_frames=1,
        )
        outside = [
            {"bbox": [20, 10, 40, 40], "class_id": 0, "confidence": 0.9},
            {"bbox": [260, 10, 280, 40], "class_id": 0, "confidence": 0.9},
        ]
        inside = [
            {"bbox": [20, 140, 40, 170], "class_id": 0, "confidence": 0.9},
            {"bbox": [260, 140, 280, 170], "class_id": 0, "confidence": 0.9},
        ]
        counter.update_tracks(outside, 320, 240)
        events = counter.update_tracks(inside, 320, 240)[1]

        self.assertEqual([event["direction"] for event in events], ["entry", "entry"])

    def test_outside_top_to_inside_bottom_is_one_entry_per_track(self):
        counter = OverheadFootfallCounter(
            min_track_frames=1, min_track_motion=0,
        )
        self.assertEqual(counter.update_tracks([box_at(35)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(43)], 100, 100)[1], [])
        events = hold_at(counter, 60)
        self.assertEqual([event["direction"] for event in events], ["entry"])
        self.assertEqual(hold_at(counter, 35), [])

    def test_inside_bottom_to_outside_top_is_an_exit(self):
        counter = OverheadFootfallCounter(
            min_track_frames=1, min_track_motion=0,
        )
        counter.update_tracks([box_at(65)], 100, 100)
        counter.update_tracks([box_at(56)], 100, 100)
        events = hold_at(counter, 35)
        self.assertEqual([event["direction"] for event in events], ["exit"])

    def test_same_track_can_count_entry_then_returning_exit(self):
        counter = OverheadFootfallCounter(
            crossing_cooldown_frames=2,
            min_track_frames=1, min_track_motion=0,
        )
        counter.update_tracks([box_at(35)], 100, 100)
        entry = hold_at(counter, 65)
        counter.update_tracks([box_at(56)], 100, 100)
        exit_events = hold_at(counter, 35)

        self.assertEqual([event["direction"] for event in entry], ["entry"])
        self.assertEqual([event["direction"] for event in exit_events], ["exit"])

    def test_line_jitter_does_not_count_until_opposite_side_is_stable(self):
        counter = OverheadFootfallCounter(
            min_track_frames=1, min_track_motion=0,
        )
        counter.update_tracks([box_at(35)], 100, 100)
        self.assertEqual(counter.update_tracks([box_at(47)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(53)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(47)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(53)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(53)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(65)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(65)], 100, 100)[1], [])
        events = counter.update_tracks([box_at(65)], 100, 100)[1]
        self.assertEqual([event["direction"] for event in events], ["entry"])

    def test_track_bridges_large_frame_gap_during_fast_crossing(self):
        counter = OverheadFootfallCounter(
            min_track_frames=1,
            min_track_motion=0,
            crossing_confirm_frames=2,
        )
        first = box_at(25)
        crossed = box_at(175)
        counter.update_tracks([first], 320, 240)
        events = counter.update_tracks([crossed], 320, 240)[1]

        self.assertEqual([event["direction"] for event in events], ["entry"])

    def test_counts_strong_single_frame_crossing_before_blob_disappears(self):
        counter = OverheadFootfallCounter(
            min_track_frames=2,
            min_track_motion=6,
            crossing_confirm_frames=3,
        )
        counter.update_tracks([box_at(25)], 100, 100)
        events = counter.update_tracks([box_at(75)], 100, 100)[1]

        self.assertEqual([event["direction"] for event in events], ["entry"])

    def test_single_frame_crossing_counts_in_reverse_direction(self):
        counter = OverheadFootfallCounter(
            min_track_frames=2,
            min_track_motion=6,
            crossing_confirm_frames=3,
        )
        counter.update_tracks([box_at(75)], 100, 100)
        events = counter.update_tracks([box_at(25)], 100, 100)[1]

        self.assertEqual([event["direction"] for event in events], ["exit"])

    def test_person_detector_detections_drive_directional_counts(self):
        import numpy as np

        counter = OverheadFootfallCounter(
            min_track_frames=1, min_track_motion=0,
        )
        fake_hog = FakeHOG([35, 45, 60, 60, 60])
        counter._hog = fake_hog
        counter._detector_mode = "hog_person"
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        events = []
        for _ in range(5):
            _, current = counter.process(frame)
            events.extend(current)

        self.assertEqual([event["direction"] for event in events], ["entry"])
        self.assertEqual(fake_hog.calls, 5)

    def test_opencv_hog_initializes_and_processes_a_camera_frame(self):
        import numpy as np

        counter = OverheadFootfallCounter()
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        preview, events = counter.process(frame)

        if counter.detector_mode == "hog_person":
            self.assertTrue(counter.ready)
        else:
            self.assertFalse(counter.ready)
        self.assertEqual(preview.shape, frame.shape)
        self.assertEqual(events, [])
        self.assertIn(counter.detector_mode, {"hog_person", "motion_fallback"})

    def test_missing_hog_detector_uses_motion_fallback(self):
        from unittest.mock import patch
        import cv2
        import numpy as np

        counter = OverheadFootfallCounter(fallback_warmup_frames=2)
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        with (
            patch.object(cv2, "HOGDescriptor", None, create=True),
            patch.object(
                cv2, "HOGDescriptor_getDefaultPeopleDetector", None, create=True
            ),
        ):
            preview, events = counter.process(frame)
            self.assertEqual(counter.detector_mode, "motion_fallback")
            self.assertFalse(counter.ready)
            preview, events = counter.process(frame)
            self.assertTrue(counter.ready)
            preview, events = counter.process(frame)

        self.assertEqual(preview.shape, frame.shape)
        self.assertEqual(events, [])

    def test_motion_fallback_preview_labels_tracks_as_blobs(self):
        from unittest.mock import patch
        import cv2
        import numpy as np

        counter = OverheadFootfallCounter(fallback_warmup_frames=0)
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        with (
            patch.object(cv2, "HOGDescriptor", None, create=True),
            patch.object(
                cv2, "HOGDescriptor_getDefaultPeopleDetector", None, create=True
            ),
        ):
            counter.process(blank)
            moving = blank.copy()
            cv2.rectangle(moving, (110, 80), (200, 180), (255, 255, 255), -1)
            preview, _ = counter.process(moving)

        self.assertEqual(preview.shape, blank.shape)
        self.assertEqual(counter.detector_mode, "motion_fallback")

    def test_motion_fallback_counts_a_persistent_crossing_blob(self):
        from unittest.mock import patch
        import cv2
        import numpy as np

        counter = OverheadFootfallCounter(
            min_area_ratio=0.001,
            min_track_frames=1,
            min_track_motion=0,
            fallback_warmup_frames=3,
            crossing_confirm_frames=1,
            line_deadband_ratio=0.01,
        )
        blank = np.zeros((240, 320, 3), dtype=np.uint8)
        events = []
        with (
            patch.object(cv2, "HOGDescriptor", None, create=True),
            patch.object(
                cv2, "HOGDescriptor_getDefaultPeopleDetector", None, create=True
            ),
        ):
            for _ in range(counter.fallback_warmup_frames):
                counter.process(blank)
            self.assertTrue(counter.ready)
            for center_y in range(55, 191, 15):
                frame = blank.copy()
                cv2.ellipse(
                    frame, (160, center_y), (30, 35), 0, 0, 360,
                    (220, 220, 220), -1,
                )
                _, current = counter.process(frame)
                events.extend(current)

        self.assertEqual([event["direction"] for event in events], ["entry"])

    def test_waits_for_persistent_moving_track_before_counting(self):
        counter = OverheadFootfallCounter(
            min_track_frames=3, min_track_motion=10,
        )
        self.assertEqual(counter.update_tracks([box_at(35)], 100, 100)[1], [])
        self.assertEqual(counter.update_tracks([box_at(45)], 100, 100)[1], [])
        events = counter.update_tracks([box_at(60)], 100, 100)[1]

        self.assertEqual([event["direction"] for event in events], ["entry"])

    def test_motion_candidate_filters_accept_overhead_person_shapes(self):
        counter = OverheadFootfallCounter()

        self.assertTrue(counter.accept_motion_candidate(2.6, 0.6, 0.25))
        self.assertFalse(counter.accept_motion_candidate(3.2, 0.9, 0.6))
        self.assertFalse(counter.accept_motion_candidate(1.0, 0.4, 0.6))
        self.assertFalse(counter.accept_motion_candidate(1.0, 0.9, 0.1))

    def test_stationary_person_does_not_create_repeated_crossings(self):
        import numpy as np

        counter = OverheadFootfallCounter(
            min_track_frames=1, min_track_motion=0,
        )
        counter._hog = FakeHOG([35, 60, 60, 60, 60, 60])
        counter._detector_mode = "hog_person"
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        events = []
        for _ in range(6):
            _, current = counter.process(frame)
            events.extend(current)

        self.assertEqual([event["direction"] for event in events], ["entry"])

    def test_persists_daily_entry_and_exit_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory) / "footfall.sqlite"
            store = DailyFootfallStore(database_path)
            store.record("usb-01", "entry")
            store.record("usb-01", "entry")
            store.record("usb-01", "exit")
            store.close()

            reopened = DailyFootfallStore(database_path)
            try:
                summary = reopened.snapshot(["usb-01"])
            finally:
                reopened.close()

        self.assertEqual(summary["state"], "AVAILABLE")
        self.assertEqual(summary["total_entries"], 2)
        self.assertEqual(summary["total_exits"], 1)
        self.assertEqual(summary["cameras"]["usb-01"], {"entries": 2, "exits": 1})


if __name__ == "__main__":
    unittest.main()
