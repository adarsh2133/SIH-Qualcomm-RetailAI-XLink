"""Persistent local-day entry and exit totals for camera footfall."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sqlite3
import threading
from typing import Any


class DailyFootfallStore:
    def __init__(self, database_path: str | Path) -> None:
        path = str(database_path)
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            path, timeout=10, check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS footfall_daily (
                    local_date TEXT NOT NULL,
                    camera_id TEXT NOT NULL,
                    entries INTEGER NOT NULL DEFAULT 0,
                    exits INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (local_date, camera_id)
                )
                """
            )
            self._connection.commit()

    @staticmethod
    def _local_now() -> datetime:
        return datetime.now().astimezone()

    def record(self, camera_id: str, direction: str) -> None:
        if not camera_id:
            raise ValueError("camera_id is required")
        if direction not in {"entry", "exit"}:
            raise ValueError("direction must be entry or exit")
        now = self._local_now()
        column = "entries" if direction == "entry" else "exits"
        with self._lock:
            self._connection.execute(
                f"""
                INSERT INTO footfall_daily
                    (local_date, camera_id, entries, exits, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(local_date, camera_id) DO UPDATE SET
                    {column} = {column} + 1,
                    updated_at = excluded.updated_at
                """,
                (
                    now.date().isoformat(), camera_id,
                    int(direction == "entry"), int(direction == "exit"),
                    now.isoformat(timespec="seconds"),
                ),
            )
            self._connection.commit()

    def snapshot(self, camera_ids: list[str]) -> dict[str, Any]:
        now = self._local_now()
        counts = {
            camera_id: {"entries": 0, "exits": 0}
            for camera_id in camera_ids
        }
        with self._lock:
            rows = self._connection.execute(
                "SELECT camera_id, entries, exits FROM footfall_daily "
                "WHERE local_date = ?",
                (now.date().isoformat(),),
            ).fetchall()
        for row in rows:
            counts.setdefault(row["camera_id"], {"entries": 0, "exits": 0})
            counts[row["camera_id"]].update({
                "entries": int(row["entries"]),
                "exits": int(row["exits"]),
            })
        return {
            "state": "AVAILABLE" if camera_ids else "UNAVAILABLE",
            "date": now.date().isoformat(),
            "timezone": now.tzname() or "local",
            "total_entries": sum(item["entries"] for item in counts.values()),
            "total_exits": sum(item["exits"] for item in counts.values()),
            "cameras": counts,
            "method": "opencv_person_or_motion_fallback",
        }

    def close(self) -> None:
        with self._lock:
            self._connection.close()
