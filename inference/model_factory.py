"""Factory for creating inference engines."""
from __future__ import annotations

from config import Settings

from .base_inference import BaseInferenceEngine
from .ncnn_inference import NCNNInferenceEngine
from .qaihub_inference import QAIHubInferenceEngine
from .remote_inference import RemoteInferenceEngine
from .yolo_inference import YOLOInferenceEngine


def create_inference_engine(kind: str, settings: Settings) -> BaseInferenceEngine:
    if kind == "ncnn":
        return NCNNInferenceEngine(
            settings.ncnn_model_path,
            settings.yolo_confidence_threshold,
            settings.yolo_image_size,
            settings.yolo_nms_threshold,
        )
    if kind == "yolo":
        return YOLOInferenceEngine(
            settings.yolo_model_path,
            settings.yolo_confidence_threshold,
            settings.yolo_image_size,
        )
    if kind == "remote":
        return RemoteInferenceEngine()
    if kind == "qaihub":
        return QAIHubInferenceEngine(
            settings.qualcomm_model_path,
            settings.qualcomm_model_name,
            settings.qualcomm_input_size,
            settings.qualcomm_confidence_threshold,
            settings.qualcomm_nms_threshold,
            checkpoint=settings.qualcomm_model_checkpoint,
        )
    raise ValueError(f"Unsupported inference backend: {kind}")


def create_inference(settings: Settings, backend: str | None = None) -> BaseInferenceEngine:
    """Create the configured inference backend using a concise public API."""
    return create_inference_engine(backend or settings.inference_backend, settings)
