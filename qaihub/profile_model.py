"""Report artifact metadata without inventing performance measurements."""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any


def profile_model(model_path: str) -> Dict[str, Any]:
    path = Path(model_path)
    return {
        "model_path": model_path,
        "artifact_exists": path.is_file(),
        "artifact_size_bytes": path.stat().st_size if path.is_file() else 0,
        "latency_ms": None,
        "throughput_fps": None,
        "memory_mb": None,
        "note": "Performance requires execution on the confirmed Qualcomm target.",
    }
