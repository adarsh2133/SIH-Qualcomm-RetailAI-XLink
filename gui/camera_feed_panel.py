"""Role-specific live camera view for footfall and queue operations."""
from __future__ import annotations

from typing import Any

import customtkinter as ctk

from .ui_components import COLORS, Card, ScrollPage


class CameraFeedPanel(ScrollPage):
    def __init__(self, master, title: str, subtitle: str, **kwargs):
        super().__init__(master, title, subtitle, **kwargs)
        self._statuses: dict[str, dict[str, Any]] = {}
        self._frames: dict[str, Any] = {}
        self._preview_errors: dict[str, str] = {}
        self._selected_camera = ""
        self._image_ref = None
        self._last_frame = None

        camera_card = Card(self.body)
        camera_card.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        header = ctk.CTkFrame(camera_card, fg_color="transparent")
        header.pack(fill="x", padx=16, pady=(14, 8))
        ctk.CTkLabel(
            header,
            text="CAMERA FEED",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left")
        self.camera_menu = ctk.CTkOptionMenu(
            header,
            values=["No camera connected"],
            command=self._select_camera,
            width=190,
        )
        self.camera_menu.pack(side="right")
        self.state_label = ctk.CTkLabel(
            camera_card,
            text="Waiting for a Pi camera",
            text_color=COLORS["amber"],
            anchor="w",
        )
        self.state_label.pack(fill="x", padx=16, pady=(0, 8))
        self.preview = ctk.CTkLabel(
            camera_card,
            text="Connect and configure this camera on the Raspberry Pi to view its stream.",
            text_color=COLORS["muted"],
        )
        self.preview.pack(anchor="w", padx=16, pady=(0, 14))
        self.footfall_label = None
        if title.lower() == "footfall":
            self.footfall_label = ctk.CTkLabel(
                camera_card,
                text="TODAY'S FOOTFALL  •  IN  N/A  •  OUT  N/A",
                text_color=COLORS["text"],
                anchor="w",
            )
            self.footfall_label.pack(fill="x", padx=16, pady=(0, 14))

    def update_footfall_summary(self, summary: dict[str, Any]) -> None:
        if self.footfall_label is None:
            return
        if summary.get("state") != "AVAILABLE":
            self.footfall_label.configure(
                text="TODAY'S FOOTFALL  •  COUNTER UNAVAILABLE"
            )
            return
        processing = summary.get("processing", {})
        camera_id = self._selected_camera
        camera_processing = (
            processing.get(camera_id, {})
            if isinstance(processing, dict) else {}
        )
        detector = str(camera_processing.get("detector", "initializing")).replace(
            "_", " "
        ).upper()
        detection_count = camera_processing.get("detections", "N/A")
        track_count = camera_processing.get("tracks", "N/A")
        inference_fps = camera_processing.get("inference_fps")
        person_model_state = str(
            camera_processing.get("person_model_state", "UNKNOWN")
        ).replace("_", " ").upper()
        person_model_error = str(camera_processing.get("person_model_error", "")).strip()
        detection_label = (
            "PERSON DETECTIONS"
            if camera_processing.get("detector") == "ncnn_person"
            else "BLOBS"
        )
        inference_rate = (
            f"  •  MODEL {float(inference_fps):.1f} FPS"
            if isinstance(inference_fps, (int, float))
            else ""
        )
        self.footfall_label.configure(
            text=(
                f"FOOTFALL TODAY ({summary.get('date', 'local day')})  •  "
                f"IN  {summary.get('total_entries', 0)}  •  "
                f"OUT  {summary.get('total_exits', 0)}  •  "
                f"{person_model_state}  •  "
                f"{detector}  •  {detection_count} {detection_label} / "
                f"{track_count} TRACKS{inference_rate}"
                + (f"  •  ERROR: {person_model_error[:120]}" if person_model_error else "")
            )
        )

    def update_camera_data(
        self,
        statuses: list[dict[str, Any]],
        frames: dict[str, Any],
        preview_errors: dict[str, str] | None = None,
    ) -> None:
        self._statuses = {
            str(status.get("camera_id")): status
            for status in statuses
            if isinstance(status, dict) and status.get("camera_id")
        }
        self._frames = frames
        self._preview_errors = preview_errors or {}

        camera_ids = list(self._statuses)
        options = camera_ids or ["No camera connected"]
        current = self._selected_camera
        if current not in self._statuses:
            current = next(
                (
                    camera_id for camera_id, status in self._statuses.items()
                    if status.get("state") == "ONLINE"
                ),
                camera_ids[0] if camera_ids else "",
            )
        self.camera_menu.configure(
            values=options,
            state="normal" if camera_ids else "disabled",
        )
        if current != self._selected_camera or not camera_ids:
            self._selected_camera = current
            self.camera_menu.set(current or "No camera connected")
            self._image_ref = None
            self._last_frame = None
        self._render_selected_camera()

    def update_preview_frames(self, frames: dict[str, Any]) -> None:
        self._frames = frames
        self._render_selected_camera()

    def _select_camera(self, camera_id: str) -> None:
        if camera_id in self._statuses:
            self._selected_camera = camera_id
            self._image_ref = None
            self._last_frame = None
            self._render_selected_camera()

    def _render_selected_camera(self) -> None:
        camera_id = self._selected_camera
        status = self._statuses.get(camera_id)
        if not camera_id or status is None:
            self._show_message("Connect and configure this camera on the Raspberry Pi to view its stream.")
            self.state_label.configure(
                text="No camera connected",
                text_color=COLORS["amber"],
            )
            return

        state = str(status.get("state", "N/A"))
        fps = status.get("fps", "N/A")
        if isinstance(fps, (int, float)):
            fps = f"{fps:.1f} FPS"
        self.state_label.configure(
            text=f"{camera_id}  •  {state}  •  {fps}",
            text_color={
                "ONLINE": COLORS["green"],
                "DEGRADED": COLORS["amber"],
                "CONNECTING": COLORS["amber"],
                "OFFLINE": COLORS["red"],
            }.get(state, COLORS["muted"]),
        )
        frame = self._frames.get(camera_id)
        if frame is None:
            error = self._preview_errors.get(camera_id)
            self._show_message(
                f"Camera stream unavailable: {error}"
                if error else "Waiting for the live camera stream..."
            )
            return

        if self._last_frame is frame:
            return
        self._last_frame = frame
        image = frame.copy()
        image.thumbnail((720, 405))
        rendered = ctk.CTkImage(
            light_image=image,
            dark_image=image,
            size=image.size,
        )
        self._image_ref = rendered
        self.preview.configure(text="", image=rendered)

    def _show_message(self, message: str) -> None:
        self._image_ref = None
        self.preview.configure(text=message, image=None)
