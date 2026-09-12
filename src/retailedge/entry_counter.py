#!/usr/bin/env python3
"""
RetailEdge AI - Entry Counter (Optimized for Raspberry Pi)
Tracks store footfall with line-crossing detection and minimal resource usage.
"""

import json
import os
import threading
import time
from pathlib import Path

from .camera_config import ENTRY_CAMERA_URL

RUNTIME_DIR = Path(os.environ.get("RETAIL_EDGE_RUNTIME_DIR", Path(__file__).resolve().parents[2] / ".runtime"))
RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def resolve_status_path(env_name, default_name):
    configured = os.environ.get(env_name)
    path = Path(configured) if configured else RUNTIME_DIR / default_name
    if not path.is_absolute():
        path = RUNTIME_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path

import cv2
import numpy as np
import torch
from ultralytics import YOLO

# ============================================================================
# CONFIGURATION (Raspberry Pi Optimized)
# ============================================================================

PHONE_IP = os.environ.get("PHONE_IP", "192.168.1.41")
VIDEO_URL = os.environ.get("VIDEO_URL", ENTRY_CAMERA_URL)
CAMERA_NAME = os.environ.get("ENTRY_CAMERA_NAME", "entry_camera")
STATUS_FILE = resolve_status_path("ENTRY_STATUS_FILE", "entry_status.json")

LINE_POSITION = float(os.environ.get("LINE_POSITION", "0.5"))
ENTRY_DIRECTION = os.environ.get("ENTRY_DIRECTION", "top_to_bottom")

# Memory efficiency
OUTPUT_WIDTH = int(os.environ.get("OUTPUT_WIDTH", "480"))
OUTPUT_HEIGHT = int(os.environ.get("OUTPUT_HEIGHT", "360"))
YOLO_SIZE = int(os.environ.get("YOLO_SIZE", "224"))
FRAME_SKIP = int(os.environ.get("FRAME_SKIP", "3"))
INFERENCE_INTERVAL = float(os.environ.get("INFERENCE_INTERVAL", "0.5"))
CONFIDENCE = float(os.environ.get("CONFIDENCE", "0.35"))

# Tracking
MAX_DETECTIONS = int(os.environ.get("MAX_DETECTIONS", "15"))
CROSSING_COOLDOWN = float(os.environ.get("CROSSING_COOLDOWN", "1.5"))
LINE_MARGIN = float(os.environ.get("LINE_MARGIN", "0.02"))  # % of height

RECONNECT_DELAY = 2.0
STATUS_WRITE_INTERVAL = 0.5
HEADLESS = os.environ.get("HEADLESS", "0") == "1"

# Validation
if not 0.2 <= LINE_POSITION <= 0.9:
    raise SystemExit("ERROR: LINE_POSITION must be between 0.2 and 0.9")
if ENTRY_DIRECTION not in {"top_to_bottom", "bottom_to_top"}:
    raise SystemExit("ERROR: ENTRY_DIRECTION must be top_to_bottom or bottom_to_top")

print("=" * 70)
print("RetailEdge AI - ENTRY COUNTER (Raspberry Pi Optimized)")
print("=" * 70)
print(f"[CONFIG] Camera URL: {VIDEO_URL}")
print(f"[CONFIG] Camera name: {CAMERA_NAME}")
print(f"[CONFIG] Output resolution: {OUTPUT_WIDTH}x{OUTPUT_HEIGHT}")
print(f"[CONFIG] Line position: {LINE_POSITION * 100:.1f}%")
print(f"[CONFIG] Entry direction: {ENTRY_DIRECTION}")
print(f"[CONFIG] Headless mode: {HEADLESS}")
print("=" * 70)


# ============================================================================
# DEVICE SETUP
# ============================================================================

def setup_device():
    """Configure PyTorch for Raspberry Pi."""
    device = "cpu"
    cpu_count = os.cpu_count() or 1
    num_threads = max(1, min(cpu_count - 1, 2))
    
    torch.set_num_threads(num_threads)
    torch.set_num_interop_threads(1)
    torch.set_float32_matmul_precision('medium')
    
    print(f"[DEVICE] CPU cores: {cpu_count}, Torch threads: {num_threads}")
    return device


device = setup_device()

# Load model
print("[MODEL] Loading YOLO11n...")
MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    str(Path(__file__).resolve().parents[2] / "models" / "yolo11n.pt"),
)
model = YOLO(MODEL_PATH)
model.eval()


# ============================================================================
# SHARED STATE
# ============================================================================

running = True
camera_connected = False

latest_frame = None
inference_frame = None
frame_lock = threading.Lock()
inference_ready = threading.Event()

latest_detections = []
detection_lock = threading.Lock()

entry_count = 0
exit_count = 0
previous_side = {}
previous_y = {}
last_crossing_time = {}
fallback_id = 0

line_y = None
line_margin = None
last_event = ""
last_status_write = 0.0
status_lock = threading.Lock()

# Performance metrics
frame_counter = 0
inference_counter = 0


# ============================================================================
# STATUS WRITER
# ============================================================================

def write_status(event=""):
    """Write entry counter status atomically."""
    global last_event, last_status_write
    
    current_time = time.time()
    if current_time - last_status_write < STATUS_WRITE_INTERVAL:
        return
    
    with status_lock:
        if event:
            last_event = event
        
        temp_file = f"{STATUS_FILE}.tmp"
        payload = {
            "camera": CAMERA_NAME,
            "connected": camera_connected,
            "entry_count": entry_count,
            "exit_count": exit_count,
            "last_event": last_event,
            "people_detected": len(latest_detections),
            "detections": [
                {
                    "id": int(pid) if isinstance(pid, (int, np.integer)) else str(pid),
                    "x1": int(x1),
                    "y1": int(y1),
                    "x2": int(x2),
                    "y2": int(y2),
                }
                for pid, x1, y1, x2, y2 in latest_detections
            ],
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        try:
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
            os.replace(temp_file, STATUS_FILE)
            last_status_write = current_time
        except OSError as e:
            print(f"[WARN] Could not write status: {e}")


# ============================================================================
# CAMERA READER THREAD
# ============================================================================

def read_camera():
    """Capture video with reconnection logic."""
    global running, camera_connected, latest_frame, inference_frame, frame_counter
    
    while running:
        print(f"[CAMERA] Connecting to {VIDEO_URL}")
        cap = cv2.VideoCapture(VIDEO_URL)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FPS, 10)
        
        if not cap.isOpened():
            camera_connected = False
            write_status()
            cap.release()
            print("[CAMERA] Connection failed")
            time.sleep(RECONNECT_DELAY)
            continue
        
        camera_connected = True
        write_status()
        print("[CAMERA] Connected")
        frame_counter = 0
        
        while running:
            ret, frame = cap.read()
            if not ret:
                camera_connected = False
                write_status()
                print("[CAMERA] Frame reception failed")
                break
            
            frame_counter += 1
            
            # Skip frames
            if frame_counter % FRAME_SKIP != 0:
                continue
            
            # Resize
            resized = cv2.resize(frame, (OUTPUT_WIDTH, OUTPUT_HEIGHT),
                                interpolation=cv2.INTER_LINEAR)
            
            with frame_lock:
                latest_frame = resized
                inference_frame = resized
            
            inference_ready.set()
        
        cap.release()
        if running:
            time.sleep(1)


# ============================================================================
# INFERENCE THREAD
# ============================================================================

def run_inference():
    """Run person tracking with line crossing detection."""
    global running, line_y, line_margin, latest_detections
    global entry_count, exit_count, fallback_id, inference_counter
    
    while running:
        if not inference_ready.wait(timeout=1):
            continue
        
        with frame_lock:
            frame = inference_frame
            if frame is not None:
                frame = frame.copy()
                inference_frame = None
            inference_ready.clear()
        
        if frame is None:
            continue
        
        height, width = frame.shape[:2]
        
        # Initialize line on first frame
        if line_y is None:
            line_y = int(height * LINE_POSITION)
            line_margin = max(12, int(height * LINE_MARGIN))
            print(f"[TRACK] Line at y={line_y}, margin={line_margin}")
        
        try:
            # Track with ByteTrack
            with torch.inference_mode():
                results = model.track(
                    frame,
                    persist=True,
                    classes=[0],  # Person only
                    imgsz=YOLO_SIZE,
                    conf=CONFIDENCE,
                    iou=0.5,
                    max_det=MAX_DETECTIONS,
                    tracker="bytetrack.yaml",
                    device=device,
                    stream_buffer=False,
                    verbose=False,
                )
            
            detections = []
            boxes = results[0].boxes
            coordinates = boxes.xyxy.cpu().numpy() if boxes is not None else []
            
            if boxes is not None and len(coordinates):
                # Get IDs
                if boxes.id is not None:
                    ids = boxes.id.cpu().numpy().astype(int)
                else:
                    ids = [f"det-{fallback_id + i}" for i in range(len(coordinates))]
                    fallback_id += len(coordinates)
                
                now = time.time()
                
                # Process each person
                for person_id, box in zip(ids, coordinates):
                    x1, y1, x2, y2 = map(int, box)
                    foot_y = y2
                    
                    # Smooth vertical position
                    prev_y = previous_y.get(person_id)
                    if prev_y is not None:
                        foot_y = int(0.65 * prev_y + 0.35 * foot_y)
                    previous_y[person_id] = foot_y
                    
                    # Determine side of line
                    if foot_y <= line_y - line_margin:
                        current_side = -1
                    elif foot_y >= line_y + line_margin:
                        current_side = 1
                    else:
                        current_side = previous_side.get(person_id, 0)
                    
                    old_side = previous_side.get(person_id)
                    can_count = now - last_crossing_time.get(person_id, 0) >= CROSSING_COOLDOWN
                    
                    # Detect crossings
                    moved_down = (old_side == -1 and current_side == 1) and can_count
                    moved_up = (old_side == 1 and current_side == -1) and can_count
                    
                    if ENTRY_DIRECTION == "top_to_bottom":
                        entered, exited = moved_down, moved_up
                    else:
                        entered, exited = moved_up, moved_down
                    
                    if entered:
                        entry_count += 1
                        last_crossing_time[person_id] = now
                        event = f"ENTRY | ID={person_id} | Total={entry_count}"
                        print(event, flush=True)
                        write_status(event)
                    elif exited:
                        exit_count += 1
                        last_crossing_time[person_id] = now
                        event = f"EXIT | ID={person_id} | Total={exit_count}"
                        print(event, flush=True)
                        write_status(event)
                    
                    if current_side:
                        previous_side[person_id] = current_side
                    
                    detections.append((person_id, x1, y1, x2, y2))
            
            with detection_lock:
                latest_detections = detections
            
            if time.time() - last_status_write >= STATUS_WRITE_INTERVAL:
                write_status()
            
            inference_counter += 1
            
        except Exception as e:
            print(f"[ERROR] Inference failed: {e}")
            time.sleep(0.1)


# ============================================================================
# START THREADS
# ============================================================================

camera_thread = threading.Thread(target=read_camera, daemon=True)
inference_thread = threading.Thread(target=run_inference, daemon=True)

camera_thread.start()
inference_thread.start()

print("[MAIN] Threads started")


# ============================================================================
# MAIN DISPLAY LOOP
# ============================================================================

last_display_time = time.perf_counter()
fps = 0.0

try:
    while running:
        if not camera_connected:
            display_frame = np.zeros((OUTPUT_HEIGHT, OUTPUT_WIDTH, 3), dtype=np.uint8)
            cv2.putText(display_frame, "CAMERA DISCONNECTED", (80, 160),
                       cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 2)
            cv2.putText(display_frame, "Reconnecting...", (130, 210),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
            if not HEADLESS:
                cv2.imshow("Entry Counter", display_frame)
                if cv2.waitKey(30) & 0xFF == ord("q"):
                    break
            else:
                time.sleep(0.03)
            continue
        
        with frame_lock:
            if latest_frame is not None:
                display_frame = latest_frame.copy()
            else:
                display_frame = None
        
        if display_frame is None:
            if not HEADLESS and cv2.waitKey(1) & 0xFF == ord("q"):
                break
            time.sleep(0.01)
            continue
        
        # Initialize line
        height, width = display_frame.shape[:2]
        if line_y is None:
            line_y = int(height * LINE_POSITION)
            line_margin = max(12, int(height * LINE_MARGIN))
        
        # Draw detections
        with detection_lock:
            detections = list(latest_detections)
        
        for person_id, x1, y1, x2, y2 in detections:
            center_x = (x1 + x2) // 2
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(display_frame, (center_x, y2), 5, (0, 0, 255), -1)
            cv2.putText(display_frame, f"ID:{person_id}", (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        
        # Calculate FPS
        current_time = time.perf_counter()
        elapsed = current_time - last_display_time
        if elapsed > 0:
            fps = 0.9 * fps + 0.1 / elapsed
        last_display_time = current_time
        
        # Draw line
        cv2.line(display_frame, (0, line_y), (width, line_y), (0, 255, 255), 3)
        cv2.putText(display_frame, "DOOR LINE", (20, line_y - 10),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        
        # Draw stats
        cv2.rectangle(display_frame, (10, 10), (280, 130), (0, 0, 0), -1)
        cv2.putText(display_frame, f"IN: {entry_count}", (20, 45),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
        cv2.putText(display_frame, f"OUT: {exit_count}", (20, 80),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2)
        cv2.putText(display_frame, f"FPS: {fps:.1f}", (20, 115),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
        
        if not HEADLESS:
            cv2.imshow("Entry Counter", display_frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
        else:
            time.sleep(0.001)

except KeyboardInterrupt:
    print("[MAIN] Keyboard interrupt")

finally:
    print("[MAIN] Shutting down...")
    running = False
    inference_ready.set()
    
    camera_thread.join(timeout=2)
    inference_thread.join(timeout=2)
    
    cv2.destroyAllWindows()
    
    # Final stats
    print(f"[STATS] Frames: {frame_counter}, Inferences: {inference_counter}")
    print(f"[FINAL] Entry count: {entry_count}, Exit count: {exit_count}")
    print("[MAIN] Shutdown complete")