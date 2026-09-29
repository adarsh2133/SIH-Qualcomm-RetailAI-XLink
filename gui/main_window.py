"""Professional local command-centre shell for PORTAL-XLINK."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Iterable
import customtkinter as ctk
from PIL import Image

from config import Settings
from cameras.camera_manager import CameraManager
from inference.model_factory import create_inference
from .camera_panel import CameraPanel
from .alerts_panel import AlertsPanel
from .camera_feed_panel import CameraFeedPanel
from .dashboard_panel import DashboardPanel
from .heatmap_panel import HeatmapPanel
from .inventory_panel import InventoryPanel
from .queue_panel import QueuePanel
from .reports_panel import ReportsPanel
from .ui_components import ScrollPage, Card, COLORS
from .icons import Icon


def _local_camera_previews(
    cameras: Iterable[Any], statuses: list[dict[str, Any]]
) -> dict[str, Image.Image]:
    online_cameras = {
        str(status.get("camera_id"))
        for status in statuses
        if status.get("state") == "ONLINE"
    }
    previews = {}
    for camera in cameras:
        camera_id = str(getattr(camera, "camera_id", ""))
        frame = getattr(camera, "latest_frame", None)
        image = frame.get("image") if isinstance(frame, dict) else None
        if camera_id not in online_cameras or image is None:
            continue
        if isinstance(image, Image.Image):
            previews[camera_id] = image
            continue
        shape = getattr(image, "shape", ())
        if len(shape) < 3 or shape[2] < 3:
            continue
        previews[camera_id] = Image.fromarray(image[:, :, :3][:, :, ::-1].copy())
    return previews


class MainWindow(ctk.CTk):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.logger = logging.getLogger(__name__)
        self._dark_mode = True
        self.title(f"{settings.app_name}  |  Edge Operations")
        self.geometry("1360x820")
        self.minsize(1040, 680)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.configure(fg_color=COLORS["bg"])
        self.protocol("WM_DELETE_WINDOW", self._shutdown)
        self.camera_manager = CameraManager.from_settings(settings)
        self.inference = create_inference(settings, settings.inference_backend)
        self.live_metrics = {}
        self._latest_alerts = []
        self._latest_alert_events = []
        self._build_shell()
        self._refresh_interval_ms = (
            min(settings.refresh_ms, 250)
            if settings.inference_backend == "remote"
            else settings.refresh_ms
        )
        if settings.inference_backend != "remote":
            self.camera_manager.start_all()
        self._refresh_job = self.after(self._refresh_interval_ms, self._refresh)
        self._preview_job = (
            self.after(33, self._refresh_previews)
            if settings.inference_backend == "remote" else None
        )
        self._alert_job = self.after(250, self._refresh_alerts)

    def _build_shell(self):
        header = ctk.CTkFrame(self, height=68, fg_color=COLORS["surface"], corner_radius=0)
        header.pack(fill="x"); header.pack_propagate(False)
        ctk.CTkLabel(header, text="PORTAL", text_color=COLORS["blue"],
                     font=ctk.CTkFont(size=20, weight="bold")).pack(side="left", padx=(26, 4))
        ctk.CTkLabel(header, text="XLINK  /  EDGE OPERATIONS", text_color=COLORS["muted"],
                     font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.mode = ctk.CTkLabel(header, text="SIMULATION / TEST" if self.settings.simulation else "LIVE HARDWARE",
                                 text_color=COLORS["amber"] if self.settings.simulation else COLORS["green"],
                                 font=ctk.CTkFont(size=11, weight="bold"))
        self.mode.pack(side="right", padx=24)
        Icon(header, "connection", size=18,
             color=COLORS["green"] if not self.settings.simulation else COLORS["amber"],
             bg=COLORS["surface"]).pack(side="right", padx=(0, 8))
        theme = ctk.CTkFrame(header, fg_color="transparent", cursor="hand2")
        theme.pack(side="right", padx=(0, 16))
        self.theme_icon = Icon(theme, "system", size=17, color=COLORS["muted"],
                               bg=COLORS["surface"])
        self.theme_icon.pack(side="left", padx=(0, 5), pady=8)
        self.theme_label = ctk.CTkLabel(theme, text="DARK", text_color=COLORS["muted"],
                                        font=ctk.CTkFont(size=10, weight="bold"))
        self.theme_label.pack(side="left")
        theme.bind("<Button-1>", lambda _event: self._toggle_theme())
        self.theme_icon.bind("<Button-1>", lambda _event: self._toggle_theme())
        self.theme_label.bind("<Button-1>", lambda _event: self._toggle_theme())
        body = ctk.CTkFrame(self, fg_color=COLORS["bg"], corner_radius=0)
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1); body.grid_rowconfigure(0, weight=1)
        sidebar = ctk.CTkFrame(body, width=220, fg_color=COLORS["surface"], corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew"); sidebar.grid_propagate(False)
        ctk.CTkLabel(sidebar, text="WORKSPACE", text_color=COLORS["muted"],
                     font=ctk.CTkFont(size=10, weight="bold")).pack(anchor="w", padx=18, pady=(22, 10))
        self.pages = {
            "Overview": DashboardPanel(body, self.settings),
            "Cameras": CameraPanel(body, self.settings),
            "Analytics": self._placeholder(body, "Analytics", "Validated event analytics and trends"),
            "Queue": CameraFeedPanel(
                body,
                "Queue",
                "Queue camera stream • queue metrics remain unavailable until queue analytics are configured",
            ),
            "Footfall": CameraFeedPanel(
                body,
                "Footfall",
                "Entrance camera stream • counts remain unavailable until a counting line/zone is configured",
            ),
            "Inventory": InventoryPanel(body, self.settings),
            "Dwell Time": self._placeholder(body, "Dwell Time", "Dwell duration from current tracked identities"),
            "Heatmap": HeatmapPanel(body, self.settings),
            "Alerts": AlertsPanel(body),
            "Reports": ReportsPanel(body, self.settings),
            "System": self._system_page(body),
        }
        self.nav_buttons = {}
        self.nav_icons = {
            "Overview": "overview", "Cameras": "cameras", "Analytics": "analytics",
            "Queue": "queue", "Footfall": "footfall", "Inventory": "inventory",
            "Dwell Time": "dwell", "Heatmap": "heatmap", "Alerts": "alerts",
            "Reports": "reports", "System": "system",
        }
        for name in self.pages:
            row = ctk.CTkFrame(sidebar, fg_color="transparent", corner_radius=8)
            row.pack(fill="x", padx=10, pady=2)
            Icon(row, self.nav_icons[name], size=17, color=COLORS["muted"],
                 bg=COLORS["surface"]).pack(side="left", padx=(10, 2), pady=9)
            button = ctk.CTkButton(
                row, text=name, anchor="w", height=36, fg_color="transparent",
                hover_color=COLORS["surface_alt"], text_color=COLORS["text"],
                command=lambda n=name: self.show_page(n),
            )
            button.pack(side="left", fill="x", expand=True)
            self.nav_buttons[name] = (row, button)
        ctk.CTkLabel(sidebar, text="LOCAL EDGE ONLY\nRTSP sources • no cloud", text_color=COLORS["muted"],
                     justify="left", font=ctk.CTkFont(size=10)).pack(side="bottom", anchor="w", padx=18, pady=20)
        self.content = body
        self.show_page("Overview")

    def _placeholder(self, master, title, subtitle):
        page = ScrollPage(master, title, subtitle)
        from .ui_components import empty_state
        empty_state(page.body, f"{title} unavailable", "No validated current telemetry is available to render this view.").grid(row=0, column=0, sticky="ew")
        return page

    def _system_page(self, master):
        page = ScrollPage(master, "System", "Actual local component readiness and runtime mode")
        inference_status = self.inference.availability()
        components = (("Camera manager", self.camera_manager.__class__.__name__),
                      ("Inference backend", self.inference.name),
                      ("Inference state", inference_status.get("state", "UNAVAILABLE")),
                      ("Inference runtime", inference_status.get("runtime", "unavailable")),
                      ("Inference model", inference_status.get("model", "N/A")),
                      ("Inference device", inference_status.get("device", "unavailable")),
                      ("Inference reason", inference_status.get("error") or "No error reported"),
                      ("Database", "Local SQLite (configured by app)"),
                      ("Capture policy", "RTSP-only production architecture"),
                      ("Runtime mode", "SIMULATION / TEST" if self.settings.simulation else "LIVE HARDWARE"))
        for i, (name, value) in enumerate(components):
            card = Card(page.body); card.grid(row=i, column=0, sticky="ew", pady=(0, 8))
            ctk.CTkLabel(card, text=name.upper(), text_color=COLORS["muted"],
                         font=ctk.CTkFont(size=10, weight="bold")).pack(side="left", padx=16, pady=14)
            ctk.CTkLabel(card, text=value, text_color=COLORS["text"]).pack(side="right", padx=16)
        return page

    def show_page(self, name):
        for page in self.pages.values(): page.grid_forget()
        self.pages[name].grid(row=0, column=1, sticky="nsew", padx=20, pady=18)
        for page_name, (row, button) in self.nav_buttons.items():
            active = page_name == name
            row.configure(fg_color=COLORS["surface_alt"] if active else "transparent")
            button.configure(text_color=COLORS["blue"] if active else COLORS["text"])

    def _toggle_theme(self):
        self._dark_mode = not self._dark_mode
        ctk.set_appearance_mode("dark" if self._dark_mode else "light")
        self.theme_label.configure(text="DARK" if self._dark_mode else "LIGHT")

    def _refresh(self):
        try:
            frames = ([] if self.settings.inference_backend == "remote"
                      else self.camera_manager.read_all())
            self._process_frames(frames)
            statuses = (self.inference.availability().get("cameras", [])
                        if self.settings.inference_backend == "remote"
                        else self.camera_manager.statuses())
            camera_frames = (
                self.inference.camera_frames()
                if self.settings.inference_backend == "remote"
                else _local_camera_previews(self.camera_manager.cameras, statuses)
            )
            self.pages["Cameras"].update_status(statuses, camera_frames)
            availability = self.inference.availability()
            preview_errors = availability.get("preview_errors", {})
            for page_name in ("Footfall", "Queue"):
                self.pages[page_name].update_camera_data(
                    statuses,
                    camera_frames,
                    preview_errors if isinstance(preview_errors, dict) else {},
                )
            self.pages["Footfall"].update_footfall_summary(
                availability.get("footfall", {})
            )
            self.pages["Overview"].update_metrics(
                statuses,
                self.live_metrics,
                availability,
                self.inference.name,
            )
        except Exception:
            self.logger.exception("Dashboard refresh failed")
        if self.winfo_exists():
            self._refresh_job = self.after(self._refresh_interval_ms, self._refresh)

    def _process_frames(self, frames):
        self.live_metrics = {}
        if self.settings.inference_backend == "remote":
            result = self.inference.predict(None)
            self.pages["Inventory"].update_detections(
                result.get("detections", []),
                live=result.get("state") in {"LIVE", "DEGRADED"} and result.get("decoded"),
            )
            self.pages["Inventory"].update_inventory_estimate(
                result.get("inventory_estimate")
            )
            footfall = result.get("footfall", {})
            if isinstance(footfall, dict) and footfall.get("state") == "AVAILABLE":
                self.live_metrics = {
                    "footfall": {
                        "status": "AVAILABLE",
                        "valid": True,
                        "value": int(footfall.get("total_entries", 0)),
                    }
                }
            return
        self.pages["Inventory"].update_detections([], live=False)
        for frame in frames:
            if frame.get("mode") != "live" or frame.get("image") is None:
                continue
            result = self.inference.predict(frame["image"])

    def _refresh_previews(self):
        try:
            frames = self.inference.camera_frames()
            self.pages["Cameras"].update_previews(frames)
            for page_name in ("Footfall", "Queue"):
                self.pages[page_name].update_preview_frames(frames)
        except Exception:
            self.logger.exception("Camera preview refresh failed")
        if self.winfo_exists():
            self._preview_job = self.after(66, self._refresh_previews)

    def _refresh_alerts(self):
        try:
            result = (
                self.inference.predict(None)
                if self.settings.inference_backend == "remote"
                else {}
            )
            alerts = result.get("alerts", [])
            events = result.get("alert_events", [])
            self._latest_alerts = alerts if isinstance(alerts, list) else []
            self._latest_alert_events = events if isinstance(events, list) else []
            self.pages["Alerts"].update_alerts(
                self._latest_alerts,
                self._latest_alert_events,
            )
            self.pages["Overview"].update_alert_summary(self._latest_alerts)
        except Exception:
            self.logger.exception("Alert refresh failed")
        if self.winfo_exists():
            self._alert_job = self.after(250, self._refresh_alerts)

    def _shutdown(self):
        refresh_job = getattr(self, "_refresh_job", None)
        if refresh_job is not None:
            try:
                self.after_cancel(refresh_job)
            except Exception:
                self.logger.exception("Dashboard refresh cancellation failed")
            self._refresh_job = None
        preview_job = getattr(self, "_preview_job", None)
        if preview_job is not None:
            try:
                self.after_cancel(preview_job)
            except Exception:
                self.logger.exception("Camera preview refresh cancellation failed")
            self._preview_job = None
        alert_job = getattr(self, "_alert_job", None)
        if alert_job is not None:
            try:
                self.after_cancel(alert_job)
            except Exception:
                self.logger.exception("Alert refresh cancellation failed")
            self._alert_job = None
        try: self.camera_manager.close_all()
        except Exception: self.logger.exception("Camera shutdown failed")
        close_inference = getattr(self.inference, "close", None)
        if close_inference is not None:
            close_inference()
        self.destroy()
