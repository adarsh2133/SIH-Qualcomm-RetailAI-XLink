"""Guardrail for the external Qualcomm AI Hub export step."""
from __future__ import annotations

from typing import Dict


def export_model(model_name: str, output_dir: str) -> Dict[str, str]:
    raise RuntimeError(
        "Model export is not implemented locally. Export and compile the "
        f"validated {model_name} model in Qualcomm AI Hub for the confirmed "
        f"target, then copy the resulting artifact to {output_dir}."
    )
