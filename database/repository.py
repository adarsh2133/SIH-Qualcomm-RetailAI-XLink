"""Repository helpers for local persistence."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, Mapping


class Repository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def seed_demo_data(self) -> None:
        self.connection.execute(
            "INSERT OR IGNORE INTO cameras (id, kind, source, enabled) VALUES (?, ?, ?, ?)",
            ("usb-01", "usb", "simulated", 1),
        )
        self.connection.execute(
            "INSERT OR IGNORE INTO cameras (id, kind, source, enabled) VALUES (?, ?, ?, ?)",
            ("pi-01", "pi", "simulated", 1),
        )
        self.connection.execute(
            "INSERT INTO analytics_events (event_type, camera_id, payload, environment, valid) VALUES (?, ?, ?, ?, 0)",
            ("footfall", "usb-01", json.dumps({"visits": 42, "occupancy": 18}), "simulation"),
        )
        self.connection.execute(
            "INSERT INTO analytics_events (event_type, camera_id, payload, environment, valid) VALUES (?, ?, ?, ?, 0)",
            ("queue", "pi-01", json.dumps({"avg_wait_s": 220.0}), "simulation"),
        )
        self.connection.commit()

    def get_dashboard_summary(self) -> Dict[str, Any]:
        camera_rows = self.connection.execute(
            "SELECT id, kind, source, enabled FROM cameras "
            "WHERE lower(source) NOT IN ('sim', 'simulation', 'simulated')"
        ).fetchall()
        event_rows = self.connection.execute(
            "SELECT event_type, camera_id, payload FROM analytics_events "
            "WHERE environment = 'live' AND valid = 1 AND created_at >= datetime('now', '-5 minutes') "
            "ORDER BY id DESC LIMIT 10"
        ).fetchall()
        footfall = {"status": "UNAVAILABLE", "value": None}
        queue = {"status": "UNAVAILABLE", "value": None}
        for row in event_rows:
            payload = json.loads(row["payload"]) if row["payload"] else {}
            if row["event_type"] == "footfall":
                footfall = {"status": "AVAILABLE", "value": payload}
            if row["event_type"] == "queue":
                queue = {"status": "AVAILABLE", "value": payload}
        return {
            "cameras": [dict(row) for row in camera_rows],
            "events": [
                {"event_type": row["event_type"], "camera_id": row["camera_id"], "payload": json.loads(row["payload"]) if row["payload"] else {}}
                for row in event_rows
            ],
            "footfall": footfall, "queue": queue,
        }

    def record_event(self, event_type: str, payload: Mapping[str, Any], camera_id: str | None = None,
                     *, environment: str = "live", valid: bool = False) -> int:
        cursor = self.connection.execute(
            "INSERT INTO analytics_events(event_type,camera_id,payload,environment,valid) VALUES(?,?,?,?,?)",
            (event_type, camera_id, json.dumps(dict(payload), default=str), environment, int(valid)))
        self.connection.commit()
        return int(cursor.lastrowid)

    def save_snapshot(self, snapshot_type: str, payload: Mapping[str, Any]) -> int:
        cursor = self.connection.execute(
            "INSERT INTO snapshots(snapshot_type,payload) VALUES(?,?)",
            (snapshot_type, json.dumps(dict(payload), default=str)))
        self.connection.commit()
        return int(cursor.lastrowid)

    def latest_snapshots(self, snapshot_type: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        if snapshot_type:
            rows = self.connection.execute("SELECT * FROM snapshots WHERE snapshot_type=? ORDER BY id DESC LIMIT ?",
                                           (snapshot_type, limit)).fetchall()
        else:
            rows = self.connection.execute("SELECT * FROM snapshots ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [{"id": row["id"], "snapshot_type": row["snapshot_type"],
                 "payload": json.loads(row["payload"]), "created_at": row["created_at"]} for row in rows]
