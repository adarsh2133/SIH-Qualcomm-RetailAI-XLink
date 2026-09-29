"""Download an artifact from a URL into a local file."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen


def download_artifact(url: str, target_path: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme:
        raise ValueError("Artifact URL is missing a scheme")
    destination = Path(target_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if parsed.scheme not in {"http", "https", "file"}:
        raise ValueError("Only http, https, and file URLs are supported")
    with urlopen(url, timeout=20) as response:
        destination.write_bytes(response.read())
    return str(destination)
