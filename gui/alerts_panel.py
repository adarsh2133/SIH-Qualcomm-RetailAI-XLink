"""Live operational alerts received from the Raspberry Pi."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import customtkinter as ctk

from .ui_components import Card, COLORS, ScrollPage, empty_state


class AlertsPanel(ScrollPage):
    def __init__(self, master, **kwargs):
        super().__init__(
            master,
            "Alerts",
            "Live detection, shelf-count, camera, and inference alerts",
            **kwargs,
        )
        self._rendered_key: tuple[str, ...] | None = None

    def update_alerts(self, alerts: list[dict[str, Any]],
                      events: list[dict[str, Any]]) -> None:
        active = [item for item in alerts if isinstance(item, dict)]
        recent = [item for item in events if isinstance(item, dict)]
        key = tuple(
            str(item.get("id", "")) + str(item.get("message", ""))
            for item in active + recent[:20]
        )
        if key == self._rendered_key:
            return
        self._rendered_key = key
        for child in self.body.winfo_children():
            child.destroy()
        self._row = 0

        self._section_title("ACTIVE ALERTS")
        if active:
            for alert in active:
                self._alert_card(alert, active=True)
        else:
            empty_state(
                self.body,
                "No active alerts",
                "Detection and system alerts will appear here as live Pi data arrives.",
            ).grid(row=self._row, column=0, sticky="ew", pady=(0, 16))
            self._row += 1

        self._section_title("RECENT EVENTS")
        for alert in recent[:20]:
            self._alert_card(alert, active=False)
        if not recent:
            ctk.CTkLabel(
                self.body,
                text="No alert events received yet.",
                text_color=COLORS["muted"],
            ).grid(row=self._row, column=0, sticky="w", pady=(0, 12))
            self._row += 1

    def _section_title(self, title: str) -> None:
        ctk.CTkLabel(
            self.body,
            text=title,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=11, weight="bold"),
        ).grid(row=self._row, column=0, sticky="w", pady=(0, 8))
        self._row += 1

    def _alert_card(self, alert: dict[str, Any], active: bool) -> None:
        severity = str(alert.get("severity", "info")).lower()
        color = {
            "critical": COLORS["red"],
            "warning": COLORS["amber"],
            "info": COLORS["blue"],
        }.get(severity, COLORS["muted"])
        card = Card(self.body)
        card.grid(row=self._row, column=0, sticky="ew", pady=(0, 8))
        self._row += 1
        heading = ctk.CTkFrame(card, fg_color="transparent")
        heading.pack(fill="x", padx=14, pady=(10, 4))
        category = str(alert.get("category", "alert")).replace("_", " ").upper()
        ctk.CTkLabel(
            heading,
            text=category,
            text_color=color,
            font=ctk.CTkFont(size=11, weight="bold"),
        ).pack(side="left")
        state = "ACTIVE" if active else "EVENT"
        ctk.CTkLabel(
            heading,
            text=state,
            text_color=COLORS["muted"],
            font=ctk.CTkFont(size=10, weight="bold"),
        ).pack(side="right")
        ctk.CTkLabel(
            card,
            text=str(alert.get("message", "Alert details unavailable.")),
            text_color=COLORS["text"],
            anchor="w",
            justify="left",
            wraplength=800,
        ).pack(fill="x", padx=14, pady=(0, 4))
        timestamp = alert.get("created_at") or alert.get("updated_at")
        if timestamp:
            text = str(timestamp)
            try:
                text = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone().strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                pass
            ctk.CTkLabel(
                card,
                text=text,
                text_color=COLORS["muted"],
                anchor="w",
                font=ctk.CTkFont(size=10),
            ).pack(fill="x", padx=14, pady=(0, 10))
