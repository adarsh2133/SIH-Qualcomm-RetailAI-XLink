"""OpenCV person detection and directional footfall counting."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .tracker import ObjectTracker


def select_person_detections(
    detections: list[dict[str, Any]],
    class_id: int = 0,
    confidence_threshold: float = 0.25,
) -> list[dict[str, Any]]:
    if class_id < 0:
        raise ValueError("person class_id cannot be negative")
    if not 0 <= confidence_threshold <= 1:
        raise ValueError("confidence_threshold must be between 0 and 1")
    selected = []
    for detection in detections:
        if not isinstance(detection, dict):
            raise ValueError("each model detection must be an object")
        confidence = detection.get("confidence")
        detected_class = detection.get("class_id")
        if not isinstance(confidence, (int, float)) or not isinstance(
            detected_class, int
        ):
            raise ValueError("model detection requires numeric confidence and class_id")
        if detected_class == class_id and confidence >= confidence_threshold:
            selected.append(detection)
    return selected


@dataclass
class OverheadFootfallCounter:
    line_ratio: float = 0.5
    line_axis: str = "horizontal"
    entry_side: str = "positive"
    min_area_ratio: float = 0.003
    max_area_ratio: float = 0.28
    min_solidity: float = 0.55
    min_track_frames: int = 2
    min_track_motion: float = 6.0
    fallback_warmup_frames: int = 30
    tracker: ObjectTracker = field(default_factory=lambda: ObjectTracker(
        max_tracks=32, max_distance=85, max_missed_frames=10,
    ))
    frames_seen: int = 0
    last_detection_count: int = 0
    last_track_count: int = 0
    _cv2: Any = field(default=None, init=False, repr=False)
    _hog: Any = field(default=None, init=False, repr=False)
    _subtractor: Any = field(default=None, init=False, repr=False)
    _detector_mode: str | None = field(default=None, init=False, repr=False)
    _stable_sides: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _candidate_sides: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _candidate_frames: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _last_crossing_frame: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _track_observations: dict[int, int] = field(default_factory=dict, init=False, repr=False)
    _track_motion: dict[int, float] = field(default_factory=dict, init=False, repr=False)
    _track_positions: dict[int, tuple[float, float]] = field(default_factory=dict, init=False, repr=False)
    _pending_crossings: dict[int, list[str]] = field(default_factory=dict, init=False, repr=False)
    crossing_cooldown_frames: int = 8
    crossing_confirm_frames: int = 3
    line_deadband_ratio: float = 0.025

    def __post_init__(self) -> None:
        if not 0.1 <= self.line_ratio <= 0.9:
            raise ValueError("line_ratio must be between 0.1 and 0.9")
        if self.line_axis not in {"horizontal", "vertical"}:
            raise ValueError("line_axis must be horizontal or vertical")
        if self.entry_side not in {"negative", "positive"}:
            raise ValueError("entry_side must be negative or positive")
        if not 0 < self.min_area_ratio < self.max_area_ratio < 1:
            raise ValueError("area ratios must satisfy 0 < min_area_ratio < max_area_ratio < 1")
        if not 0.5 <= self.min_solidity <= 1:
            raise ValueError("min_solidity must be between 0.5 and 1")
        if self.min_track_frames < 1:
            raise ValueError("min_track_frames must be positive")
        if self.min_track_motion < 0:
            raise ValueError("min_track_motion cannot be negative")
        if self.fallback_warmup_frames < 0:
            raise ValueError("fallback_warmup_frames cannot be negative")
        if self.crossing_cooldown_frames < 0:
            raise ValueError("crossing_cooldown_frames cannot be negative")
        if self.crossing_confirm_frames < 1:
            raise ValueError("crossing_confirm_frames must be positive")
        if not 0.005 <= self.line_deadband_ratio <= 0.1:
            raise ValueError("line_deadband_ratio must be between 0.005 and 0.1")

    @property
    def ready(self) -> bool:
        if self._detector_mode == "motion_fallback":
            return self.frames_seen >= self.fallback_warmup_frames
        return self._detector_mode in {"hog_person", "ncnn_person"}

    @property
    def detector_mode(self) -> str:
        return self._detector_mode or "initializing"

    def enable_ncnn_person_mode(self) -> None:
        self._detector_mode = "ncnn_person"
        self._hog = None
        self._subtractor = None

    def process_person_detections(
        self, image: Any, detections: list[dict[str, Any]]
    ) -> tuple[Any, list[dict[str, Any]]]:
        if self._detector_mode is None:
            self.enable_ncnn_person_mode()
        if self._detector_mode != "ncnn_person":
            raise RuntimeError(
                "NCNN person detections cannot be mixed with the active "
                f"{self._detector_mode} detector"
            )
        height, width = image.shape[:2]
        tracked, events = self.update_tracks(detections, width, height)
        self.last_detection_count = len(detections)
        self.last_track_count = len(tracked)
        return self._annotate(image, detections, tracked, "PERSON"), events

    def process(self, image: Any) -> tuple[Any, list[dict[str, Any]]]:
        import cv2

        if self._detector_mode == "ncnn_person":
            raise RuntimeError(
                "NCNN person mode requires detections from its NCNN model"
            )
        if self._detector_mode is None:
            self._cv2 = cv2
            hog_type = getattr(cv2, "HOGDescriptor", None)
            hog_model = getattr(cv2, "HOGDescriptor_getDefaultPeopleDetector", None)
            if callable(hog_type) and callable(hog_model):
                self._hog = hog_type()
                self._hog.setSVMDetector(hog_model())
                self._detector_mode = "hog_person"
            else:
                self._hog = None
                self._subtractor = cv2.createBackgroundSubtractorMOG2(
                    history=max(120, self.fallback_warmup_frames),
                    varThreshold=24,
                    detectShadows=False,
                )
                self._detector_mode = "motion_fallback"
        height, width = image.shape[:2]
        line_coordinate = self._line_coordinate(width, height)

        processing_width = min(width, 320)
        processing_height = max(1, round(height * processing_width / width))
        processing_image = (
            cv2.resize(
                image,
                (processing_width, processing_height),
                interpolation=cv2.INTER_AREA,
            )
            if processing_width != width else image
        )
        processing_scale = width / processing_width
        detections = []
        if self._detector_mode == "hog_person":
            locations, weights = self._hog.detectMultiScale(
                processing_image,
                0.0,
                (8, 8),
                (8, 8),
                1.05,
                2,
                False,
            )
            for (x, y, box_width, box_height), weight in zip(locations, weights):
                detections.append({
                    "bbox": [
                        round(x * processing_scale),
                        round(y * processing_scale),
                        round((x + box_width) * processing_scale),
                        round((y + box_height) * processing_scale),
                    ],
                    "class_id": 0,
                    "confidence": round(
                        max(0.0, min(1.0, (float(weight) + 1.0) / 3.0)), 3
                    ),
                })
        else:
            if not self.ready:
                self._subtractor.apply(processing_image, learningRate=0.05)
                self.frames_seen += 1
                preview = image.copy()
                self.last_detection_count = 0
                self.last_track_count = 0
                cv2.putText(
                    preview,
                    f"MOTION FALLBACK CALIBRATING "
                    f"{self.frames_seen}/{self.fallback_warmup_frames}",
                    (12, 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 2, cv2.LINE_AA,
                )
                self._draw_counting_line(preview)
                return preview, []

            mask = self._subtractor.apply(processing_image, learningRate=0.0)
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
            mask = cv2.dilate(mask, kernel, iterations=1)
            contours, _ = cv2.findContours(
                mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            frame_area = processing_image.shape[0] * processing_image.shape[1]
            minimum_area = max(250.0, frame_area * self.min_area_ratio)
            maximum_area = frame_area * self.max_area_ratio
            for contour in contours:
                area = cv2.contourArea(contour)
                if area < minimum_area or area > maximum_area:
                    continue
                x, y, box_width, box_height = cv2.boundingRect(contour)
                if box_width <= 0 or box_height <= 0:
                    continue
                hull_area = cv2.contourArea(cv2.convexHull(contour))
                solidity = area / hull_area if hull_area else 0.0
                extent = area / (box_width * box_height)
                aspect_ratio = box_width / box_height
                if not self.accept_motion_candidate(aspect_ratio, solidity, extent):
                    continue
                detections.append({
                    "bbox": [
                        round(x * processing_scale),
                        round(y * processing_scale),
                        round((x + box_width) * processing_scale),
                        round((y + box_height) * processing_scale),
                    ],
                    "class_id": 0,
                    "confidence": round(solidity * extent, 3),
                })

        tracked, events = self.update_tracks(detections, width, height)
        self.last_detection_count = len(detections)
        self.last_track_count = len(tracked)
        label = "PERSON" if self._detector_mode == "hog_person" else "BLOB"
        return self._annotate(image, detections, tracked, label), events

    def _annotate(
        self,
        image: Any,
        detections: list[dict[str, Any]],
        tracked: list[dict[str, Any]],
        label: str,
    ) -> Any:
        import cv2

        height, width = image.shape[:2]
        preview = image.copy()
        self._draw_counting_line(preview)
        label_regions = [(0, 0, width, 34)]
        tracked_boxes = {
            tuple(int(value) for value in track["bbox"])
            for track in tracked
            if isinstance(track.get("bbox"), list)
        }
        for detection in detections:
            bbox = detection["bbox"]
            if tuple(bbox) in tracked_boxes:
                continue
            left, top, right, bottom = (int(value) for value in bbox)
            cv2.rectangle(preview, (left, top), (right, bottom), (255, 180, 0), 1)
            self._draw_box_label(
                preview,
                f"{label} CANDIDATE",
                (left, top, right, bottom),
                (255, 180, 0),
                label_regions,
            )
        for track in tracked:
            bbox = track.get("bbox")
            if not isinstance(bbox, list):
                continue
            left, top, right, bottom = (int(value) for value in bbox)
            cv2.rectangle(preview, (left, top), (right, bottom), (0, 200, 255), 2)
            self._draw_box_label(
                preview,
                f"{label} #{track['track_id']}",
                (left, top, right, bottom),
                (0, 200, 255),
                label_regions,
            )
        return preview

    @staticmethod
    def _draw_box_label(
        image: Any,
        text: str,
        bbox: tuple[int, int, int, int],
        color: tuple[int, int, int],
        occupied_regions: list[tuple[int, int, int, int]],
    ) -> None:
        import cv2

        height, width = image.shape[:2]
        (text_width, text_height), baseline = cv2.getTextSize(
            text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1
        )
        left, top, right, bottom = bbox
        candidates = (
            (left, top - 4),
            (left, bottom + text_height + baseline + 4),
            (left, top + text_height + baseline + 4),
        )
        for x, y in candidates:
            x = min(max(0, x), max(0, width - text_width - 8))
            text_left, text_top = x, y - text_height - baseline
            region = (
                text_left - 3,
                text_top - 2,
                text_left + text_width + 3,
                y + 2,
            )
            if (
                region[1] < 0
                or region[3] >= height
                or any(
                    region[0] < other[2]
                    and region[2] > other[0]
                    and region[1] < other[3]
                    and region[3] > other[1]
                    for other in occupied_regions
                )
            ):
                continue
            cv2.rectangle(
                image, (region[0], region[1]), (region[2], region[3]),
                (0, 0, 0), cv2.FILLED,
            )
            cv2.putText(
                image, text, (x, y), cv2.FONT_HERSHEY_SIMPLEX,
                0.4, color, 1, cv2.LINE_AA,
            )
            occupied_regions.append(region)
            return

    def _line_coordinate(self, width: int, height: int) -> int:
        axis_length = width if self.line_axis == "vertical" else height
        return round(axis_length * self.line_ratio)

    def _draw_counting_line(self, image: Any) -> None:
        import cv2

        height, width = image.shape[:2]
        coordinate = self._line_coordinate(width, height)
        if self.line_axis == "vertical":
            cv2.line(image, (coordinate, 0), (coordinate, height - 1), (0, 255, 255), 2)
        else:
            cv2.line(image, (0, coordinate), (width - 1, coordinate), (0, 255, 255), 2)

    def update_tracks(
        self,
        detections: list[dict[str, Any]],
        width: int,
        height: int,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        self.frames_seen += 1
        line_coordinate = self._line_coordinate(width, height)
        axis_length = width if self.line_axis == "vertical" else height
        deadband = max(4.0, axis_length * self.line_deadband_ratio)
        self.tracker.max_distance = max(100.0, max(width, height) * 0.7)
        tracked = self.tracker.update_detections(detections)
        active_ids = {
            int(track["track_id"]) for track in self.tracker.get_active_tracks()
        }
        tracked_ids = (
            self._last_crossing_frame.keys()
            | self._stable_sides.keys()
            | self._candidate_sides.keys()
            | self._track_observations.keys()
            | self._track_motion.keys()
            | self._track_positions.keys()
            | self._pending_crossings.keys()
        )
        for expired_id in tracked_ids - active_ids:
            self._last_crossing_frame.pop(expired_id, None)
            self._stable_sides.pop(expired_id, None)
            self._candidate_sides.pop(expired_id, None)
            self._candidate_frames.pop(expired_id, None)
            self._track_observations.pop(expired_id, None)
            self._track_motion.pop(expired_id, None)
            self._track_positions.pop(expired_id, None)
            self._pending_crossings.pop(expired_id, None)

        events = []
        confirmed_tracks = []
        for track in tracked:
            track_id = track.get("track_id")
            bbox = track.get("bbox")
            if not isinstance(track_id, int) or not isinstance(bbox, list):
                continue
            left, top, right, bottom = (int(value) for value in bbox)
            center_x = (left + right) // 2
            # Use the detected person's center so a box edge does not trigger
            # a crossing before the person has passed the threshold.
            center_y = (top + bottom) // 2
            previous_position = self._track_positions.get(track_id)
            if previous_position is not None:
                delta_x = center_x - previous_position[0]
                delta_y = center_y - previous_position[1]
                self._track_motion[track_id] = (
                    self._track_motion.get(track_id, 0.0)
                    + (delta_x * delta_x + delta_y * delta_y) ** 0.5
                )
            self._track_positions[track_id] = (center_x, center_y)
            self._track_observations[track_id] = (
                self._track_observations.get(track_id, 0) + 1
            )
            position_on_axis = center_x if self.line_axis == "vertical" else center_y
            previous_axis_position = (
                previous_position[0]
                if previous_position is not None and self.line_axis == "vertical"
                else previous_position[1]
                if previous_position is not None
                else None
            )
            distance_from_line = position_on_axis - line_coordinate
            observed_side = (
                -1 if distance_from_line < -deadband
                else 1 if distance_from_line > deadband
                else 0
            )
            stable_side = self._stable_sides.get(track_id)
            if stable_side is None and observed_side:
                self._stable_sides[track_id] = observed_side
                stable_side = observed_side

            direction = None
            if observed_side == 0 or observed_side == stable_side:
                self._candidate_sides.pop(track_id, None)
                self._candidate_frames.pop(track_id, None)
            elif observed_side:
                jumped_across_line = (
                    previous_axis_position is not None
                    and (previous_axis_position - line_coordinate) * distance_from_line < 0
                    and abs(position_on_axis - previous_axis_position)
                    >= max(2.0 * deadband, axis_length * 0.1)
                    and abs(previous_axis_position - line_coordinate) >= axis_length * 0.05
                    and abs(distance_from_line) >= axis_length * 0.05
                )
                if jumped_across_line:
                    direction = (
                        "entry"
                        if observed_side == (-1 if self.entry_side == "negative" else 1)
                        else "exit"
                    )
                    self._stable_sides[track_id] = observed_side
                    self._candidate_sides.pop(track_id, None)
                    self._candidate_frames.pop(track_id, None)
                elif self._candidate_sides.get(track_id) != observed_side:
                    self._candidate_sides[track_id] = observed_side
                    self._candidate_frames[track_id] = 1
                else:
                    self._candidate_frames[track_id] += 1
                if not jumped_across_line:
                    if self._candidate_frames[track_id] >= self.crossing_confirm_frames:
                        direction = (
                            "entry"
                            if observed_side == (-1 if self.entry_side == "negative" else 1)
                            else "exit"
                        )
                        self._stable_sides[track_id] = observed_side
                        self._candidate_sides.pop(track_id, None)
                        self._candidate_frames.pop(track_id, None)
            last_crossing = self._last_crossing_frame.get(track_id, -self.crossing_cooldown_frames)
            if (
                direction
                and self.frames_seen - last_crossing >= self.crossing_cooldown_frames
            ):
                self._pending_crossings.setdefault(track_id, []).append(
                    direction
                )
                self._last_crossing_frame[track_id] = self.frames_seen
            observed_long_enough = (
                self._track_observations[track_id] >= self.min_track_frames
            )
            moved_enough = self._track_motion.get(track_id, 0.0) >= self.min_track_motion
            if observed_long_enough and moved_enough:
                confirmed_tracks.append(track)
            pending = self._pending_crossings.get(track_id, [])
            if observed_long_enough and moved_enough and pending:
                for pending_direction in pending:
                    events.append({
                        "direction": pending_direction,
                        "track_id": track_id,
                    })
                pending.clear()
        return confirmed_tracks, events

    def accept_motion_candidate(
        self, aspect_ratio: float, solidity: float, extent: float
    ) -> bool:
        return (
            0.3 <= aspect_ratio <= 3.0
            and solidity >= self.min_solidity
            and 0.2 <= extent <= 0.95
        )


def create_footfall_counter_from_env() -> OverheadFootfallCounter:
    import os

    def read_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)))
        except ValueError as exc:
            raise ValueError(f"{name} must be a number") from exc

    def read_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc

    return OverheadFootfallCounter(
        line_ratio=read_float("PORTAL_FOOTFALL_LINE_RATIO", 0.5),
        line_axis=os.getenv("PORTAL_FOOTFALL_LINE_AXIS", "horizontal").strip().lower(),
        entry_side=os.getenv("PORTAL_FOOTFALL_ENTRY_SIDE", "negative").strip().lower(),
        min_area_ratio=read_float("PORTAL_FOOTFALL_MIN_AREA_RATIO", 0.008),
        max_area_ratio=read_float("PORTAL_FOOTFALL_MAX_AREA_RATIO", 0.18),
        min_solidity=read_float("PORTAL_FOOTFALL_MIN_SOLIDITY", 0.72),
        min_track_frames=read_int("PORTAL_FOOTFALL_MIN_TRACK_FRAMES", 2),
        min_track_motion=read_float("PORTAL_FOOTFALL_MIN_TRACK_MOTION", 6.0),
        fallback_warmup_frames=read_int("PORTAL_FOOTFALL_BACKGROUND_FRAMES", 30),
        crossing_cooldown_frames=read_int("PORTAL_FOOTFALL_CROSSING_COOLDOWN_FRAMES", 8),
        crossing_confirm_frames=read_int("PORTAL_FOOTFALL_CROSSING_CONFIRM_FRAMES", 2),
        line_deadband_ratio=read_float("PORTAL_FOOTFALL_LINE_DEADBAND_RATIO", 0.015),
    )
