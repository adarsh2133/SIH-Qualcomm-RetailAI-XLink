from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
import threading
import types
import unittest
from unittest.mock import patch

from cameras.camera_manager import CameraManager
from cameras.camera_worker import CameraWorker
from cameras.source import simulated_frame
from cameras.rtsp_camera import RTSPCamera
from config import Settings
from integration.pi_service import (
    _snapshot,
    _footfall_person_model_path,
    _footfall_ncnn_thread_count,
    _ncnn_threads_per_camera,
    discover_linux_camera_sources,
    initialize_pi_database,
)
from integration.runtime_monitor import RuntimeMonitor


class GStreamerAndCameraTests(unittest.TestCase):
    def test_bundled_coco_person_model_is_default_and_path_is_overridable(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            bundled_model = Path(_footfall_person_model_path())
        self.assertEqual(bundled_model.name, "footfall-person-ncnn")
        self.assertTrue((bundled_model / "model.ncnn.param").is_file())
        self.assertTrue((bundled_model / "model.ncnn.bin").is_file())

        configured_model = Path("custom-person-model")
        with patch.dict(
            os.environ,
            {"PORTAL_FOOTFALL_PERSON_MODEL_PATH": str(configured_model)},
            clear=True,
        ):
            self.assertEqual(
                Path(_footfall_person_model_path()), configured_model
            )

    def test_person_model_uses_two_threads_for_one_camera_when_cores_allow(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("integration.pi_service.os.cpu_count", return_value=4),
        ):
            self.assertEqual(_footfall_ncnn_thread_count(1), 2)
            self.assertEqual(_footfall_ncnn_thread_count(2), 1)
            self.assertEqual(_ncnn_threads_per_camera(1), 2)
            self.assertEqual(_ncnn_threads_per_camera(2), 1)

    def test_person_model_thread_count_can_be_overridden(self) -> None:
        with patch.dict(os.environ, {"PORTAL_FOOTFALL_NCNN_THREADS": "3"}):
            self.assertEqual(_footfall_ncnn_thread_count(1), 3)
        with patch.dict(os.environ, {"PORTAL_FOOTFALL_NCNN_THREADS": "0"}):
            with self.assertRaisesRegex(ValueError, "positive integer"):
                _footfall_ncnn_thread_count(1)
        with patch.dict(os.environ, {"PORTAL_NCNN_THREADS_PER_CAMERA": "2"}):
            self.assertEqual(_ncnn_threads_per_camera(2), 2)
        with patch.dict(os.environ, {"PORTAL_NCNN_THREADS_PER_CAMERA": "0"}):
            with self.assertRaisesRegex(ValueError, "positive integer"):
                _ncnn_threads_per_camera(2)

    def test_linux_usb_camera_defaults_to_supported_yuyv_capture(self) -> None:
        settings = Settings.from_env()
        with (
            patch("cameras.camera_manager.platform.system", return_value="Linux"),
            patch.dict(os.environ, {}, clear=True),
        ):
            manager = CameraManager.from_settings(
                Settings(**{**settings.__dict__, "camera_sources": ("usb:0",)})
            )

        camera = manager.cameras[0]
        self.assertEqual((camera.width, camera.height, camera.fps), (320, 240, 30))
        self.assertEqual(camera.fourcc, "YUYV")

    def test_gstreamer_pipeline_drops_old_frames(self) -> None:
        pipeline = RTSPCamera.gstreamer_pipeline(
            'rtsp://example.invalid/stream?token="quoted"'
        )
        self.assertIn("queue max-size-buffers=1", pipeline)
        self.assertIn("leaky=downstream", pipeline)
        self.assertIn("appsink drop=true max-buffers=1 sync=false", pipeline)
        self.assertIn('\\"quoted\\"', pipeline)

    def test_four_configured_sources_create_independent_camera_objects(self) -> None:
        settings = Settings.from_env()
        four_sources = (
            "usb:0",
            "usb:1",
            "rtsp:rtsp://camera-3.invalid/live",
            "rtsp:rtsp://camera-4.invalid/live",
        )
        with patch.dict(os.environ, {"PORTAL_RTSP_BACKEND": "gstreamer"}):
            manager = CameraManager.from_settings(
                Settings(
                    **{
                        **settings.__dict__,
                        "camera_sources": four_sources,
                    }
                )
            )
        self.assertEqual(
            [camera.camera_id for camera in manager.cameras],
            ["usb-01", "usb-02", "rtsp-03", "rtsp-04"],
        )
        self.assertEqual(len({id(camera) for camera in manager.cameras}), 4)
        self.assertEqual(
            [camera.backend for camera in manager.cameras[2:]],
            ["gstreamer", "gstreamer"],
        )

    def test_discovered_four_camera_device_paths_create_independent_workers(self) -> None:
        settings = Settings.from_env()
        with patch.dict(os.environ, {"PORTAL_RTSP_BACKEND": "opencv"}):
            manager = CameraManager.from_settings(
                Settings(**{**settings.__dict__, "camera_sources": (
                    "usb:/dev/video0",
                    "usb:/dev/video2",
                    "usb:/dev/video4",
                    "usb:/dev/video6",
                )})
            )
        self.assertEqual(len(manager.cameras), 4)
        self.assertEqual(
            [camera.source for camera in manager.cameras],
            ["/dev/video0", "/dev/video2", "/dev/video4", "/dev/video6"],
        )
        self.assertEqual(len({id(camera) for camera in manager.cameras}), 4)

    def test_ordered_usb_sources_keep_footfall_and_shelf_camera_ids_stable(self) -> None:
        settings = Settings.from_env()
        sources = (
            "usb:/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0",
            "usb:/dev/v4l/by-id/usb-BC-250603-ZW_ZEB_LIVE_PRO-video-index0",
        )
        with (
            patch("cameras.camera_manager.platform.system", return_value="Linux"),
            patch.dict(os.environ, {}, clear=True),
        ):
            manager = CameraManager.from_settings(
                Settings(**{**settings.__dict__, "camera_sources": sources})
            )

        self.assertEqual(
            [(camera.camera_id, camera.source) for camera in manager.cameras],
            [
                ("usb-01", "/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0"),
                ("usb-02", "/dev/v4l/by-id/usb-BC-250603-ZW_ZEB_LIVE_PRO-video-index0"),
            ],
        )

    def test_usb_camera_capture_options_can_be_tuned_per_camera_slot(self) -> None:
        settings = Settings.from_env()
        sources = ("usb:0", "usb:2")
        with (
            patch("cameras.camera_manager.platform.system", return_value="Linux"),
            patch.dict(os.environ, {
                "PORTAL_USB_CAMERA_01_WIDTH": "320",
                "PORTAL_USB_CAMERA_01_HEIGHT": "240",
                "PORTAL_USB_CAMERA_01_FOURCC": "YUYV",
                "PORTAL_USB_CAMERA_02_WIDTH": "640",
                "PORTAL_USB_CAMERA_02_HEIGHT": "480",
                "PORTAL_USB_CAMERA_02_FOURCC": "MJPG",
            }, clear=True),
        ):
            manager = CameraManager.from_settings(
                Settings(**{**settings.__dict__, "camera_sources": sources})
            )

        self.assertEqual(
            [
                (camera.width, camera.height, camera.fps, camera.fourcc)
                for camera in manager.cameras
            ],
            [
                (320, 240, 30, "YUYV"),
                (640, 480, 30, "MJPG"),
            ],
        )

    def test_camera_autodiscovery_is_capped_at_four_and_releases_probes(self) -> None:
        devices = [f"/dev/video{index}" for index in range(6)]
        released: list[str] = []

        class Capture:
            def __init__(self, device: str, backend: int) -> None:
                self.device = device

            def isOpened(self) -> bool:
                return True

            def release(self) -> None:
                released.append(self.device)

        cv2 = types.ModuleType("cv2")
        cv2.CAP_V4L2 = 200
        cv2.VideoCapture = Capture
        with (
            patch("integration.pi_service.platform.system", return_value="Linux"),
            patch("integration.pi_service.glob.glob", side_effect=([], devices)),
            patch.dict(sys.modules, {"cv2": cv2}),
        ):
            sources = discover_linux_camera_sources()
        self.assertEqual(sources, tuple(f"usb:{device}" for device in devices[:4]))
        self.assertEqual(released, devices[:4])

    def test_pi_database_initialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            database_path = Path(temporary) / "state" / "retail.db"
            initialize_pi_database(database_path)
            initialize_pi_database(database_path)
            self.assertTrue(database_path.is_file())

    def test_four_workers_run_independently_and_reconnect_after_one_camera_fails(self) -> None:
        events = {f"camera-{index}": threading.Event() for index in range(4)}

        class Camera:
            def __init__(self, camera_id: str, fail_first_open: bool = False) -> None:
                self.camera_id = camera_id
                self.fail_first_open = fail_first_open
                self.open_attempts = 0
                self.opened = False
                self.simulated = True
                self.fps = 30
                self.last_error = ""

            def open(self) -> bool:
                self.open_attempts += 1
                if self.fail_first_open and self.open_attempts == 1:
                    raise OSError("temporary camera failure")
                self.opened = True
                return True

            def capture(self):
                events[self.camera_id].set()
                return simulated_frame(
                    self.camera_id, "test", (16, 16), self.open_attempts
                )

            def record_frame(self, frame) -> None:
                return

            def close(self) -> None:
                self.opened = False

        cameras = [
            Camera("camera-0", fail_first_open=True),
            *(Camera(f"camera-{index}") for index in range(1, 4)),
        ]
        manager = CameraManager(cameras=cameras)
        manager.workers = [CameraWorker(camera) for camera in cameras]
        for worker in manager.workers:
            worker.reconnect_interval_s = 0.01
            worker.start()
        try:
            self.assertTrue(all(event.wait(2) for event in events.values()))
            self.assertGreaterEqual(cameras[0].open_attempts, 2)
            self.assertEqual(len(manager.workers), 4)
            self.assertTrue(all(worker.is_alive() for worker in manager.workers))
        finally:
            manager.close_all()

    def test_snapshot_reports_dropped_frames_latency_and_bounded_mailbox(self) -> None:
        snapshot = _snapshot(
            [{"camera_id": "cam-1", "state": "ONLINE", "fps": 20.0}],
            {
                "cam-1": {
                    "decoded": True,
                    "state": "LIVE",
                    "frame_index": 15,
                    "timestamp": 1000.0,
                    "detections": [],
                    "inference_fps": 8.0,
                    "inference_latency_ms": 125.0,
                    "frame_age_ms": 10.0,
                    "dropped_frames_total": 42,
                }
            },
            {"alerts": [], "alert_events": []},
            {"process_rss_mb": 100.0},
            {"cam-1": 1},
        )
        camera = snapshot["cameras"][0]
        self.assertEqual(camera["processed_fps"], 8.0)
        self.assertEqual(camera["dropped_frames_total"], 42)
        self.assertEqual(camera["queue_depth"], 1)
        self.assertEqual(snapshot["performance"]["process_rss_mb"], 100.0)

    def test_snapshot_exposes_shelf_camera_live_sku_box_estimate(self) -> None:
        snapshot = _snapshot(
            [
                {"camera_id": "usb-01", "state": "ONLINE", "fps": 10.0},
                {"camera_id": "usb-02", "state": "ONLINE", "fps": 9.0},
            ],
            {
                "usb-01": {"decoded": True, "state": "LIVE", "detections": []},
                "usb-02": {
                    "decoded": True,
                    "state": "LIVE",
                    "detections": [
                        {"class_id": 0, "confidence": 0.8, "bbox": [0, 0, 10, 10]},
                        {"class_id": 0, "confidence": 0.6, "bbox": [20, 0, 30, 10]},
                        {"class_id": 1, "confidence": 0.9, "bbox": [40, 0, 50, 10]},
                    ],
                },
            },
            {"alerts": [], "alert_events": []},
            footfall={
                "processing": {"usb-01": {"detector": "ncnn_person"}},
            },
        )

        self.assertEqual(snapshot["inventory_estimate"]["state"], "AVAILABLE")
        self.assertEqual(snapshot["inventory_estimate"]["camera_id"], "usb-02")
        self.assertEqual(snapshot["inventory_estimate"]["visible_sku_boxes"], 2)
        self.assertEqual(snapshot["inventory_estimate"]["confidence"], 0.7)
        self.assertFalse(snapshot["inventory_estimate"]["physical_stock_verified"])


class RuntimeMonitorTests(unittest.TestCase):
    def test_cpu_rss_and_system_memory_are_sampled_and_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "self").mkdir()
            (root / "stat").write_text("cpu 100 0 50 850 0\n")
            (root / "self" / "stat").write_text(
                "1 (python test) S " + " ".join(["0"] * 10) + " 20 10\n"
            )
            (root / "self" / "status").write_text("VmRSS:\t2048 kB\n")
            (root / "meminfo").write_text(
                "MemTotal: 10000 kB\nMemAvailable: 2000 kB\n"
            )
            time_values = iter((0.0, 1.0, 1.1))
            monitor = RuntimeMonitor(
                root,
                interval_s=1.0,
                clock=lambda: next(time_values),
                clock_ticks_per_second=100,
            )
            first = monitor.snapshot()
            (root / "stat").write_text("cpu 200 0 100 1700 0\n")
            (root / "self" / "stat").write_text(
                "1 (python test) S " + " ".join(["0"] * 10) + " 30 20\n"
            )
            second = monitor.snapshot()
            cached = monitor.snapshot()

        self.assertIsNone(first["process_cpu_percent"])
        self.assertEqual(second["process_cpu_percent"], 20.0)
        self.assertEqual(second["system_cpu_percent"], 15.0)
        self.assertEqual(second["process_rss_mb"], 2.0)
        self.assertEqual(second["system_memory_percent"], 80.0)
        self.assertEqual(cached, second)


if __name__ == "__main__":
    unittest.main()
