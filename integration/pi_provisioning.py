"""Windows dashboard pairing and post-pair health verification."""
from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.request import Request
from urllib.parse import urlsplit
from typing import Any

from desktop_config import validate_connection
from secure_http import open_request


def pair_with_pi(
    api_url: str,
    approval_code: str,
    certificate_sha256: str,
) -> dict[str, str]:
    url = api_url.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Automatic pairing requires the discovered secure Pi address")
    if len(approval_code.strip()) != 10 or not approval_code.strip().isdigit():
        raise ValueError("Enter the 10-digit local approval code shown by the Pi service")
    request = Request(
        f"{url}/api/v1/pair",
        data=json.dumps({"code": approval_code.strip()}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with open_request(
            request, timeout=5, fingerprint=certificate_sha256
        ) as response:
            payload: Any = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            raise ValueError(
                "The Pi approval code is invalid, expired, or already used. "
                "On the Pi, run app.py --re-pair and restart portal-xlink.service."
            ) from exc
        if exc.code == 429:
            raise ValueError("Too many pairing attempts; restart the local pairing flow") from exc
        raise ValueError(f"The Pi pairing service returned HTTP {exc.code}") from exc
    token = payload.get("token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise ValueError("The Pi pairing response did not contain a usable credential")
    connection = {
        "api_url": url,
        "token": token,
        "certificate_sha256": certificate_sha256.replace(":", "").lower(),
    }
    validate_connection(url, token)
    check_pi_health(connection)
    return connection


def check_pi_health(connection: dict[str, str]) -> dict[str, Any]:
    request = Request(
        f"{connection['api_url'].rstrip('/')}/api/v1/health",
        headers={"Authorization": f"Bearer {connection['token']}"},
    )
    with open_request(
        request,
        timeout=5,
        fingerprint=connection.get("certificate_sha256", ""),
    ) as response:
        payload: Any = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("state"), str):
        raise ValueError("The Pi returned an invalid health response")
    return payload
