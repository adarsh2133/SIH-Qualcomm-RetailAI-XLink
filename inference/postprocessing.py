"""Post-processing helpers."""
from __future__ import annotations

from typing import Any, Dict, Iterable, List


def decode_predictions(raw: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [dict(item) for item in raw if float(item.get("confidence", 1.0)) >= 0.0]


def non_max_suppression(predictions: Iterable[Dict[str, Any]], threshold: float = 0.5) -> List[Dict[str, Any]]:
    """Small dependency-free NMS for xyxy detections."""
    result: List[Dict[str, Any]] = []
    for item in sorted(predictions, key=lambda x: float(x.get("confidence", 0)), reverse=True):
        box = item.get("bbox", [0, 0, 0, 0])
        def iou(other: Dict[str, Any]) -> float:
            b = other.get("bbox", [0, 0, 0, 0])
            ix1, iy1 = max(box[0], b[0]), max(box[1], b[1])
            ix2, iy2 = min(box[2], b[2]), min(box[3], b[3])
            inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
            area = max(0, box[2]-box[0]) * max(0, box[3]-box[1])
            area_b = max(0, b[2]-b[0]) * max(0, b[3]-b[1])
            return inter / (area + area_b - inter) if area + area_b - inter else 0.0
        if all(iou(existing) <= threshold for existing in result):
            result.append(dict(item))
    return result


def summarize_predictions(predictions: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    items = list(predictions)
    return {
        "count": len(items),
        "detections": items,
        "max_confidence": max((item.get("confidence", 0.0) for item in items), default=0.0),
    }
