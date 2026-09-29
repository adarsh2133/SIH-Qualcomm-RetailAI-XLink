"""Direct NCNN inference backend for exported single-class YOLO detectors."""
from __future__ import annotations

import time
import os
from pathlib import Path
from typing import Any, Dict

from .base_inference import BaseInferenceEngine


class NCNNInferenceEngine(BaseInferenceEngine):
    def __init__(self, model_path: str, confidence_threshold: float = 0.25,
                 image_size: int = 416, nms_threshold: float = 0.45,
                 num_threads: int | None = None) -> None:
        self.model_path = Path(model_path)
        self.confidence_threshold = confidence_threshold
        self.image_size = image_size
        self.nms_threshold = nms_threshold
        if num_threads is None:
            try:
                num_threads = int(os.getenv("PORTAL_NCNN_THREADS", "4"))
            except ValueError:
                num_threads = 4
        self.num_threads = max(1, num_threads)
        self.net = None
        self.ncnn = None
        self.cv2 = None
        self.np = None
        self.input_name = ""
        self.output_names: list[str] = []
        self.status: Dict[str, Any] = {
            "backend": "ncnn",
            "runtime": "Tencent NCNN",
            "model_path": str(self.model_path),
            "artifact": False,
            "device": "cpu",
            "input": f"{image_size}x{image_size}",
            "threads": self.num_threads,
            "state": "UNAVAILABLE",
            "error": "",
            "latency_ms": None,
            "fps": None,
        }
        self._initialize()

    @property
    def name(self) -> str:
        return "YOLOv8n (NCNN CPU)"

    def _model_files(self) -> tuple[Path, Path] | None:
        if self.model_path.is_dir():
            param_files = sorted(self.model_path.glob("*.param"))
            if len(param_files) != 1:
                return None
            param_path = param_files[0]
        elif self.model_path.suffix == ".param":
            param_path = self.model_path
        else:
            return None
        bin_path = param_path.with_suffix(".bin")
        if param_path.is_file() and bin_path.is_file():
            return param_path, bin_path
        return None

    def _initialize(self) -> None:
        files = self._model_files()
        self.status["artifact"] = files is not None
        if files is None:
            self.status["error"] = (
                "NCNN model directory must contain one matching .param/.bin pair"
            )
            return
        try:
            import cv2
            import ncnn
            import numpy as np
            net = ncnn.Net()
            net.opt.use_vulkan_compute = False
            net.opt.num_threads = self.num_threads
            param_result = net.load_param(str(files[0]))
            model_result = net.load_model(str(files[1]))
            if param_result != 0 or model_result != 0:
                raise RuntimeError(
                    f"NCNN failed to load model files (param={param_result}, "
                    f"weights={model_result})"
                )
            input_names = list(net.input_names())
            output_names = sorted(net.output_names())
            if not input_names or not output_names:
                raise RuntimeError("NCNN model has no input or output tensors")
            self.cv2, self.ncnn, self.np = cv2, ncnn, np
            self.net = net
            self.input_name = input_names[0]
            self.output_names = output_names
            self.status["state"] = "AVAILABLE"
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            self.status["error"] = str(exc)

    def predict(self, image: Any) -> Dict[str, Any]:
        if self.net is None or image is None:
            return self._unavailable()
        try:
            height, width = image.shape[:2]
            if height <= 0 or width <= 0:
                raise ValueError("empty input frame")
            started = time.perf_counter()
            tensor, scale, pad_x, pad_y = self._preprocess(image)
            with self.net.create_extractor() as extractor:
                input_result = extractor.input(
                    self.input_name, self.ncnn.Mat(tensor)
                )
                if input_result != 0:
                    raise RuntimeError(f"NCNN input failed with code {input_result}")
                outputs = []
                for output_name in self.output_names:
                    result_code, output = extractor.extract(output_name)
                    if result_code != 0:
                        raise RuntimeError(
                            f"NCNN extraction failed for {output_name}: {result_code}"
                        )
                    outputs.append(self.np.array(output))
            latency_ms = (time.perf_counter() - started) * 1000.0
            detections = self._decode(outputs, width, height, scale, pad_x, pad_y)
            self.status.update({
                "state": "LIVE",
                "latency_ms": round(latency_ms, 2),
                "fps": round(1000.0 / latency_ms, 2) if latency_ms > 0 else None,
                "error": "",
            })
            return {
                "engine": "ncnn",
                "model_path": str(self.model_path),
                "detections": detections,
                "decoded": True,
                "state": "LIVE",
                "status": self.availability(),
            }
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            self.status.update({"state": "UNAVAILABLE", "error": str(exc)})
            return self._unavailable()

    def _preprocess(self, image: Any) -> tuple[Any, float, int, int]:
        height, width = image.shape[:2]
        scale = min(self.image_size / width, self.image_size / height)
        resized_width = max(1, round(width * scale))
        resized_height = max(1, round(height * scale))
        resized = self.cv2.resize(image, (resized_width, resized_height))
        pad_x = (self.image_size - resized_width) // 2
        pad_y = (self.image_size - resized_height) // 2
        canvas = self.np.full(
            (self.image_size, self.image_size, 3), 114, dtype=self.np.uint8
        )
        canvas[pad_y:pad_y + resized_height, pad_x:pad_x + resized_width] = resized
        rgb = self.cv2.cvtColor(canvas, self.cv2.COLOR_BGR2RGB)
        tensor = self.np.ascontiguousarray(
            self.np.transpose(rgb.astype(self.np.float32) / 255.0, (2, 0, 1))
        )
        return tensor, scale, pad_x, pad_y

    def _decode(self, outputs: list[Any], width: int, height: int,
                scale: float, pad_x: int, pad_y: int) -> list[dict[str, Any]]:
        if not outputs:
            raise RuntimeError("NCNN produced no output tensors")
        predictions = self.np.squeeze(outputs[0])
        if predictions.ndim != 2:
            raise ValueError(
                f"Expected a 2D YOLO detection output, received shape {predictions.shape}"
            )
        if not self.np.isfinite(predictions).all():
            raise ValueError("NCNN output contains non-finite values")
        if predictions.shape[0] <= 256 and predictions.shape[1] > predictions.shape[0]:
            predictions = predictions.T
        if predictions.shape[1] < 5:
            raise ValueError(
                f"Expected box coordinates and class scores, received shape {predictions.shape}"
            )

        score_values = predictions[:, 4:]
        class_ids = self.np.argmax(score_values, axis=1)
        scores = score_values[self.np.arange(len(score_values)), class_ids]
        candidate_indices = self.np.flatnonzero(scores >= self.confidence_threshold)
        if candidate_indices.size == 0:
            return []

        boxes: list[list[float]] = []
        confidences: list[float] = []
        classes: list[int] = []
        for index in candidate_indices:
            center_x, center_y, box_width, box_height = (
                float(value) for value in predictions[index, :4]
            )
            left = (center_x - box_width / 2 - pad_x) / scale
            top = (center_y - box_height / 2 - pad_y) / scale
            right = (center_x + box_width / 2 - pad_x) / scale
            bottom = (center_y + box_height / 2 - pad_y) / scale
            left = min(max(left, 0.0), float(width))
            top = min(max(top, 0.0), float(height))
            right = min(max(right, 0.0), float(width))
            bottom = min(max(bottom, 0.0), float(height))
            if right <= left or bottom <= top:
                continue
            boxes.append([left, top, right, bottom])
            confidences.append(float(scores[index]))
            classes.append(int(class_ids[index]))

        cv_boxes = [
            [box[0], box[1], box[2] - box[0], box[3] - box[1]]
            for box in boxes
        ]
        selected = self.cv2.dnn.NMSBoxes(
            cv_boxes,
            confidences,
            self.confidence_threshold,
            self.nms_threshold,
        )
        selected = self.np.asarray(selected).reshape(-1).tolist()
        return [
            {
                "bbox": [round(value, 2) for value in boxes[index]],
                "confidence": round(confidences[index], 4),
                "class_id": classes[index],
            }
            for index in selected
        ]

    def _unavailable(self) -> Dict[str, Any]:
        return {
            "engine": "ncnn",
            "model_path": str(self.model_path),
            "detections": [],
            "decoded": False,
            "state": "UNAVAILABLE",
            "reason": self.status.get("error") or "NCNN inference is unavailable",
            "status": self.availability(),
        }

    def availability(self) -> Dict[str, Any]:
        return dict(self.status)
