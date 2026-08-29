#!/usr/bin/env python3
"""Shelf stock monitor with real camera reconnect logic and runtime JSON output."""

import json
import os
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

from camera_config import STOCK_CAMERAS

RUNTIME_DIR = Path(os.environ.get("RETAIL_EDGE_RUNTIME_DIR", Path(__file__).resolve().parent / ".runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def resolve_status_path(env_name, default_name):
    configured = os.environ.get(env_name)
    path = Path(configured) if configured else RUNTIME_DIR / default_name
    if not path.is_absolute():
        path = RUNTIME_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

MODEL_PATH = os.environ.get("MODEL_PATH", "shelf_model.pt")
CONFIDENCE = float(os.environ.get("CONFIDENCE", "0.35"))
IMG_SIZE = int(os.environ.get("IMG_SIZE", "320"))
OUTPUT_PATH = resolve_status_path("STOCK_OUTPUT", "stock_status.json")
FRAME_RESIZE = int(os.environ.get("FRAME_RESIZE", "480"))
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "2"))
INFERENCE_INTERVAL = float(os.environ.get("INFERENCE_INTERVAL", "0.5"))
WRITE_INTERVAL = int(os.environ.get("WRITE_INTERVAL", "3"))
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

print("=" * 70)
print("RetailEdge AI - SHELF STOCK MONITOR")
print("=" * 70)
print(f"[CONFIG] Model: {MODEL_PATH}")
print(f"[CONFIG] IMG_SIZE: {IMG_SIZE}")
print(f"[CONFIG] Frame resize: {FRAME_RESIZE}px")
print(f"[CONFIG] Headless mode: {HEADLESS}")
print("=" * 70)


# device setup
cpu_count = os.cpu_count() or 1
num_threads = max(1, min(cpu_count - 1, 2))
torch.set_num_threads(num_threads)
torch.set_num_interop_threads(1)
torch.set_float32_matmul_precision('medium')


def load_model(model_path, fallback_model="yolo11n.pt"):
    if Path(model_path).exists():
        print(f"[MODEL] Loading {model_path}...")
        model = YOLO(model_path)
    else:
        if not Path(fallback_model).exists():
            raise SystemExit(f"ERROR: No model found: {model_path} or {fallback_model}")
        print(f"[MODEL] {model_path} not found, using {fallback_model}")
        model = YOLO(fallback_model)
    model.eval()
    return model


model = load_model(MODEL_PATH)


# Load cameras
configured = os.environ.get("SHELF_CAMERAS")
if configured:
    try:
        cameras = json.loads(configured)
    except json.JSONDecodeError:
        cameras = STOCK_CAMERAS
else:
    cameras = STOCK_CAMERAS

if not isinstance(cameras, list) or not cameras:
    cameras = STOCK_CAMERAS

if not cameras:
    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "products": {},
        "cameras": {},
        "status": "OFFLINE",
        "connected": False,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        OUTPUT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        print(f"[WARN] Could not write offline shelf status: {exc}")
    print("[CAMERA] No shelf cameras enabled. Shelf monitoring is disabled.")
    raise SystemExit(0)

print(f"[CAMERA] Loaded {len(cameras)} camera(s)")
for index, camera in enumerate(cameras, start=1):
    camera.setdefault("name", f"shelf_{index}")
    if "url" not in camera:
        if "ip" not in camera:
            raise SystemExit(f"ERROR: Camera {camera['name']} missing 'url' or 'ip'")
        camera["url"] = f"http://{camera['ip']}:{camera.get('port', 4747)}/video"
    print(f"[CAMERA {index}] {camera['name']}: {camera['url']}")

running = True
state_lock = threading.Lock()
latest_frames = {cam["name"]: None for cam in cameras}
inference_frames = {cam["name"]: None for cam in cameras}
connected = {cam["name"]: False for cam in cameras}
stock_by_camera = {cam["name"]: {} for cam in cameras}
camera_detections = {cam["name"]: [] for cam in cameras}
last_detection_time = {cam["name"]: 0.0 for cam in cameras}
last_inference_time = {cam["name"]: 0.0 for cam in cameras}
frame_events = {cam["name"]: threading.Event() for cam in cameras}
frame_count = {cam["name"]: 0 for cam in cameras}
inference_count = {cam["name"]: 0 for cam in cameras}


def capture_camera(camera):
    name = camera["name"]
    url = camera["url"]
    reconnect_attempts = 0
    max_reconnect_attempts = 30
    while running:
        backoff = min(2 ** reconnect_attempts, 32)
        print(f"[{name}] Connecting (attempt {reconnect_attempts + 1})...")
        cap = cv2.VideoCapture(url)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not cap.isOpened():
            with state_lock:
                connected[name] = False
            cap.release()
            if reconnect_attempts < max_reconnect_attempts:
                reconnect_attempts += 1
                time.sleep(backoff)
            else:
                reconnect_attempts = 0
                time.sleep(60)
            continue

        reconnect_attempts = 0
        with state_lock:
            connected[name] = True
        print(f"[{name}] Connected")
        while running:
            ret, frame = cap.read()
            if not ret:
                with state_lock:
                    connected[name] = False
                print(f"[{name}] Disconnected (no frame)")
                break
            with state_lock:
                if frame.shape[1] > FRAME_RESIZE:
                    scale = FRAME_RESIZE / frame.shape[1]
                    new_height = int(frame.shape[0] * scale)
                    frame = cv2.resize(frame, (FRAME_RESIZE, new_height), interpolation=cv2.INTER_LINEAR)
                latest_frames[name] = frame
                inference_frames[name] = frame
                frame_count[name] += 1
            frame_events[name].set()
        cap.release()
        frame_events[name].set()
        if running:
            time.sleep(1)


def run_inference():
    while running:
        processed_any = False
        for camera in cameras:
            name = camera["name"]
            current_time = time.time()
            if current_time - last_inference_time[name] < INFERENCE_INTERVAL:
                continue
            with state_lock:
                frame = inference_frames[name]
                inference_frames[name] = None
            if frame is None:
                continue
            processed_any = True
            try:
                with torch.inference_mode():
                    results = model.predict(
                        frame,
                        imgsz=IMG_SIZE,
                        conf=CONFIDENCE,
                        device="cpu",
                        verbose=False,
                        stream=False,
                    )
                current_stock = {}
                detections = []
                if results[0].boxes is not None:
                    for box in results[0].boxes:
                        class_id = int(box.cls[0])
                        confidence = float(box.conf[0])
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        product_name = model.names[class_id]
                        current_stock[product_name] = current_stock.get(product_name, 0) + 1
                        detections.append((product_name, confidence, x1, y1, x2, y2))
                with state_lock:
                    stock_by_camera[name] = current_stock
                    camera_detections[name] = detections
                    last_detection_time[name] = current_time
                    last_inference_time[name] = current_time
                    inference_count[name] += 1
            except Exception as exc:
                print(f"[ERROR {name}] Inference failed: {exc}")
                time.sleep(0.1)
        if not processed_any:
            time.sleep(0.05)


def write_stock_file():
    with state_lock:
        per_camera = {name: dict(stock) for name, stock in stock_by_camera.items()}
    total = {}
    for stock in per_camera.values():
        for product, quantity in stock.items():
            total[product] = total.get(product, 0) + quantity
    payload = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "products": total,
        "cameras": {
            name: {"connected": connected.get(name, False), "stock": dict(stock_by_camera.get(name, {}))}
            for name in sorted(per_camera)
        },
    }
    temp = OUTPUT_PATH.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        temp.replace(OUTPUT_PATH)
    except Exception as exc:
        print(f"[ERROR] Failed to write stock status: {exc}")


capture_threads = [threading.Thread(target=capture_camera, args=(camera,), daemon=True) for camera in cameras]
inference_thread = threading.Thread(target=run_inference, daemon=True)
for thread in capture_threads + [inference_thread]:
    thread.start()
print("[MAIN] All threads started")

last_write = 0.0
last_display = 0.0
try:
    while running:
        current_time = time.time()
        if current_time - last_write >= WRITE_INTERVAL:
            write_stock_file()
            last_write = current_time
        if not HEADLESS and current_time - last_display >= 2.0:
            for camera in cameras:
                name = camera["name"]
                with state_lock:
                    frame = latest_frames[name]
                    if frame is None:
                        continue
                    frame = frame.copy()
                    is_connected = connected[name]
                    detections = list(camera_detections[name])
                    stock = dict(stock_by_camera[name])
                if frame is None:
                    frame = np.zeros((360, 480, 3), dtype=np.uint8)
                if not is_connected:
                    cv2.putText(frame, "DISCONNECTED", (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
                for product, confidence, x1, y1, x2, y2 in detections:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(frame, f"{product} {confidence:.2f}", (x1, max(20, y1 - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 0), 2)
                y = 30
                cv2.rectangle(frame, (10, 10), (320, 45 + 25 * len(stock)), (0, 0, 0), -1)
                cv2.putText(frame, name, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
                for product, quantity in stock.items():
                    y += 25
                    cv2.putText(frame, f"{product}: {quantity}", (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                cv2.imshow(f"Shelf - {name}", frame)
            last_display = current_time
        if not HEADLESS and cv2.waitKey(1) & 0xFF == ord("q"):
            break
        time.sleep(0.01)
except KeyboardInterrupt:
    print("[MAIN] Keyboard interrupt received")
finally:
    print("[MAIN] Shutting down...")
    running = False
    for event in frame_events.values():
        event.set()
    for thread in capture_threads + [inference_thread]:
        thread.join(timeout=2)
    cv2.destroyAllWindows()
    print("[MAIN] Shutdown complete")
