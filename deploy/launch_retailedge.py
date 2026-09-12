#!/usr/bin/env python3
"""
RetailEdge AI - System Launcher

Starts every edge sensor process (entry counter, queue monitor, shelf
monitor, health monitor), the metrics API, and the dashboard, all pointed
at ONE shared runtime directory. This is the missing "glue": individually
each script already reads/writes the .runtime/*.json files correctly, but
nothing was starting them together with a guaranteed-consistent
RETAIL_EDGE_RUNTIME_DIR, and the dashboard's direct-file fallback did not
even honor that variable (fixed in dashboard.py).

This launcher does NOT invent, simulate, or fake any metric. If a camera
is unreachable or a model file is missing, that sensor process will log a
connection failure and simply not produce fresh status data - the
dashboard and API already show "OFFLINE" / stale-camera states correctly
in that case, by design (see RuntimeDataCollector / _runtime_metrics).

Usage:
    python launch_retailedge.py                 # start everything + GUI
    python launch_retailedge.py --no-dashboard   # headless: just sensors + API
    python launch_retailedge.py --only api,dashboard   # attach to already-running sensors
"""

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BASE_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
RUNTIME_DIR = Path(os.environ.get("RETAIL_EDGE_RUNTIME_DIR", BASE_DIR / ".runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

# Make sure every child process we spawn (and this process's own imports,
# e.g. metrics_api) resolve the SAME runtime dir.
os.environ["RETAIL_EDGE_RUNTIME_DIR"] = str(RUNTIME_DIR)
os.environ.setdefault("METRICS_API_URL", "http://127.0.0.1:8000/api/metrics")

EDGE_SCRIPTS = {
    "entry": "retailedge.entry_counter",
    "queue": "retailedge.queue_monitor",
    "shelf": "retailedge.shelf_monitor",
    "health": "retailedge.health_monitor",
}

REQUIRED_MODULES = {
    "entry": ["cv2", "torch", "ultralytics"],
    "queue": ["cv2", "torch", "ultralytics"],
    "shelf": ["cv2", "torch", "ultralytics"],
    "health": ["psutil"],
}


def check_module(name):
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def start_process(name, module):
    env = os.environ.copy()
    env["HEADLESS"] = "1"
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(SRC_DIR), existing_pythonpath) if value
    )
    print(f"[LAUNCHER] Starting {name}: {module}")
    return subprocess.Popen(
        [sys.executable, "-m", module],
        env=env,
        cwd=str(BASE_DIR),
        stdout=None,
        stderr=None,
    )


def write_process_registry(procs):
    """Record PID + script name for each sensor process we started, so
    edge_health_monitor.py can report real health even when these are
    plain subprocesses instead of installed systemd units."""
    registry = {
        name: {"pid": proc.pid, "script": EDGE_SCRIPTS[name]}
        for name, proc in procs.items()
    }
    registry_path = RUNTIME_DIR / "process_registry.json"
    try:
        registry_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    except OSError as e:
        print(f"[LAUNCHER] WARNING: could not write process registry: {e}")


def start_metrics_api():
    # Imported (not subprocess'd) so it shares this process's env directly
    # and we can keep a handle on the thread.
    from retailedge.metrics_api import run_server

    thread = threading.Thread(
        target=run_server, kwargs={"host": "127.0.0.1", "port": 8000}, daemon=True
    )
    thread.start()
    return thread


def main():
    parser = argparse.ArgumentParser(description="Launch the RetailEdge AI system")
    parser.add_argument(
        "--only",
        default="",
        help="Comma-separated subset to start: entry,queue,shelf,health,api,dashboard",
    )
    parser.add_argument("--no-dashboard", action="store_true", help="Run headless (no GUI)")
    args = parser.parse_args()

    requested = set(x.strip() for x in args.only.split(",") if x.strip()) or {
        "entry", "queue", "shelf", "health", "api", "dashboard"
    }
    if args.no_dashboard:
        requested.discard("dashboard")

    print("=" * 70)
    print("RetailEdge AI - SYSTEM LAUNCHER")
    print(f"Shared runtime dir : {RUNTIME_DIR}")
    print(f"Components         : {sorted(requested)}")
    print("=" * 70)

    procs = {}

    for name, module in EDGE_SCRIPTS.items():
        if name not in requested:
            continue
        missing = [m for m in REQUIRED_MODULES.get(name, []) if not check_module(m)]
        if missing:
            print(
                f"[LAUNCHER] SKIP {name}: missing Python packages {missing}. "
                f"Install them (pip install ...) to run real detection for this sensor. "
                f"No placeholder data will be generated in its place."
            )
            continue
        procs[name] = start_process(name, module)
        time.sleep(1.0)  # stagger model loads / camera connects

    if "api" in requested:
        start_metrics_api()
        print("[LAUNCHER] Metrics API live at http://127.0.0.1:8000/api/metrics")
        time.sleep(0.5)

    if "dashboard" in requested:
        if not check_module("customtkinter"):
            print("[LAUNCHER] Cannot start dashboard: customtkinter not installed.")
        else:
            print("[LAUNCHER] Launching dashboard GUI...")
            from retailedge.dashboard import RetailEdgeDashboard

            app = RetailEdgeDashboard()
            try:
                app.mainloop()
            finally:
                shutdown(procs)
                return

    # Headless mode: just keep the sensors/API alive until interrupted.
    try:
        print("[LAUNCHER] Running headless. Press Ctrl+C to stop.")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown(procs)


def shutdown(procs):
    print("[LAUNCHER] Shutting down edge processes...")
    for name, proc in procs.items():
        proc.terminate()
    for name, proc in procs.items():
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    print("[LAUNCHER] Shutdown complete")


if __name__ == "__main__":
    main()