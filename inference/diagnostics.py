"""Read-only diagnostics for the configured Qualcomm inference path."""
from __future__ import annotations

import os
import platform
import subprocess
import time
from typing import Any, Dict

from config import Settings
from cameras.camera_manager import CameraManager
from .model_factory import create_inference
from qaihub.workflow import status as qaihub_status


def collect_qualcomm_diagnostic(settings: Settings) -> Dict[str, Any]:
    engine = create_inference(settings, "qaihub")
    status = engine.availability()
    return {
        "target_device": status.get("target_device", "unspecified"),
        "development_host": status.get(
            "development_host",
            f"{platform.system()} {platform.machine()}",
        ),
        "runtime": status.get("runtime", "unavailable"),
        "runtime_version": status.get("runtime_version", "unavailable"),
        "execution_provider": ", ".join(status.get("providers", [])) or "unavailable",
        "model": status.get("model", settings.qualcomm_model_name),
        "artifact": status.get("model_path", settings.qualcomm_model_path),
        "artifact_exists": status.get("artifact", False),
        "input": status.get("input", "unavailable"),
        "status": status.get("state", "UNAVAILABLE"),
        "error": status.get("error") or "none",
        "inference_executed": False,
    }


def print_qualcomm_diagnostic(settings: Settings) -> None:
    result = collect_qualcomm_diagnostic(settings)
    print("TARGET DEVICE:", result["target_device"])
    print("DEVELOPMENT HOST:", result["development_host"])
    print("RUNTIME:", result["runtime"])
    print("RUNTIME VERSION:", result["runtime_version"])
    print("EXECUTION PROVIDER:", result["execution_provider"])
    print("MODEL:", result["model"])
    print("ARTIFACT:", result["artifact"])
    print("ARTIFACT EXISTS:", result["artifact_exists"])
    print("INPUT:", result["input"])
    print("STATUS:", result["status"])
    print("INFERENCE EXECUTED:", result["inference_executed"])
    print("ERROR:", result["error"])


def _windows_hardware() -> Dict[str, str]:
    if platform.system() != "Windows":
        return {}
    command = (
        "$os=Get-CimInstance Win32_OperatingSystem;"
        "$cpu=Get-CimInstance Win32_Processor | Select-Object -First 1;"
        "$gpu=Get-CimInstance Win32_VideoController | Select-Object -First 1;"
        "$cs=Get-CimInstance Win32_ComputerSystem;"
        "[pscustomobject]@{OS=$os.Caption;Build=$os.BuildNumber;"
        "CPU=$cpu.Name;GPU=$gpu.Name;RAM=$cs.TotalPhysicalMemory;"
        "Arch=$os.OSArchitecture} | ConvertTo-Json -Compress"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True, text=True, timeout=5, check=False,
        )
        if completed.returncode == 0 and completed.stdout.strip():
            import json
            return json.loads(completed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return {}


def _masked_environment() -> Dict[str, str]:
    result = {}
    for key, value in os.environ.items():
        if any(token in key.upper() for token in ("PASSWORD", "TOKEN", "SECRET", "API_KEY")):
            result[key] = "<redacted>"
        elif key.startswith(("PORTAL_", "QNN_", "QAIRT_", "QUALCOMM_", "SNPE_")):
            result[key] = value
    return result


def print_live_diagnostic(settings: Settings) -> None:
    hardware = _windows_hardware()
    inference = create_inference(settings, settings.inference_backend)
    inference_status = inference.availability()
    hub_status = qaihub_status()
    manager = CameraManager.from_settings(settings)
    configured = bool(settings.camera_sources)
    manager.start_all()
    time.sleep(3.0 if configured else 0.25)
    frames = manager.read_all()
    statuses = manager.statuses()
    manager.close_all()

    print("=== PORTAL-XLINK LIVE DIAGNOSTIC ===")
    print("\nSYSTEM:")
    print("OS:", hardware.get("OS") or platform.platform())
    print("BUILD:", hardware.get("Build") or "N/A")
    print("CPU:", hardware.get("CPU") or platform.processor() or "N/A")
    print("GPU:", hardware.get("GPU") or "N/A")
    print("RAM_BYTES:", hardware.get("RAM") or "N/A")
    print("ARCHITECTURE:", hardware.get("Arch") or platform.machine())
    print("PYTHON:", platform.python_version(), platform.architecture()[0])
    print("QUALCOMM HARDWARE:", "NOT DETECTED (current PC)")
    print("ENVIRONMENT:", _masked_environment() or "none")

    print("\nCAMERAS:")
    if not configured:
        print("RTSP SOURCES NOT CONFIGURED")
    for status in statuses:
        print(
            f"- {status.get('camera_id')}: "
            f"source={status.get('source', '<none>')} "
            f"state={status.get('state', 'OFFLINE')} "
            f"last_frame={status.get('last_frame_time') or 'N/A'} "
            f"frame_age={status.get('frame_age_s') if status.get('frame_age_s') is not None else 'N/A'} "
            f"reconnects={status.get('reconnect_attempts', 0)} "
            f"read_failures={status.get('consecutive_read_failures', 0)} "
            f"error={status.get('error') or status.get('stream_error') or 'none'}"
        )
    print("DECODED LIVE FRAMES:", len([frame for frame in frames if frame.get("mode") == "live"]))

    print("\nINFERENCE:")
    print("BACKEND:", inference.name)
    print("RUNTIME:", inference_status.get("runtime", "N/A"))
    print("RUNTIME VERSION:", inference_status.get("runtime_version", "N/A"))
    print("EXECUTION PROVIDER:", ", ".join(inference_status.get("providers", [])) or "N/A")
    print("QUALCOMM DEVICE:", inference_status.get("target_device") or inference_status.get("device", "N/A"))
    print("MODEL:", inference_status.get("model", "N/A"))
    print("MODEL ARTIFACT:", inference_status.get("model_path", "N/A"))
    print("INPUT SHAPE:", inference_status.get("input", "N/A"))
    print("STATUS:", inference_status.get("state", "UNAVAILABLE"))
    print("ERROR:", inference_status.get("error") or "none")
    print("LATENCY:", inference_status.get("latency_ms") or "N/A")
    print("FPS:", inference_status.get("fps") or "N/A")

    print("\nHOST HARDWARE (INFORMATIONAL; NOT A QUALCOMM ACCELERATOR):")
    print("GPU:", hardware.get("GPU") or "N/A")
    print("QUALCOMM EXECUTION:", "NOT AVAILABLE ON THIS HOST")
    print("\nQUALCOMM AI HUB:")
    print("STATUS:", hub_status.get("status", "N/A"))
    print("TARGET DEVICE:", hub_status.get("target_device") or "N/A")
    print("RUNTIME:", hub_status.get("runtime") or "N/A")
    print("ERROR:", hub_status.get("error") or "N/A")
    print("COMPILE:", "N/A (not run)")
    print("PROFILE:", "N/A (not run)")
    print("INFERENCE:", "N/A (not run)")

    print("\nPIPELINE:")
    print("camera -> RTSP:", "BLOCKED" if not configured else "CONFIGURED")
    print("RTSP -> OpenCV:", "FRAMES RECEIVED" if frames else "NO FRESH FRAMES")
    print("OpenCV -> inference:", "BLOCKED" if not frames else "READY TO PROCESS")
    print("inference -> detection:", "BLOCKED" if inference_status.get("state") == "UNAVAILABLE" else "NOT EXECUTED")
    print("detection -> analytics:", "BLOCKED (no validated detections)")

    if not configured:
        first_blocker = "RTSP SOURCES NOT CONFIGURED"
    elif not frames:
        first_blocker = "NO FRESH RTSP FRAMES RECEIVED"
    elif inference_status.get("state") == "UNAVAILABLE":
        first_blocker = inference_status.get("error") or "QUALCOMM INFERENCE UNAVAILABLE"
    else:
        first_blocker = "MODEL-SPECIFIC DECODER/REAL INFERENCE SMOKE TEST REQUIRED"
    print("\nFIRST BLOCKER:", first_blocker)
    print("LIVE PIPELINE BLOCKED")
