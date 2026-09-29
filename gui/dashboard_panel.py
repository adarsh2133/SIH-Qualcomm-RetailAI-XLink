"""Overview page: only current, validated runtime state is displayed."""
from __future__ import annotations
import customtkinter as ctk
from .ui_components import ScrollPage, MetricCard, Card, Badge, COLORS


class DashboardPanel(ScrollPage):
    def __init__(self, master, settings=None, **kwargs):
        super().__init__(master, "Overview", "Command centre for live edge operations • no historical values mixed into live views", **kwargs)
        self.settings = settings
        self.system = ctk.CTkLabel(self.body, text="SYSTEM STARTING", text_color=COLORS["amber"],
                                   font=ctk.CTkFont(size=13, weight="bold"))
        self.system.grid(row=0, column=0, sticky="w", pady=(0, 16))
        self.cards = {}
        grid = ctk.CTkFrame(self.body, fg_color="transparent")
        grid.grid(row=1, column=0, sticky="ew")
        for col in range(4): grid.grid_columnconfigure(col, weight=1)
        for i, (key, title, icon) in enumerate((
                ("footfall", "Footfall today", "footfall"),
                ("queue", "Queue length", "queue"),
                ("inventory", "Inventory units", "inventory"),
                ("dwell", "Avg dwell time", "dwell"))):
            card = MetricCard(grid, title, icon=icon)
            card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 6 if i < 3 else 0))
            self.cards[key] = card
        alert = Card(self.body)
        alert.grid(row=2, column=0, sticky="ew", pady=(18, 0))
        from .icons import Icon
        alert_title = ctk.CTkFrame(alert, fg_color="transparent")
        alert_title.pack(anchor="w", padx=16, pady=(13, 4))
        Icon(alert_title, "alerts", size=16, color=COLORS["amber"], bg=COLORS["surface"]).pack(side="left", padx=(0, 7))
        ctk.CTkLabel(alert_title, text="ALERT CENTRE", text_color=COLORS["amber"],
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.alert_text = ctk.CTkLabel(alert, text="No validated alerts available.", text_color=COLORS["muted"])
        self.alert_text.pack(anchor="w", padx=16, pady=(0, 15))
        inference = Card(self.body)
        inference.grid(row=3, column=0, sticky="ew", pady=(18, 0))
        inference_title = ctk.CTkFrame(inference, fg_color="transparent")
        inference_title.pack(anchor="w", padx=16, pady=(13, 4))
        Icon(inference_title, "ai", size=16, color=COLORS["blue"], bg=COLORS["surface"]).pack(side="left", padx=(0, 7))
        ctk.CTkLabel(inference_title, text="INFERENCE ENGINE", text_color=COLORS["muted"],
                     font=ctk.CTkFont(size=11, weight="bold")).pack(side="left")
        self.inference_text = ctk.CTkLabel(
            inference,             text="Qualcomm AI Hub\nUNAVAILABLE",
            text_color=COLORS["text"], justify="left",
        )
        self.inference_text.pack(anchor="w", padx=16, pady=(0, 15))

    def update_metrics(self, statuses, metrics=None, inference_status=None, inference_name=None):
        online = sum(s.get("state") == "ONLINE" for s in statuses)
        total = len(statuses)
        state = "ONLINE" if online == total and online else ("DEGRADED" if online else "OFFLINE")
        color = {"ONLINE": COLORS["green"], "DEGRADED": COLORS["amber"], "OFFLINE": COLORS["red"]}[state]
        self.system.configure(text=f"SYSTEM {state}   •   {online}/{total} CAMERAS ONLINE", text_color=color)
        for key, card in self.cards.items():
            item = (metrics or {}).get(key, {})
            card.set_value(item.get("value") if item.get("valid") and item.get("status") == "AVAILABLE" else "N/A")
        inference_status = inference_status or {}
        backend = inference_name or inference_status.get("runtime", "Inference")
        state = inference_status.get("state", "UNAVAILABLE")
        reason = inference_status.get("error") or "No validated runtime telemetry"
        self.inference_text.configure(
            text=f"{backend}\n{state}\n{reason}",
            text_color=COLORS["green"] if state in {"ONLINE", "RUNNING"} else COLORS["amber"],
        )

    def update_alert_summary(self, alerts):
        alerts = [item for item in alerts if isinstance(item, dict)]
        if not alerts:
            self.alert_text.configure(
                text="No active alerts.",
                text_color=COLORS["muted"],
            )
            return
        summary = "  •  ".join(
            str(item.get("message", "Alert")) for item in alerts[:3]
        )
        self.alert_text.configure(
            text=f"{len(alerts)} active  •  {summary}",
            text_color=(
                COLORS["red"] if any(
                    item.get("severity") == "critical" for item in alerts
                ) else COLORS["amber"]
            ),
        )
