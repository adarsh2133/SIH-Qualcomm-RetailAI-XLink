"""USB camera adapter; unavailable hardware is never replaced with fake frames."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional
import platform
import time
from .source import is_valid_frame, simulated_frame, windows_camera_health


@dataclass
class USBVideoCamera:
    MIN_VALID_FRAMES_FOR_ONLINE = 2
    camera_id: str = "usb-01"
    source: str = "0"
    fps: int = 30
    width: int = 640
    height: int = 480
    fourcc: str = ""
    simulated: bool = False
    opened: bool = False
    frame_index: int = 0
    last_error: str = ""
    _capture: Any = None
    last_frame_time: float | None = None
    frame_times: list[float] | None = None
    valid_frame_count: int = 0
    last_read_ok: bool = False
    latest_frame: dict[str, Any] | None = None
    negotiated_width: int = 0
    negotiated_height: int = 0

    def open(self) -> bool:
        self.frame_times = [] if self.frame_times is None else self.frame_times
        self.simulated = self.source == "sim"
        if self.simulated:
            self.opened = True
            return True
        if windows_camera_health() is False:
            self.last_error = "Windows reports no healthy camera device"
            self.opened = False
            return False
        try:
            import cv2  # type: ignore
            source: Any = int(self.source) if str(self.source).isdigit() else self.source
            if platform.system() == "Linux":
                self._capture = cv2.VideoCapture(source, cv2.CAP_V4L2)
            elif platform.system() == "Windows":
                self._capture = cv2.VideoCapture(source, cv2.CAP_DSHOW)
            else:
                self._capture = cv2.VideoCapture(source)
            if not self._capture.isOpened():
                self.last_error = "camera source unavailable"
                self._capture.release()
                self._capture = None
                self.opened = False
                return False
            self._capture.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            self._capture.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            if self.fourcc:
                self._capture.set(
                    cv2.CAP_PROP_FOURCC,
                    cv2.VideoWriter_fourcc(*self.fourcc),
                )
            self._capture.set(cv2.CAP_PROP_FPS, self.fps)
            self._capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            actual_width = int(self._capture.get(cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(self._capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
            if actual_width > 0 and actual_height > 0:
                self.negotiated_width = actual_width
                self.negotiated_height = actual_height
        except ImportError:
            self.last_error = "opencv-python unavailable"
            self.opened = False
            return False
        except (OSError, ValueError) as exc:
            self.last_error = str(exc)
            self.opened = False
            return False
        self.opened = True
        return True

    def capture(self) -> Optional[dict[str, Any]]:
        if not self.opened and not self.open():
            return None
        self.frame_index += 1
        if self.simulated:
            return simulated_frame(self.camera_id, self.source, (self.width, self.height),
                                   self.frame_index, status="SIMULATION/TEST")
        if self._capture is not None:
            ok, image = self._capture.read()
            if ok:
                frame = {"camera_id": self.camera_id, "source": self.source, "mode": "live",
                         "frame_size": (self.width, self.height), "frame_index": self.frame_index,
                         "image": image, "timestamp": time.time()}
                if is_valid_frame(frame):
                    self.last_read_ok = True
                    shape = getattr(image, "shape", ())
                    self.negotiated_width, self.negotiated_height = (
                        int(shape[1]), int(shape[0])
                    )
                    frame["frame_size"] = (
                        self.negotiated_width, self.negotiated_height
                    )
                    return frame
                self.last_error = "capture returned an empty or invalid frame"
            else:
                self.last_error = "capture returned no frame"
            self._capture.release()
            self._capture = None
            self.opened = False
            self.last_read_ok = False
            self._clear_frame_health()
        return None

    def record_frame(self, frame: dict[str, Any]) -> None:
        now = time.time()
        self.latest_frame = frame
        self.last_frame_time = now
        self.frame_times = (self.frame_times or [])[-29:] + [now]
        self.valid_frame_count += 1
        self.last_read_ok = True

    def _clear_frame_health(self) -> None:
        self.last_frame_time = None
        self.frame_times = []
        self.valid_frame_count = 0

    def close(self) -> None:
        if self._capture is not None:
            self._capture.release()
        self._capture = None
        self.opened = False
        self.last_read_ok = False
        self._clear_frame_health()
        self.latest_frame = None

    def status(self, freshness_timeout_s: float = 5.0) -> dict[str, Any]:
        now = time.time()
        age = None if self.last_frame_time is None else max(0.0, now - self.last_frame_time)
        times = self.frame_times or []
        elapsed = times[-1] - times[0] if len(times) > 1 else 0
        fps = (len(times) - 1) / elapsed if elapsed > 0 else 0.0
        online = (self.opened and self.last_read_ok
                  and self.valid_frame_count >= self.MIN_VALID_FRAMES_FOR_ONLINE
                  and age is not None and age <= freshness_timeout_s)
        return {"camera_id": self.camera_id, "kind": "usb",
                "source": f"USB index {self.source}",
                "requested_fps": self.fps,
                "requested_size": [self.width, self.height],
                "capture_size": (
                    [self.negotiated_width, self.negotiated_height]
                    if self.negotiated_width and self.negotiated_height
                    else None
                ),
                "requested_capture_fps": self.fps,
                "pixel_format": self.fourcc or "driver-default",
                "state": "ONLINE" if online else "OFFLINE", "opened": self.opened,
                "simulated": self.simulated, "last_frame_time": self.last_frame_time,
                "frame_age_s": age if online else None,
                "fps": round(fps, 2) if online else "N/A",
                "worker_status": "running" if online else "stopped",
                "error": self.last_error}
