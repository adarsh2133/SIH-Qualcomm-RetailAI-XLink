"""YOLO inference backend for the Raspberry Pi deployment."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict

from .base_inference import BaseInferenceEngine


class YOLOInferenceEngine(BaseInferenceEngine):
    def __init__(self, model_path: str, confidence_threshold: float = 0.25,
                 image_size: int = 640) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
        self.model = None
        self.status: Dict[str, Any] = {
            "backend": "yolo",
            "runtime": "Ultralytics",
            "model_path": model_path,
            "artifact": Path(model_path).is_file(),
            "device": "cpu",
            "input": f"{image_size}x{image_size}",
            "state": "UNAVAILABLE",
            "error": "",
            "latency_ms": None,
            "fps": None,
        }
        self._initialize()

    @property
    def name(self) -> str:
        return "YOLOv8n (Raspberry Pi CPU)"

    def _initialize(self) -> None:
        if not self.status["artifact"]:
            self.status["error"] = "YOLO model artifact is missing"
            return
        try:
            from ultralytics import YOLO
            self.model = YOLO(self.model_path)
            self.status["state"] = "AVAILABLE"
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.status["error"] = str(exc)

    def predict(self, image: Any) -> Dict[str, Any]:
        if self.model is None or image is None:
            return self._unavailable()
        try:
            started = time.perf_counter()
            results = self.model.predict(
                source=image,
                imgsz=self.image_size,
                conf=self.confidence_threshold,
                device="cpu",
                verbose=False,
            )
            latency_ms = (time.perf_counter() - started) * 1000.0
            detections = []
            boxes = results[0].boxes if results else None
            if boxes is not None:
                for coordinates, confidence, class_id in zip(
                    boxes.xyxy.cpu().tolist(),
                    boxes.conf.cpu().tolist(),
                    boxes.cls.cpu().tolist(),
                ):
                    detections.append({
                        "bbox": [round(value, 2) for value in coordinates],
                        "confidence": round(float(confidence), 4),
                        "class_id": int(class_id),
                    })
            self.status.update({
                "state": "LIVE",
                "latency_ms": round(latency_ms, 2),
                "fps": round(1000.0 / latency_ms, 2) if latency_ms > 0 else None,
                "error": "",
            })
            return {
                "engine": "yolo",
                "model_path": self.model_path,
                "detections": detections,
                "decoded": True,
                "state": "LIVE",
                "status": self.availability(),
            }
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self.status.update({"state": "UNAVAILABLE", "error": str(exc)})
            return self._unavailable()

    def _unavailable(self) -> Dict[str, Any]:
        return {
            "engine": "yolo",
            "model_path": self.model_path,
            "detections": [],
            "decoded": False,
            "state": "UNAVAILABLE",
            "reason": self.status.get("error") or "YOLO inference is unavailable",
            "status": self.availability(),
        }

    def availability(self) -> Dict[str, Any]:
        return dict(self.status)
