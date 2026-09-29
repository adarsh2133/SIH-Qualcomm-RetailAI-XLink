"""Run the Pi camera/YOLO pipeline and publish detections over HTTP."""
from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
from dataclasses import replace
import glob
import logging
import os
import platform
import threading
import time
from pathlib import Path
from typing import Any

from cameras.camera_manager import CameraManager
from analytics.daily_footfall import DailyFootfallStore
from analytics.inventory_alerts import InventoryAlertEngine
from analytics.shelf_alert_config import load_shelf_alert_rules
from config import Settings
from database.connection import connect_database
from database.schema import initialize_database
from hardware.realtime_alerts import RealtimeAlertManager
from inference.ncnn_inference import NCNNInferenceEngine
from integration.runtime_monitor import RuntimeMonitor
from hardware.lcd_display import CustomerLCDWorker, LCDSettings
from vision.zones import ZoneSet
from vision.overhead_footfall import (
    create_footfall_counter_from_env,
    select_person_detections,
)

from .pi_api import DetectionStore, make_server
from .pi_discovery import PiDiscoveryResponder
from .pi_identity import PairingManager, create_server_ssl_context, ensure_tls_identity


def initialize_pi_database(database_path: str | Path) -> None:
    Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    database = connect_database(database_path)
    try:
        initialize_database(database)
    finally:
        database.close()


def _footfall_ncnn_thread_count(camera_count: int) -> int:
    configured = os.getenv("PORTAL_FOOTFALL_NCNN_THREADS", "").strip()
    if configured:
        try:
            thread_count = int(configured)
        except ValueError as exc:
            raise ValueError(
                "PORTAL_FOOTFALL_NCNN_THREADS must be a positive integer"
            ) from exc
        if thread_count < 1:
            raise ValueError(
                "PORTAL_FOOTFALL_NCNN_THREADS must be a positive integer"
            )
        return thread_count
    available_cores = os.cpu_count() or 1
    if camera_count > 1:
        return 1
    return max(1, min(2, available_cores // max(1, camera_count)))


def _ncnn_threads_per_camera(camera_count: int) -> int:
    try:
        configured = int(os.getenv(
            "PORTAL_NCNN_THREADS_PER_CAMERA",
            "1" if camera_count > 1 else str(min(2, os.cpu_count() or 4)),
        ))
    except ValueError as exc:
        raise ValueError(
            "PORTAL_NCNN_THREADS_PER_CAMERA must be a positive integer"
        ) from exc
    if configured < 1:
        raise ValueError(
            "PORTAL_NCNN_THREADS_PER_CAMERA must be a positive integer"
        )
    return configured


def _footfall_person_model_path() -> str:
    configured = os.getenv("PORTAL_FOOTFALL_PERSON_MODEL_PATH", "").strip()
    if configured:
        return configured
    return str(
        Path(__file__).resolve().parent.parent
        / "models"
        / "footfall-person-ncnn"
    )


def discover_linux_camera_sources(max_cameras: int = 4) -> tuple[str, ...]:
    """Probe unique V4L2 devices at startup; camera capture workers own them afterward."""
    if platform.system() != "Linux" or max_cameras < 1:
        return ()
    stable_paths = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    candidates = stable_paths or sorted(glob.glob("/dev/video[0-9]*"))
    try:
        import cv2
    except ImportError as exc:
        raise RuntimeError(
            "OpenCV is required to discover Raspberry Pi cameras; "
            "install the dependencies from requirements-pi.txt."
        ) from exc
    selected: list[str] = []
    for source in candidates:
        capture = None
        try:
            capture = cv2.VideoCapture(source, cv2.CAP_V4L2)
            if capture.isOpened():
                selected.append(source)
                if len(selected) == max_cameras:
                    break
        except (OSError, RuntimeError, ValueError):
            logging.getLogger(__name__).exception(
                "Could not probe camera device %s", source
            )
        finally:
            if capture is not None:
                capture.release()
    return tuple(f"usb:{source}" for source in selected)


def _snapshot(cameras: list[dict[str, Any]],
              results: dict[str, dict[str, Any]],
              alert_state: dict[str, list[dict[str, Any]]],
              performance: dict[str, Any] | None = None,
              mailbox_depths: dict[str, int] | None = None,
              footfall: dict[str, Any] | None = None) -> dict[str, Any]:
    statuses = {item.get("camera_id"): item for item in cameras}
    detections: list[dict[str, Any]] = []
    camera_data = []
    enriched_statuses = []
    for camera_id, status in statuses.items():
        result = results.get(camera_id, {})
        items = result.get("detections", []) if result.get("decoded") else []
        inference_status = result.get("status", {})
        enriched_statuses.append({
            **status,
            "inference_latency_ms": inference_status.get("latency_ms"),
            "inference_fps": inference_status.get("fps"),
        })
        for detection in items:
            detections.append({"camera_id": camera_id, **detection})
        camera_data.append({
            "camera_id": camera_id,
            "state": status.get("state", "N/A"),
            "capture_fps": status.get("fps"),
            "frame_timestamp": result.get("timestamp"),
            "latency_ms": result.get(
                "inference_latency_ms", inference_status.get("latency_ms")
            ),
            "inference_fps": inference_status.get("fps"),
            "processed_fps": result.get("inference_fps"),
            "dropped_frames_total": result.get("dropped_frames_total", 0),
            "frame_age_ms": result.get("frame_age_ms"),
            "queue_depth": (mailbox_depths or {}).get(str(camera_id), 0),
            "detections": items,
            "inference_state": result.get("state", "UNAVAILABLE"),
        })
    footfall_camera_ids = set()
    if isinstance(footfall, dict) and isinstance(footfall.get("processing"), dict):
        footfall_camera_ids = set(footfall["processing"])
    shelf_camera = next(
        (
            camera for camera in camera_data
            if camera.get("camera_id") not in footfall_camera_ids
            and camera.get("state") == "ONLINE"
        ),
        None,
    )
    inventory_estimate = {
        "state": "UNAVAILABLE",
        "camera_id": shelf_camera.get("camera_id") if shelf_camera else None,
        "visible_sku_boxes": None,
        "confidence": None,
        "method": "single_class_detection_estimate",
        "physical_stock_verified": False,
    }
    if shelf_camera and shelf_camera.get("inference_state") == "LIVE":
        sku_detections = [
            detection for detection in shelf_camera["detections"]
            if detection.get("class_id") == 0
        ]
        inventory_estimate.update({
            "state": "AVAILABLE",
            "visible_sku_boxes": len(sku_detections),
            "confidence": (
                round(
                    sum(float(detection.get("confidence", 0.0))
                        for detection in sku_detections) / len(sku_detections),
                    3,
                )
                if sku_detections else None
            ),
        })
    live = bool(camera_data) and all(
        item.get("state") == "ONLINE" and item.get("inference_state") == "LIVE"
        for item in camera_data
    )
    return {
        "schema_version": 1,
        "state": "LIVE" if live else "DEGRADED",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cameras": camera_data,
        "camera_status": enriched_statuses,
        "detections": detections,
        "performance": performance or {},
        "inventory_estimate": inventory_estimate,
        "footfall": footfall or {
            "state": "UNAVAILABLE",
            "total_entries": 0,
            "total_exits": 0,
            "cameras": {},
        },
        **alert_state,
    }


def run_pi_service(settings: Settings) -> None:
    if platform.system() != "Linux":
        raise RuntimeError(
            "The Pi camera service must run on the Raspberry Pi (Linux), where "
            "the USB webcams are connected. Start it there with "
            "`python app.py --serve-api`; on Windows, run "
            "`python app.py --backend remote` instead."
        )
    logger = logging.getLogger(__name__)
    initialize_pi_database(settings.db_path)
    logger.info("Pi database schema is ready at %s", settings.db_path)
    footfall_store = DailyFootfallStore(settings.db_path)
    if not settings.camera_sources:
        discovered_sources = discover_linux_camera_sources()
        if not discovered_sources:
            discovered_sources = tuple(
                f"usb:{index}" for index in range(max(1, settings.camera_count))
            )
            logger.warning(
                "No camera is currently available; starting reconnecting USB workers "
                "for indices 0-%d",
                len(discovered_sources) - 1,
            )
        else:
            logger.info("Auto-discovered %d camera(s)", len(discovered_sources))
        settings = replace(settings, camera_sources=discovered_sources)
    if settings.inference_backend != "ncnn":
        raise RuntimeError("The Pi detection service requires the local ncnn backend")

    state_dir = Path(os.getenv(
        "PORTAL_STATE_DIR", str(Path(settings.root_dir) / "data" / "runtime")
    ))
    host = os.getenv("PORTAL_API_HOST", "0.0.0.0")
    try:
        port = int(os.getenv("PORTAL_API_PORT", "8765"))
    except ValueError as exc:
        raise ValueError("PORTAL_API_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError("PORTAL_API_PORT must be between 1 and 65535")
    try:
        interval = max(0.01, float(os.getenv("PORTAL_API_PUBLISH_INTERVAL_S", "0.02")))
    except ValueError as exc:
        raise ValueError("PORTAL_API_PUBLISH_INTERVAL_S must be a number") from exc
    try:
        frame_size = max(160, int(os.getenv("PORTAL_API_FRAME_MAX_SIZE", "320")))
    except ValueError as exc:
        raise ValueError("PORTAL_API_FRAME_MAX_SIZE must be an integer") from exc
    try:
        preview_fps = min(
            30.0,
            max(1.0, float(os.getenv("PORTAL_API_PREVIEW_FPS", "15"))),
        )
    except ValueError as exc:
        raise ValueError("PORTAL_API_PREVIEW_FPS must be a number") from exc
    try:
        preview_quality = min(
            90, max(30, int(os.getenv("PORTAL_API_JPEG_QUALITY", "40")))
        )
    except ValueError as exc:
        raise ValueError("PORTAL_API_JPEG_QUALITY must be an integer") from exc

    import cv2
    cv2.setNumThreads(1)
    manager = CameraManager.from_settings(settings)
    camera_count = max(1, len(manager.cameras))
    threads_per_camera = _ncnn_threads_per_camera(camera_count)
    configured_footfall_cameras = os.getenv("PORTAL_FOOTFALL_CAMERA_IDS", "").strip()
    if configured_footfall_cameras:
        footfall_camera_ids = {
            item.strip() for item in configured_footfall_cameras.split(",")
            if item.strip()
        }
        unknown_footfall_cameras = footfall_camera_ids - {
            camera.camera_id for camera in manager.cameras
        }
        if unknown_footfall_cameras:
            raise ValueError(
                "PORTAL_FOOTFALL_CAMERA_IDS references unconfigured cameras: "
                + ", ".join(sorted(unknown_footfall_cameras))
            )
    else:
        footfall_camera_ids = (
            {manager.cameras[0].camera_id} if manager.cameras else set()
        )
    footfall_person_model_path = _footfall_person_model_path()
    footfall_person_threads = (
        _footfall_ncnn_thread_count(camera_count)
        if footfall_person_model_path else threads_per_camera
    )
    try:
        footfall_person_class_id = int(
            os.getenv("PORTAL_FOOTFALL_PERSON_CLASS_ID", "0")
        )
        footfall_person_confidence = float(
            os.getenv("PORTAL_FOOTFALL_PERSON_CONFIDENCE", "0.25")
        )
        footfall_person_image_size = int(
            os.getenv("PORTAL_FOOTFALL_PERSON_IMAGE_SIZE", "320")
        )
    except ValueError as exc:
        raise ValueError(
            "Footfall person class, confidence, and image size settings must be numeric"
        ) from exc
    if footfall_person_class_id < 0:
        raise ValueError("PORTAL_FOOTFALL_PERSON_CLASS_ID cannot be negative")
    if not 0 <= footfall_person_confidence <= 1:
        raise ValueError(
            "PORTAL_FOOTFALL_PERSON_CONFIDENCE must be between 0 and 1"
        )
    if footfall_person_image_size < 160:
        raise ValueError("PORTAL_FOOTFALL_PERSON_IMAGE_SIZE must be at least 160")

    engines = {
        camera.camera_id: NCNNInferenceEngine(
            settings.ncnn_model_path,
            settings.yolo_confidence_threshold,
            settings.yolo_image_size,
            settings.yolo_nms_threshold,
            num_threads=threads_per_camera,
        )
        for camera in manager.cameras
        if camera.camera_id not in footfall_camera_ids
    }
    footfall_counters = {
        camera_id: create_footfall_counter_from_env()
        for camera_id in footfall_camera_ids
    }
    footfall_person_engines = {}
    if footfall_person_model_path:
        for camera_id in footfall_camera_ids:
            person_engine = NCNNInferenceEngine(
                footfall_person_model_path,
                footfall_person_confidence,
                footfall_person_image_size,
                settings.yolo_nms_threshold,
                num_threads=footfall_person_threads,
            )
            person_status = person_engine.availability()
            if person_status.get("state") != "AVAILABLE":
                raise RuntimeError(
                    f"Footfall person model is unavailable for {camera_id}: "
                    f"{person_status.get('error')}"
                )
            footfall_person_engines[camera_id] = person_engine
            footfall_counters[camera_id].enable_ncnn_person_mode()
    for camera_id, engine in engines.items():
        inference_status = engine.availability()
        if inference_status.get("state") != "AVAILABLE":
            raise RuntimeError(
                f"YOLO inference is unavailable for {camera_id}: "
                f"{inference_status.get('error')}"
            )
    identity = ensure_tls_identity(state_dir)
    pairing = PairingManager(
        state_dir,
        token_override=os.getenv("PORTAL_API_TOKEN", ""),
        certificate_sha256=identity.certificate_sha256,
        logger=logger,
    )
    tls_context = create_server_ssl_context(identity)
    token = pairing.token
    alerts = RealtimeAlertManager()
    shelf_configs = load_shelf_alert_rules()
    camera_ids = {camera.camera_id for camera in manager.cameras}
    unknown_cameras = {
        item.rule.camera_id for item in shelf_configs
        if item.rule.camera_id not in camera_ids
    }
    if unknown_cameras:
        raise ValueError(
            "inventory alert rules reference unconfigured cameras: "
            + ", ".join(sorted(unknown_cameras))
        )
    inventory_alerts = InventoryAlertEngine(
        [item.rule for item in shelf_configs]
    )
    if shelf_configs:
        logging.getLogger(__name__).info(
            "[INVENTORY] Enabled %d configured single-SKU alert regions",
            len(shelf_configs),
        )
    else:
        logging.getLogger(__name__).info(
            "[INVENTORY] No shelf alert rules configured; product stock alerts disabled"
        )
    shelf_configs_by_camera: dict[str, list[Any]] = {}
    for item in shelf_configs:
        shelf_configs_by_camera.setdefault(item.rule.camera_id, []).append(item)
    inventory_alert_lock = threading.Lock()

    try:
        lcd_settings = LCDSettings.from_env()
    except ValueError:
        logger.exception("[LCD] Invalid LCD configuration; continuing without display")
        lcd_settings = LCDSettings.disabled()

    def current_inventory_alerts() -> list[dict[str, Any]]:
        with inventory_alert_lock:
            return inventory_alerts.snapshot()["alerts"]

    lcd = CustomerLCDWorker(
        lcd_settings,
        alert_provider=current_inventory_alerts,
        logger=logger,
    )

    def acknowledge_alert(alert_id: str) -> dict[str, Any]:
        with inventory_alert_lock:
            return inventory_alerts.acknowledge(alert_id)

    store = DetectionStore()
    server = make_server(
        host,
        port,
        token,
        store,
        acknowledge_alert,
        pairing_manager=pairing,
        ssl_context=tls_context,
    )
    discovery = PiDiscoveryResponder(port, identity.certificate_sha256, logger=logger)
    lcd.start()
    runtime_monitor = RuntimeMonitor()
    server_thread = None
    preview_stop = threading.Event()
    inference_stop = threading.Event()
    preview_threads: list[threading.Thread] = []
    inference_threads: list[threading.Thread] = []
    results_lock = threading.Lock()
    latest_results: dict[str, dict[str, Any]] = {}
    last_processed_frame: dict[str, int] = {}
    dropped_frames: dict[str, int] = {}
    processed_times: dict[str, deque[float]] = {
        camera.camera_id: deque(maxlen=30) for camera in manager.cameras
    }
    zones = ZoneSet()
    latest_footfall = footfall_store.snapshot(list(footfall_counters))
    person_inference_metrics: dict[str, dict[str, Any]] = {
        camera_id: {
            "latency_ms": None,
            "fps": None,
            "state": "READY",
            "error": "",
        }
        for camera_id in footfall_person_engines
    }

    def footfall_summary() -> dict[str, Any]:
        summary = footfall_store.snapshot(list(footfall_counters))
        summary["processing_state"] = (
            "READY"
            if all(counter.ready for counter in footfall_counters.values())
            else "WARMING_UP"
        )
        summary["processing"] = {
            camera_id: {
                "state": "READY" if counter.ready else "WARMING_UP",
                "frames_processed": counter.frames_seen,
                "line_ratio": counter.line_ratio,
                "line_axis": counter.line_axis,
                "entry_side": counter.entry_side,
                "detector": counter.detector_mode,
                "detections": counter.last_detection_count,
                "tracks": counter.last_track_count,
                "person_model": footfall_person_model_path or None,
                "inference_latency_ms": person_inference_metrics.get(
                    camera_id, {}
                ).get("latency_ms"),
                "inference_fps": person_inference_metrics.get(
                    camera_id, {}
                ).get("fps"),
                "person_model_state": person_inference_metrics.get(
                    camera_id, {}
                ).get(
                    "state",
                    "NOT_CONFIGURED" if not footfall_person_model_path else "INITIALIZING",
                ),
                "person_model_error": person_inference_metrics.get(
                    camera_id, {}
                ).get("error", ""),
            }
            for camera_id, counter in footfall_counters.items()
        }
        return summary

    latest_footfall = footfall_summary()
    preview_footfall_counts = {
        camera_id: dict(counts)
        for camera_id, counts in latest_footfall["cameras"].items()
    }
    footfall_refresh_at = 0.0
    footfall_modes_logged: dict[str, str] = {}

    def publish_previews(preview_camera_id: str) -> None:
        last_frame_index: dict[str, int] = {}
        delay = 1.0 / preview_fps
        while not preview_stop.is_set():
            loop_started = time.monotonic()
            for camera in manager.cameras:
                if camera.camera_id != preview_camera_id:
                    continue
                frame = getattr(camera, "latest_frame", None)
                if not isinstance(frame, dict):
                    continue
                camera_id = str(frame.get("camera_id", ""))
                frame_index = frame.get("frame_index")
                if not camera_id or frame_index == last_frame_index.get(camera_id):
                    continue
                image = frame.get("image")
                if image is None:
                    continue
                counter = footfall_counters.get(camera_id)
                if counter is not None:
                    try:
                        person_engine = footfall_person_engines.get(camera_id)
                        if person_engine is None:
                            preview, events = counter.process(image)
                        else:
                            inference = person_engine.predict(image)
                            inference_status = inference.get("status", {})
                            if not inference.get("decoded"):
                                error = str(
                                    inference.get("reason", "unknown inference error")
                                )
                                person_inference_metrics[camera_id] = {
                                    "latency_ms": inference_status.get("latency_ms"),
                                    "fps": inference_status.get("fps"),
                                    "state": "ERROR",
                                    "error": error,
                                }
                                raise RuntimeError(
                                    "Footfall person inference failed: " + error
                                )
                            person_inference_metrics[camera_id] = {
                                "latency_ms": inference_status.get("latency_ms"),
                                "fps": inference_status.get("fps"),
                                "state": "LIVE",
                                "error": "",
                            }
                            detections = select_person_detections(
                                inference["detections"],
                                footfall_person_class_id,
                                footfall_person_confidence,
                            )
                            preview, events = counter.process_person_detections(
                                image, detections
                            )
                        if footfall_modes_logged.get(camera_id) != counter.detector_mode:
                            if counter.detector_mode == "motion_fallback":
                                logger.warning(
                                    "OpenCV HOG person detection is unavailable for %s; "
                                    "using motion-only fallback, which cannot verify people",
                                    camera_id,
                                )
                            else:
                                logger.info(
                                    "Footfall detector for %s: %s",
                                    camera_id, counter.detector_mode,
                                )
                            footfall_modes_logged[camera_id] = counter.detector_mode
                    except (AttributeError, cv2.error, OSError, RuntimeError, ValueError) as exc:
                        if camera_id in footfall_person_engines:
                            metric = person_inference_metrics[camera_id]
                            metric["state"] = "ERROR"
                            metric["error"] = str(exc)
                        logger.exception(
                            "OpenCV footfall processing failed for %s", camera_id
                        )
                        preview = image.copy()
                        cv2.putText(
                            preview,
                            "FOOTFALL DETECTOR ERROR",
                            (12, 26),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 0, 255),
                            2,
                            cv2.LINE_AA,
                        )
                        events = []
                    for event in events:
                        footfall_store.record(camera_id, event["direction"])
                        key = (
                            "entries" if event["direction"] == "entry" else "exits"
                        )
                        preview_footfall_counts[camera_id][key] += 1
                    counts = preview_footfall_counts[camera_id]
                    banner_bottom = min(34, preview.shape[0] - 1)
                    cv2.rectangle(
                        preview,
                        (0, 0),
                        (preview.shape[1] - 1, banner_bottom),
                        (0, 0, 0),
                        cv2.FILLED,
                    )
                    cv2.putText(
                        preview,
                        (
                            f"IN {counts['entries']}  OUT {counts['exits']}  "
                            f"{counter.detector_mode.upper()}  "
                            f"{counter.last_detection_count} DET / "
                            f"{counter.last_track_count} TRACKS"
                        ),
                        (8, min(24, preview.shape[0] - 4)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                        (0, 255, 255),
                        1,
                        cv2.LINE_AA,
                    )
                else:
                    preview = image.copy()
                with results_lock:
                    result = latest_results.get(camera_id, {})
                    detections = result.get("detections", []) if result.get("decoded") else []
                if counter is None:
                    for detection in detections[:80]:
                        bbox = detection.get("bbox")
                        if not isinstance(bbox, list) or len(bbox) != 4:
                            continue
                        left, top, right, bottom = (int(value) for value in bbox)
                        cv2.rectangle(preview, (left, top), (right, bottom), (67, 209, 122), 2)
                        label = (
                            f"SKU {detection.get('class_id', '?')} "
                            f"{float(detection.get('confidence', 0.0)):.2f}"
                        )
                        cv2.putText(
                            preview, label, (left, max(18, top - 6)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (67, 209, 122), 2,
                            cv2.LINE_AA,
                        )
                height, width = preview.shape[:2]
                scale = min(1.0, frame_size / max(width, height))
                if scale < 1.0:
                    preview = cv2.resize(
                        preview,
                        (max(1, round(width * scale)), max(1, round(height * scale))),
                        interpolation=cv2.INTER_LINEAR,
                    )
                encoded, buffer = cv2.imencode(
                    ".jpg", preview,
                    [int(cv2.IMWRITE_JPEG_QUALITY), preview_quality],
                )
                if encoded:
                    store.publish_frame(camera_id, buffer.tobytes())
                    last_frame_index[camera_id] = frame_index
            elapsed = time.monotonic() - loop_started
            preview_stop.wait(max(0.0, delay - elapsed))

    def infer_camera(camera: Any) -> None:
        camera_id = camera.camera_id
        footfall_only = camera_id in footfall_counters
        engine = engines.get(camera_id)
        while not inference_stop.is_set():
            frame = getattr(camera, "latest_frame", None)
            frame_index = frame.get("frame_index") if isinstance(frame, dict) else None
            if (
                not isinstance(frame, dict)
                or frame_index is None
                or frame_index == last_processed_frame.get(camera_id)
            ):
                inference_stop.wait(0.005)
                continue
            image = frame.get("image")
            if image is None:
                last_processed_frame[camera_id] = frame_index
                continue
            previous_index = last_processed_frame.get(camera_id)
            dropped_frames[camera_id] = dropped_frames.get(camera_id, 0) + (
                max(0, int(frame_index) - int(previous_index) - 1)
                if previous_index is not None else 0
            )
            started = time.monotonic()
            if footfall_only:
                result = {
                    "engine": "opencv_footfall",
                    "detections": [],
                    "decoded": True,
                    "state": "LIVE",
                    "status": {
                        "state": "LIVE",
                        "latency_ms": 0.0,
                        "fps": None,
                    },
                    "timestamp": frame.get("timestamp"),
                    "frame_index": frame_index,
                }
            else:
                if engine is None:
                    raise RuntimeError(
                        f"No inference engine configured for camera {camera_id}"
                    )
                result = {
                    **engine.predict(image),
                    "timestamp": frame.get("timestamp"),
                    "frame_index": frame_index,
                }
            elapsed = time.monotonic() - started
            processed_times[camera_id].append(time.monotonic())
            samples = processed_times[camera_id]
            window = samples[-1] - samples[0] if len(samples) > 1 else 0.0
            result["inference_fps"] = (
                round((len(samples) - 1) / window, 2) if window > 0 else 0.0
            )
            result["inference_latency_ms"] = round(elapsed * 1000.0, 2)
            frame_timestamp = frame.get("timestamp")
            result["frame_age_ms"] = (
                max(0.0, (time.time() - float(frame_timestamp)) * 1000.0)
                if isinstance(frame_timestamp, (int, float)) else None
            )
            result["dropped_frames_total"] = dropped_frames[camera_id]
            last_processed_frame[camera_id] = frame_index
            if result.get("decoded"):
                frame_height, frame_width = image.shape[:2]
                for config in shelf_configs_by_camera.get(camera_id, []):
                    selected = []
                    for detection in result.get("detections", []):
                        if detection.get("class_id") != config.class_id:
                            continue
                        bbox = detection.get("bbox")
                        if not isinstance(bbox, list) or len(bbox) != 4:
                            continue
                        center = (
                            (float(bbox[0]) + float(bbox[2]))
                            / (2.0 * frame_width),
                            (float(bbox[1]) + float(bbox[3]))
                            / (2.0 * frame_height),
                        )
                        if zones.contains_zone(config.region, center):
                            selected.append(detection)
                    quantity = len(selected)
                    confidence = (
                        min(float(item.get("confidence", 0.0)) for item in selected)
                        if selected else 0.0
                    )
                    observed_at = frame_timestamp
                    if isinstance(observed_at, (int, float)):
                        observed_at = datetime.fromtimestamp(
                            observed_at, timezone.utc
                        ).isoformat()
                    with inventory_alert_lock:
                        inventory_alerts.observe(
                            camera_id,
                            config.rule.sku_id,
                            config.rule.shelf_id,
                            quantity,
                            confidence,
                            observed_at=observed_at,
                        )
                        lcd.set_alerts(inventory_alerts.snapshot()["alerts"])
            with results_lock:
                latest_results[camera_id] = result

    try:
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            discovery.start()
        except OSError:
            logger.exception("LAN discovery could not start; direct HTTPS remains available")
        manager.start_all(enqueue_frames=False)
        inference_threads = [
            threading.Thread(
                target=infer_camera,
                args=(camera,),
                daemon=True,
                name=f"ncnn-{camera.camera_id}",
            )
            for camera in manager.cameras
        ]
        for thread in inference_threads:
            thread.start()
        preview_threads = [
            threading.Thread(
                target=publish_previews,
                args=(camera.camera_id,),
                daemon=True,
                name=f"preview-{camera.camera_id}",
            )
            for camera in manager.cameras
        ]
        for thread in preview_threads:
            thread.start()
        logger.info("Pi detection API listening securely on %s:%s", host, port)
        print(
            f"PORTAL Pi API listening securely on {host}:{port}; "
            f"NCNN inference workers={len(inference_threads)}, "
            f"threads per camera={threads_per_camera}; "
            f"footfall cameras={','.join(sorted(footfall_camera_ids)) or 'none'}; "
            f"person model={footfall_person_model_path or 'NOT CONFIGURED'}; "
            f"person input={footfall_person_image_size}px; "
            f"person NCNN threads={footfall_person_threads if footfall_person_model_path else 'N/A'}; "
            f"preview target={preview_fps:g} FPS, max dimension={frame_size}px, "
            f"JPEG quality={preview_quality}"
        )
        while True:
            statuses = manager.statuses()
            with results_lock:
                results = dict(latest_results)
            online_ids = {
                item.get("camera_id") for item in statuses
                if item.get("state") in {"ONLINE", "DEGRADED"}
            }
            for status in statuses:
                camera_id = str(status.get("camera_id", ""))
                result = results.get(camera_id, {})
                inference_state = str(result.get("state", "N/A"))
                alerts.update_camera(
                    camera_id,
                    str(status.get("state", "N/A")),
                    inference_state,
                )
                camera_online = status.get("state") in {"ONLINE", "DEGRADED"}
                if not camera_online:
                    alerts.clear_camera_detections(camera_id)
                alerts.update_detections(
                    camera_id,
                    result.get("detections", []),
                    valid=camera_online and bool(result.get("decoded")),
                )
            with inventory_alert_lock:
                inventory_alert_state = inventory_alerts.snapshot()
                lcd.set_alerts(inventory_alert_state["alerts"])
            alert_state = alerts.snapshot()
            alert_state["alerts"].extend(inventory_alert_state["alerts"])
            alert_state["alert_events"].extend(
                inventory_alert_state["alert_events"]
            )
            try:
                performance = runtime_monitor.snapshot()
            except RuntimeError:
                logging.getLogger(__name__).exception(
                    "Unable to sample Pi process resources"
                )
                performance = {
                    "process_cpu_percent": None,
                    "system_cpu_percent": None,
                    "process_rss_mb": None,
                    "system_memory_percent": None,
                }
            results = {
                camera_id: result for camera_id, result in results.items()
                if camera_id in online_ids
            }
            with results_lock:
                latest_results = {
                    camera_id: result for camera_id, result in results.items()
                    if camera_id in online_ids
                }
            for camera in manager.cameras:
                if camera.camera_id not in online_ids:
                    store.clear_frame(camera.camera_id)
            mailbox_depths = {}
            for camera in manager.cameras:
                latest_frame = getattr(camera, "latest_frame", None)
                latest_index = (
                    latest_frame.get("frame_index")
                    if isinstance(latest_frame, dict) else None
                )
                processed_index = results.get(camera.camera_id, {}).get("frame_index")
                mailbox_depths[camera.camera_id] = int(
                    latest_index is not None and latest_index != processed_index
                )
            if time.monotonic() >= footfall_refresh_at:
                latest_footfall = footfall_summary()
                footfall_refresh_at = time.monotonic() + 0.5
            store.publish(
                _snapshot(
                    statuses,
                    results,
                    alert_state,
                    performance,
                    mailbox_depths,
                    latest_footfall,
                )
            )
            time.sleep(interval)
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Pi detection API stopping")
    finally:
        preview_stop.set()
        inference_stop.set()
        discovery.close()
        server.shutdown()
        server.server_close()
        for thread in preview_threads:
            thread.join(timeout=2)
        for thread in inference_threads:
            thread.join(timeout=2)
        if server_thread is not None:
            server_thread.join(timeout=2)
        manager.close_all()
        lcd.stop()
        footfall_store.close()
