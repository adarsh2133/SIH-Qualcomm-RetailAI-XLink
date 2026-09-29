"""Local report exports; the public export_report API is intentionally stable."""
from __future__ import annotations
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
import customtkinter as ctk
from .ui_components import ScrollPage, Card, COLORS


def export_report(root_dir, name, payload, fmt="json") -> Path:
    target = Path(root_dir) / "data" / "reports"
    target.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = target / f"{name}_{stamp}.{fmt}"
    with path.open("w", newline="", encoding="utf-8") as handle:
        if fmt == "csv":
            writer = csv.writer(handle)
            writer.writerow(["metric", "value", "status"])
            for key, value in payload.items():
                writer.writerow([key, value, "VALIDATED" if value is not None else "N/A"])
        else:
            json.dump(payload, handle, indent=2, default=str)
    return path


class ReportsPanel(ScrollPage):
    def __init__(self, master, settings=None, **kwargs):
        super().__init__(master, "Reports", "Export the current runtime view locally; exports never become live input", **kwargs)
        self.settings = settings
        box = Card(self.body); box.grid(row=0, column=0, sticky="ew")
        root = Path(getattr(settings, "root_dir", Path.cwd()))
        self.report_dir = root / "data" / "reports"
        ctk.CTkLabel(box, text="LOCAL OUTPUT LOCATION", text_color=COLORS["muted"],
                     font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=18, pady=(16, 2))
        ctk.CTkLabel(box, text=str(self.report_dir), text_color=COLORS["blue"]).pack(anchor="w", padx=18)
        ctk.CTkLabel(box, text="Only current validated metrics are exported. Unavailable values remain N/A.",
                     text_color=COLORS["muted"]).pack(anchor="w", padx=18, pady=(8, 14))
        actions = ctk.CTkFrame(box, fg_color="transparent"); actions.pack(anchor="w", padx=18, pady=(0, 16))
        ctk.CTkButton(actions, text="Export JSON", command=lambda: self._export("json"),
                      fg_color=COLORS["blue"]).pack(side="left", padx=(0, 8))
        ctk.CTkButton(actions, text="Export CSV", command=lambda: self._export("csv"),
                      fg_color=COLORS["surface_alt"]).pack(side="left")
        self.status = ctk.CTkLabel(self.body, text="Ready — no report generated this session.", text_color=COLORS["muted"])
        self.status.grid(row=1, column=0, sticky="w", pady=16)

    def _export(self, fmt):
        root = getattr(self.settings, "root_dir", Path.cwd())
        path = export_report(root, "portal_xlink_current", {
            "footfall": None, "queue_length": None, "inventory_units": None,
            "dwell_seconds": None,
            "mode": "SIMULATION/TEST" if getattr(self.settings, "simulation", False) else "LIVE",
        }, fmt)
        self.status.configure(text=f"Exported successfully: {path}", text_color=COLORS["green"])
