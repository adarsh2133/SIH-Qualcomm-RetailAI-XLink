"""Preprocessing helpers for model input."""
from __future__ import annotations

from typing import Any, Iterable, List, Tuple


def prepare_frame(frame: Iterable[int], width: int = 320, height: int = 320) -> List[int]:
    data = list(frame)
    if len(data) < width * height:
        padding = [0] * (width * height - len(data))
        data.extend(padding)
    return data[: width * height]


def preprocess_image(image: Any, size: Tuple[int, int] = (320, 320)) -> Any:
    """Resize/normalize when OpenCV or numpy exists; otherwise return input."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
        resized = cv2.resize(image, size)
        return np.asarray(resized, dtype=np.float32) / 255.0
    except ImportError:
        return image
    except (TypeError, ValueError):
        return image
