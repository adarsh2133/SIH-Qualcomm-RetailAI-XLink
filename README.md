PORTAL-XLINK
> Offline-First Retail Edge Intelligence
PORTAL-XLINK is a privacy-conscious retail edge-intelligence system that converts existing store camera feeds into actionable operational insights such as shopper footfall, shelf-visibility estimates, camera health and inventory alerts.
Instead of continuously sending video to cloud servers, the system performs its core processing locally on edge hardware using YOLOv8n + NCNN. Detected events are stored locally and securely delivered to a desktop operations dashboard.
---
1. PORTAL-XLINK Overview
What is PORTAL-XLINK?
PORTAL-XLINK brings computer vision closer to the retail store, allowing camera streams to be processed locally and converted into structured retail events.
A typical deployment can use different cameras for different purposes:
```text
RETAIL STORE
            │
   ┌────────┼────────┐
   ▼        ▼        ▼
Entrance   Shelf    Other
Camera     Camera    Zone
   │        │        │
   └────────┼────────┘
            ▼
   ┌─────────────────┐
   │ Raspberry Pi    │
   │  Edge AI        │
   └────────┬────────┘
            ▼
     YOLOv8n / NCNN
            ▼
      AI Detections
            ▼
   Analytics + Alerts
            ▼
          SQLite
            ▼
   Authenticated HTTPS
            ▼
    Desktop Dashboard
```
How it works
Entrance camera
Detects people and uses a configured virtual line to generate entry/exit counts and daily footfall.
```text
Person Detection
      ↓
Line Crossing
      ↓
Entry / Exit
      ↓
Footfall
```
Shelf camera
Monitors configured shelf regions and uses object detections to estimate visible product availability.
```text
Shelf Camera
     ↓
Shelf Region
     ↓
Object Detection
     ↓
Availability Estimate
     ↓
Stabilised Alert
```
The current shelf system provides a visible-product estimate, not guaranteed physical inventory verification.
Edge Intelligence
The Raspberry Pi handles the main local processing pipeline:
Camera capture
Frame preprocessing
YOLOv8n/NCNN inference
Footfall processing
Shelf-alert evaluation
Local persistence
Camera/system monitoring
```text
Camera → Capture → AI Inference → Analytics → SQLite / Alerts
```
The dashboard then receives structured information such as camera status, footfall data, detection events and alerts through authenticated HTTPS.
Why Edge Processing?
PORTAL-XLINK is designed around offline-first operation:
```text
Camera
   ↓
Local Edge AI
   ↓
Local Analytics
   ↓
Local Storage
   ↓
Dashboard
```
This reduces dependence on continuous cloud-video processing and allows the core local processing pipeline to continue during internet interruptions.
Privacy-Conscious Design
The system keeps the primary AI-processing path local and uses authenticated communication between the edge device and dashboard.
Current privacy-related design choices include:
Local AI inference
Local SQLite storage
Authenticated HTTPS
Structured event transfer
No facial-recognition requirement for current footfall functionality
The MVP does not currently implement face anonymisation, identity anonymisation, configurable video-retention policies or a formal DPDP compliance assessment. Therefore, the project is positioned as privacy-conscious, rather than claiming complete regulatory compliance.
Current MVP
Capability	Status
USB / RTSP camera input	✅ Implemented
Camera health monitoring	✅ Implemented
Raspberry Pi edge inference	✅ Implemented
YOLOv8n + NCNN	✅ Implemented
Person detection & footfall	✅ Implemented
SQLite persistence	✅ Implemented
Shelf visibility estimation	✅ Implemented
Stabilised shelf alerts	✅ Implemented
Authenticated HTTPS & secure pairing	✅ Implemented
Desktop operations dashboard	✅ Implemented
CSV / JSON reporting	✅ Implemented
Live queue analytics	🔄 Partial / Future
Dwell & live heatmap analytics	🔄 Future
Staffing recommendations	🔄 Future
General named-SKU recognition	🔄 Requires suitable model
Face anonymisation	🔄 Future
In One Sentence
> PORTAL-XLINK converts retail camera streams into locally processed operational insights using YOLOv8n + NCNN on edge hardware, stores validated events locally, and securely delivers them to a desktop dashboard without requiring continuous cloud-video processing.
---
2. System Architecture
The complete runtime pipeline is:
```text
Camera Inputs
     │
     ▼
Capture Layer
     │
     ▼
Frame Pre-processing
     │
     ▼
YOLOv8n / NCNN
     │
     ▼
Detection Results
     │
     ▼
Analytics Engine
 ┌───┼─────────────┐
 │   │             │
 ▼   ▼             ▼
Footfall  Shelf    Camera
Counting  Alerts   Health
 │         │
 └────┬────┘
      ▼
   SQLite
      │
      ▼
Authenticated HTTPS / JSON
      │
      ▼
Desktop Dashboard
      │
      ▼
CSV / JSON Reports
```
The architecture is designed so that capture, inference, analytics and local storage can continue without a cloud service dependency.
---
3. Typical Store Deployment
A camera does not have to perform every task.
Each camera can be assigned a specific operational role.
Camera 1 — Entrance
```text
Person Detection
       ↓
Virtual Line
       ↓
Entry / Exit
       ↓
Daily Footfall
```
Camera 2 — Shelf
```text
Shelf Camera
      ↓
Configured Shelf Region
      ↓
Visible Product Detection
      ↓
Availability Estimate
      ↓
Alert
```
Camera 3 — Additional Zone
Provides additional detection/monitoring coverage depending on the deployment.
The current system does not claim fully implemented live queue analytics, staffing recommendations, or complete dwell-time/heatmap analytics.
---
4. Camera Input & Capture
PORTAL-XLINK supports:
USB cameras
RTSP/IP camera streams
Each camera has an independent processing path.
Camera status is explicitly reported as:
```text
CONNECTING
ONLINE
DEGRADED
OFFLINE
```
The capture system prioritizes the latest frame instead of allowing old frames to accumulate in an inference queue.
For Linux USB capture, OpenCV/V4L2 is used.
Typical USB configuration:
```text
640 × 480
30 FPS requested
1-frame buffer
```
Actual throughput depends on camera hardware, resolution and edge-device load.
---
5. Edge Processing
The primary edge deployment uses a Raspberry Pi 4 Model B.
The edge device performs:
Camera capture
Frame preprocessing
AI inference
Footfall processing
Shelf-alert evaluation
Local persistence
API serving
A Main Edge PC can also be used when additional local compute is required.
The architecture remains the same:
```text
Camera
  ↓
Edge Processing
  ↓
AI
  ↓
Analytics
  ↓
Local Storage
```
---
6. YOLOv8n Model
PORTAL-XLINK uses a self-trained YOLOv8n-based detector.
The model provides detections containing information such as:
```text
Class ID
Bounding Box
Confidence
Camera ID
Timestamp
```
These detections form the input to the downstream analytics pipeline.
The lightweight YOLOv8n architecture is used because the project targets edge hardware rather than relying exclusively on high-end cloud GPUs.
---
7. Dataset & Training
The project includes utilities for retail dataset preparation and YOLOv8n training.
The training workflow is:
```text
Retail Dataset
      ↓
Dataset Preparation
      ↓
YOLOv8n Training
      ↓
Validation
      ↓
best.pt
      ↓
NCNN Export
      ↓
Raspberry Pi
```
The repository also includes SKU110K preparation utilities for retail-object detection experimentation.
The final README should list the exact dataset source, image count, classes and train/validation/test split once those project details are documented, rather than inventing them.
---
8. Model Specifications & Results
The supplied trained-model results are:
Metric	Result
Model	YOLOv8n
Epochs	100
Training time	7.43 hours
Precision	90.8%
Recall	83.3%
mAP@50	88.9%
mAP@50–95	54.7%
Parameters	3,005,843 (~3.0M)
Model size	6.2 MB
Compute	8.1 GFLOPs
Inference time	5.6 ms/image
Training/benchmark GPU	NVIDIA RTX 3050
Benchmark note
The reported 5.6 ms/image inference result is from the RTX 3050 benchmark environment.
It is not a Raspberry Pi performance claim.
The NCNN model should be benchmarked separately on the actual Pi deployment hardware.
---
9. NCNN Conversion & Pi Inference
The trained model is converted from the training format to NCNN before deployment.
```text
best.pt
   │
   ▼
Ultralytics Export
   │
   ▼
best_ncnn_model/
   │
   ▼
Raspberry Pi
   │
   ▼
NCNN Runtime
   │
   ▼
Local CPU Inference
```
Example:
```bash
python -m training.train --export-only --export --weights C:\path\best.pt --imgsz 416
```
The `.pt` training artifact does not need to be installed on the Pi.
This keeps heavyweight training dependencies away from the edge runtime.
---
10. Detection & Analytics Pipeline
Raw detections are converted into structured operational events.
```text
YOLO Detection
      ↓
Class + Confidence + Position
      ↓
Analytics Rules
      ↓
Operational Event
```
Examples:
```text
Person detected
Entry / Exit
Shelf availability state
Inventory alert
Camera health event
```
This allows the dashboard to work with meaningful structured information instead of requiring it to interpret raw camera video.
---
11. Footfall Analytics
For an entrance camera, a configurable virtual line can be used.
```text
Person Detection
      ↓
Line Crossing
      ↓
ENTRY / EXIT
      ↓
Daily Footfall
      ↓
SQLite
```
The current implementation supports configurable line-crossing counts and local daily persistence.
This provides the currently implemented shopper-flow capability.
---
12. Shelf Visibility & Inventory Alerts
A shelf-facing camera can be assigned a specific shelf region.
```text
Shelf Camera
      ↓
Latest Frame
      ↓
YOLO Detection
      ↓
Configured Shelf Region
      ↓
Visible Product Estimate
      ↓
Alert Rules
```
Shelf rules can define:
Camera ID
Shelf ID
Product/SKU metadata
Region coordinates
Confidence threshold
Low-stock threshold
Critical threshold
The system can generate states such as:
```text
AVAILABLE
LOW STOCK
CRITICAL
INVENTORY UNCERTAIN
```
---
13. Alert Stabilization & Limitations
The system does not immediately change inventory state based on one unreliable detection.
Configured rules can require multiple consistent observations.
```text
Frame 1 → Low
Frame 2 → Low
Frame 3 → Low
       ↓
Stable Low-Stock State
       ↓
Alert
```
Low-confidence observations can result in:
```text
INVENTORY_UNCERTAIN
```
Important limitation
The current generic detector provides a visible-SKU-box estimate.
It does not guarantee actual physical inventory.
The current generic SKU detector also does not automatically identify arbitrary named products in mixed-product regions.
---
14. Local Data & SQLite
Operational information is persisted locally using SQLite.
Examples include:
Footfall records
Detection/events
Camera status
Inventory alerts
Operational state
Report data
The core data path is:
```text
Detection
   ↓
Analytics
   ↓
Validated Event
   ↓
SQLite
```
No cloud database is required for the standard runtime.
---
15. Pi → Desktop Communication
The Raspberry Pi exposes authenticated HTTPS endpoints on the local network.
The communication flow is:
```text
Raspberry Pi
     │
     │ Detection data
     │ Camera health
     │ Alert data
     ▼
Authenticated HTTPS
     ▼
Desktop Client
```
The desktop client receives structured JSON/detection information.
It does not treat RTSP video itself as structured detection data.
---
16. Secure Pairing
The desktop application uses a controlled pairing process.
```text
Discover Pi
    ↓
Verify Certificate Fingerprint
    ↓
Enter Short-Lived Approval Code
    ↓
Authenticate
    ↓
Certificate Pinning
    ↓
Credential Stored Securely
```
The approval code is:
Short-lived
Single-use
Rate-limited
The Windows dashboard stores its reusable credential using Windows DPAPI.
---
17. Operations Dashboard
The desktop application provides the operational interface.
Current pages include:
```text
Overview
Cameras
Analytics
Queue
Footfall
Inventory
Dwell Time
Heatmap
Alerts
Reports
System
```
The dashboard distinguishes between live, unavailable and simulated states.
For unavailable live metrics:
```text
N/A
```
is shown instead of fabricated data.
---
18. Reports & API
Validated operational information can be exported as:
```text
CSV
JSON
```
Reports are stored under:
```text
data/reports/
```
Inventory alert APIs include:
```text
GET /api/v1/alerts/active
GET /api/v1/alerts
POST /api/v1/alerts/{alert_id}/acknowledge
```
The active-alert endpoint is designed to provide compact alert information without requiring the dashboard to download full camera detections.
---
19. Offline-First & Privacy-Conscious Design
The standard runtime keeps the main processing path local:
```text
Camera
  ↓
Edge AI
  ↓
Analytics
  ↓
SQLite
  ↓
Local Network
  ↓
Dashboard
```
Continuous cloud-video processing is therefore not required.
Privacy approach
The project uses:
Local inference
Local storage
Authenticated local communication
Structured event transfer
However, the project does not currently claim:
Automatic face anonymisation
Face blurring
Identity anonymisation
Zero personal-data processing
Formal DPDP compliance certification
Camera previews remain accessible to the authorised paired dashboard.
---
20. Failure Handling & Reliability
The system isolates individual camera failures.
Example:
```text
Camera 1 → ONLINE
Camera 2 → OFFLINE
Camera 3 → ONLINE
```
Camera 2 being unavailable should not stop Cameras 1 and 3.
RTSP reconnection is handled in the background.
The dashboard reports unavailable information honestly:
```text
OFFLINE
DEGRADED
N/A
```
rather than fabricating values.
---
21. Performance Monitoring
The detection pipeline reports metrics such as:
Capture FPS
Inference FPS
Inference latency
Frame age
Skipped frames
Mailbox depth
CPU usage
Memory usage
Performance depends on:
```text
Number of cameras
+
Resolution
+
Model
+
Pi CPU load
+
Inference configuration
+
LAN capacity
```
Therefore, actual Pi deployment performance must be measured on the target hardware.
---
22. Deployment & Setup
Raspberry Pi
```bash
cd /home/xlink/PORTAL-XLINK

chmod +x deploy/install_pi_service.sh

./deploy/install_pi_service.sh
```
Check the service:
```bash
sudo systemctl status portal-xlink.service
```
View logs:
```bash
sudo journalctl -u portal-xlink.service -n 40 --no-pager
```
Windows
Normal launch:
```bash
python app.py
```
Headless:
```bash
python app.py --headless
```
Setup/pairing:
```bash
python app.py --setup
```
---
23. Simulation, Headless & CI
The project separates live operation from simulation.
Hardware-independent validation
```bash
python app.py --headless
```
This reports missing hardware as unavailable.
Controlled demonstration
```bash
python app.py --headless --simulation
```
Simulation is explicitly labelled:
```text
SIMULATION / TEST
```
It is never presented as live camera output.
The repository also includes a headless smoke-test path for CI/local validation.
---
24. Current Implementation vs Future Work
Capability	Status
USB / RTSP camera capture	Implemented
Camera health/status	Implemented
Raspberry Pi edge inference	Implemented
YOLOv8n + NCNN	Implemented
Person detection	Implemented
Line-crossing footfall	Implemented
SQLite persistence	Implemented
Shelf visibility estimate	Implemented
Stabilised shelf alerts	Implemented / configuration required
Authenticated HTTPS	Implemented
Desktop dashboard	Implemented
CSV / JSON reports	Implemented
Queue analytics	Future / partial UI
Live wait-time estimation	Future
Dwell-time analytics	Future
Live heatmap analytics	Future
Staffing recommendations	Future
Named-SKU recognition	Requires suitable trained model
Face anonymisation	Not implemented
Formal privacy/compliance assessment	Not yet completed
---
25. Repository Map
```text
PORTAL-XLINK/
│
├── app.py
├── config.py
├── desktop_config.py
├── secure_http.py
│
├── cameras/          # Camera capture & stream handling
├── inference/        # AI / NCNN inference
├── analytics/        # Operational analytics
├── database/         # SQLite persistence
├── integration/      # Pi ↔ desktop integration
├── hardware/         # Raspberry Pi / LCD hardware
├── vision/           # Vision processing
├── heatmap/          # Heatmap functionality
├── gui/              # Desktop dashboard
├── training/         # YOLO training/export utilities
├── deploy/           # Raspberry Pi deployment
├── models/           # Deployed model files
├── data/             # Local data & reports
│
└── .github/          # CI / release workflows
```
---
26. End-to-End Technical Flow
The complete system can be understood in one sequence:
```text
1. Cameras capture store activity
              ↓
2. Raspberry Pi receives the streams
              ↓
3. Latest frames are selected
              ↓
4. Frames are preprocessed
              ↓
5. YOLOv8n performs local detection
              ↓
6. NCNN executes inference on the Pi
              ↓
7. Analytics interpret detections
              ↓
8. Footfall / shelf events are generated
              ↓
9. Alert rules validate shelf states
              ↓
10. Events are persisted in SQLite
              ↓
11. Structured data is exposed through
    authenticated HTTPS
              ↓
12. Desktop dashboard receives the data
              ↓
13. Operators view analytics and alerts
              ↓
14. Validated data can be exported
    as CSV / JSON
```
Technical Summary
> PORTAL-XLINK converts existing camera streams into locally processed retail events using YOLOv8n + NCNN on edge hardware, persists validated events in SQLite, and securely delivers structured insights to a desktop operations dashboard — without requiring continuous cloud-video processing.
