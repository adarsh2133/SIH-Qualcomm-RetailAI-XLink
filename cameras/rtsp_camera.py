"""Authoritative production RTSP/network camera adapter."""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque
import json
from typing import Any, Dict, Optional
from urllib.parse import urlsplit, urlunsplit
import time

from .source import simulated_frame


def display_source(url: str) -> str:
    """Mask credentials while retaining enough URL to identify a stream."""
    try:
        parsed = urlsplit(url)
        if parsed.username is None:
            return url
        host = parsed.hostname or ""
        if parsed.port:
            host += f":{parsed.port}"
        return urlunsplit((parsed.scheme, f"redacted@{host}", parsed.path,
                           parsed.query, parsed.fragment))
    except ValueError:
        return "<invalid RTSP URL>"


@dataclass
class RTSPCamera:
    camera_id: str = "rtsp-01"
    url: str = ""
    backend: str = "opencv"
    simulated: bool = False
    opened: bool = False
    frame_index: int = 0
    last_error: str = ""
    consecutive_read_failures: int = 0
    reconnect_attempts: int = 0
    stream_error: str = ""
    latest_frame: Optional[Dict[str, Any]] = field(default=None, init=False, repr=False)
    _last_frame_time: Optional[float] = field(default=None, init=False, repr=False)
    _capture: Any = field(default=None, init=False, repr=False)
    _frame_times: deque[float] = field(
        default_factory=lambda: deque(maxlen=30), init=False, repr=False
    )

    def open(self) -> bool:
        if self.simulated and self.url in {"sim", "simulation"}:
            self.opened = True
            return True
        if not self.url.strip():
            self.opened = False
            self.last_error = "NOT CONFIGURED"
            return False
        if self.backend not in {"opencv", "gstreamer"}:
            self.opened = False
            self.last_error = f"unsupported RTSP capture backend: {self.backend}"
            return False
        self.reconnect_attempts += 1
        try:
            import cv2  # type: ignore
            if self.backend == "gstreamer":
                pipeline = self.gstreamer_pipeline(self.url)
                self._capture = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
            else:
                self._capture = cv2.VideoCapture(self.url)
            if not self._capture.isOpened():
                self.last_error = "RTSP stream unavailable"
                self.stream_error = self.last_error
                self._capture.release()
                self._capture = None
            else:
                self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except ImportError:
            self.last_error = "opencv-python unavailable"
            self.stream_error = self.last_error
            self._capture = None
        except (OSError, ValueError) as exc:
            self.last_error = str(exc)
            self.stream_error = self.last_error
            self._capture = None
        self.opened = self._capture is not None
        return self.opened

    def capture(self) -> Optional[Dict[str, Any]]:
        if self.simulated:
            self.frame_index += 1
            return simulated_frame(self.camera_id, self.url, (1280, 720),
                                   self.frame_index, status="SIMULATION/TEST")
        if not self.opened or self._capture is None:
            return None
        ok, image = self._capture.read()
        if ok and image is not None:
            self.frame_index += 1
            self.consecutive_read_failures = 0
            self.stream_error = ""
            self._frame_times.append(time.monotonic())
            return {"camera_id": self.camera_id, "source": self.url, "mode": "live",
                    "frame_size": (int(image.shape[1]), int(image.shape[0])),
                    "frame_index": self.frame_index, "image": image,
                    "timestamp": time.time()}
        self.consecutive_read_failures += 1
        self.stream_error = "RTSP capture returned no valid frame"
        self.last_error = self.stream_error
        return None

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
        self._capture = None
        self.opened = False
        self.latest_frame = None

    def record_frame(self, frame: dict[str, Any]) -> None:
        self.latest_frame = frame
        self._last_frame_time = time.time()

    @staticmethod
    def gstreamer_pipeline(url: str) -> str:
        if not url.strip():
            raise ValueError("RTSP URL cannot be empty")
        uri = json.dumps(url)
        return (
            f"uridecodebin uri={uri} ! "
            "queue max-size-buffers=1 max-size-bytes=0 max-size-time=0 "
            "leaky=downstream ! videoconvert ! "
            "video/x-raw,format=BGR ! "
            "appsink drop=true max-buffers=1 sync=false"
        )

    def status(self, freshness_timeout_s: float = 5.0) -> dict[str, Any]:
        now = time.time()
        age = None if self._last_frame_time is None else max(0.0, now - self._last_frame_time)
        frame_times = list(self._frame_times)
        elapsed = frame_times[-1] - frame_times[0] if len(frame_times) > 1 else 0
        fps = (len(frame_times) - 1) / elapsed if elapsed > 0 else 0.0
        if not self.url.strip():
            state = "NOT CONFIGURED"
        elif not self.opened:
            state = "CONNECTING" if self.reconnect_attempts == 0 else "OFFLINE"
        elif self._last_frame_time is None:
            state = "CONNECTING"
        elif age is not None and age <= freshness_timeout_s:
            state = "DEGRADED" if self.consecutive_read_failures else "ONLINE"
        else:
            state = "OFFLINE"
        return {"camera_id": self.camera_id, "kind": "rtsp", "state": state,
                "opened": self.opened, "simulated": self.simulated,
                "source": display_source(self.url),
                "last_frame_time": self._last_frame_time, "frame_age_s": age,
                "fps": round(fps, 2), "worker_status": "running" if self.opened else "stopped",
                "capture_backend": self.backend,
                "consecutive_read_failures": self.consecutive_read_failures,
                "reconnect_attempts": self.reconnect_attempts,
                "stream_error": self.stream_error, "error": self.last_error}
