"""Authenticated JSON API publishing detections produced on the Pi."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
import ssl
import threading
import time
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit


class DetectionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snapshot: dict[str, Any] = {
            "state": "STARTING",
            "timestamp": None,
            "cameras": [],
            "detections": [],
            "alerts": [],
            "alert_events": [],
        }
        self._frames: dict[str, bytes] = {}
        self._frames_lock = threading.Lock()
        self._frame_versions: dict[str, int] = {}
        self._frames_changed = threading.Condition(self._frames_lock)

    def publish(self, snapshot: dict[str, Any],
                frames: dict[str, bytes] | None = None) -> None:
        with self._lock:
            self._snapshot = snapshot
        if frames is not None:
            for camera_id, frame in frames.items():
                self.publish_frame(camera_id, frame)

    def publish_frame(self, camera_id: str, frame: bytes) -> None:
        with self._frames_changed:
            self._frames[camera_id] = frame
            self._frame_versions[camera_id] = self._frame_versions.get(camera_id, 0) + 1
            self._frames_changed.notify_all()

    def read(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._snapshot)

    def read_alerts(self, active_only: bool = False) -> dict[str, Any]:
        with self._lock:
            snapshot = self._snapshot
            return {
                "timestamp": snapshot.get("timestamp"),
                "alerts": [
                    item for item in snapshot.get("alerts", [])
                    if not active_only or not item.get("notification_suppressed", False)
                ],
                "alert_events": [] if active_only else list(
                    snapshot.get("alert_events", [])
                ),
            }

    def read_frame(self, camera_id: str) -> bytes | None:
        with self._frames_lock:
            return self._frames.get(camera_id)

    def clear_frame(self, camera_id: str) -> None:
        with self._frames_changed:
            self._frames.pop(camera_id, None)
            self._frames_changed.notify_all()

    def wait_for_frame(self, camera_id: str, after_version: int,
                       timeout: float) -> tuple[int, bytes] | None:
        with self._frames_changed:
            self._frames_changed.wait_for(
                lambda: self._frame_versions.get(camera_id, 0) > after_version,
                timeout=timeout,
            )
            version = self._frame_versions.get(camera_id, 0)
            frame = self._frames.get(camera_id)
            if frame is None or version <= after_version:
                return None
            return version, frame


def make_server(
    host: str,
    port: int,
    token: str,
    store: DetectionStore,
    acknowledge_alert: Any = None,
    *,
    pairing_manager: Any = None,
    ssl_context: ssl.SSLContext | None = None,
) -> ThreadingHTTPServer:
    if not token:
        raise ValueError("PORTAL_API_TOKEN must be set to a non-empty secret")
    if pairing_manager is not None and ssl_context is None:
        raise ValueError("Dashboard pairing must only be enabled over TLS")
    pairing_attempts: dict[str, list[float]] = {}
    pairing_attempts_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if not hmac.compare_digest(
                self.headers.get("Authorization", ""), f"Bearer {token}"
            ):
                self._send(401, {"error": "unauthorized"})
                return
            parsed_path = urlsplit(self.path)
            if parsed_path.path == "/api/v1/health":
                payload = store.read()
                self._send(200, {
                    "state": payload.get("state", "UNAVAILABLE"),
                    "timestamp": payload.get("timestamp"),
                })
            elif parsed_path.path == "/api/v1/detections":
                self._send(200, store.read())
            elif parsed_path.path in {
                "/api/v1/alerts",
                "/api/v1/alerts/active",
            }:
                self._send(
                    200,
                    store.read_alerts(
                        active_only=parsed_path.path.endswith("/active")
                    ),
                )
            elif parsed_path.path == "/api/v1/camera-frame":
                camera_id = parse_qs(parsed_path.query).get("camera_id", [""])[0]
                frame = store.read_frame(camera_id)
                if not camera_id or frame is None:
                    self._send(404, {"error": "camera frame unavailable"})
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(frame)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(frame)
            elif parsed_path.path == "/api/v1/camera-stream":
                camera_id = parse_qs(parsed_path.query).get("camera_id", [""])[0]
                if not camera_id:
                    self._send(400, {"error": "camera_id is required"})
                    return
                self.send_response(200)
                self.send_header(
                    "Content-Type", "multipart/x-mixed-replace; boundary=frame"
                )
                self.send_header("Cache-Control", "no-store")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True
                version = 0
                try:
                    while True:
                        item = store.wait_for_frame(camera_id, version, timeout=10)
                        if item is None:
                            continue
                        version, frame = item
                        self.wfile.write(
                            b"--frame\r\n"
                            b"Content-Type: image/jpeg\r\n"
                            + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                            + frame
                            + b"\r\n"
                        )
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    return
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self) -> None:
            if urlsplit(self.path).path == "/api/v1/pair":
                self._pair()
                return
            if not hmac.compare_digest(
                self.headers.get("Authorization", ""), f"Bearer {token}"
            ):
                self._send(401, {"error": "unauthorized"})
                return
            parsed_path = urlsplit(self.path)
            prefix = "/api/v1/alerts/"
            suffix = "/acknowledge"
            if (
                not parsed_path.path.startswith(prefix)
                or not parsed_path.path.endswith(suffix)
            ):
                self._send(404, {"error": "not found"})
                return
            if acknowledge_alert is None:
                self._send(501, {"error": "alert acknowledgement unavailable"})
                return
            alert_id = unquote(parsed_path.path[len(prefix):-len(suffix)])
            if not alert_id or "/" in alert_id:
                self._send(400, {"error": "invalid alert id"})
                return
            try:
                alert = acknowledge_alert(alert_id)
            except KeyError:
                self._send(404, {"error": "active alert not found"})
                return
            self._send(200, {"alert": alert})

        def _pair(self) -> None:
            if pairing_manager is None:
                self._send(404, {"error": "not found"})
                return
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._send(400, {"error": "invalid content length"})
                return
            if not 0 < content_length <= 1024:
                self._send(400, {"error": "invalid pairing request"})
                return
            try:
                payload = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._send(400, {"error": "invalid JSON"})
                return
            code = payload.get("code") if isinstance(payload, dict) else None
            if not isinstance(code, str):
                self._send(400, {"error": "pairing code is required"})
                return
            timestamp = time.monotonic()
            address = self.client_address[0]
            with pairing_attempts_lock:
                recent = [
                    attempted for attempted in pairing_attempts.get(address, [])
                    if timestamp - attempted < 600
                ]
                if len(recent) >= 5:
                    self._send(429, {"error": "pairing attempts temporarily limited"})
                    return
                recent.append(timestamp)
                pairing_attempts[address] = recent
            credential = pairing_manager.claim(code)
            if credential is None:
                logging.getLogger(__name__).warning(
                    "Rejected dashboard pairing attempt from %s", address
                )
                self._send(401, {"error": "pairing code is invalid, expired, or already used"})
                return
            self._send(200, {"token": credential})

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    if ssl_context is not None:
        server.socket = ssl_context.wrap_socket(server.socket, server_side=True)
    return server
