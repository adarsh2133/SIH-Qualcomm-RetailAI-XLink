from __future__ import annotations

import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from integration.pi_api import DetectionStore, make_server


class AlertApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.acknowledged: list[str] = []
        self.store = DetectionStore()
        self.store.publish({
            "timestamp": "2026-09-29T00:00:00+00:00",
            "alerts": [
                {"id": "a-1", "type": "LOW_STOCK"},
                {
                    "id": "a-2",
                    "type": "LOW_STOCK",
                    "notification_suppressed": True,
                },
            ],
            "alert_events": [{"id": "a-1", "type": "LOW_STOCK"}],
        })
        self.server = make_server(
            "127.0.0.1",
            0,
            "test-token",
            self.store,
            lambda alert_id: self.acknowledged.append(alert_id) or {
                "id": alert_id,
                "acknowledged": True,
            },
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def request(self, path: str, *, token: str = "test-token", method: str = "GET"):
        request = Request(
            self.base_url + path,
            data=b"" if method == "POST" else None,
            method=method,
            headers={"Authorization": f"Bearer {token}"},
        )
        return urlopen(request, timeout=2)

    def test_active_alert_endpoint_is_small_and_authenticated(self) -> None:
        with self.request("/api/v1/alerts/active") as response:
            payload = json.loads(response.read())
        self.assertEqual(payload["alerts"], [{"id": "a-1", "type": "LOW_STOCK"}])
        self.assertEqual(payload["alert_events"], [])

        with self.assertRaises(HTTPError) as error:
            self.request("/api/v1/alerts/active", token="invalid")
        self.assertEqual(error.exception.code, 401)

    def test_alert_acknowledgement_is_authenticated(self) -> None:
        with self.request("/api/v1/alerts/a-1/acknowledge", method="POST") as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["alert"]["acknowledged"])
        self.assertEqual(self.acknowledged, ["a-1"])

        with self.assertRaises(HTTPError) as error:
            self.request(
                "/api/v1/alerts/a-1/acknowledge",
                token="invalid",
                method="POST",
            )
        self.assertEqual(error.exception.code, 401)


if __name__ == "__main__":
    unittest.main()
