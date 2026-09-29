"""Guardrail for the external Qualcomm target compilation step."""
from __future__ import annotations

from pathlib import Path
from typing import Dict


def compile_model(source_path: str, output_path: str) -> Dict[str, str]:
    source = Path(source_path)
    return {
        "source_path": str(source),
        "output_path": str(output_path),
        "status": "external Qualcomm compilation required"
        if source.is_file() else "source artifact missing",
    }
