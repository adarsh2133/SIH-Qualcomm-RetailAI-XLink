"""Camera-local, frame-to-frame object tracking."""
from __future__ import annotations

from math import hypot, isfinite
from typing import Any, Dict, Mapping, Sequence


class ObjectTracker:
    def __init__(
        self,
        max_tracks: int = 32,
        max_distance: float = 60.0,
        max_missed_frames: int = 8,
    ) -> None:
        if max_tracks < 1:
            raise ValueError("max_tracks must be positive")
        if not isfinite(max_distance) or max_distance < 0:
            raise ValueError("max_distance must be finite and non-negative")
        if max_missed_frames < 0:
            raise ValueError("max_missed_frames cannot be negative")
        self.max_tracks = max_tracks
        self.max_distance = float(max_distance)
        self.max_missed_frames = max_missed_frames
        self.active_tracks: Dict[int, Dict[str, Any]] = {}
        self.next_id = 1

    def register(
        self,
        position: Sequence[float],
        confidence: float = 0.0,
        class_id: int | None = None,
        bbox: Sequence[float] | None = None,
    ) -> int:
        x, y = self._position(position)
        self._validate_confidence(confidence)
        if len(self.active_tracks) >= self.max_tracks:
            del self.active_tracks[next(iter(self.active_tracks))]
        track_id = self.next_id
        self.next_id += 1
        self.active_tracks[track_id] = {
            "x": x,
            "y": y,
            "confidence": float(confidence),
            "class_id": class_id,
            "bbox": list(bbox) if bbox is not None else None,
            "missed_frames": 0,
        }
        return track_id

    def update(
        self,
        track_id: int,
        position: Sequence[float],
        confidence: float,
        class_id: int | None = None,
        bbox: Sequence[float] | None = None,
    ) -> None:
        state = self.active_tracks.get(track_id)
        if state is None:
            return
        x, y = self._position(position)
        self._validate_confidence(confidence)
        state.update({
            "x": x,
            "y": y,
            "confidence": float(confidence),
            "missed_frames": 0,
        })
        if class_id is not None:
            state["class_id"] = class_id
        if bbox is not None:
            state["bbox"] = list(bbox)

    def get_active_tracks(self) -> list[Dict[str, Any]]:
        return [
            {"track_id": track_id, **state.copy()}
            for track_id, state in sorted(self.active_tracks.items())
        ]

    def update_detections(
        self, detections: Sequence[Mapping[str, object]]
    ) -> list[Dict[str, Any]]:
        parsed = [self._parse_detection(detection) for detection in detections]
        candidates: list[tuple[float, int, int]] = []
        for detection_index, detection in enumerate(parsed):
            for track_id, state in self.active_tracks.items():
                old_class = state["class_id"]
                new_class = detection["class_id"]
                if old_class is not None and new_class is not None and old_class != new_class:
                    continue
                distance = hypot(
                    float(state["x"]) - detection["x"],
                    float(state["y"]) - detection["y"],
                )
                if distance <= self.max_distance:
                    candidates.append((distance, detection_index, track_id))

        assignments: dict[int, int] = {}
        used_tracks: set[int] = set()
        for _, detection_index, track_id in sorted(candidates):
            if detection_index in assignments or track_id in used_tracks:
                continue
            assignments[detection_index] = track_id
            used_tracks.add(track_id)

        for track_id, state in list(self.active_tracks.items()):
            if track_id not in used_tracks:
                state["missed_frames"] += 1
                if state["missed_frames"] > self.max_missed_frames:
                    del self.active_tracks[track_id]

        tracked: list[Dict[str, Any]] = []
        for detection_index, detection in enumerate(parsed):
            track_id = assignments.get(detection_index)
            if track_id is None:
                if len(self.active_tracks) >= self.max_tracks:
                    evictable = [
                        candidate_id for candidate_id in self.active_tracks
                        if candidate_id not in used_tracks
                    ]
                    if not evictable:
                        tracked.append({
                            "track_id": None,
                            "tracked": False,
                            **detection,
                        })
                        continue
                    oldest = max(
                        evictable,
                        key=lambda candidate_id: (
                            self.active_tracks[candidate_id]["missed_frames"],
                            -candidate_id,
                        ),
                    )
                    del self.active_tracks[oldest]
                track_id = self.register(
                    (detection["x"], detection["y"]),
                    detection["confidence"],
                    detection["class_id"],
                    detection["bbox"],
                )
                used_tracks.add(track_id)
            else:
                self.update(
                    track_id,
                    (detection["x"], detection["y"]),
                    detection["confidence"],
                    detection["class_id"],
                    detection["bbox"],
                )
            tracked.append({
                "track_id": track_id,
                "tracked": True,
                **self.active_tracks[track_id].copy(),
            })
        return tracked

    @staticmethod
    def _position(position: Sequence[float]) -> tuple[float, float]:
        if len(position) != 2:
            raise ValueError("position must contain x and y coordinates")
        x, y = float(position[0]), float(position[1])
        if not isfinite(x) or not isfinite(y):
            raise ValueError("position coordinates must be finite")
        return x, y

    @staticmethod
    def _validate_confidence(confidence: float) -> None:
        value = float(confidence)
        if not isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("confidence must be finite and between 0 and 1")

    @classmethod
    def _parse_detection(cls, detection: Mapping[str, object]) -> Dict[str, Any]:
        bbox = detection.get("bbox")
        if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
            raise ValueError("each detection must have a four-coordinate bbox")
        coordinates = [float(value) for value in bbox]
        if not all(isfinite(value) for value in coordinates):
            raise ValueError("bbox coordinates must be finite")
        left, top, right, bottom = coordinates
        if right <= left or bottom <= top:
            raise ValueError("bbox must have positive width and height")
        confidence = detection.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)):
            raise ValueError("confidence must be numeric")
        cls._validate_confidence(float(confidence))
        class_id = detection.get("class_id")
        if class_id is not None and (
            not isinstance(class_id, int) or isinstance(class_id, bool)
        ):
            raise ValueError("class_id must be an integer when provided")
        return {
            "x": (left + right) / 2.0,
            "y": bottom,
            "bbox": coordinates,
            "confidence": float(confidence),
            "class_id": class_id,
        }
