from __future__ import annotations

import os
import tempfile
import unittest
from unittest.mock import patch

import desktop_config


class DesktopCredentialPersistenceTests(unittest.TestCase):
    def test_tls_pin_and_token_round_trip_with_dpapi_boundary_mocked(self) -> None:
        fingerprint = "ab" * 32
        with tempfile.TemporaryDirectory() as temporary:
            with (
                patch.dict(os.environ, {
                    "APPDATA": temporary,
                    "PORTAL_API_CERT_SHA256": "",
                }),
                patch.object(desktop_config, "_protect_token", side_effect=lambda value: f"protected:{value}"),
                patch.object(desktop_config, "_unprotect_token", side_effect=lambda value: value.removeprefix("protected:")),
            ):
                path = desktop_config.save_connection(
                    "https://192.168.1.20:8765",
                    "mock-api-token",
                    fingerprint,
                )
                result = desktop_config.load_connection()
                desktop_config.apply_connection(result)
                self.assertEqual(os.environ["PORTAL_API_CERT_SHA256"], fingerprint)
                self.assertTrue(path.is_file())
        self.assertEqual(path.name, "desktop.json")
        self.assertEqual(result["api_url"], "https://192.168.1.20:8765")
        self.assertEqual(result["token"], "mock-api-token")
        self.assertEqual(result["certificate_sha256"], fingerprint)

    def test_invalid_certificate_pin_is_rejected_before_persisting(self) -> None:
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            desktop_config.save_connection(
                "https://192.168.1.20:8765", "api-token", "not-a-fingerprint"
            )
