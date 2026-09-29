"""Background camera worker for polling camera feeds."""
from __future__ import annotations

import threading
import time
from queue import Empty, Full, Queue
from typing import Any, Dict, Optional
from .source import is_valid_frame


class CameraWorker(threading.Thread):
    def __init__(self, camera, queue: Optional[Queue[Dict[str, Any]]] = None) -> None:
        super().__init__(daemon=True)
        self.camera = camera
        self.queue = queue
        self._stop_event = threading.Event()
        self._retry_after = 0.0
        self.reconnect_interval_s = 5.0

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            capture_started = time.monotonic()
            try:
                if not getattr(self.camera, "opened", False):
                    now = time.monotonic()
                    if now < self._retry_after:
                        self._stop_event.wait(min(0.2, self._retry_after - now))
                        continue
                    self.camera.open()
                    if not getattr(self.camera, "opened", False):
                        self._retry_after = now + self.reconnect_interval_s
                        self._stop_event.wait(0.2)
                        continue
                frame = self.camera.capture()
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                self.camera.last_error = str(exc)
                # A capture exception is a disconnect for every adapter,
                # including Pi cameras which do not expose `_capture`.
                self.camera.opened = False
                if hasattr(self.camera, "_clear_frame_health"):
                    self.camera._clear_frame_health()
                frame = None
            if frame is not None:
                if not is_valid_frame(frame):
                    self.camera.last_error = "capture returned an empty or invalid frame"
                    self.camera.opened = False
                    self._retry_after = time.monotonic() + self.reconnect_interval_s
                    if hasattr(self.camera, "_clear_frame_health"):
                        self.camera._clear_frame_health()
                elif hasattr(self.camera, "record_frame"):
                    self.camera.record_frame(frame)
                    if self.queue is not None:
                        try:
                            self.queue.put_nowait(frame)
                        except Full:
                            try:
                                self.queue.get_nowait()
                            except Empty:
                                pass
                            try:
                                self.queue.put_nowait(frame)
                            except Full:
                                pass
            else:
                failures = getattr(self.camera, "consecutive_read_failures", 0)
                # Keep a stream DEGRADED during transient read failures, then
                # mark it OFFLINE and let the normal reconnect path run.
                if failures >= 3 or not getattr(self.camera, "opened", False):
                    self.camera.opened = False
                    self._retry_after = time.monotonic() + self.reconnect_interval_s
                    if hasattr(self.camera, "_clear_frame_health"):
                        self.camera._clear_frame_health()
                self._stop_event.wait(0.02)
            if getattr(self.camera, "simulated", False):
                self._stop_event.wait(1 / 30)
            elif frame is not None:
                target_fps = getattr(self.camera, "fps", None)
                if isinstance(target_fps, (int, float)) and target_fps > 0:
                    elapsed = time.monotonic() - capture_started
                    self._stop_event.wait(max(0.0, 1.0 / target_fps - elapsed))
