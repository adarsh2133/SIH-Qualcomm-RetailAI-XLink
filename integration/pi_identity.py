"""Persistent Pi API identity and one-time local pairing approval."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import logging
import os
import os
from pathlib import Path
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
import time
from typing import Any


_PAIRING_LIFETIME_S = 600
_PAIRING_ATTEMPTS = 5


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_suffix(path.suffix + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        try:
            path.chmod(0o600)
            path.parent.chmod(0o700)
        except OSError:
            if os.name != "nt":
                raise
    finally:
        if temporary.exists():
            temporary.unlink()


@dataclass(frozen=True)
class PiIdentity:
    certificate_path: Path
    private_key_path: Path
    certificate_sha256: str


class PairingManager:
    """Issues a short-lived local approval code; never logs or returns the API token."""

    def __init__(
        self,
        state_dir: str | Path,
        *,
        token_override: str = "",
        certificate_sha256: str = "",
        logger: logging.Logger | None = None,
        now: Any = time.time,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.token_path = self.state_dir / "api-token"
        self.pairing_path = self.state_dir / "pairing.json"
        self._logger = logger or logging.getLogger(__name__)
        self.certificate_sha256 = certificate_sha256.lower()
        self._now = now
        self._lock = threading.Lock()
        self._token_override = token_override.strip()
        self.token = self._load_token()
        self._ensure_pairing_code()

    def _load_token(self) -> str:
        if self._token_override:
            return self._token_override
        if self.token_path.is_file():
            token = self.token_path.read_text(encoding="utf-8").strip()
            if len(token) < 32:
                raise ValueError("Stored Pi API credential is invalid; use the local re-pair command")
            return token
        token = secrets.token_urlsafe(48)
        _atomic_write(self.token_path, token + "\n")
        return token

    def _read_pairing(self) -> dict[str, Any]:
        try:
            value = json.loads(self.pairing_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"paired": False, "attempts": 0}
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Could not read Pi pairing state: {exc}") from exc
        if not isinstance(value, dict):
            raise RuntimeError("Pi pairing state is invalid")
        return value

    def _write_pairing(self, value: dict[str, Any]) -> None:
        _atomic_write(self.pairing_path, json.dumps(value, separators=(",", ":")))

    def _ensure_pairing_code(self) -> None:
        with self._lock:
            state = self._read_pairing()
            if state.get("paired"):
                return
            if float(state.get("expires_at", 0)) > self._now():
                return
            self._issue_pairing_code_locked()

    def _issue_pairing_code_locked(self) -> str:
        code = f"{secrets.randbelow(10_000_000_000):010d}"
        self._write_pairing({
            "paired": False,
            "code_sha256": hashlib.sha256(code.encode("ascii")).hexdigest(),
            "expires_at": self._now() + _PAIRING_LIFETIME_S,
            "attempts": 0,
        })
        message = (
            "Local dashboard pairing approval code (expires in 10 minutes): "
            f"{code}"
        )
        if self.certificate_sha256:
            message += (
                "\nVerify the Pi TLS certificate SHA-256 fingerprint in the "
                "Windows setup wizard: " + self.certificate_sha256
            )
        print(message, file=sys.stdout, flush=True)
        self._logger.info("Local dashboard pairing approval is active")
        return code

    def claim(self, code: str) -> str | None:
        candidate = code.strip()
        if len(candidate) != 10 or not candidate.isdigit():
            return None
        with self._lock:
            state = self._read_pairing()
            if (
                state.get("paired")
                or float(state.get("expires_at", 0)) <= self._now()
                or int(state.get("attempts", 0)) >= _PAIRING_ATTEMPTS
            ):
                return None
            expected = str(state.get("code_sha256", ""))
            supplied = hashlib.sha256(candidate.encode("ascii")).hexdigest()
            if not hmac.compare_digest(expected, supplied):
                state["attempts"] = int(state.get("attempts", 0)) + 1
                self._write_pairing(state)
                return None
            state = {"paired": True, "paired_at": self._now()}
            self._write_pairing(state)
            return self.token

    def rotate(self) -> str:
        """Rotate the API credential and create a fresh local pairing approval code."""
        if self._token_override:
            raise RuntimeError(
                "PORTAL_API_TOKEN is externally managed; remove it before rotating the Pi credential"
            )
        with self._lock:
            self.token = secrets.token_urlsafe(48)
            _atomic_write(self.token_path, self.token + "\n")
            return self._issue_pairing_code_locked()


def ensure_tls_identity(state_dir: str | Path) -> PiIdentity:
    directory = Path(state_dir)
    certificate = directory / "api-cert.pem"
    private_key = directory / "api-key.pem"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not certificate.is_file() or not private_key.is_file():
        openssl = shutil.which("openssl")
        if not openssl:
            raise RuntimeError(
                "OpenSSL is required for secure Pi API startup. Install it with "
                "'sudo apt install openssl' and restart the service."
            )
        result = subprocess.run(
            [
                openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                "-days", "3650", "-keyout", str(private_key), "-out",
                str(certificate), "-subj", "/CN=PORTAL-XLINK-Pi",
                "-addext", "subjectAltName=DNS:portal-xlink.local,IP:127.0.0.1",
            ],
            capture_output=True,
            text=True,
            check=False,
            env={**os.environ, "OPENSSL_CONF": os.devnull},
        )
        if result.returncode:
            raise RuntimeError(
                "Could not create the Pi API TLS identity: "
                + (result.stderr.strip() or f"OpenSSL exited {result.returncode}")
            )
        private_key.chmod(0o600)
        certificate.chmod(0o600)
    pem = certificate.read_text(encoding="ascii")
    fingerprint = hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
    return PiIdentity(certificate, private_key, fingerprint)


def create_server_ssl_context(identity: PiIdentity) -> ssl.SSLContext:
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(
        certfile=str(identity.certificate_path),
        keyfile=str(identity.private_key_path),
    )
    return context
