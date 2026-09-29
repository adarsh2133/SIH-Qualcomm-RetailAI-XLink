"""Manager for multiple camera sources."""
from __future__ import annotations

from dataclasses import dataclass, field
from queue import Empty, Queue
from typing import Any, Dict, List
import platform
import os

from .usb_camera import USBVideoCamera
from .pi_camera import PiCamera
from .rtsp_camera import RTSPCamera
from .camera_worker import CameraWorker
from config import Settings


def _usb_capture_options(camera_slot: int | None = None) -> Dict[str, Any]:
    if platform.system() != "Linux":
        return {}
    defaults = {"width": 320, "height": 240, "fps": 30, "fourcc": "YUYV"}
    values: Dict[str, Any] = {}
    for name, default in defaults.items():
        global_value = os.getenv(f"PORTAL_USB_CAMERA_{name.upper()}")
        slot_value = (
            os.getenv(f"PORTAL_USB_CAMERA_{camera_slot:02d}_{name.upper()}")
            if camera_slot is not None else None
        )
        raw = slot_value or global_value or str(default)
        setting_name = (
            f"PORTAL_USB_CAMERA_{camera_slot:02d}_{name.upper()}"
            if slot_value and camera_slot is not None
            else f"PORTAL_USB_CAMERA_{name.upper()}"
        )
        if name == "fourcc":
            value = raw.strip().upper()
            if len(value) != 4:
                raise ValueError(f"{setting_name} must contain four characters")
        else:
            try:
                value = int(raw)
            except ValueError as exc:
                raise ValueError(f"{setting_name} must be an integer") from exc
            if value <= 0:
                raise ValueError(f"{setting_name} must be positive")
        values[name] = value
    return values


@dataclass
class CameraManager:
    cameras: List[Any] = field(default_factory=list)
    frame_queue: Queue = field(default_factory=lambda: Queue(maxsize=32), repr=False)
    workers: List[CameraWorker] = field(default_factory=list, repr=False)
    freshness_timeout_s: float = 5.0

    def __post_init__(self) -> None:
        if not self.cameras:
            self.cameras = [RTSPCamera(camera_id=f"rtsp-{index:02d}", url="")
                            for index in range(1, 4)]

    def open_all(self) -> None:
        for camera in self.cameras:
            try:
                camera.open()
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                camera.last_error = str(exc)
                camera.opened = False

    @classmethod
    def from_settings(cls, settings: Settings) -> "CameraManager":
        cameras: List[Any] = []
        specs = settings.camera_sources or tuple("" for _ in range(max(1, settings.camera_count)))
        rtsp_backend = os.getenv("PORTAL_RTSP_BACKEND", "opencv").strip().lower()
        if rtsp_backend not in {"opencv", "gstreamer"}:
            raise ValueError("PORTAL_RTSP_BACKEND must be 'opencv' or 'gstreamer'")
        for index, spec in enumerate(specs, 1):
            if spec.lower().startswith(("rtsp://", "rtsps://")):
                kind, value = "rtsp", spec
            else:
                kind, _, value = spec.partition(":")
            kind, value = kind.lower(), value
            camera_id = f"rtsp-{index:02d}"
            if settings.simulation:
                cameras.append(USBVideoCamera(camera_id=f"sim-{index:02d}", source="sim"))
            elif kind in {"rtsp", "pi-rtsp"} and value.strip():
                cameras.append(RTSPCamera(
                    camera_id=camera_id,
                    url=value.strip(),
                    backend=rtsp_backend,
                ))
            elif kind == "usb" and value.strip():
                source = value.strip()
                usb_options = _usb_capture_options(index)
                if source.startswith("/dev/"):
                    cameras.append(USBVideoCamera(
                        camera_id=f"usb-{index:02d}",
                        source=source,
                        **usb_options,
                    ))
                else:
                    try:
                        device_index = int(source)
                    except ValueError:
                        cameras.append(RTSPCamera(
                            camera_id=f"usb-{index:02d}",
                            url="",
                            last_error=f"USB camera source must be an integer index or /dev path: {source!r}",
                        ))
                    else:
                        cameras.append(USBVideoCamera(
                            camera_id=f"usb-{index:02d}",
                            source=str(device_index),
                            **usb_options,
                        ))
            elif kind == "pi" and platform.system() == "Linux" and value.strip():
                cameras.append(PiCamera(camera_id=f"pi-{index:02d}", source=value))
            else:
                # Keep the configured slot visible without opening local USB
                # devices or inventing a network endpoint.
                cameras.append(RTSPCamera(camera_id=camera_id, url="",
                                          last_error=("NOT CONFIGURED" if not spec.strip()
                                                      else f"unsupported source type: {kind}")))
        return cls(cameras=cameras, freshness_timeout_s=settings.camera_freshness_timeout_s)

    def start_all(self, enqueue_frames: bool = True) -> None:
        # Opening network streams can block inside the capture backend. Let
        # each worker connect independently so the dashboard remains usable.
        output_queue = self.frame_queue if enqueue_frames else None
        self.workers = [CameraWorker(camera, output_queue) for camera in self.cameras]
        for worker in self.workers:
            worker.start()

    def close_all(self) -> None:
        for worker in self.workers:
            worker.stop()
        for worker in self.workers:
            worker.join(timeout=1)
        self.workers.clear()
        for camera in self.cameras:
            try:
                camera.close()
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                camera.last_error = str(exc)

    def stop_all(self) -> None:
        self.close_all()

    def capture_snapshot(self) -> List[Dict[str, Any]]:
        frames = []
        for camera in self.cameras:
            try:
                frame = camera.capture()
                if frame is not None:
                    camera.record_frame(frame)
                    frames.append(frame)
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                camera.last_error = str(exc)
        return frames

    def read_all(self) -> List[Dict[str, Any]]:
        if self.workers:
            frames = []
            while True:
                try:
                    frames.append(self.frame_queue.get_nowait())
                except Empty:
                    return frames
            return frames
        return self.capture_snapshot()

    def status(self) -> List[Dict[str, Any]]:
        result = []
        for camera in self.cameras:
            try:
                result.append(camera.status(self.freshness_timeout_s))
            except (OSError, RuntimeError, ValueError, AttributeError) as exc:
                result.append({"camera_id": getattr(camera, "camera_id", "unknown"),
                               "opened": False, "error": str(exc)})
        return result

    def statuses(self) -> List[Dict[str, Any]]:
        return self.status()
