"""Camera health page backed exclusively by CameraManager worker status."""
from __future__ import annotations

import customtkinter as ctk

from .icons import Icon
from .ui_components import COLORS, Card, ScrollPage


class CameraPanel(ScrollPage):
    def __init__(self, master, settings=None, **kwargs):
        super().__init__(
            master,
            "Cameras",
            "Live camera previews, source health and frame status",
            **kwargs,
        )
        self.cards = ctk.CTkFrame(self.body, fg_color="transparent")
        self.cards.grid(row=0, column=0, sticky="nsew")
        self._image_refs = []
        self._preview_widgets = {}
        self._camera_widgets = {}
        self._last_frames = {}
        self._camera_signature = None
        self._empty_label = ctk.CTkLabel(
            self.cards,
            text="No configured camera slots.",
            text_color=COLORS["muted"],
        )

    def update_status(self, statuses, camera_frames=None):
        statuses = [status for status in statuses if isinstance(status, dict)]
        camera_ids = tuple(str(status.get("camera_id", "unknown")) for status in statuses)
        if camera_ids != self._camera_signature:
            for child in self.cards.winfo_children():
                child.destroy()
            self._camera_widgets.clear()
            self._preview_widgets.clear()
            self._last_frames.clear()
            self._camera_signature = camera_ids
            self._image_refs.clear()
            if not statuses:
                self._empty_label = ctk.CTkLabel(
                    self.cards,
                    text="No configured camera slots.",
                    text_color=COLORS["muted"],
                )
                self._empty_label.pack(anchor="w")
            else:
                for status in statuses:
                    self._create_camera_card(status)

        for status in statuses:
            camera_id = str(status.get("camera_id", "unknown"))
            widgets = self._camera_widgets.get(camera_id)
            if widgets is None:
                continue
            state = str(status.get("state", "N/A"))
            widgets["state"].configure(
                text=state,
                text_color={
                    "ONLINE": COLORS["green"],
                    "DEGRADED": COLORS["amber"],
                    "CONNECTING": COLORS["amber"],
                    "OFFLINE": COLORS["red"],
                }.get(state, COLORS["muted"]),
            )
            age = status.get("frame_age_s")
            freshness = "N/A" if age is None else f"{age:.1f}s"
            fps = status.get("fps", "N/A")
            if isinstance(fps, (int, float)):
                fps = f"{fps:.1f}"
            inference_latency = status.get("inference_latency_ms")
            if isinstance(inference_latency, (int, float)):
                inference_latency = f"{inference_latency:.1f}"
            else:
                inference_latency = "N/A"
            inference_fps = status.get("inference_fps")
            if isinstance(inference_fps, (int, float)):
                inference_fps = f"{inference_fps:.1f}"
            else:
                inference_fps = "N/A"
            widgets["frame"].configure(text=f"FRAME AGE  {freshness}   FPS  {fps}")
            widgets["details"].configure(
                text=(
                    f"SOURCE  {status.get('source', 'N/A') or 'N/A'}\n"
                    f"INFERENCE  {inference_latency} ms  "
                    f"({inference_fps} FPS)\n"
                    f"FAILURES  {status.get('consecutive_read_failures', 0)}   "
                    f"RECONNECTS  {status.get('reconnect_attempts', 0)}   "
                    f"WORKER  {status.get('worker_status', 'N/A')}"
                )
            )
            error = status.get("stream_error") or status.get("error") or ""
            widgets["error"].configure(
                text=f"ERROR  {error}" if error else "",
                text_color=COLORS["red"],
            )
            self._set_preview(camera_id, (camera_frames or {}).get(camera_id))

    def _create_camera_card(self, status):
        camera_id = str(status.get("camera_id", "unknown"))
        card = Card(self.cards)
        card.pack(fill="x", pady=(0, 10))
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(14, 4))
        Icon(
            top, "camera", size=18, color=COLORS["blue"], bg=COLORS["surface"]
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            top,
            text=camera_id.upper(),
            text_color=COLORS["text"],
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(side="left")
        state_label = ctk.CTkLabel(
            top,
            text="N/A",
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        state_label.pack(side="left", padx=12)
        frame_label = ctk.CTkLabel(top, text="FRAME AGE  N/A   FPS  N/A",
                                   text_color=COLORS["muted"])
        frame_label.pack(side="right")

        preview = ctk.CTkLabel(
            card,
            text="Live preview unavailable; waiting for a Pi frame.",
            text_color=COLORS["muted"],
        )
        preview.pack(anchor="w", padx=16, pady=(4, 12))
        details = ctk.CTkLabel(
            card,
            text="",
            text_color=COLORS["muted"],
            anchor="w",
            justify="left",
        )
        details.pack(fill="x", padx=16, pady=(0, 4))
        error = ctk.CTkLabel(
            card,
            text="",
            text_color=COLORS["red"],
            anchor="w",
            justify="left",
            wraplength=900,
        )
        error.pack(fill="x", padx=16, pady=(0, 14))
        self._camera_widgets[camera_id] = {
            "state": state_label,
            "frame": frame_label,
            "details": details,
            "error": error,
        }
        self._preview_widgets[camera_id] = preview

    def update_previews(self, camera_frames):
        for camera_id in self._preview_widgets:
            self._set_preview(camera_id, (camera_frames or {}).get(camera_id))

    def _set_preview(self, camera_id, frame):
        widget = self._preview_widgets.get(camera_id)
        if widget is None:
            return
        if frame is None:
            self._last_frames.pop(camera_id, None)
            widget.configure(
                text="Live preview unavailable; waiting for a Pi frame.",
                image=None,
            )
            return
        if self._last_frames.get(camera_id) is frame:
            return
        self._last_frames[camera_id] = frame
        preview = frame.copy()
        preview.thumbnail((560, 315))
        image = ctk.CTkImage(
            light_image=preview,
            dark_image=preview,
            size=preview.size,
        )
        self._image_refs.append(image)
        max_refs = 4 * max(1, len(self._preview_widgets))
        if len(self._image_refs) > max_refs:
            self._image_refs = self._image_refs[-2 * max(1, len(self._preview_widgets)):]
        widget.configure(text="", image=image)
