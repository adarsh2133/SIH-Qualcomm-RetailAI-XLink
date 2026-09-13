from __future__ import annotations

import io
import json
from unittest.mock import patch

from config.live_cameras import load_live_camera_publish_urls
from integrations.mediamtx import path_status


def test_publish_urls_use_rtmp_and_camera_paths():
    urls = load_live_camera_publish_urls({"STORESENSE_CAMERA_IDS": "entry-cam,queue-cam-1"})

    assert urls == {
        "entry-cam": "rtmp://192.168.1.68:1935/entry-cam",
        "queue-cam-1": "rtmp://192.168.1.68:1935/queue-cam-1",
    }


def test_mediamtx_reports_active_publisher():
    payload = {"items": [{"name": "entry-cam", "source": {"type": "rtmpConn"}, "ready": True}]}
    response = io.BytesIO(json.dumps(payload).encode())

    with patch("integrations.mediamtx.urlopen", return_value=response):
        status = path_status("entry-cam", api_url="http://mediamtx.test/paths")

    assert status.active is True
    assert status.status == "Stream connected"


def test_mediamtx_reports_missing_publisher():
    response = io.BytesIO(json.dumps({"items": []}).encode())

    with patch("integrations.mediamtx.urlopen", return_value=response):
        status = path_status("entry-cam", api_url="http://mediamtx.test/paths")

    assert status.active is False
    assert status.status == "No publisher detected"