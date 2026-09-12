import os


def build_url(ip: str, port: int | str, path: str = "/video") -> str:
    return f"http://{ip}:{port}{path}"


ENTRY_CAMERA_IP = os.environ.get("ENTRY_CAMERA_IP", "192.168.1.41")
ENTRY_CAMERA_PORT = os.environ.get("ENTRY_CAMERA_PORT", "4747")
ENTRY_CAMERA_URL = os.environ.get("ENTRY_CAMERA_URL", build_url(ENTRY_CAMERA_IP, ENTRY_CAMERA_PORT))

QUEUE_CAMERA_1_IP = os.environ.get("QUEUE_CAMERA_1_IP", "192.168.1.42")
QUEUE_CAMERA_1_PORT = os.environ.get("QUEUE_CAMERA_1_PORT", "4747")
QUEUE_CAMERA_1_URL = os.environ.get("QUEUE_CAMERA_1_URL", build_url(QUEUE_CAMERA_1_IP, QUEUE_CAMERA_1_PORT))

QUEUE_CAMERA_2_IP = os.environ.get("QUEUE_CAMERA_2_IP", "192.168.1.43")
QUEUE_CAMERA_2_PORT = os.environ.get("QUEUE_CAMERA_2_PORT", "4747")
QUEUE_CAMERA_2_URL = os.environ.get("QUEUE_CAMERA_2_URL", build_url(QUEUE_CAMERA_2_IP, QUEUE_CAMERA_2_PORT))

STOCK_CAMERA_1_IP = os.environ.get("STOCK_CAMERA_1_IP", "192.168.1.44")
STOCK_CAMERA_1_PORT = os.environ.get("STOCK_CAMERA_1_PORT", "4747")
STOCK_CAMERA_1_URL = os.environ.get("STOCK_CAMERA_1_URL", build_url(STOCK_CAMERA_1_IP, STOCK_CAMERA_1_PORT))

STOCK_CAMERA_2_IP = os.environ.get("STOCK_CAMERA_2_IP", "192.168.1.45")
STOCK_CAMERA_2_PORT = os.environ.get("STOCK_CAMERA_2_PORT", "4747")
STOCK_CAMERA_2_URL = os.environ.get("STOCK_CAMERA_2_URL", build_url(STOCK_CAMERA_2_IP, STOCK_CAMERA_2_PORT))

ALL_CAMERA_URLS = {
    "entry": ENTRY_CAMERA_URL,
    "queue_1": QUEUE_CAMERA_1_URL,
    "queue_2": QUEUE_CAMERA_2_URL,
    "stock_1": STOCK_CAMERA_1_URL,
    "stock_2": STOCK_CAMERA_2_URL,
}

QUEUE_CAMERAS = [
    {"name": "queue_camera_1", "url": QUEUE_CAMERA_1_URL},
    {"name": "queue_camera_2", "url": QUEUE_CAMERA_2_URL},
]

STOCK_CAMERAS = [
    {"name": "stock_camera_1", "url": STOCK_CAMERA_1_URL},
    {"name": "stock_camera_2", "url": STOCK_CAMERA_2_URL},
]