"""Truthful Qualcomm AI Hub inference adapter."""
from __future__ import annotations

import time
import platform
import os
from pathlib import Path
from typing import Any, Dict

from .base_inference import BaseInferenceEngine


class QAIHubInferenceEngine(BaseInferenceEngine):
    def __init__(
        self,
        model_path: str,
        model_name: str = "Detectron2-Detection",
        input_size: tuple[int, int] = (800, 800),
        confidence_threshold: float = 0.25,
        nms_threshold: float = 0.45,
        checkpoint: str = "faster_rcnn_R_50_C4_1x",
    ) -> None:
        self.model_path = model_path
        self.model_name = model_name
        self.input_size = input_size
        self.confidence_threshold = confidence_threshold
        self.nms_threshold = nms_threshold
        self.checkpoint = checkpoint
        self.session = None
        self._cv2 = None
        self._np = None
        self.status: Dict[str, Any] = {
            "backend": "qaihub",
            "runtime": "Qualcomm AI Hub hosted/device runtime",
            "device": "unavailable",
            "target_device": os.getenv("PORTAL_QUALCOMM_TARGET_DEVICE", "unspecified"),
            "development_host": f"{platform.system()} {platform.machine()}",
            "model": model_name,
            "checkpoint": checkpoint,
            "model_path": model_path,
            "input": f"{input_size[0]}x{input_size[1]}",
            "artifact": Path(model_path).is_file(),
            "state": "UNAVAILABLE",
            "error": "",
            "latency_ms": None,
            "fps": None,
        }
        self._initialize()

    @property
    def name(self) -> str:
        return "Qualcomm AI Hub"

    def _initialize(self) -> None:
        path = Path(self.model_path)
        if path.suffix.lower() not in {".onnx", ".tflite", ".dlc"}:
            self.status["error"] = (
                "A validated Qualcomm AI Hub artifact is required; "
                f"received {path.suffix or 'no extension'}"
            )
            return
        if not path.is_file():
            self.status["error"] = "Qualcomm model artifact is missing"
            return
        try:
            import cv2  # type: ignore
            import numpy as np  # type: ignore
            import qai_hub  # type: ignore
        except ImportError as exc:
            self.status["error"] = f"Qualcomm AI Hub SDK is unavailable: {exc}"
            return
        self._cv2 = cv2
        self._np = np
        self.status["error"] = (
            "AI Hub model/session execution is not configured; "
            "compile or hosted inference has not been run"
        )

    def predict(self, image: Any) -> Dict[str, Any]:
        if self.session is None or image is None:
            return self._unavailable()
        try:
            tensor = self._preprocess(image)
            started = time.perf_counter()
            outputs = self.session.run(None, {self.status["input_name"]: tensor})
            latency_ms = (time.perf_counter() - started) * 1000.0
            self.status.update({
                "state": "RUNNING",
                "latency_ms": round(latency_ms, 2),
                "fps": round(1000.0 / latency_ms, 2) if latency_ms > 0 else None,
            })
            # A model-specific decoder is mandatory.  Returning raw tensors as
            # detections would make analytics appear valid when they are not.
            return {
                "engine": "qaihub",
                "model_path": self.model_path,
                "state": "UNAVAILABLE",
                "decoded": False,
                "detections": [],
                "raw_output_count": len(outputs),
                "reason": "Detectron2 output decoder is not configured for this artifact",
                "status": self.availability(),
            }
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self.status.update({"state": "UNAVAILABLE", "error": str(exc)})
            return self._unavailable()

    def _preprocess(self, image: Any) -> Any:
        if self._cv2 is None or self._np is None:
            raise RuntimeError("image preprocessing dependencies are unavailable")
        if getattr(image, "size", 0) == 0:
            raise ValueError("empty input frame")
        resized = self._cv2.resize(image, self.input_size)
        rgb = self._cv2.cvtColor(resized, self._cv2.COLOR_BGR2RGB)
        tensor = self._np.asarray(rgb, dtype=self._np.float32) / 255.0
        return self._np.transpose(tensor, (2, 0, 1))[self._np.newaxis, ...]

    def _unavailable(self) -> Dict[str, Any]:
        return {
            "engine": "qaihub",
            "model_path": self.model_path,
            "detections": [],
            "decoded": False,
            "state": "UNAVAILABLE",
            "reason": self.status.get("error") or "Qualcomm inference is unavailable",
            "status": self.availability(),
        }

    def availability(self) -> Dict[str, Any]:
        return dict(self.status)
