"""Small UDP discovery beacon for Pi devices on the local subnet."""
from __future__ import annotations

import json
import logging
import socket
import threading
import time


DISCOVERY_PORT = 8766
_DISCOVERY_REQUEST = b"PORTAL-XLINK-DISCOVER-V1"


class PiDiscoveryResponder:
    def __init__(
        self,
        api_port: int,
        certificate_sha256: str,
        *,
        port: int = DISCOVERY_PORT,
        logger: logging.Logger | None = None,
    ) -> None:
        self.api_port = api_port
        self.certificate_sha256 = certificate_sha256.lower()
        self.port = port
        self.logger = logger or logging.getLogger(__name__)
        self._stop = threading.Event()
        self._socket: socket.socket | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("0.0.0.0", self.port))
        listener.settimeout(0.5)
        self._socket = listener
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="pi-discovery"
        )
        self._thread.start()

    def _run(self) -> None:
        assert self._socket is not None
        response = json.dumps({
            "service": "PORTAL-XLINK",
            "version": 1,
            "api_port": self.api_port,
            "certificate_sha256": self.certificate_sha256,
        }, separators=(",", ":")).encode("ascii")
        while not self._stop.is_set():
            try:
                request, address = self._socket.recvfrom(256)
            except socket.timeout:
                continue
            except OSError:
                if not self._stop.is_set():
                    self.logger.exception("Pi discovery listener failed")
                return
            if request == _DISCOVERY_REQUEST:
                try:
                    self._socket.sendto(response, address)
                except OSError:
                    if not self._stop.is_set():
                        self.logger.exception("Could not answer Pi discovery request")

    def close(self) -> None:
        self._stop.set()
        if self._socket is not None:
            self._socket.close()
            self._socket = None
        if self._thread is not None:
            self._thread.join(timeout=1)
            self._thread = None


def discover_pis(
    timeout_s: float = 2.0,
    *,
    broadcast_address: str = "255.255.255.255",
    discovery_port: int = DISCOVERY_PORT,
) -> list[dict[str, str]]:
    """Return validated peers answering the LAN broadcast; no credentials are sent."""
    if not 0.2 <= timeout_s <= 10:
        raise ValueError("Discovery timeout must be between 0.2 and 10 seconds")
    peers: dict[str, dict[str, str]] = {}
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
        client.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        client.settimeout(min(0.25, timeout_s))
        client.sendto(_DISCOVERY_REQUEST, (broadcast_address, discovery_port))
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            client.settimeout(remaining)
            try:
                body, address = client.recvfrom(2048)
            except socket.timeout:
                break
            try:
                payload = json.loads(body)
                port = int(payload["api_port"])
                fingerprint = str(payload["certificate_sha256"]).lower()
                if (
                    payload.get("service") != "PORTAL-XLINK"
                    or payload.get("version") != 1
                    or not 1 <= port <= 65535
                    or len(fingerprint) != 64
                    or any(character not in "0123456789abcdef" for character in fingerprint)
                ):
                    continue
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            peer = {
                "api_url": f"https://{address[0]}:{port}",
                "certificate_sha256": fingerprint,
            }
            peers[peer["api_url"]] = peer
    return list(peers.values())
