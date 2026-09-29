"""Background polling client for detection data published by a Raspberry Pi."""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from io import BytesIO
from typing import Any, Dict
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request

from .base_inference import BaseInferenceEngine
from secure_http import open_request


class RemoteInferenceEngine(BaseInferenceEngine):
    def __init__(self, base_url: str | None = None, token: str | None = None,
                 poll_interval_s: float | None = None) -> None:
        self.base_url = (
            base_url or os.getenv(
                "PORTAL_REMOTE_API_URL", "https://storesense.local:8765"
            )
        ).rstrip("/")
        self.token = token if token is not None else os.getenv("PORTAL_API_TOKEN", "")
        self.certificate_sha256 = os.getenv("PORTAL_API_CERT_SHA256", "")
        try:
            interval = float(poll_interval_s if poll_interval_s is not None else
                             os.getenv("PORTAL_REMOTE_POLL_INTERVAL_S", "0.5"))
        except ValueError:
            interval = 1.0
        self.poll_interval_s = max(0.2, interval)
        self._lock = threading.Lock()
        self._camera_frames: dict[str, Any] = {}
        self._preview_errors: dict[str, str] = {}
        self._preview_alerts: dict[str, dict[str, Any]] = {}
        self._preview_alert_events: list[dict[str, Any]] = []
        self._preview_threads: dict[str, threading.Thread] = {}
        self._connection_alert: dict[str, Any] | None = None
        self._connection_events: list[dict[str, Any]] = []
        self._snapshot: dict[str, Any] = {
            "state": "UNAVAILABLE",
            "detections": [],
            "cameras": [],
            "error": "PORTAL_REMOTE_API_URL is not configured" if not self.base_url else "",
        }
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if self.base_url:
            if not self.token:
                self._set_error("PORTAL_API_TOKEN is not configured")
            else:
                self._thread = threading.Thread(target=self._poll, daemon=True)
                self._thread.start()

    @property
    def name(self) -> str:
        return "Raspberry Pi remote detections"

    def _poll(self) -> None:
        endpoint = f"{self.base_url}/api/v1/detections"
        while not self._stop.is_set():
            try:
                request = Request(endpoint, headers={"Authorization": f"Bearer {self.token}"})
                with open_request(
                    request, timeout=3, fingerprint=self.certificate_sha256
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Pi API response must be a JSON object")
                detections = payload.get("detections")
                if not isinstance(detections, list):
                    raise ValueError("Pi API response is missing its detections list")
                for detection in detections:
                    if not isinstance(detection, dict):
                        raise ValueError("Pi API returned a malformed detection")
                    bbox = detection.get("bbox")
                    confidence = detection.get("confidence")
                    if (
                        not isinstance(detection.get("camera_id"), str)
                        or not isinstance(detection.get("class_id"), int)
                        or not isinstance(confidence, (int, float))
                        or not isinstance(bbox, list)
                        or len(bbox) != 4
                        or not all(isinstance(value, (int, float)) for value in bbox)
                    ):
                        raise ValueError("Pi API returned a malformed detection")
                camera_status = payload.get("camera_status", [])
                if not isinstance(camera_status, list):
                    raise ValueError("Pi API camera_status must be a list")
                if not isinstance(payload.get("alerts", []), list):
                    raise ValueError("Pi API alerts must be a list")
                if not isinstance(payload.get("alert_events", []), list):
                    raise ValueError("Pi API alert_events must be a list")
                with self._lock:
                    self._snapshot = {
                        **payload,
                        "error": "",
                        "api_state": "AVAILABLE",
                    }
                    self._connection_alert = None
                self._ensure_preview_threads(camera_status)
            except HTTPError as exc:
                error = f"Pi API returned HTTP {exc.code}"
                self._set_error(error)
            except (URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
                self._set_error(str(exc))
            self._stop.wait(self.poll_interval_s)

    def _ensure_preview_threads(self, camera_status: list[dict[str, Any]]) -> None:
        camera_ids = {
            camera.get("camera_id")
            for camera in camera_status
            if isinstance(camera, dict)
            and camera.get("state") in {"ONLINE", "DEGRADED"}
            and isinstance(camera.get("camera_id"), str)
        }
        with self._lock:
            for camera_id in set(self._camera_frames) - camera_ids:
                self._camera_frames.pop(camera_id, None)
            for camera_id in camera_ids:
                thread = self._preview_threads.get(camera_id)
                if thread is None or not thread.is_alive():
                    thread = threading.Thread(
                        target=self._read_camera_stream,
                        args=(camera_id,),
                        daemon=True,
                        name=f"pi-preview-{camera_id}",
                    )
                    self._preview_threads[camera_id] = thread
                    thread.start()

    def _read_camera_stream(self, camera_id: str) -> None:
        try:
            from PIL import Image
        except ImportError as exc:
            self._set_preview_error(
                camera_id, f"Pillow is required for previews: {exc}"
            )
            return

        endpoint = (
            f"{self.base_url}/api/v1/camera-stream"
            f"?camera_id={quote(camera_id, safe='')}"
        )
        while not self._stop.is_set():
            try:
                request = Request(
                    endpoint,
                    headers={"Authorization": f"Bearer {self.token}"},
                )
                with open_request(
                    request, timeout=15, fingerprint=self.certificate_sha256
                ) as response:
                    if response.headers.get_content_type() != "multipart/x-mixed-replace":
                        raise ValueError("Pi preview endpoint did not return an MJPEG stream")
                    while not self._stop.is_set():
                        boundary = response.readline()
                        if not boundary:
                            raise ConnectionError("Pi preview stream closed")
                        if not boundary.strip().startswith(b"--"):
                            continue
                        headers = {}
                        while True:
                            line = response.readline()
                            if not line:
                                raise ConnectionError("Pi preview frame ended unexpectedly")
                            if line in {b"\r\n", b"\n"}:
                                break
                            key, separator, value = line.decode("ascii").partition(":")
                            if separator:
                                headers[key.strip().lower()] = value.strip()
                        content_length = int(headers.get("content-length", "0"))
                        if content_length <= 0:
                            raise ValueError("Pi preview frame has no content length")
                        encoded = response.read(content_length)
                        response.read(2)
                        if len(encoded) != content_length:
                            raise ConnectionError("Pi preview frame was truncated")
                        with Image.open(BytesIO(encoded)) as image:
                            decoded = image.convert("RGB").copy()
                        with self._lock:
                            self._camera_frames[camera_id] = decoded
                            self._preview_errors.pop(camera_id, None)
                            self._preview_alerts.pop(camera_id, None)
            except HTTPError as exc:
                error = f"Pi preview returned HTTP {exc.code}"
            except (URLError, TimeoutError, OSError, ValueError, ConnectionError) as exc:
                error = str(exc)
            else:
                if self._stop.is_set():
                    break
                error = "Pi preview stream closed"
            self._set_preview_error(camera_id, error)
            self._stop.wait(0.5)

    def _set_preview_error(self, camera_id: str, error: str) -> None:
        with self._lock:
            self._preview_errors[camera_id] = error
            alert = self._preview_alerts.get(camera_id)
            if alert is None:
                now = datetime.now(timezone.utc).isoformat()
                alert = {
                    "id": f"camera-stream:{camera_id}:{time.time_ns()}",
                    "category": "connection_failure",
                    "severity": "warning",
                    "message": f"Camera preview unavailable for {camera_id}: {error}",
                    "camera_id": camera_id,
                    "created_at": now,
                }
                self._preview_alerts[camera_id] = alert
                self._preview_alert_events.append(dict(alert))
                self._preview_alert_events = self._preview_alert_events[-30:]
            else:
                alert["message"] = (
                    f"Camera preview unavailable for {camera_id}: {error}"
                )

    def _set_error(self, error: str) -> None:
        with self._lock:
            if self._connection_alert is None:
                now = datetime.now(timezone.utc).isoformat()
                self._connection_alert = {
                    "id": f"connection:pi-api:{time.time_ns()}",
                    "category": "connection_failure",
                    "severity": "critical",
                    "message": f"Raspberry Pi API unavailable: {error}",
                    "camera_id": None,
                    "created_at": now,
                }
                self._connection_events.append(dict(self._connection_alert))
                self._connection_events = self._connection_events[-30:]
            else:
                self._connection_alert["message"] = (
                    f"Raspberry Pi API unavailable: {error}"
                )
            self._snapshot = {
                **self._snapshot,
                "api_state": "UNAVAILABLE",
                "error": error,
            }
            self._camera_frames = {}
            self._preview_errors = {}
            self._preview_alerts = {}

    def predict(self, image: Any) -> Dict[str, Any]:
        with self._lock:
            snapshot = dict(self._snapshot)
            connection_alert = (
                dict(self._connection_alert) if self._connection_alert else None
            )
            connection_events = list(self._connection_events)
            preview_alerts = [
                dict(alert) for alert in self._preview_alerts.values()
            ]
            preview_events = [dict(alert) for alert in self._preview_alert_events]
        connected = snapshot.get("api_state") == "AVAILABLE"
        state = snapshot.get("state")
        usable = connected and state in {"LIVE", "DEGRADED"}
        return {
            "engine": "remote",
            "state": state if usable else "UNAVAILABLE",
            "decoded": usable,
            "detections": snapshot.get("detections", []),
            "timestamp": snapshot.get("timestamp"),
            "cameras": snapshot.get("cameras", []),
            "camera_status": snapshot.get("camera_status", []),
            "footfall": snapshot.get("footfall", {}),
            "inventory_estimate": snapshot.get("inventory_estimate", {}),
            "alerts": (
                ([connection_alert] if connection_alert else snapshot.get("alerts", []))
                + preview_alerts
            ),
            "alert_events": sorted(
                connection_events
                + snapshot.get("alert_events", [])
                + preview_events,
                key=lambda alert: str(alert.get("created_at", "")),
                reverse=True,
            )[:30],
            "reason": snapshot.get("error") or state,
            "status": self.availability(),
        }

    def availability(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "backend": "remote",
                "runtime": "HTTP/JSON",
                "endpoint": f"{self.base_url}/api/v1/detections" if self.base_url else "",
                "state": (
                    "ONLINE" if self._snapshot.get("api_state") == "AVAILABLE"
                    and self._snapshot.get("state") == "LIVE"
                    else "DEGRADED" if self._snapshot.get("api_state") == "AVAILABLE"
                    else "UNAVAILABLE"
                ),
                "error": self._snapshot.get("error", ""),
                "timestamp": self._snapshot.get("timestamp"),
                "cameras": (
                    self._snapshot.get("camera_status", [])
                    if self._snapshot.get("api_state") == "AVAILABLE" else []
                ),
                "detections": self._snapshot.get("detections", []),
                "footfall": self._snapshot.get("footfall", {}),
                "video_streaming": bool(self._camera_frames),
                "preview_errors": dict(self._preview_errors),
            }

    def camera_frames(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._camera_frames)

    def close(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1)
        with self._lock:
            preview_threads = list(self._preview_threads.values())
        for thread in preview_threads:
            thread.join(timeout=1)
