#!/usr/bin/env python3
"""Shared metrics API for the Raspberry Pi retail edge system."""

import json
import os
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_RUNTIME_DIR = Path(
    os.environ.get("RETAIL_EDGE_RUNTIME_DIR", Path(__file__).resolve().parent / ".runtime")
)
DEFAULT_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


class RuntimeDataCollector:
    """Aggregate values from the sensor status files."""

    STALE_SECONDS = 15

    def __init__(self, runtime_dir=None):
        self.runtime_dir = Path(runtime_dir) if runtime_dir else DEFAULT_RUNTIME_DIR
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read_json(path, default=None):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return default

    @staticmethod
    def _as_int(value, default=0):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _is_recent_timestamp(value, stale_seconds=15):
        if not value:
            return False
        if isinstance(value, (int, float)):
            try:
                return (time.time() - float(value)) <= stale_seconds
            except Exception:
                return False
        if not isinstance(value, str):
            return False
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                ts = dt.timestamp()
            else:
                ts = dt.replace(tzinfo=None).timestamp()
            return (time.time() - ts) <= stale_seconds
        except ValueError:
            try:
                dt = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                return (time.time() - dt.timestamp()) <= stale_seconds
            except ValueError:
                return False

    @staticmethod
    def _explicitly_connected(payload):
        if not isinstance(payload, dict):
            return False
        if payload.get("connected") is True:
            return True
        cameras = payload.get("cameras")
        if isinstance(cameras, dict):
            return any(
                isinstance(cam, dict) and cam.get("connected") is True
                for cam in cameras.values()
            )
        return False

    def _normalize_status_payload(self, payload, *, kind):
        if not isinstance(payload, dict):
            return {}, False

        updated = payload.get("timestamp")
        fresh = self._is_recent_timestamp(updated, self.STALE_SECONDS)
        if kind == "entry":
            connected = fresh and payload.get("connected") is True
            return {**payload, "connected": connected}, connected
        if kind in {"queue", "stock"}:
            connected = fresh and self._explicitly_connected(payload)
            return {**payload, "connected": connected}, connected
        return payload, fresh

    def _per_camera_flags(self, feed_data, feed_fresh, cam1_key, cam2_key):
        """Determine each individual camera's real online state.

        Each camera is only considered online when the payload explicitly says it is
        connected and the timestamp is fresh. If there is no explicit per-camera
        status, the feed is not treated as live.
        """
        cameras_field = feed_data.get("cameras")
        if isinstance(cameras_field, dict) and cameras_field:
            cam1 = cameras_field.get(cam1_key, {})
            cam2 = cameras_field.get(cam2_key, {})
            cam1_online = feed_fresh and isinstance(cam1, dict) and cam1.get("connected") is True
            cam2_online = feed_fresh and isinstance(cam2, dict) and cam2.get("connected") is True
            return cam1_online, cam2_online

        # Legacy single-camera payload: only true if the payload explicitly marks it live.
        legacy_online = feed_fresh and feed_data.get("connected") is True
        return legacy_online, False

    def get_metrics(self):
        entry_data = self._read_json(self.runtime_dir / "entry_status.json", {})
        queue_data = self._read_json(self.runtime_dir / "queue_status.json", {})
        stock_data = self._read_json(self.runtime_dir / "stock_status.json", {})
        health_data = self._read_json(self.runtime_dir / "edge_health.json", {})

        entry_data, entry_live = self._normalize_status_payload(entry_data, kind="entry")

        queue_fresh = self._is_recent_timestamp(queue_data.get("timestamp"), self.STALE_SECONDS)
        stock_fresh = self._is_recent_timestamp(stock_data.get("timestamp"), self.STALE_SECONDS)
        queue_live = queue_fresh and bool(queue_data)
        stock_live = stock_fresh and bool(stock_data)

        queue1_online, queue2_online = self._per_camera_flags(
            queue_data, queue_fresh, "queue_camera_1", "queue_camera_2"
        )
        stock1_online, stock2_online = self._per_camera_flags(
            stock_data, stock_fresh, "stock_camera_1", "stock_camera_2"
        )

        cameras = {
            "cam_entry": "online" if entry_live else "offline",
            "cam_queue1": "online" if queue1_online else "offline",
            "cam_queue2": "online" if queue2_online else "offline",
            "cam_stock1": "online" if stock1_online else "offline",
            "cam_stock2": "online" if stock2_online else "offline",
        }

        online_count = sum(1 for state in cameras.values() if state == "online")
        if online_count == 0:
            return {
                "cameras": cameras,
                "footfall": {"current": "OFFLINE", "today": "OFFLINE", "peak": "OFFLINE"},
                "queue": {"active_queues": "OFFLINE", "avg_wait": "OFFLINE", "max_wait": "OFFLINE", "congestion": "Offline"},
                "inventory": {"total": "OFFLINE", "optimal": "OFFLINE", "critical": 0, "low": 0, "normal": 0},
                "inventory_status": {"critical": 0, "low": 0, "normal": 0},
                "active_nodes": 0,
                "events": [{
                    "time": health_data.get("timestamp", "--:--:--"),
                    "cam": "system",
                    "type": "HEALTH",
                    "val": "OFFLINE",
                    "details": "All edge camera feeds are disconnected. No live metrics are available.",
                }],
                "system": {"healthy": False},
                "overall_health": {"healthy": False, "status": "OFFLINE"},
            }

        entry_count = self._as_int(entry_data.get("entry_count"), 0)
        exit_count = self._as_int(entry_data.get("exit_count"), 0)
        queue_length = self._as_int(queue_data.get("queue_length"), 0)
        queue_status = str(queue_data.get("status") or queue_data.get("congestion_level") or "Low")
        queue_congestion = str(queue_data.get("congestion_level") or queue_status or "Low")

        product_totals = stock_data.get("products", {})
        product_values = [self._as_int(value) for value in product_totals.values()]
        total_inventory = sum(product_values)

        inventory_status = {"critical": 0, "low": 0, "normal": 0}
        for quantity in product_values:
            if quantity <= 1:
                inventory_status["critical"] += 1
            elif quantity <= 5:
                inventory_status["low"] += 1
            else:
                inventory_status["normal"] += 1

        health_summary = health_data.get("overall_health", {})
        all_services_running = health_data.get("services", {})
        active_nodes = 0
        active_nodes += 1 if entry_data.get("connected") else 0
        active_nodes += 1 if queue1_online else 0
        active_nodes += 1 if queue2_online else 0
        active_nodes += 1 if stock1_online else 0
        active_nodes += 1 if stock2_online else 0
        active_nodes += sum(1 for service in all_services_running.values() if service.get("running") is True)

        max_wait = max(queue_length * 5, self._as_int(queue_data.get("max_wait"), 0))
        avg_wait = max(queue_length * 5, self._as_int(queue_data.get("avg_wait"), 0))

        events = []
        if entry_data.get("last_event"):
            events.append({
                "time": entry_data.get("timestamp", "--:--:--"),
                "cam": "cam_entry",
                "type": "ENTRY",
                "val": entry_count,
                "details": entry_data.get("last_event"),
            })
        if queue_data:
            events.append({
                "time": queue_data.get("timestamp", "--:--:--"),
                "cam": "cam_queue1",
                "type": "QUEUE",
                "val": queue_length,
                "details": f"{queue_status} ({queue_congestion})",
            })
        if stock_data:
            events.append({
                "time": stock_data.get("timestamp", "--:--:--"),
                "cam": "cam_stock1",
                "type": "STOCK",
                "val": total_inventory,
                "details": "Inventory snapshot captured",
            })
        if health_summary.get("healthy") is False:
            events.append({
                "time": health_data.get("timestamp", "--:--:--"),
                "cam": "system",
                "type": "HEALTH",
                "val": "WARN",
                "details": "One or more edge services are unhealthy",
            })

        return {
            "cameras": cameras,
            "footfall": {
                "current": entry_count,
                "today": entry_count + exit_count,
                "peak": max(entry_count, self._as_int(entry_data.get("peak"), entry_count)),
            },
            "queue": {
                "active_queues": queue_length,
                "avg_wait": avg_wait,
                "max_wait": max_wait,
                "congestion": str(queue_congestion or queue_status or "Low"),
            },
            "inventory": {
                "total": total_inventory,
                "optimal": max(0, total_inventory - inventory_status["critical"] - inventory_status["low"]),
                "critical": inventory_status["critical"],
                "low": inventory_status["low"],
                "normal": inventory_status["normal"],
            },
            "inventory_status": inventory_status,
            "active_nodes": max(0, active_nodes),
            "events": events[:10],
            "system": {"healthy": bool(health_summary.get("healthy", True))},
            "overall_health": health_summary,
        }


class MetricsRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/api/metrics"):
            payload = RuntimeDataCollector().get_metrics()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(json.dumps(payload).encode("utf-8"))))
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))
            return

        if self.path in ("/", "/health"):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok"}).encode("utf-8"))
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def run_server(host="127.0.0.1", port=8000):
    server = ThreadingHTTPServer((host, port), MetricsRequestHandler)
    print(f"[API] Metrics server listening on http://{host}:{port}/api/metrics")
    server.serve_forever()


if __name__ == "__main__":
    run_server()