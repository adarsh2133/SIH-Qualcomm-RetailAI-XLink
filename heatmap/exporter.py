"""Exports a heatmap to JSON in data/heatmaps."""
from __future__ import annotations

import json
from pathlib import Path
from typing import List


def export_heatmap(filename: str, matrix: List[List[int]], output_dir: str = "data/heatmaps") -> dict[str, str]:
    if Path(filename).name != filename or Path(filename).suffix.lower() != ".json":
        raise ValueError("filename must be a simple .json filename")
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    target = path / filename
    payload = {"matrix": matrix}
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"filename": filename, "path": str(target)}
