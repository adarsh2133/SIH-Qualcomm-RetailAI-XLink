import os
from datetime import datetime
from pathlib import Path

import customtkinter as ctk
import requests

from metrics_api import RuntimeDataCollector

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

METRICS_API_URL = os.environ.get("METRICS_API_URL", "http://127.0.0.1:8000/api/metrics")


class RetailEdgeDashboard(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("XLink EdgeAI Dashboard")
        self.geometry("1500x900")
        self.minsize(1280, 760)
        self.configure(fg_color="#0b1220")

        # NOTE: this now honors the same RETAIL_EDGE_RUNTIME_DIR env var that
        # entry_counter.py / queue_monitor.py / shelf_monitor.py /
        # edge_health_monitor.py / metrics_api.py all use. Previously this was
        # hardcoded to a path relative to dashboard.py, so if the runtime dir
        # was overridden (e.g. by a launcher, or a different working
        # directory) the dashboard's file-based fallback silently read stale
        # or empty data instead of the real sensor output.
        self.runtime_dir = Path(
            os.environ.get("RETAIL_EDGE_RUNTIME_DIR", Path(__file__).resolve().parent / ".runtime")
        )
        self.event_history = []
        self.alert_history = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.build_header()

        self.main = ctk.CTkFrame(self, fg_color="transparent")
        self.main.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        self.main.grid_rowconfigure(1, weight=1)
        self.main.grid_columnconfigure(0, weight=1)

        self.kpi_panel = ctk.CTkFrame(self.main, fg_color="transparent")
        self.kpi_panel.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        self.kpi_panel.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.build_kpis()

        self.content = ctk.CTkFrame(self.main, fg_color="transparent")
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=2)
        self.content.grid_columnconfigure(1, weight=1)
        self.content.grid_rowconfigure(0, weight=1)

        self.build_left_panel()
        self.build_right_panel()

        self.update_dashboard()

    def build_header(self):
        header = ctk.CTkFrame(self, fg_color="#111827", corner_radius=12, border_width=1, border_color="#243244")
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 10))
        header.grid_columnconfigure(0, weight=1)
        header.grid_columnconfigure(1, weight=0)

        title_label = ctk.CTkLabel(
            header,
            text="⚡ RetailEdge AI",
            font=("Segoe UI", 24, "bold"),
            text_color="#60a5fa",
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="w", padx=22, pady=16)

        right_stack = ctk.CTkFrame(header, fg_color="transparent")
        right_stack.grid(row=0, column=1, sticky="e", padx=22, pady=16)

        self.sys_status_badge = ctk.CTkLabel(
            right_stack,
            text="● LIVE",
            fg_color="#0f172a",
            text_color="#22c55e",
            font=("Segoe UI", 11, "bold"),
            corner_radius=9,
            padx=12,
            pady=6,
        )
        self.sys_status_badge.pack(side="left", padx=(0, 12))

        self.time_label = ctk.CTkLabel(
            right_stack,
            text="--:--:--",
            text_color="#cbd5e1",
            font=("Segoe UI", 11),
        )
        self.time_label.pack(side="left")

    def build_kpis(self):
        self.kpi_cards = {}
        cards = [
            ("footfall", "👥 Footfall", "0", "visitors/min"),
            ("queue", "⏱ Avg Wait", "0s", "seconds"),
            ("inventory", "📦 Stock", "--", "items"),
            ("conversion", "💰 Conversion", "0%", "rate"),
            ("network", "🌐 Network", "OK", "status"),
        ]

        for idx, (key, label, value, unit) in enumerate(cards):
            card = ctk.CTkFrame(
                self.kpi_panel,
                fg_color="#111827",
                corner_radius=14,
                border_width=1,
                border_color="#273548",
            )
            card.grid(row=0, column=idx, sticky="nsew", padx=8)

            title = ctk.CTkLabel(card, text=label, text_color="#94a3b8", font=("Segoe UI", 10, "bold"), anchor="w")
            title.pack(anchor="w", padx=16, pady=(12, 2))

            val = ctk.CTkLabel(card, text=value, text_color="#f8fafc", font=("Segoe UI", 24, "bold"), anchor="w")
            val.pack(anchor="w", padx=16, pady=(0, 2))

            unit_lbl = ctk.CTkLabel(card, text=unit, text_color="#64748b", font=("Segoe UI", 9), anchor="w")
            unit_lbl.pack(anchor="w", padx=16, pady=(0, 12))

            self.kpi_cards[key] = {"value": val, "unit": unit_lbl, "card": card}

    def build_left_panel(self):
        left = ctk.CTkFrame(self.content, fg_color="#0f172a", corner_radius=16, border_width=1, border_color="#243244")
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        left.grid_rowconfigure(2, weight=1)
        left.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(left, text="📹 Camera Network", text_color="#e2e8f0", font=("Segoe UI", 16, "bold"), anchor="w")
        title.grid(row=0, column=0, sticky="w", padx=18, pady=(18, 10))

        camera_grid = ctk.CTkFrame(left, fg_color="transparent")
        camera_grid.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        for i in range(5):
            camera_grid.grid_columnconfigure(i, weight=1)

        self.cam_cards = {}
        cameras = [
            ("cam_entry", "Entry", "Footfall"),
            ("cam_queue1", "Queue 1", "Congestion"),
            ("cam_queue2", "Queue 2", "Wait time"),
            ("cam_stock1", "Shelf 1", "Inventory"),
            ("cam_stock2", "Shelf 2", "Inventory"),
        ]

        for idx, (cam_id, label, purpose) in enumerate(cameras):
            card = ctk.CTkFrame(camera_grid, fg_color="#111827", corner_radius=12, border_width=1, border_color="#334155")
            card.grid(row=0, column=idx, sticky="nsew", padx=5)
            card.grid_columnconfigure(0, weight=1)

            name = ctk.CTkLabel(card, text=label, text_color="#f8fafc", font=("Segoe UI", 11, "bold"), anchor="w")
            name.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 2))

            purpose_label = ctk.CTkLabel(card, text=purpose, text_color="#94a3b8", font=("Segoe UI", 8), anchor="w")
            purpose_label.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

            state_label = ctk.CTkLabel(
                card,
                text="● WAITING",
                fg_color="#1f2937",
                text_color="#fbbf24",
                font=("Segoe UI", 9, "bold"),
                corner_radius=7,
                padx=8,
                pady=5,
                anchor="w",
            )
            state_label.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))
            self.cam_cards[cam_id] = state_label

        events_title = ctk.CTkLabel(left, text="🧾 Live Event Log", text_color="#e2e8f0", font=("Segoe UI", 16, "bold"), anchor="w")
        events_title.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 10))

        event_box = ctk.CTkFrame(left, fg_color="#020817", corner_radius=12, border_width=1, border_color="#1f2937")
        event_box.grid(row=3, column=0, sticky="nsew", padx=18, pady=(0, 18))
        event_box.grid_rowconfigure(0, weight=1)
        event_box.grid_columnconfigure(0, weight=1)

        self.logs_box = ctk.CTkTextbox(event_box, fg_color="transparent", text_color="#34d399", font=("Consolas", 10), activate_scrollbars=True)
        self.logs_box.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        self.logs_box.insert("0.0", "[INIT] Dashboard ready. Waiting for sensor data...\n")
        self.logs_box.configure(state="disabled")

    def build_right_panel(self):
        right = ctk.CTkFrame(self.content, fg_color="#0f172a", corner_radius=16, border_width=1, border_color="#243244")
        right.grid(row=0, column=1, sticky="nsew")
        right.grid_rowconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        right.grid_rowconfigure(2, weight=1)
        right.grid_columnconfigure(0, weight=1)

        alerts = ctk.CTkFrame(right, fg_color="#111827", corner_radius=12, border_width=1, border_color="#334155")
        alerts.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 10))
        alerts.grid_columnconfigure(0, weight=1)

        alert_title = ctk.CTkLabel(alerts, text="🚨 Alerts", text_color="#f8fafc", font=("Segoe UI", 14, "bold"), anchor="w")
        alert_title.grid(row=0, column=0, sticky="w", padx=14, pady=(12, 10))

        self.alerts_box = ctk.CTkTextbox(alerts, fg_color="transparent", text_color="#fca5a5", font=("Segoe UI", 10), height=6)
        self.alerts_box.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.alerts_box.insert("0.0", "[OK] No active operational alerts.\n")
        self.alerts_box.configure(state="disabled")

        inv = ctk.CTkFrame(right, fg_color="#111827", corner_radius=12, border_width=1, border_color="#334155")
        inv.grid(row=1, column=0, sticky="nsew", padx=12, pady=10)
        inv.grid_columnconfigure(0, weight=1)
        inv.grid_columnconfigure(1, weight=0)

        inv_title = ctk.CTkLabel(inv, text="📦 Inventory", text_color="#f8fafc", font=("Segoe UI", 14, "bold"), anchor="w")
        inv_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 10))

        for idx, (key, label, color) in enumerate([
            ("critical", "Critical", "#ef4444"),
            ("low", "Low", "#f59e0b"),
            ("normal", "Normal", "#22c55e"),
        ]):
            lbl = ctk.CTkLabel(inv, text=f"{label}", text_color=color, font=("Segoe UI", 10, "bold"), anchor="w")
            lbl.grid(row=idx + 1, column=0, sticky="w", padx=14, pady=6)
            value = ctk.CTkLabel(inv, text="0", text_color="#f8fafc", font=("Segoe UI", 10, "bold"), anchor="e")
            value.grid(row=idx + 1, column=1, sticky="e", padx=14, pady=6)
            if key == "critical":
                self.inv_critical = value
            elif key == "low":
                self.inv_low = value
            else:
                self.inv_normal = value

        queue = ctk.CTkFrame(right, fg_color="#111827", corner_radius=12, border_width=1, border_color="#334155")
        queue.grid(row=2, column=0, sticky="nsew", padx=12, pady=(10, 12))
        queue.grid_columnconfigure(0, weight=1)
        queue.grid_columnconfigure(1, weight=0)

        q_title = ctk.CTkLabel(queue, text="⏱ Queue", text_color="#f8fafc", font=("Segoe UI", 14, "bold"), anchor="w")
        q_title.grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(12, 8))

        self.queue_current = ctk.CTkLabel(queue, text="0", text_color="#f8fafc", font=("Segoe UI", 18, "bold"))
        self.queue_current.grid(row=1, column=0, sticky="w", padx=14, pady=(6, 2))

        self.queue_wait = ctk.CTkLabel(queue, text="0s", text_color="#60a5fa", font=("Segoe UI", 13, "bold"))
        self.queue_wait.grid(row=2, column=0, sticky="w", padx=14, pady=(2, 6))

        self.queue_pred = ctk.CTkLabel(queue, text="LOW", text_color="#22c55e", font=("Segoe UI", 10, "bold"), anchor="e")
        self.queue_pred.grid(row=1, column=1, rowspan=2, sticky="e", padx=14, pady=(4, 8))

        self.staffing_label = ctk.CTkLabel(queue, text="Staffing: Optimal", text_color="#94a3b8", font=("Segoe UI", 9), anchor="w")
        self.staffing_label.grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 12))

    def fetch_live_data(self):
        try:
            response = requests.get(METRICS_API_URL, timeout=1.2)
            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        # API unreachable -> fall back to reading the shared runtime dir
        # directly, using the EXACT SAME RuntimeDataCollector the API uses.
        # (Previously this duplicated the aggregation logic by hand, which
        # had drifted out of sync with metrics_api.py - e.g. it mirrored
        # camera 2's status off camera 1's feed instead of checking it
        # independently. Sharing one implementation means the dashboard can
        # never show something the API wouldn't also show.)
        return RuntimeDataCollector(self.runtime_dir).get_metrics()

    def update_dashboard(self):
        now = datetime.now().strftime("%H:%M:%S")
        self.time_label.configure(text=now)

        data = self.fetch_live_data()
        self.apply_data(data)

        self.after(1500, self.update_dashboard)

    def set_camera_status(self, key, status):
        label = self.cam_cards.get(key)
        if not label:
            return
        color_map = {
            "online": ("● ONLINE", "#22c55e", "#0b3b2e"),
            "offline": ("● OFFLINE", "#ef4444", "#3b1f1f"),
            "initializing": ("● INIT", "#fbbf24", "#3d2a0f"),
            "waiting": ("● WAITING", "#fbbf24", "#3d2a0f"),
        }
        text, color, bg = color_map.get(status, color_map["waiting"])
        label.configure(text=text, text_color=color, fg_color=bg)

    def apply_data(self, data):
        if not data:
            self.sys_status_badge.configure(text="● OFFLINE", text_color="#f97316")
            for cam_id in self.cam_cards:
                self.set_camera_status(cam_id, "offline")
            self.kpi_cards["footfall"]["value"].configure(text="OFFLINE")
            self.kpi_cards["queue"]["value"].configure(text="N/A")
            self.kpi_cards["inventory"]["value"].configure(text="N/A")
            self.kpi_cards["network"]["value"].configure(text="OFFLINE")
            self.inv_critical.configure(text="0")
            self.inv_low.configure(text="0")
            self.inv_normal.configure(text="0")
            self.queue_current.configure(text="N/A")
            self.queue_wait.configure(text="N/A")
            self.queue_pred.configure(text="OFFLINE", text_color="#ef4444")
            self.staffing_label.configure(text="System offline", text_color="#f97316")
            self.alerts_box.configure(state="normal")
            self.alerts_box.delete("0.0", "end")
            self.alerts_box.insert("0.0", "[OFFLINE] No live data is available. Cameras are disconnected.\n")
            self.alerts_box.configure(state="disabled")
            self.logs_box.configure(state="normal")
            self.logs_box.delete("0.0", "end")
            self.logs_box.insert("0.0", "[OFFLINE] All systems are disconnected. No live telemetry available.\n")
            self.logs_box.configure(state="disabled")
            return

        cameras = data.get("cameras", {})
        online_count = sum(1 for status in cameras.values() if status == "online")
        for cam_id in self.cam_cards:
            status = cameras.get(cam_id, "offline")
            self.set_camera_status(cam_id, status)

        if online_count == 0:
            self.sys_status_badge.configure(text="● OFFLINE", text_color="#f97316")
            self.kpi_cards["footfall"]["value"].configure(text="OFFLINE")
            self.kpi_cards["queue"]["value"].configure(text="N/A")
            self.kpi_cards["inventory"]["value"].configure(text="N/A")
            self.kpi_cards["network"]["value"].configure(text="OFFLINE")
            self.inv_critical.configure(text="0")
            self.inv_low.configure(text="0")
            self.inv_normal.configure(text="0")
            self.queue_current.configure(text="N/A")
            self.queue_wait.configure(text="N/A")
            self.queue_pred.configure(text="OFFLINE", text_color="#ef4444")
            self.staffing_label.configure(text="System offline", text_color="#f97316")
            self.alerts_box.configure(state="normal")
            self.alerts_box.delete("0.0", "end")
            self.alerts_box.insert("0.0", "[OFFLINE] No live telemetry received. System is disconnected.\n")
            self.alerts_box.configure(state="disabled")
            self.logs_box.configure(state="normal")
            self.logs_box.delete("0.0", "end")
            self.logs_box.insert("0.0", "[OFFLINE] No live telemetry received. All camera feeds are disconnected.\n")
            self.logs_box.configure(state="disabled")
            return

        footfall = data.get("footfall", {})
        queue = data.get("queue", {})
        inventory = data.get("inventory", {})
        inv_status = data.get("inventory_status", {"critical": 0, "low": 0, "normal": 0})

        self.kpi_cards["footfall"]["value"].configure(text=str(footfall.get("current", 0)))
        self.kpi_cards["queue"]["value"].configure(text=f"{queue.get('avg_wait', 0)}s")
        if inventory:
            total = inventory.get("total", 0)
            optimal = inventory.get("optimal", 0)
            self.kpi_cards["inventory"]["value"].configure(text=f"{optimal}/{total}" if total else "0")
        self.kpi_cards["conversion"]["value"].configure(text="--")
        active_nodes = data.get("active_nodes", 0)
        self.kpi_cards["network"]["value"].configure(text=f"{active_nodes} OK" if active_nodes else "WAIT")

        self.inv_critical.configure(text=str(inv_status.get("critical", 0)))
        self.inv_low.configure(text=str(inv_status.get("low", 0)))
        self.inv_normal.configure(text=str(inv_status.get("normal", 0)))

        congestion = str(queue.get("congestion", "Low")).capitalize()
        self.queue_current.configure(text=str(queue.get("active_queues", 0)))
        self.queue_wait.configure(text=f"{queue.get('max_wait', 0)}s")
        color = {"Low": "#22c55e", "Medium": "#fbbf24", "High": "#ef4444"}.get(congestion, "#22c55e")
        self.queue_pred.configure(text=congestion.upper(), text_color=color)

        if congestion == "High":
            self.staffing_label.configure(text="Staffing: Open additional counter", text_color="#fbbf24")
        elif congestion == "Medium":
            self.staffing_label.configure(text="Staffing: Monitor queue growth", text_color="#f59e0b")
        else:
            self.staffing_label.configure(text="Staffing: Optimal", text_color="#94a3b8")

        healthy = bool(data.get("system", {}).get("healthy", False)) or bool(data.get("overall_health", {}).get("healthy", False))
        self.sys_status_badge.configure(text="● LIVE" if healthy else "● WARN", text_color="#22c55e" if healthy else "#fbbf24")

        alert_lines = []
        critical_items = inv_status.get("critical", 0)
        if critical_items > 0:
            alert_lines.append(f"⚠️ {critical_items} items are at critical stock level.")
        if queue.get("congestion") in ("High", "Medium"):
            alert_lines.append(f"⚠️ Queue congestion is {str(queue.get('congestion', 'Low')).capitalize()}.")
        if not alert_lines:
            alert_lines.append("[OK] No active operational alerts.")

        self.alerts_box.configure(state="normal")
        self.alerts_box.delete("0.0", "end")
        self.alerts_box.insert("0.0", "\n".join(f"{line}" for line in alert_lines) + "\n")
        self.alerts_box.configure(state="disabled")

        events = data.get("events", [])
        self.logs_box.configure(state="normal")
        self.logs_box.delete("0.0", "end")
        if not events:
            self.logs_box.insert("0.0", "[INFO] Monitoring active sensors...\n")
        else:
            for event in events[:10]:
                ts = event.get("time", datetime.now().strftime("%H:%M:%S"))
                cam = str(event.get("cam", "system"))
                et = str(event.get("type", "EVENT")).upper()
                val = str(event.get("val", "--"))
                detail = str(event.get("details", ""))
                self.logs_box.insert("end", f"[{ts}] {cam:<12} | {et:<10} | {val:<6} | {detail}\n")
        self.logs_box.configure(state="disabled")


if __name__ == "__main__":
    app = RetailEdgeDashboard()
    app.mainloop()