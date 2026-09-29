"""Low-overhead Linux process resource sampling for the Pi API."""
from __future__ import annotations

from pathlib import Path
import time
from typing import Callable


class RuntimeMonitor:
    def __init__(
        self,
        proc_root: str | Path = "/proc",
        *,
        interval_s: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        clock_ticks_per_second: int | None = None,
    ) -> None:
        if interval_s <= 0:
            raise ValueError("interval_s must be positive")
        self.proc_root = Path(proc_root)
        self.interval_s = interval_s
        self.clock = clock
        self.clock_ticks_per_second = (
            self._clock_ticks()
            if clock_ticks_per_second is None
            else clock_ticks_per_second
        )
        if self.clock_ticks_per_second <= 0:
            raise ValueError("clock_ticks_per_second must be positive")
        self._last_sample_at: float | None = None
        self._last_cpu: tuple[int, int, int] | None = None
        self._cached: dict[str, float | None] = {
            "process_cpu_percent": None,
            "system_cpu_percent": None,
            "process_rss_mb": None,
            "system_memory_percent": None,
        }

    def snapshot(self) -> dict[str, float | None]:
        now = self.clock()
        if (
            self._last_sample_at is not None
            and now - self._last_sample_at < self.interval_s
        ):
            return dict(self._cached)

        try:
            cpu = self._read_cpu()
            memory = self._read_memory()
        except (OSError, ValueError, IndexError) as exc:
            raise RuntimeError(f"unable to read Linux process resource metrics: {exc}") from exc

        if self._last_cpu is not None and self._last_sample_at is not None:
            elapsed = now - self._last_sample_at
            process_delta = cpu[0] - self._last_cpu[0]
            total_delta = cpu[1] - self._last_cpu[1]
            cpu_percent = (
                max(0.0, process_delta / (elapsed * self.clock_ticks_per_second) * 100.0)
                if elapsed > 0 else None
            )
            system_cpu_percent = (
                max(
                    0.0,
                    (total_delta - (cpu[2] - self._last_cpu[2]))
                    / total_delta * 100.0,
                )
                if total_delta > 0 else None
            )
            if cpu_percent is not None:
                cpu_percent = max(0.0, cpu_percent)
        else:
            cpu_percent = None
            system_cpu_percent = None

        rss_kb, total_kb, available_kb = memory
        self._cached = {
            "process_cpu_percent": (
                round(cpu_percent, 1) if cpu_percent is not None else None
            ),
            "system_cpu_percent": (
                round(system_cpu_percent, 1)
                if system_cpu_percent is not None else None
            ),
            "process_rss_mb": round(rss_kb / 1024.0, 1),
            "system_memory_percent": (
                round((total_kb - available_kb) / total_kb * 100.0, 2)
                if total_kb else None
            ),
        }
        self._last_cpu = cpu
        self._last_sample_at = now
        return dict(self._cached)

    def _read_cpu(self) -> tuple[int, int, int]:
        stat_lines = (self.proc_root / "stat").read_text(encoding="ascii").splitlines()
        cpu_line = next(
            (line for line in stat_lines if line.startswith("cpu ")), None
        )
        if cpu_line is None:
            raise ValueError("aggregate CPU counters are missing")
        values = [int(value) for value in cpu_line.split()[1:]]
        if len(values) < 4:
            raise ValueError("aggregate CPU counters are incomplete")
        total = sum(values)
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        process_stat = (self.proc_root / "self" / "stat").read_text(encoding="ascii")
        command_end = process_stat.rfind(")")
        if command_end < 0:
            raise ValueError("malformed process stat")
        process_fields = process_stat[command_end + 1:].split()
        process_ticks = int(process_fields[11]) + int(process_fields[12])
        return process_ticks, total, idle

    def _read_memory(self) -> tuple[int, int, int]:
        status = (self.proc_root / "self" / "status").read_text(encoding="ascii")
        memory = (self.proc_root / "meminfo").read_text(encoding="ascii")
        rss_line = next(
            (line for line in status.splitlines() if line.startswith("VmRSS:")),
            None,
        )
        total_line = next(
            (line for line in memory.splitlines() if line.startswith("MemTotal:")),
            None,
        )
        available_line = next(
            (line for line in memory.splitlines() if line.startswith("MemAvailable:")),
            None,
        )
        if rss_line is None or total_line is None or available_line is None:
            raise ValueError("required Linux memory counters are missing")
        rss = int(rss_line.split()[1])
        total = int(total_line.split()[1])
        available = int(available_line.split()[1])
        return rss, total, available

    @staticmethod
    def _clock_ticks() -> int:
        import os

        return int(os.sysconf("SC_CLK_TCK"))
