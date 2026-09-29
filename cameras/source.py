"""Camera source protocol and dependency-free simulated frame generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import platform
import subprocess
from typing import Any, Mapping, Optional, Protocol, Tuple


@dataclass
class CameraFrame:
    camera_id: str
    source: str
    timestamp: str
    frame_index: int
    size: Tuple[int, int]
    image: Any = None
    mode: str = "simulation"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "camera_id": self.camera_id, "source": self.source,
            "timestamp": self.timestamp, "frame_index": self.frame_index,
            "frame_size": self.size, "image": self.image, "mode": self.mode,
            "metadata": dict(self.metadata),
        }


class CameraSource(Protocol):
    camera_id: str
    opened: bool

    def open(self) -> bool: ...
    def capture(self) -> Optional[dict[str, Any]]: ...
    def close(self) -> None: ...
    def status(self) -> dict[str, Any]: ...


def is_valid_frame(frame: Any) -> bool:
    """Return whether a frame contains usable image data and dimensions.

    Synthetic frames intentionally have no image payload, but are valid only
    when explicitly marked as simulation.  A live capture must contain a
    non-empty array with at least height and width dimensions.
    """
    if not isinstance(frame, dict):
        return False
    size = frame.get("frame_size")
    if (not isinstance(size, (tuple, list)) or len(size) < 2
            or not all(isinstance(value, (int, float)) and value > 0 for value in size[:2])):
        return False
    if frame.get("mode") in {"simulation", "SIMULATION/TEST"}:
        return True
    image = frame.get("image")
    if image is None:
        return False
    shape = getattr(image, "shape", None)
    if shape is None or len(shape) < 2:
        return False
    try:
        return all(int(dimension) > 0 for dimension in shape[:2]) and int(getattr(image, "size", 1)) > 0
    except (TypeError, ValueError, OverflowError):
        return False


def windows_camera_health() -> bool | None:
    """Return Windows Plug-and-Play camera health when it is queryable."""
    if platform.system() != "Windows":
        return None
    command = (
        "Get-PnpDevice -PresentOnly -Class Camera -ErrorAction SilentlyContinue "
        "| Where-Object { $_.Status -eq 'OK' } | Select-Object -First 1 -ExpandProperty Status"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return bool(result.stdout.strip())


def simulated_frame(camera_id: str, source: str, size: Tuple[int, int],
                    index: int, **metadata: Any) -> dict[str, Any]:
    frame = CameraFrame(camera_id, source, datetime.now(timezone.utc).isoformat(),
                        index, size, metadata=metadata)
    return frame.as_dict()
