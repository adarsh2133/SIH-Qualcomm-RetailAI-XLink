#!/usr/bin/env python3
"""Queue monitor with real camera reconnect and live JSON status writes."""

import json
import os
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from .camera_config import QUEUE_CAMERA_1_URL, QUEUE_CAMERA_2_URL

RUNTIME_DIR = Path(os.environ.get("RETAIL_EDGE_RUNTIME_DIR", Path(__file__).resolve().parents[2] / ".runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def resolve_status_path(env_name, default_name):
    configured = os.environ.get(env_name)
    path = Path(configured) if configured else RUNTIME_DIR / default_name
    if not path.is_absolute():
        path = RUNTIME_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


VIDEO_URL = os.environ.get("VIDEO_URL", QUEUE_CAMERA_1_URL)
STATUS_FILE = resolve_status_path("QUEUE_STATUS_FILE", "queue_status.json")
QUEUE_THRESHOLD = int(os.environ.get("QUEUE_THRESHOLD", "3"))
OUTPUT_WIDTH = int(os.environ.get("OUTPUT_WIDTH", "480"))
OUTPUT_HEIGHT = int(os.environ.get("OUTPUT_HEIGHT", "270"))
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "4"))
YOLO_SIZE = int(os.environ.get("YOLO_SIZE", "224"))
CONFIDENCE = float(os.environ.get("CONFIDENCE", "0.35"))
MAX_DETECTIONS = int(os.environ.get("MAX_DETECTIONS", "10"))
INFERENCE_INTERVAL = float(os.environ.get("INFERENCE_INTERVAL", "0.8"))
STATUS_INTERVAL = float(os.environ.get("STATUS_INTERVAL", "1.0"))
SMOOTHING_WINDOW = int(os.environ.get("SMOOTHING_WINDOW", "3"))
RECONNECT_DELAY = 2.0
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

print("=" * 70)
print("RetailEdge AI - QUEUE INTELLIGENCE")
print("=" * 70)
print(f"[CONFIG] Camera URL: {VIDEO_URL}")
print(f"[CONFIG] Output resolution: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}")
print(f"[CONFIG] Queue threshold: {QUEUE_THRESHOLD}")
print(f"[CONFIG] Headless mode: {HEADLESS}")
print("=" * 70)


def create_queue_roi(width, height):
    roi = np.array([
        [int(width * 0.15), int(height * 0.2)],
        [int(width * 0.85), int(height * 0.2)],
        [int(width * 1.0), int(height * 1.0)],
        [int(width * 0.0), int(height * 1.0)],
    ], dtype=np.int32)
    return roi


QUEUE_ROI = create_queue_roi(OUTPUT_WIDTH, OUTPUT_HEIGHT)

running = True
camera_running = True
camera_connected = False
latest_frame = None
frame_lock = threading.Lock()
new_frame_event = threading.Event()
queue_count = 0
queue_count_lock = threading.Lock()
last_status_write = 0.0
status_lock = threading.Lock()
count_history = deque(maxlen=SMOOTHING_WINDOW)
frame_counter = 0
inference_counter = 0


def write_status(count):
    global last_status_write
    now = time.time()
    if now - last_status_write < STATUS_INTERVAL:
        return
    with status_lock:
        is_congested = count >= QUEUE_THRESHOLD
        payload = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "queue_length": int(count),
            "status": "CONGESTED" if is_congested else "NORMAL",
            "threshold": QUEUE_THRESHOLD,
            "congestion_level": "High" if count > QUEUE_THRESHOLD * 2 else "Medium" if is_congested else "Low",
            "connected": camera_connected,
            "cameras": {
                "queue_camera_1": {"connected": camera_connected},
                "queue_camera_2": {"connected": False},
            },
        }
        temp_file = f"{STATUS_FILE}.tmp"
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_file, STATUS_FILE)
            last_status_write = now
        except OSError as exc:
            print(f"[WARN] Could not write queue status: {exc}")


def read_camera():
    global camera_running, camera_connected, latest_frame, frame_counter
    while camera_running:
        print(f"[CAMERA] Connecting to {VIDEO_URL}")
        cap = cv2.VideoCapture(VIDEO_URL)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 10)
        if not cap.isOpened():
            camera_connected = False
            write_status(queue_count)
            print("[CAMERA] Connection failed, retrying in 2s...")
            cap.release()
            time.sleep(RECONNECT_DELAY)
            continue

        camera_connected = True
        print("[CAMERA] Connected")
        frame_counter = 0
        while camera_running:
            ret, frame = cap.read()
            if not ret:
                camera_connected = False
                write_status(queue_count)
                print("[CAMERA] Frame reception failed")
                break
            frame_counter += 1
            if frame_counter % FRAME_SKIP != 0:
                continue
            resized = cv2.resize(frame, (OUTPUT_WIDTH, OUTPUT_HEIGHT), interpolation=cv2.INTER_LINEAR)
            with frame_lock:
                latest_frame = resized
            new_frame_event.set()
        cap.release()
        if camera_running:
            time.sleep(1)


cpu_count = os.cpu_count() or 1
num_threads = max(1, min(cpu_count - 1, 2))
torch.set_num_threads(num_threads)
torch.set_num_interop_threads(1)
torch.set_float32_matmul_precision('medium')
print("[MODEL] Loading YOLO11n...")
MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    str(Path(__file__).resolve().parents[2] / "models" / "yolo11n.pt"),
)
model = YOLO(MODEL_PATH)
model.eval()


def get_latest_frame():
    with frame_lock:
        if latest_frame is None:
            return None
        return latest_frame.copy()


def count_people_in_roi(result):
    if result is None or result.boxes is None:
        return 0
    count = 0
    boxes = result.boxes
    coordinates = boxes.xyxy.detach().cpu().numpy()
    for box in coordinates:
        x1, y1, x2, y2 = map(int, box)
        foot_x = (x1 + x2) // 2
        foot_y = y2
        if cv2.pointPolygonTest(QUEUE_ROI, (foot_x, foot_y), False) >= 0:
            count += 1
    return count


def smooth_queue_count(count):
    count_history.append(count)
    return int(round(np.median(list(count_history))))


def run_inference():
    global queue_count, inference_counter
    last_inference_time = 0.0
    while camera_running:
        new_frame_event.wait(timeout=1.0)
        if not camera_running:
            break
        current_time = time.time()
        if current_time - last_inference_time < INFERENCE_INTERVAL:
            time.sleep(0.01)
            continue
        frame = get_latest_frame()
        if frame is None:
            continue
        last_inference_time = current_time
        try:
            with torch.inference_mode():
                results = model.predict(
                    source=frame,
                    classes=[0],
                    imgsz=YOLO_SIZE,
                    conf=CONFIDENCE,
                    device="cpu",
                    max_det=MAX_DETECTIONS,
                    verbose=False,
                )
            current_count = count_people_in_roi(results[0])
            stable_count = smooth_queue_count(current_count)
            with queue_count_lock:
                queue_count = stable_count
            write_status(stable_count)
            inference_counter += 1
        except Exception as exc:
            print(f"[ERROR] Inference failed: {exc}")
            time.sleep(0.1)


camera_thread = threading.Thread(target=read_camera, daemon=True)
inference_thread = threading.Thread(target=run_inference, daemon=True)
camera_thread.start()
inference_thread.start()
print("[MAIN] Threads started")

try:
    while camera_running:
        frame = get_latest_frame()
        if frame is None:
            time.sleep(0.01)
            if not HEADLESS and cv2.waitKey(1) & 0xFF == ord("q"):
                break
            continue
        cv2.polylines(frame, [QUEUE_ROI], True, (255, 0, 0), 2)
        with queue_count_lock:
            current_count = queue_count
        if current_count >= QUEUE_THRESHOLD * 2:
            status = "CRITICAL"
            color = (0, 0, 255)
        elif current_count >= QUEUE_THRESHOLD:
            status = "CONGESTED"
            color = (0, 165, 255)
        else:
            status = "NORMAL"
            color = (0, 255, 0)
        cv2.rectangle(frame, (10, 10), (320, 120), (0, 0, 0), -1)
        cv2.putText(frame, f"QUEUE: {current_count}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
        cv2.putText(frame, status, (20, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        cv2.putText(frame, f"RES: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}", (20, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
        if not HEADLESS:
            cv2.imshow("Queue Intelligence", frame)
        if not HEADLESS and cv2.waitKey(1) & 0xFF == ord("q"):
            break
        time.sleep(0.01)
except KeyboardInterrupt:
    print("[MAIN] Keyboard interrupt")
finally:
    print("[MAIN] Shutting down...")
    camera_running = False
    new_frame_event.set()
    camera_thread.join(timeout=2)
    inference_thread.join(timeout=2)
    cv2.destroyAllWindows()
    print(f"[STATS] Frames: {frame_counter}, Inferences: {inference_counter}")
    print("[MAIN] Shutdown complete")
