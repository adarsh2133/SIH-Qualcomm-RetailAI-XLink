"""Per-user desktop connection settings with Windows DPAPI token protection."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


class _DataBlob(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _protect_token(token: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Secure desktop token storage is supported on Windows only")
    source = token.encode("utf-8")
    source_buffer = ctypes.create_string_buffer(source)
    source_blob = _DataBlob(
        len(source),
        ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    result_blob = _DataBlob()
    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    protect = crypt32.CryptProtectData
    protect.argtypes = [
        ctypes.POINTER(_DataBlob),
        wintypes.LPCWSTR,
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    protect.restype = ctypes.wintypes.BOOL
    if not protect(
        ctypes.byref(source_blob),
        "PORTAL-XLINK Pi API token",
        None,
        None,
        None,
        0x1,
        ctypes.byref(result_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        encrypted = ctypes.string_at(result_blob.pbData, result_blob.cbData)
        return base64.b64encode(encrypted).decode("ascii")
    finally:
        kernel32.LocalFree(result_blob.pbData)


def _unprotect_token(encoded: str) -> str:
    if os.name != "nt":
        raise RuntimeError("Secure desktop token storage is supported on Windows only")
    encrypted = base64.b64decode(encoded, validate=True)
    source_buffer = ctypes.create_string_buffer(encrypted)
    source_blob = _DataBlob(
        len(encrypted),
        ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)),
    )
    result_blob = _DataBlob()
    description = wintypes.LPWSTR()
    crypt32 = ctypes.WinDLL("Crypt32.dll", use_last_error=True)
    kernel32 = ctypes.WinDLL("Kernel32.dll", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    unprotect = crypt32.CryptUnprotectData
    unprotect.argtypes = [
        ctypes.POINTER(_DataBlob),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(_DataBlob),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(_DataBlob),
    ]
    unprotect.restype = ctypes.wintypes.BOOL
    if not unprotect(
        ctypes.byref(source_blob),
        ctypes.byref(description),
        None,
        None,
        None,
        0x1,
        ctypes.byref(result_blob),
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(result_blob.pbData, result_blob.cbData).decode("utf-8")
    finally:
        kernel32.LocalFree(result_blob.pbData)
        if description:
            kernel32.LocalFree(description)


def config_path() -> Path:
    base = os.getenv("APPDATA")
    if not base:
        base = str(Path.home() / "AppData" / "Roaming")
    return Path(base) / "PORTAL-XLINK" / "desktop.json"


def validate_connection(api_url: str, token: str) -> tuple[str, str]:
    url = api_url.strip().rstrip("/")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Enter a valid Pi API address, such as https://storesense.local:8765")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("The Pi API address must not contain credentials, query, or fragment")
    if not token.strip():
        raise ValueError("Enter the API token configured on the Raspberry Pi")
    return url, token.strip()


def save_connection(
    api_url: str, token: str, certificate_sha256: str = ""
) -> Path:
    url, secret = validate_connection(api_url, token)
    fingerprint = certificate_sha256.replace(":", "").lower()
    if fingerprint and (
        len(fingerprint) != 64
        or any(character not in "0123456789abcdef" for character in fingerprint)
    ):
        raise ValueError("Pi TLS certificate fingerprint is invalid")
    destination = config_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 2,
        "api_url": url,
        "token_dpapi": _protect_token(secret),
        "certificate_sha256": fingerprint,
    }
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    temporary.replace(destination)
    return destination


def load_connection() -> dict[str, str] | None:
    path = config_path()
    if not path.is_file():
        return None
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") not in {1, 2}:
            raise ValueError("Desktop connection settings have an unsupported format")
        api_url, token = validate_connection(
            str(payload.get("api_url", "")),
            _unprotect_token(str(payload.get("token_dpapi", ""))),
        )
        fingerprint = str(payload.get("certificate_sha256", "")).replace(":", "").lower()
        if fingerprint and (
            len(fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in fingerprint)
        ):
            raise ValueError("Saved Pi TLS certificate fingerprint is invalid")
        return {
            "api_url": api_url,
            "token": token,
            "certificate_sha256": fingerprint,
        }
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read desktop connection settings: {exc}") from exc


def apply_connection(connection: dict[str, str]) -> None:
    os.environ["PORTAL_REMOTE_API_URL"] = connection["api_url"]
    os.environ["PORTAL_API_TOKEN"] = connection["token"]
    fingerprint = connection.get("certificate_sha256", "")
    if fingerprint:
        os.environ["PORTAL_API_CERT_SHA256"] = fingerprint
    else:
        os.environ.pop("PORTAL_API_CERT_SHA256", None)
