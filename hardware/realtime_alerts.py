"""Stateful alerts for detections, shelf counts, and Pi runtime health."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import time
from typing import Any


class RealtimeAlertManager:
    def __init__(self, detection_rearm_s: float = 1.5,
                 history_limit: int = 30) -> None:
        self.detection_rearm_s = max(0.0, detection_rearm_s)
        self._active: dict[str, dict[str, Any]] = {}
        self._events: deque[dict[str, Any]] = deque(maxlen=max(1, history_limit))
        self._detection_missing_since: dict[str, float] = {}

    @staticmethod
    def _key(category: str, camera_id: str, class_id: int | None = None) -> str:
        suffix = "" if class_id is None else f":{class_id}"
        return f"{category}:{camera_id}{suffix}"

    def _activate(self, key: str, category: str, severity: str,
                  message: str, camera_id: str,
                  class_id: int | None = None) -> None:
        if key in self._active:
            self._active[key]["message"] = message
            self._active[key]["updated_at"] = datetime.now(timezone.utc).isoformat()
            return
        now = datetime.now(timezone.utc).isoformat()
        event = {
            "id": f"{key}:{time.time_ns()}",
            "category": category,
            "severity": severity,
            "message": message,
            "camera_id": camera_id,
            "class_id": class_id,
            "created_at": now,
        }
        self._active[key] = {**event, "updated_at": now}
        self._events.append(event)

    def _deactivate(self, key: str) -> None:
        self._active.pop(key, None)

    def update_camera(self, camera_id: str, camera_state: str,
                      inference_state: str) -> None:
        camera_key = self._key("camera_failure", camera_id)
        camera_failed = camera_state not in {"ONLINE", "DEGRADED"}
        if camera_failed:
            self._activate(
                camera_key, "camera_failure", "critical",
                f"Camera {camera_id} is {camera_state.lower()}.",
                camera_id,
            )
        else:
            self._deactivate(camera_key)

        inference_key = self._key("inference_failure", camera_id)
        inference_failed = inference_state in {"ERROR", "UNAVAILABLE", "DEGRADED"}
        if inference_failed:
            self._activate(
                inference_key, "inference_failure", "critical",
                f"Inference is {inference_state.lower()} on {camera_id}.",
                camera_id,
            )
        else:
            self._deactivate(inference_key)

    def update_detections(self, camera_id: str,
                          detections: list[dict[str, Any]],
                          valid: bool) -> None:
        if not valid:
            return
        now = time.monotonic()
        by_class: dict[int, list[dict[str, Any]]] = {}
        for detection in detections:
            class_id = detection.get("class_id")
            if isinstance(class_id, int):
                by_class.setdefault(class_id, []).append(detection)

        for class_id, items in by_class.items():
            key = self._key("detection", camera_id, class_id)
            confidence = max(
                (float(item.get("confidence", 0.0)) for item in items),
                default=0.0,
            )
            self._activate(
                key, "detection", "info",
                f"Class {class_id} detected on {camera_id} "
                f"({len(items)} item(s), confidence {confidence:.0%}).",
                camera_id, class_id,
            )
            self._detection_missing_since.pop(key, None)

        detection_keys = [
            key for key in self._active
            if key.startswith(f"detection:{camera_id}:")
        ]
        for key in detection_keys:
            if key in {
                self._key("detection", camera_id, class_id)
                for class_id in by_class
            }:
                continue
            missing_since = self._detection_missing_since.setdefault(key, now)
            if now - missing_since >= self.detection_rearm_s:
                self._deactivate(key)
                self._detection_missing_since.pop(key, None)

    def clear_camera_detections(self, camera_id: str) -> None:
        prefix = f"detection:{camera_id}:"
        for key in list(self._active):
            if key.startswith(prefix):
                self._deactivate(key)
                self._detection_missing_since.pop(key, None)

    def snapshot(self) -> dict[str, list[dict[str, Any]]]:
        active = sorted(
            (dict(alert) for alert in self._active.values()),
            key=lambda alert: alert["created_at"],
            reverse=True,
        )
        events = sorted(
            (dict(alert) for alert in self._events),
            key=lambda alert: alert["created_at"],
            reverse=True,
        )
        return {"alerts": active, "alert_events": events}
