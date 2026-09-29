"""Application configuration and environment-backed settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
import sys


@dataclass(frozen=True)
class Settings:
    app_name: str = "PORTAL-XLINK"
    root_dir: str = str(Path(__file__).resolve().parent)
    db_path: str = str(Path(__file__).resolve().parent / "data" / "retail.db")
    logs_path: str = str(Path(__file__).resolve().parent / "logs" / "app.log")
    cpu_model_path: str = str(Path(__file__).resolve().parent / "models" / "cpu" / "model.onnx")
    # QNN execution through ONNX Runtime requires a validated ONNX artifact.
    # The existing TFLite file is only a placeholder and is not used.
    qualcomm_model_path: str = str(Path(__file__).resolve().parent / "models" / "qualcomm" / "model.onnx")
    qualcomm_weights_path: str = str(Path(__file__).resolve().parent / "models" / "qualcomm" / "model.bin")
    qualcomm_library_path: str = str(Path(__file__).resolve().parent / "models" / "qualcomm" / "model.so")
    labels_path: str = str(Path(__file__).resolve().parent / "models" / "qualcomm" / "labels.txt")
    headless: bool = False
    simulation: bool = False
    camera_freshness_timeout_s: float = 5.0
    refresh_ms: int = 2000
    camera_count: int = 4
    # Normal mode has no implicit local devices. Configure explicit `usb:<index>`
    # or `rtsp:<url>` values through PORTAL_CAMERA_SOURCES.
    camera_sources: tuple[str, ...] = ()
    inference_backend: str = "ncnn"
    yolo_model_path: str = str(Path(__file__).resolve().parent / "models" / "yolo" / "best.pt")
    ncnn_model_path: str = str(
        Path(__file__).resolve().parent / "models" / "yolo" / "best_ncnn_model"
    )
    yolo_confidence_threshold: float = 0.25
    yolo_nms_threshold: float = 0.45
    yolo_image_size: int = 416
    qualcomm_model_name: str = "Detectron2-Detection"
    qualcomm_model_checkpoint: str = "faster_rcnn_R_50_C4_1x"
    qualcomm_input_size: tuple[int, int] = (800, 800)
    qualcomm_confidence_threshold: float = 0.25
    qualcomm_nms_threshold: float = 0.45
    serial_port: str = ""
    serial_baudrate: int = 9600
    gpio_pins: tuple[int, ...] = ()

    @classmethod
    def from_env(cls) -> "Settings":
        if getattr(sys, "frozen", False) and os.name == "nt":
            user_data_root = os.getenv("LOCALAPPDATA") or str(Path.home())
            root_dir = Path(user_data_root) / "PORTAL-XLINK"
        else:
            root_dir = Path(__file__).resolve().parent
        try:
            refresh = max(500, int(os.getenv("PORTAL_REFRESH_MS", "2000")))
        except ValueError:
            refresh = 2000
        try:
            camera_count = max(1, int(os.getenv("PORTAL_CAMERA_COUNT", "4")))
        except ValueError:
            camera_count = 4
        configured_sources = os.getenv("PORTAL_CAMERA_SOURCES")
        sources = tuple(item.strip() for item in configured_sources.split(",")
                        if item.strip()) if configured_sources else ()
        # Simulation is deliberately opt-in at the command line.  An inherited
        # environment must never make a normal `python app.py` run synthetic data.
        simulation = False
        if not sources:
            sources = ()
        try:
            freshness = max(0.5, float(os.getenv("PORTAL_CAMERA_FRESHNESS_TIMEOUT_S", "5")))
        except ValueError:
            freshness = 5.0
        try:
            baudrate = max(1, int(os.getenv("PORTAL_SERIAL_BAUDRATE", "9600")))
        except ValueError:
            baudrate = 9600
        try:
            gpio_pins = tuple(int(item.strip()) for item in os.getenv(
                "PORTAL_GPIO_PINS", "").split(",") if item.strip())
        except ValueError:
            gpio_pins = ()
        try:
            yolo_confidence = max(0.0, min(1.0, float(os.getenv(
                "PORTAL_YOLO_CONFIDENCE_THRESHOLD", "0.25"))))
        except ValueError:
            yolo_confidence = 0.25
        try:
            yolo_nms = max(0.0, min(1.0, float(os.getenv(
                "PORTAL_YOLO_NMS_THRESHOLD", "0.45"))))
        except ValueError:
            yolo_nms = 0.45
        try:
            confidence = max(0.0, min(1.0, float(os.getenv(
                "PORTAL_QUALCOMM_CONFIDENCE_THRESHOLD", "0.25"))))
        except ValueError:
            confidence = 0.25
        try:
            nms = max(0.0, min(1.0, float(os.getenv(
                "PORTAL_QUALCOMM_NMS_THRESHOLD", "0.45"))))
        except ValueError:
            nms = 0.45
        try:
            image_size = max(32, int(os.getenv("PORTAL_YOLO_IMAGE_SIZE", "416")))
        except ValueError:
            image_size = 416
        return cls(
            app_name=os.getenv("PORTAL_APP_NAME", "PORTAL-XLINK"),
            root_dir=str(root_dir),
            db_path=os.getenv("PORTAL_DB_PATH", str(root_dir / "data" / "retail.db")),
            logs_path=os.getenv("PORTAL_LOGS_PATH", str(root_dir / "logs" / "app.log")),
            cpu_model_path=os.getenv("PORTAL_CPU_MODEL_PATH", str(root_dir / "models" / "cpu" / "model.onnx")),
            qualcomm_model_path=os.getenv("PORTAL_QUALCOMM_MODEL_PATH", str(root_dir / "models" / "qualcomm" / "model.onnx")),
            qualcomm_weights_path=os.getenv("PORTAL_QUALCOMM_WEIGHTS_PATH", str(root_dir / "models" / "qualcomm" / "model.bin")),
            qualcomm_library_path=os.getenv("PORTAL_QUALCOMM_LIBRARY_PATH", str(root_dir / "models" / "qualcomm" / "model.so")),
            labels_path=os.getenv("PORTAL_LABELS_PATH", str(root_dir / "models" / "qualcomm" / "labels.txt")),
            headless=os.getenv("PORTAL_HEADLESS", "false").lower() in {"1", "true", "yes"},
            simulation=simulation, camera_freshness_timeout_s=freshness,
            refresh_ms=refresh, camera_count=camera_count,
            camera_sources=sources,
            inference_backend=os.getenv("PORTAL_INFERENCE_BACKEND", "ncnn"),
            yolo_model_path=os.getenv("PORTAL_YOLO_MODEL_PATH", str(root_dir / "models" / "yolo" / "best.pt")),
            ncnn_model_path=os.getenv(
                "PORTAL_NCNN_MODEL_PATH", str(root_dir / "models" / "yolo" / "best_ncnn_model")
            ),
            yolo_confidence_threshold=yolo_confidence,
            yolo_nms_threshold=yolo_nms,
            yolo_image_size=image_size,
            qualcomm_model_name=os.getenv("PORTAL_QUALCOMM_MODEL_NAME", "Detectron2-Detection"),
            qualcomm_model_checkpoint=os.getenv(
                "PORTAL_QUALCOMM_MODEL_CHECKPOINT", "faster_rcnn_R_50_C4_1x"
            ),
            qualcomm_input_size=(800, 800),
            qualcomm_confidence_threshold=confidence,
            qualcomm_nms_threshold=nms,
            serial_port=os.getenv("PORTAL_SERIAL_PORT", ""),
            serial_baudrate=baudrate, gpio_pins=gpio_pins,
        )

    def with_headless(self, headless: bool) -> "Settings":
        return Settings(
            app_name=self.app_name,
            root_dir=self.root_dir,
            db_path=self.db_path,
            logs_path=self.logs_path,
            cpu_model_path=self.cpu_model_path,
            qualcomm_model_path=self.qualcomm_model_path,
            qualcomm_weights_path=self.qualcomm_weights_path,
            qualcomm_library_path=self.qualcomm_library_path,
            labels_path=self.labels_path,
            headless=headless,
            simulation=self.simulation,
            camera_freshness_timeout_s=self.camera_freshness_timeout_s,
            refresh_ms=self.refresh_ms,
            camera_count=self.camera_count,
            camera_sources=self.camera_sources,
            inference_backend=self.inference_backend,
            yolo_model_path=self.yolo_model_path,
            ncnn_model_path=self.ncnn_model_path,
            yolo_confidence_threshold=self.yolo_confidence_threshold,
            yolo_nms_threshold=self.yolo_nms_threshold,
            yolo_image_size=self.yolo_image_size,
            qualcomm_model_name=self.qualcomm_model_name,
            qualcomm_model_checkpoint=self.qualcomm_model_checkpoint,
            qualcomm_input_size=self.qualcomm_input_size,
            qualcomm_confidence_threshold=self.qualcomm_confidence_threshold,
            qualcomm_nms_threshold=self.qualcomm_nms_threshold,
            serial_port=self.serial_port,
            serial_baudrate=self.serial_baudrate,
            gpio_pins=self.gpio_pins,
        )

    def with_inference_backend(self, backend: str) -> "Settings":
        if backend not in {"yolo", "ncnn", "qaihub", "remote"}:
            raise ValueError(f"Unsupported inference backend: {backend}")
        return Settings(
            app_name=self.app_name, root_dir=self.root_dir, db_path=self.db_path,
            logs_path=self.logs_path, cpu_model_path=self.cpu_model_path,
            qualcomm_model_path=self.qualcomm_model_path,
            qualcomm_weights_path=self.qualcomm_weights_path,
            qualcomm_library_path=self.qualcomm_library_path,
            labels_path=self.labels_path, headless=self.headless,
            simulation=self.simulation,
            camera_freshness_timeout_s=self.camera_freshness_timeout_s,
            refresh_ms=self.refresh_ms, camera_count=self.camera_count,
            camera_sources=self.camera_sources, inference_backend=backend,
            yolo_model_path=self.yolo_model_path,
            ncnn_model_path=self.ncnn_model_path,
            yolo_confidence_threshold=self.yolo_confidence_threshold,
            yolo_nms_threshold=self.yolo_nms_threshold,
            yolo_image_size=self.yolo_image_size,
            qualcomm_model_name=self.qualcomm_model_name,
            qualcomm_model_checkpoint=self.qualcomm_model_checkpoint,
            qualcomm_input_size=self.qualcomm_input_size,
            qualcomm_confidence_threshold=self.qualcomm_confidence_threshold,
            qualcomm_nms_threshold=self.qualcomm_nms_threshold,
            serial_port=self.serial_port, serial_baudrate=self.serial_baudrate,
            gpio_pins=self.gpio_pins,
        )

    def with_simulation(self, simulation: bool) -> "Settings":
        """Return a copy with explicit simulation mode enabled or disabled."""
        sources = self.camera_sources
        if simulation:
            sources = tuple("usb:sim" for _ in range(self.camera_count))
        return Settings(
            app_name=self.app_name,
            root_dir=self.root_dir,
            db_path=self.db_path,
            logs_path=self.logs_path,
            cpu_model_path=self.cpu_model_path,
            qualcomm_model_path=self.qualcomm_model_path,
            qualcomm_weights_path=self.qualcomm_weights_path,
            qualcomm_library_path=self.qualcomm_library_path,
            labels_path=self.labels_path,
            headless=self.headless,
            simulation=simulation,
            camera_freshness_timeout_s=self.camera_freshness_timeout_s,
            refresh_ms=self.refresh_ms,
            camera_count=self.camera_count,
            camera_sources=sources,
            inference_backend=self.inference_backend,
            yolo_model_path=self.yolo_model_path,
            ncnn_model_path=self.ncnn_model_path,
            yolo_confidence_threshold=self.yolo_confidence_threshold,
            yolo_nms_threshold=self.yolo_nms_threshold,
            yolo_image_size=self.yolo_image_size,
            qualcomm_model_name=self.qualcomm_model_name,
            qualcomm_model_checkpoint=self.qualcomm_model_checkpoint,
            qualcomm_input_size=self.qualcomm_input_size,
            qualcomm_confidence_threshold=self.qualcomm_confidence_threshold,
            qualcomm_nms_threshold=self.qualcomm_nms_threshold,
            serial_port=self.serial_port,
            serial_baudrate=self.serial_baudrate,
            gpio_pins=self.gpio_pins,
        )
