#!/usr/bin/env python3
"""
RetailEdge AI - Edge Health Monitor
Monitors status of all edge processors and reports health to dashboard.
Runs on Raspberry Pi to track system and service health.
"""

import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

try:
    import psutil
except ImportError:
    print("Warning: psutil not installed. Install with: pip install psutil")
    psutil = None


# ============================================================================
# CONFIGURATION
# ============================================================================

RUNTIME_DIR = Path(os.environ.get("RETAIL_EDGE_RUNTIME_DIR", Path(__file__).resolve().parents[2] / ".runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

STATUS_FILES = {
    "entry": str(RUNTIME_DIR / "entry_status.json"),
    "queue": str(RUNTIME_DIR / "queue_status.json"),
    "stock": str(RUNTIME_DIR / "stock_status.json"),
}

SERVICES = [
    "retailedge-entry-counter.service",
    "retailedge-queue-monitor.service",
    "retailedge-shelf-monitor.service",
]

HEALTH_OUTPUT = str(RUNTIME_DIR / "edge_health.json")
CHECK_INTERVAL = 5  # seconds
STALE_THRESHOLD = 30  # seconds (if status file hasn't updated)

# Maps each systemd unit this monitor knows about to the key launch_retailedge.py
# uses when it registers a process it started directly (not via systemd).
PROCESS_REGISTRY_FILE = RUNTIME_DIR / "process_registry.json"
SERVICE_REGISTRY_KEYS = {
    "retailedge-entry-counter.service": "entry",
    "retailedge-queue-monitor.service": "queue",
    "retailedge-shelf-monitor.service": "shelf",
}

print("=" * 70)
print("RetailEdge AI - EDGE HEALTH MONITOR")
print("=" * 70)


# ============================================================================
# HEALTH CHECKS
# ============================================================================

class EdgeHealthMonitor:
    def __init__(self):
        self.check_interval = CHECK_INTERVAL
        self.stale_threshold = STALE_THRESHOLD
        
    def check_file_exists_and_fresh(self, filepath, stale_threshold=None):
        """Check if status file exists and has recent data."""
        if stale_threshold is None:
            stale_threshold = self.stale_threshold
        
        if not Path(filepath).exists():
            return False, "NOT_FOUND", 0
        
        try:
            mtime = os.path.getmtime(filepath)
            age = time.time() - mtime
            
            if age > stale_threshold:
                return False, "STALE", age
            
            return True, "FRESH", age
        except OSError:
            return False, "ERROR", 0
    
    def read_status_file(self, filepath):
        """Read and parse status JSON file."""
        try:
            with open(filepath, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
    
    def _read_process_registry(self):
        try:
            return json.loads(PROCESS_REGISTRY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def check_service_status(self, service_name):
        """Check if the service is running.

        FIXED: this only ever checked `systemctl is-active`, which reports
        every service as inactive/unknown when the pipeline is started via
        launch_retailedge.py in development (plain subprocesses, not
        installed systemd units) - so the dashboard's health badge was
        permanently stuck on WARN even when everything was working. It now
        falls back to checking the actual OS process the launcher started
        (real PID liveness + command-line match, not a guess) when systemd
        doesn't recognize the unit.
        """
        systemd_reachable = False
        try:
            result = subprocess.run(
                ['systemctl', 'is-active', service_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            systemd_reachable = True
            if result.stdout.strip() == 'active':
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            systemd_reachable = False
        except Exception:
            systemd_reachable = False

        key = SERVICE_REGISTRY_KEYS.get(service_name)
        if key and psutil is not None:
            entry = self._read_process_registry().get(key)
            if entry:
                pid = entry.get("pid")
                script = entry.get("script", "")
                try:
                    if pid is not None and psutil.pid_exists(pid):
                        proc = psutil.Process(pid)
                        if script and script in " ".join(proc.cmdline()):
                            return True
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # Not managed by systemd and no matching live process in the
        # registry: genuinely unknown rather than a guessed True/False.
        return False if systemd_reachable else None
    
    def get_service_uptime(self, service_name):
        """Get service uptime in seconds."""
        try:
            result = subprocess.run(
                ['systemctl', 'show', service_name, '-p', 'ActiveEnterTimestamp'],
                capture_output=True,
                text=True,
                timeout=2
            )
            # Parse ActiveEnterTimestamp
            if 'ActiveEnterTimestamp=' in result.stdout:
                timestamp_str = result.stdout.split('=')[1].strip()
                # Simple parsing - in production use dateutil
                return 0  # Placeholder
        except Exception:
            pass
        return None
    
    def get_process_stats(self):
        """Get CPU and memory stats."""
        if psutil is None:
            return None
        
        try:
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            return {
                "cpu_percent": round(cpu_percent, 1),
                "memory_percent": round(memory.percent, 1),
                "memory_mb": round(memory.used / 1024 / 1024, 1),
                "disk_percent": round(disk.percent, 1),
                "temperature": self.get_temperature()
            }
        except Exception as e:
            print(f"[WARN] Could not get process stats: {e}")
            return None
    
    def get_temperature(self):
        """Get CPU temperature (Raspberry Pi)."""
        try:
            result = subprocess.run(
                ['vcgencmd', 'measure_temp'],
                capture_output=True,
                text=True,
                timeout=2
            )
            # Output format: temp=XX.X'C
            if 'temp=' in result.stdout:
                temp_str = result.stdout.split('=')[1].split("'")[0]
                return float(temp_str)
        except Exception:
            pass
        return None
    
    def check_network(self):
        """Check network connectivity."""
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '8.8.8.8'],
                capture_output=True,
                timeout=2
            )
            return result.returncode == 0
        except Exception:
            return None
    
    def generate_health_report(self):
        """Generate comprehensive health report."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "edge_node_id": os.environ.get("EDGE_NODE_ID", "pi-1"),
            "services": {},
            "status_files": {},
            "system": {},
            "network": {}
        }
        
        # Check services
        for service in SERVICES:
            is_running = self.check_service_status(service)
            uptime = self.get_service_uptime(service)
            report["services"][service.replace(".service", "")] = {
                "running": is_running,
                "uptime_seconds": uptime
            }
        
        # Check status files
        for name, filepath in STATUS_FILES.items():
            exists, status, age = self.check_file_exists_and_fresh(filepath)
            data = self.read_status_file(filepath) if exists else None
            
            report["status_files"][name] = {
                "exists": exists,
                "status": status,
                "age_seconds": round(age, 1),
                "data": data
            }
        
        # System stats
        system_stats = self.get_process_stats()
        if system_stats:
            report["system"] = system_stats
        
        # Network
        is_online = self.check_network()
        report["network"] = {
            "online": is_online,
            "gateway": "8.8.8.8"
        }
        
        # Overall health
        all_services_running = all(
            s["running"] for s in report["services"].values() if s["running"] is not None
        )
        all_files_fresh = all(
            f["status"] == "FRESH" for f in report["status_files"].values()
        )
        
        report["overall_health"] = {
            "healthy": all_services_running and all_files_fresh and is_online,
            "services_ok": all_services_running,
            "files_ok": all_files_fresh,
            "network_ok": is_online
        }
        
        return report
    
    def write_health_report(self, report):
        """Write health report atomically."""
        temp_file = f"{HEALTH_OUTPUT}.tmp"
        try:
            with open(temp_file, 'w') as f:
                json.dump(report, f, indent=2)
            os.replace(temp_file, HEALTH_OUTPUT)
            return True
        except OSError as e:
            print(f"[ERROR] Could not write health report: {e}")
            return False
    
    def run(self):
        """Main monitoring loop."""
        print(f"[MONITOR] Starting health check every {self.check_interval}s")
        print(f"[MONITOR] Output file: {HEALTH_OUTPUT}")
        print(f"[MONITOR] Press Ctrl+C to stop")
        
        try:
            while True:
                report = self.generate_health_report()
                
                # Print summary
                health = report["overall_health"]
                status = "✓ HEALTHY" if health["healthy"] else "✗ UNHEALTHY"
                
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] {status}")
                print(f"  Services: {'OK' if health['services_ok'] else 'FAILED'}")
                print(f"  Status Files: {'OK' if health['files_ok'] else 'STALE'}")
                print(f"  Network: {'OK' if health['network_ok'] else 'OFFLINE'}")
                
                if report["system"]:
                    sys_stats = report["system"]
                    print(f"  CPU: {sys_stats['cpu_percent']}% | "
                          f"Memory: {sys_stats['memory_percent']}% | "
                          f"Disk: {sys_stats['disk_percent']}%")
                    if sys_stats['temperature'] is not None:
                        temp = sys_stats['temperature']
                        temp_status = "WARN" if temp > 80 else "OK"
                        print(f"  Temp: {temp}°C [{temp_status}]")
                
                # Service details
                for name, service_status in report["services"].items():
                    status_str = "running" if service_status["running"] else "stopped"
                    print(f"  - {name}: {status_str}")
                
                # File details
                for name, file_status in report["status_files"].items():
                    print(f"  - {name}: {file_status['status']} "
                          f"(age: {file_status['age_seconds']}s)")
                
                # Write report
                self.write_health_report(report)
                
                # Wait for next check
                time.sleep(self.check_interval)
        
        except KeyboardInterrupt:
            print("\n[MONITOR] Shutting down...")


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    monitor = EdgeHealthMonitor()
    monitor.run()