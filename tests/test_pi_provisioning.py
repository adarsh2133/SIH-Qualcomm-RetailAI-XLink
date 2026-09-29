from __future__ import annotations

import logging
import os
from pathlib import Path
import shutil
import io
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch
from urllib.error import URLError
from urllib.request import Request

from integration.pi_api import DetectionStore, make_server
from integration.pi_discovery import PiDiscoveryResponder, discover_pis
from integration.pi_identity import (
    PairingManager,
    create_server_ssl_context,
    ensure_tls_identity,
)
from integration.pi_provisioning import pair_with_pi
from secure_http import open_request


class PairingManagerTests(unittest.TestCase):
    def test_credentials_are_persistent_private_and_pairing_is_one_time(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            logger = logging.getLogger("test-pairing-private")
            output = io.StringIO()
            with redirect_stdout(output):
                with patch("integration.pi_identity.secrets.randbelow", return_value=321):
                    pairing = PairingManager(temporary, logger=logger)
            code = "0000000321"
            self.assertEqual(pairing.claim(code), pairing.token)
            self.assertIsNone(pairing.claim(code))
            self.assertNotIn(pairing.token, output.getvalue())
            self.assertIn(code, output.getvalue())
            self.assertEqual(
                Path(temporary, "api-token").read_text(encoding="utf-8").strip(),
                pairing.token,
            )
            if os.name != "nt":
                self.assertEqual(Path(temporary, "api-token").stat().st_mode & 0o777, 0o600)
                self.assertEqual(Path(temporary).stat().st_mode & 0o777, 0o700)

    def test_invalid_attempts_exhaust_pairing_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch("integration.pi_identity.secrets.randbelow", return_value=8):
                pairing = PairingManager(temporary, logger=logging.getLogger("pair-limit"))
            for _ in range(5):
                self.assertIsNone(pairing.claim("9999999999"))
            self.assertIsNone(pairing.claim("0000000008"))

    def test_repair_rotates_token_and_rejects_environment_managed_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch("integration.pi_identity.secrets.randbelow", side_effect=(1, 2)):
                pairing = PairingManager(temporary, logger=logging.getLogger("pair-rotate"))
                old_token = pairing.token
                code = pairing.rotate()
            self.assertNotEqual(pairing.token, old_token)
            self.assertEqual(code, "0000000002")
            external = PairingManager(
                temporary,
                token_override="externally-managed-test-token",
                logger=logging.getLogger("pair-external"),
            )
            with self.assertRaisesRegex(RuntimeError, "externally managed"):
                external.rotate()

    def test_expired_code_cannot_pair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            now = [100.0]
            with patch("integration.pi_identity.secrets.randbelow", return_value=123):
                pairing = PairingManager(
                    temporary,
                    logger=logging.getLogger("pair-expiry"),
                    now=lambda: now[0],
                )
            now[0] += 601
            self.assertIsNone(pairing.claim("0000000123"))


class SecurePairingApiTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("openssl"), "OpenSSL executable is not available")
    def test_tls_pairing_provisions_token_then_authenticates_health(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            logger = logging.getLogger("test-pi-tls")
            with patch("integration.pi_identity.secrets.randbelow", return_value=456):
                pairing = PairingManager(temporary, logger=logger)
            identity = ensure_tls_identity(temporary)
            server = make_server(
                "127.0.0.1",
                0,
                pairing.token,
                DetectionStore(),
                pairing_manager=pairing,
                ssl_context=create_server_ssl_context(identity),
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                connection = pair_with_pi(
                    f"https://127.0.0.1:{server.server_port}",
                    "0000000456",
                    identity.certificate_sha256,
                )
                self.assertEqual(connection["token"], pairing.token)
                self.assertEqual(
                    connection["certificate_sha256"],
                    identity.certificate_sha256,
                )
                with self.assertRaises(URLError):
                    with open_request(
                        Request(f"{connection['api_url']}/api/v1/health"),
                        timeout=2,
                        fingerprint="0" * 64,
                    ):
                        self.fail("mismatched certificate pin was accepted")
                with self.assertRaisesRegex(ValueError, "already used"):
                    pair_with_pi(
                        connection["api_url"],
                        "0000000456",
                        identity.certificate_sha256,
                    )
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

    def test_pairing_cannot_be_enabled_without_tls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            pairing = PairingManager(
                temporary, logger=logging.getLogger("pair-tls-required")
            )
            with self.assertRaisesRegex(ValueError, "only be enabled over TLS"):
                make_server("127.0.0.1", 0, pairing.token, DetectionStore(),
                            pairing_manager=pairing)


class PiDiscoveryTests(unittest.TestCase):
    def test_discovery_returns_tls_pin_without_sending_credentials(self) -> None:
        fingerprint = "a" * 64
        responder = PiDiscoveryResponder(
            8765,
            fingerprint,
            port=0,
            logger=logging.getLogger("test-discovery"),
        )
        # The production listener uses a fixed port; bind an ephemeral socket in
        # the responder test by reserving the expected socket port via the class.
        responder.port = _free_udp_port()
        responder.start()
        try:
            peers = discover_pis(
                timeout_s=0.5,
                broadcast_address="127.0.0.1",
                discovery_port=responder.port,
            )
        finally:
            responder.close()
        self.assertEqual(len(peers), 1)
        self.assertTrue(peers[0]["api_url"].startswith("https://127.0.0.1:8765"))
        self.assertEqual(peers[0]["certificate_sha256"], fingerprint)


def _free_udp_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


if __name__ == "__main__":
    unittest.main()
