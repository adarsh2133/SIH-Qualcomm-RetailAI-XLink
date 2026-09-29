"""Optional, real Qualcomm AI Hub Workbench operations.

These functions never manufacture devices, jobs, artifacts, or measurements.
They call the installed ``qai_hub`` SDK only when explicitly requested.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _base_status() -> Dict[str, Any]:
    return {
        "status": "NOT CONFIGURED",
        "target_device": os.getenv("PORTAL_QAIHUB_TARGET_DEVICE") or None,
        "runtime": os.getenv("PORTAL_QAIHUB_RUNTIME") or None,
        "model": os.getenv("PORTAL_QAIHUB_MODEL", "Detectron2-Detection"),
        "checkpoint": os.getenv("PORTAL_QAIHUB_CHECKPOINT", "faster_rcnn_R_50_C4_1x"),
        "job_id": None,
        "artifact": None,
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def status() -> Dict[str, Any]:
    result = _base_status()
    if not os.getenv("QAI_HUB_API_TOKEN"):
        result["error"] = "QAI_HUB_API_TOKEN is not configured"
        result["authentication"] = "NOT CONFIGURED"
        return result
    try:
        import qai_hub  # type: ignore
    except ImportError:
        result["error"] = "qai_hub SDK is not installed"
        result["authentication"] = "NOT CONFIGURED"
        return result
    result["sdk"] = getattr(qai_hub, "__version__", "installed")
    result["authentication"] = "CONFIGURED"
    result["status"] = "CONFIGURED" if result["target_device"] else "NOT CONFIGURED"
    if not result["target_device"]:
        result["error"] = "PORTAL_QAIHUB_TARGET_DEVICE is not configured"
    return result


def devices() -> Dict[str, Any]:
    result = _base_status()
    try:
        import qai_hub  # type: ignore
        listed = qai_hub.get_devices()
        result.update({
            "status": "SUCCESS",
            "devices": [
                {
                    "name": getattr(device, "name", None),
                    "os": getattr(device, "os", None),
                    "runtime": getattr(device, "runtime", None),
                    "chipset": getattr(device, "chipset", None),
                }
                for device in listed
            ],
        })
    except ImportError:
        result.update({"status": "NOT CONFIGURED", "error": "qai_hub SDK is not installed"})
    except (OSError, RuntimeError, ValueError) as exc:
        result.update({"status": "FAILED", "error": str(exc)})
    return result


def _require_configured() -> Dict[str, Any] | None:
    result = status()
    if result["status"] != "CONFIGURED":
        return result
    model = os.getenv("PORTAL_QAIHUB_SOURCE_MODEL")
    if not model or not Path(model).is_file():
        result.update({
            "status": "NOT CONFIGURED",
            "error": "PORTAL_QAIHUB_SOURCE_MODEL must point to a real local model artifact",
        })
        return result
    result["source_model"] = model
    return None


def _submit(operation: str) -> Dict[str, Any]:
    blocked = _require_configured()
    if blocked:
        return blocked
    result = _base_status()
    try:
        import qai_hub  # type: ignore
        submit = getattr(qai_hub, f"submit_{operation}_job", None)
        if submit is None:
            raise RuntimeError(f"installed qai_hub SDK does not expose submit_{operation}_job")
        kwargs = {
            "model": result.get("source_model") or os.getenv("PORTAL_QAIHUB_SOURCE_MODEL"),
            "device": os.getenv("PORTAL_QAIHUB_TARGET_DEVICE"),
        }
        job = submit(**kwargs)
        result.update({
            "status": getattr(job, "status", "SUBMITTED"),
            "job_id": getattr(job, "job_id", None) or getattr(job, "id", None),
        })
        return result
    except ImportError:
        result.update({"status": "NOT CONFIGURED", "error": "qai_hub SDK is not installed"})
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        result.update({"status": "FAILED", "error": str(exc)})
    return result


def compile_model() -> Dict[str, Any]:
    return _submit("compile")


def profile_model() -> Dict[str, Any]:
    return _submit("profile")


def inference() -> Dict[str, Any]:
    return _submit("inference")


def write_metadata(payload: Dict[str, Any], path: str) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
