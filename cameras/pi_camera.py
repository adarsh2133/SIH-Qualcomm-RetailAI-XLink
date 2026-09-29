"""Raspberry Pi camera adapter."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional
from .source import simulated_frame
import time


@dataclass
class PiCamera:
    camera_id: str = "pi-01"
    source: str = "picamera"
    width: int = 1920
    height: int = 1080
    simulated: bool = False
    opened: bool = False
    frame_index: int = 0
    last_error: str = ""
    _camera: Any = None
    _last_frame_time: float | None = None
    latest_frame: Dict[str, Any] | None = None

    def open(self) -> bool:
        if self.source in {"sim", "simulation"}:
            self.simulated = True
            self.opened = True
            return True
        try:
            from picamera2 import Picamera2  # type: ignore
            self._camera = Picamera2()
            self._camera.configure(self._camera.create_video_configuration(
                main={"size": (self.width, self.height), "format": "RGB888"}))
            self._camera.start()
            self.simulated = False
        except ImportError:
            self.last_error = "picamera2 unavailable"
            self.opened = False
        except (OSError, RuntimeError) as exc:
            self.last_error = str(exc)
            self.simulated = False
        self.opened = self._camera is not None
        return self.opened

    def capture(self) -> Optional[Dict[str, Any]]:
        if not self.opened:
            self.open()
        self.frame_index += 1
        if not self.simulated and self._camera is not None:
            return {"camera_id": self.camera_id, "source": self.source, "mode": "live",
                    "frame_size": (self.width, self.height), "frame_index": self.frame_index,
                    "image": self._camera.capture_array(), "timestamp": time.time()}
        if self.simulated:
            return simulated_frame(self.camera_id, self.source, (self.width, self.height), self.frame_index,
                                   status="SIMULATION/TEST")
        return None

    def close(self) -> None:
        if self._camera is not None:
            self._camera.stop()
        self._camera = None
        self.opened = False
        self.latest_frame = None

    def record_frame(self, frame: dict[str, Any]) -> None:
        self.latest_frame = frame
        self._last_frame_time = time.time()

    def status(self, freshness_timeout_s: float = 5.0) -> dict[str, Any]:
        age = (None if self._last_frame_time is None
               else max(0.0, time.time() - self._last_frame_time))
        online = self.opened and age is not None and age <= freshness_timeout_s
        return {"camera_id": self.camera_id, "kind": "pi",
                "state": "ONLINE" if online else "OFFLINE", "opened": self.opened,
                "simulated": self.simulated,
                "last_frame_time": getattr(self, "_last_frame_time", None),
                "frame_age_s": age,
                "fps": 0.0, "worker_status": "running" if self.opened else "stopped",
                "error": self.last_error}
