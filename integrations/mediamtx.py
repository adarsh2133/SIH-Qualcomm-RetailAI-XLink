"""Read-only MediaMTX path diagnostics for camera status reporting."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class MediaMTXPathStatus:
    active: bool
    status: str
    source: str | None = None


def _path_name(item: dict) -> str | None:
    return item.get("name") or item.get("pathName") or item.get("path")


def _is_active(item: dict) -> bool:
    source = item.get("source")
    if not source:
        return False
    flags = [item.get(key) for key in ("ready", "online", "available") if key in item]
    return all(flag is not False for flag in flags)


def path_status(camera_id: str, api_url: str | None = None, timeout: float = 2.0) -> MediaMTXPathStatus:
    """Return publisher state without making camera configuration look online."""

    endpoint = api_url or os.environ.get(
        "STORESENSE_MEDIAMTX_API_URL",
        "http://127.0.0.1:9997/v3/paths/list",
    )
    try:
        with urlopen(endpoint, timeout=timeout) as response:
            payload = json.load(response)
    except (OSError, URLError, ValueError):
        return MediaMTXPathStatus(False, "MediaMTX unreachable")

    for item in payload.get("items", []):
        if _path_name(item) == camera_id:
            active = _is_active(item)
            return MediaMTXPathStatus(
                active,
                "Stream connected" if active else "MediaMTX path not active",
                str(item.get("source")) if item.get("source") else None,
            )
    return MediaMTXPathStatus(False, "No publisher detected")