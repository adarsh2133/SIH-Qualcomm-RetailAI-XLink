"""CPU inference implementation backed by an ONNX placeholder."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from .base_inference import BaseInferenceEngine


class CPUInferenceEngine(BaseInferenceEngine):
    def __init__(self, model_path: str) -> None:
        self.model_path = model_path
        self.net = None
        self.status = {"runtime": "unavailable", "artifact": Path(model_path).is_file(),
                       "dependency": False, "state": "UNAVAILABLE", "error": ""}
        try:
            import cv2  # type: ignore
        except ImportError:
            self.status["error"] = "opencv-python is not installed"
        else:
            self.status["dependency"] = True
            if self.status["artifact"]:
                try:
                    self.net = cv2.dnn.readNetFromONNX(model_path)
                    self.status["runtime"] = "opencv-dnn"
                    self.status["state"] = "AVAILABLE"
                except (cv2.error, OSError, ValueError) as exc:
                    self.status["error"] = str(exc)

    @property
    def name(self) -> str:
        return "CPU (development)"

    def predict(self, image: Any) -> Dict[str, Any]:
        if self.net is not None and image is not None:
            try:
                import cv2  # type: ignore
                blob = cv2.dnn.blobFromImage(image, 1 / 255.0, (320, 320), swapRB=True)
                self.net.setInput(blob)
                output = self.net.forward()
                # This project has no model-specific decoder.  An undecoded
                # tensor is not evidence of zero detections.
                return {"engine": "cpu", "model_path": self.model_path,
                        "detections": [], "raw_shape": list(output.shape),
                        "decoded": False, "state": "UNAVAILABLE",
                        "reason": "model output decoder unavailable",
                        "status": self.availability()}
            except (cv2.error, ValueError, TypeError) as exc:
                self.status["error"] = str(exc)
        return {
            "engine": "cpu",
            "model_path": self.model_path,
            "detections": [], "decoded": False, "state": "UNAVAILABLE",
            "reason": self.status.get("error") or "model or inference unavailable",
            "status": self.availability(),
        }

    def availability(self) -> Dict[str, Any]:
        return dict(self.status)
