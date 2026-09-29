# PORTAL-XLINK

PORTAL-XLINK is a privacy-conscious retail edge-intelligence MVP. It is being
built to use on-device AI for shopper-flow analytics, shelf-visibility
estimates, and proactive operational alerts, helping retailers reduce
stock-outs, improve customer experience, and make better use of staff while
keeping inference and data storage on local edge devices.

The current implementation is strongest in edge camera capture, local
inference, daily footfall counting, and configurable shelf alerts. Queue
management, staffing recommendations, and some shopper analytics remain
future work; the status below distinguishes working paths from dashboard
placeholders and estimates.

## Features

- USB and RTSP camera inputs with truthful CONNECTING/ONLINE/DEGRADED/OFFLINE status
- Local NCNN inference on the Raspberry Pi, with detections shared to the desktop over authenticated HTTPS on the local network
- Person detection and configurable line-crossing entry/exit counts, persisted by local day in SQLite
- Configurable, stabilized low/critical/uncertain shelf alerts for explicitly mapped single-SKU regions
- A visible-SKU-box estimate from the latest shelf-camera frame; this is not verified physical inventory
- Local SQLite persistence, camera and alert status, and a CustomTkinter operations dashboard
- A polished dark CustomTkinter operations dashboard with honest `OFFLINE`/`N/A` states
- CSV and JSON report exports under `data/reports/`
- Headless smoke test for CI and local validation
- SKU110K preparation and YOLOv8n training utilities

Capture, orchestration, analytics, and SQLite persistence run on the Main Edge
PC or Raspberry Pi, depending on deployment mode. The Pi service runs YOLO
locally and exposes authenticated detection snapshots to a PORTAL-XLINK client
over the local network. The client never treats RTSP video as structured
detections. The standard deployment has no cloud or messaging dependency. A
failed/disconnected source is isolated and reported while other sources
continue. Camera previews can be streamed over the local network to the paired
dashboard; local processing does not by itself provide face anonymization or
make a privacy/compliance guarantee.

## Product vision alignment

| Goal | Current status | What the project does today / remaining gap |
|---|---|---|
| On-device AI with less cloud dependency | Implemented in the Pi architecture | NCNN inference and persistence run locally on the Pi; the desktop receives detections and can view local camera previews. There is no cloud service dependency. Validate performance on the target hardware and network. |
| Real-time shopper analytics | Partial | The Pi can detect people, count configured line crossings, and persist daily entry/exit totals. The Queue page is currently a camera view, not a live queue analytics pipeline. Dwell-time and heatmap views do not yet consume live shopper tracks. |
| Automated inventory visibility and fewer stock-outs | Partial | A latest-frame generic SKU-box estimate and optional stabilized shelf alerts are available. Alerts require configured dedicated-SKU shelf regions and a suitably validated model. They are estimates, not physical stock verification, and named SKU recognition is not provided by the generic detector. |
| Proactive queue management and staffing optimization | Not implemented | Queue length, wait-time estimation, queue escalation, staffing recommendations, and staff assignment are not currently produced from live camera data. |
| Better customer experience and operational efficiency | Enablement, not yet measured | Footfall and shelf alerts can inform operations, but the repository does not yet measure customer-experience outcomes, staffing efficiency, stock-out reduction, or return on investment. |
| Privacy-conscious operation | Partially addressed | Inference and database storage can remain on-device and transport to the paired dashboard uses authenticated TLS. Camera previews are still available to that dashboard; face blurring, identity anonymization, retention controls, and a formal privacy/compliance assessment are not claimed. |

The checked-out project includes the footfall person model, but not a trained
retail SKU model artifact. Before relying on shelf estimates or alerts, deploy
and validate a suitable SKU model, configure the shelf regions and thresholds,
and test it against representative store conditions. See the Raspberry Pi
deployment and inventory alert sections below for setup details.

### Self-trained YOLOv8n model

PORTAL-XLINK's retail detector is a self-trained YOLOv8n model trained on the
project's retail dataset. The reported training and benchmark details are:

| Metric | Reported result |
|---|---:|
| Training epochs | 100 / 100 |
| Training time | 7.43 hours |
| Precision | 90.8% |
| Recall | 83.3% |
| mAP@50 | 88.9% |
| mAP@50-95 | 54.7% |
| Parameters | 3,005,843 (~3.0M) |
| Model size | 6.2 MB |
| Inference time | 5.6 ms/image |
| Training / benchmark GPU | NVIDIA RTX 3050 |
| Compute | 8.1 GFLOPs |

These are the supplied model results; the dataset split, evaluation protocol,
and benchmark setup beyond the stated GPU were not included here. Treat the
inference time as the RTX 3050 result, not a Raspberry Pi performance claim.
For Pi deployment, export the trained `best.pt` weights to NCNN and validate
accuracy and throughput on the target camera views. The trained `best.pt`
artifact is not included in this checkout; see the Raspberry Pi deployment
instructions for the export and copy steps.

## Run on Windows (no hardware)

```bash
python app.py --headless                 # no hardware: reports OFFLINE/N/A
python app.py --headless --simulation    # explicit controlled demo only
python app.py                         # stays in the GUI mainloop without cameras
```

`--headless` does not enable simulation. Simulation is enabled only by the
explicit `--simulation` flag and is always labeled `SIMULATION/TEST`, never
`LIVE`. Set `PORTAL_HEADLESS=true`,
`PORTAL_DB_PATH`, `PORTAL_LOGS_PATH`, `PORTAL_REFRESH_MS`, and
`PORTAL_CAMERA_COUNT` or a comma-separated `PORTAL_CAMERA_SOURCES` list of
configured values such as `rtsp:<publisher-url>` or `usb:<index>` (see
`.env.example`). Camera indices must match devices attached to the host running
the capture process.
CustomTkinter is required for the desktop shell. OpenCV, Ultralytics, and
NumPy are required on the Pi detection service; install using
`requirements-pi.txt`. The application never fabricates frames or detections.
RTSP reconnects are polled in the background and diagnostics mask RTSP
credentials.

## Downloadable Windows dashboard

The Windows installer packages the dashboard client only; the Raspberry Pi
continues to run the camera, NCNN model, and authenticated API. On first launch, the dashboard discovers PORTAL-XLINK devices on the local
network. For first-time pairing, enter the short-lived approval code printed
to the Pi's local console/systemd journal and confirm that the full certificate
fingerprint in the wizard matches the Pi's local console; the reusable API
credential is never shown or typed. The wizard pins the Pi's TLS certificate,
tests the authenticated health endpoint, and stores the credential with Windows DPAPI. Later launches
reuse the saved pairing automatically. Use `--setup` to reconnect or pair again:

```powershell
python app.py --setup
```

The same wizard appears when running `python app.py --backend remote` without
saved connection settings. Pairing uses TLS with a SHA-256 certificate pin
advertised by the local-network discovery beacon. Pair codes are valid for ten
minutes, single-use, and rate-limited. The bearer credential is persisted only
in the Pi's service-owned state directory and the Windows DPAPI-protected
desktop settings. Network discovery does not carry credentials. If the Pi
credential is rotated, the dashboard opens the re-pair flow automatically.

To build the installer locally on Windows, install Python 3.11 and Inno Setup 6,
then run from PowerShell. The build script creates an isolated `.venv-build`
environment so it does not install packaging dependencies into the system
Python:

```powershell
.\build\windows\build.ps1
```

The output is `dist\PORTAL-XLINK-Setup.exe`. To publish a downloadable release
from your GitHub repository, push the project and create a version tag such as
`v1.0.0`; `.github/workflows/windows-release.yml` builds the installer and
attaches it to the GitHub release. The installer is currently unsigned, so
Windows SmartScreen may show a publisher warning until code signing is set up.

## Final camera architecture

```text
USB webcams -> Raspberry Pi 4 (PORTAL-XLINK + YOLO) -> authenticated HTTPS/JSON
                                                   -> desktop PORTAL-XLINK UI
```

The Pi service captures USB webcam video, runs YOLO locally, then sends
detection boxes, class IDs, confidence, and camera health to the desktop client
as JSON. RTSP is not needed for webcams plugged directly into the Pi.

## Dashboard and reports

The desktop dashboard is a command-centre shell with a permanent sidebar and
scrollable pages: Overview, Cameras, Analytics, Queue, Footfall, Inventory,
Dwell Time, Heatmap, Alerts, Reports, and System. In normal live mode, panels never read seeded analytics,
historical snapshots, or placeholder inventory as current values: unavailable
metrics remain `N/A`. Use `--simulation` only for an explicitly labelled
`SIMULATION / TEST` run. The Reports section shows the exact local output
directory (`data/reports`) and can export the current validated view as CSV or
JSON. Historical reports should be kept and reviewed as historical data; they
are not used to populate live cards.

## Raspberry Pi deployment

The Raspberry Pi 4 Model B (4 GB) runs camera capture and YOLO inference. The
desktop computer runs the dashboard client and receives detection data over
the LAN.

## Raspberry Pi to PORTAL-XLINK integration

Train `best.pt` on your training computer and export it to NCNN there. This
keeps PyTorch, Ultralytics, and training dependencies off the Pi; Raspberry Pi
inference uses NCNN on CPU. Deploy the exported model before installing the
boot service; this checkout intentionally contains no trained model artifact.

On the training computer, from the project root:

```powershell
python -m training.train --export-only --export --weights C:\Users\Adarsh\Desktop\best.pt --imgsz 416
```

Ultralytics creates a `best_ncnn_model` folder beside `best.pt`. Copy this
folder and the updated runtime code to the Pi, but not the `.pt` file, dataset,
or training outputs:

```powershell
ssh xlink@storesense.local "mkdir -p /home/xlink/PORTAL-XLINK/models/yolo"
scp app.py config.py desktop_config.py secure_http.py requirements-pi.txt xlink@storesense.local:/home/xlink/PORTAL-XLINK/
scp -r cameras database inference integration hardware analytics heatmap vision gui deploy xlink@storesense.local:/home/xlink/PORTAL-XLINK/
scp -r C:\Users\Adarsh\Desktop\best_ncnn_model xlink@storesense.local:/home/xlink/PORTAL-XLINK/models/yolo/
```

Install and start the Pi service after copying the exported model:

```bash
cd /home/xlink/PORTAL-XLINK
chmod +x deploy/install_pi_service.sh
./deploy/install_pi_service.sh
sudo systemctl status portal-xlink.service
```

The installer provisions a virtual environment and OS packages, initializes
the persistent service directory, and enables a restarting systemd unit.
V4L2 cameras are discovered at boot (up to four) when camera sources have not
been explicitly configured. It verifies that the exported NCNN `.param` and
`.bin` files exist before installing the unit. For a first dashboard pairing,
read the one-time code from the Pi console or:

```bash
sudo journalctl -u portal-xlink.service -n 40 --no-pager
```

The code is a local approval, not the API token. In the Windows dashboard,
choose **Find Pi on this network**, compare the displayed certificate
fingerprint with the local Pi console, confirm it, enter the code once, and
connect. No
environment file or API token copy/paste is required for normal startup.
To rotate the API credential and require a fresh pairing, on the Pi run:

```bash
sudo -u xlink env PORTAL_STATE_DIR=/var/lib/portal-xlink \
  /home/xlink/PORTAL-XLINK/.venv-ncnn/bin/python \
  /home/xlink/PORTAL-XLINK/app.py --re-pair
sudo systemctl restart portal-xlink.service
```

Replace `xlink` and the project path if the Pi account or install location is
different. The new short-lived approval code is printed locally; existing
dashboard credentials stop working after the service restart.

USB capture uses OpenCV's V4L2 backend on Linux and requests 640x480 at 30 FPS
with a one-frame buffer, matching the confirmed webcam modes and favoring the
newest frame over queued stale frames. RTSP streams also request a one-frame
OpenCV buffer. Pi camera workers publish only their newest frame; the Pi does
not build an inference backlog. Each configured stream has an independent NCNN
inference worker and model instance, so one slow stream does not block the
others. By default, NCNN threads per camera are based on the Pi's CPU core count
divided by the configured camera count. Tune this with
`PORTAL_NCNN_THREADS_PER_CAMERA`; avoid oversubscribing CPU cores. The
`PORTAL_NCNN_THREADS` setting controls the default thread count for a
single/local NCNN engine. Each configured camera is captured using OpenCV and
processed by the same NCNN SKU detector; OpenCV supplies capture/resize/video
overlays and is not used to load or replace the NCNN model.

The MJPEG preview runs independently per camera with a 15 FPS target per
camera by default, drawing the latest available detections on each stream.
Set `PORTAL_API_PREVIEW_FPS` (1-30) to tune preview bandwidth; the target does
not increase the camera's capture rate, and actual throughput is limited by
capture FPS, inference time, Pi load, and LAN capacity. The detection
API reports per-camera inference latency and estimated inference FPS. These
rates depend on model latency, Pi load, resolution, and LAN capacity; more
camera streams increase total CPU work.

RTSP capture uses OpenCV by default. To opt into OpenCV's GStreamer backend on
the Pi, install a GStreamer-enabled OpenCV build and its RTSP/decode plugins,
set `PORTAL_RTSP_BACKEND=gstreamer`, and restart the service. That backend uses
a leaky one-buffer queue and a dropping appsink so capture does not build a
stale-frame backlog. It does not promise hardware decoding: the selected
decoder depends on installed GStreamer plugins. Compare camera FPS, inference
latency, dropped-frame counts and CPU on the actual Pi before keeping this
setting; the default remains OpenCV because this workspace cannot benchmark the
Pi's GStreamer build.

The detection response's `performance` object reports Linux process/system CPU
and memory, while each camera entry reports capture/inference FPS, inference
latency, input frame age, skipped frame count and latest-frame mailbox depth.
Each stream already has an independent capture worker and an inference worker;
the inference worker reads the latest frame rather than draining a FIFO.

### Configuring product alerts

The Pi can produce stock alerts only for explicitly configured single-SKU
regions. `PORTAL_INVENTORY_ALERT_RULES_JSON` is an optional JSON array. Each
region uses normalized image coordinates, and `dedicated_sku_region` must be
`true` to affirm that the polygon contains only the configured product. The
checked-in detector has a generic `sku` class; it cannot identify a named SKU
in a mixed-product region. For example:

```json
[
  {
    "camera_id": "usb-01",
    "sku_id": "cola-500",
    "product": "Cola 500 ml",
    "shelf_id": "A-03",
    "section": "Drinks",
    "class_id": 0,
    "dedicated_sku_region": true,
    "region": [[0.10, 0.20], [0.42, 0.20], [0.42, 0.86], [0.10, 0.86]],
    "low_stock_threshold": 5,
    "critical_stock_threshold": 2,
    "min_confidence": 0.70,
    "stable_samples": 3,
    "max_quantity_spread": 0,
    "confirmation_s": 2,
    "cooldown_s": 60,
    "message_template": "{product} has limited availability in {section}, shelf {shelf_id}.",
    "uncertain_message_template": "Availability could not be verified for {product} at {shelf_id}.",
    "out_of_stock_message_template": "{product} is currently unavailable at {shelf_id}."
  }
]
```

At least three consistent, sufficiently confident observations are required
before stock state changes; a low-confidence or empty region is classified as
`INVENTORY_UNCERTAIN`, never as out-of-stock. Thresholds and cooldown are set
per rule. Camera-offline conditions remain sourced from live camera health.
These alerts are estimates based on detector observations, not a guarantee of
physical inventory.

An authenticated customer display can poll the compact active list without
downloading camera detections:

```text
GET /api/v1/alerts/active
GET /api/v1/alerts
POST /api/v1/alerts/{alert_id}/acknowledge
```

Poll the active endpoint at a modest interval (for example, one second); a
response includes alert type, severity, product/shelf metadata, estimated
quantity where reliable, timestamp and customer message. Acknowledgement is
supported for inventory alerts.

### Raspberry Pi 16x2 customer LCD

The Pi service optionally connects a physical HD44780-compatible 16x2 display
directly to the same stabilized inventory alerts used by the authenticated
API. Display I/O runs on a dedicated worker thread. GPIO/I2C failures are
logged and retried without stopping cameras, inference, alerts, or the API.
If a display or bus is not present, initialization retries every five seconds.
Set `PORTAL_LCD_INTERFACE=auto` to probe common PCF8574/PCF8574A backpack
addresses on the configured I2C bus first; if no backpack is found, a parallel
display is selected only when a complete explicit `PORTAL_LCD_GPIO_JSON`
mapping is supplied. Set the interface to `i2c` or `parallel` to require one
type, or `disabled` to turn the display off. Software probing cannot identify
the LCD controller chip or verify electrical wiring; confirm the module/
backpack marking and use `i2cdetect` before powering it.

After the display is wired, run the guided LCD setup from the Pi project
directory. It selects an unambiguous I2C backpack automatically or guides you
through a validated BCM pin map for parallel mode, then updates the systemd
drop-in without requiring environment-file editing:

```bash
cd /home/xlink/PORTAL-XLINK
sudo .venv-ncnn/bin/python -m hardware.lcd_setup
```

If the LCD is not connected yet, cancel the wizard and leave auto-detection
enabled. A missing or failed display does not stop camera, inference, alert, or
API workers.

Install the Raspberry Pi OS GPIO/I2C support and enable I2C:

```bash
sudo apt update
sudo apt install -y i2c-tools python3-lgpio
sudo raspi-config
# Interface Options -> I2C -> Enable; reboot if requested.
sudo i2cdetect -y 1
```

Common PCF8574 backpacks appear at `0x20`-`0x27` or PCF8574A addresses
`0x38`-`0x3f`; `0x27` and `0x3f` are common but not guaranteed. If exactly one
supported address is found, auto mode selects it. If more than one responds,
set the actual display address explicitly. Acknowledge and identify the
physical backpack before enabling customer messages.

#### I2C backpack wiring

Use the Pi's 40-pin header I2C1: **BCM GPIO2/SDA (physical pin 3)**,
**BCM GPIO3/SCL (physical pin 5)**, and a common ground (**physical pin 6**).
Power the backpack only according to its actual board specification. Many
backpacks power the LCD and pull SDA/SCL up to 5 V; **do not connect a 5 V
pull-up to Pi SDA/SCL**. Use a bidirectional I2C level shifter with pull-ups
to 3.3 V on the Pi side, or a verified 3.3 V-safe backpack/pull-up arrangement.
Set `PORTAL_LCD_I2C_BUS=1`, `PORTAL_LCD_I2C_ADDRESS=auto` or the detected
address such as `0x27`. Backpack expander bits are configurable using
`PORTAL_LCD_I2C_PCF8574_MAP_JSON`; the default is the common
`RS=0, RW=1, E=2, backlight=3, D4..D7=4..7` mapping. Verify the backpack's
actual mapping if the LCD shows garbled characters.

#### HD44780 parallel wiring

Use 4-bit data mode. Connect LCD `RW` to ground; configure the six distinct
**BCM** GPIO numbers (not header pin numbers) for `RS`, `E`, `D4`, `D5`, `D6`,
and `D7` in `PORTAL_LCD_GPIO_JSON`, for example:

```bash
export PORTAL_LCD_INTERFACE=parallel
export PORTAL_LCD_GPIO_JSON='{"rs":17,"enable":27,"d4":22,"d5":23,"d6":24,"d7":25}'
```

Wire those BCM pins to the corresponding LCD inputs and share Pi/LCD ground.
The driver rejects BCM GPIO2/3 for parallel use and any overlap with
`PORTAL_GPIO_PINS`. Review the whole project's GPIO assignments before
connecting anything. **Raspberry Pi GPIO is 3.3 V only**: never connect a 5 V
LCD output to a Pi pin. Many 5 V HD44780 modules are not guaranteed to accept a
3.3 V high input, so use a proper 3.3-to-5 V logic buffer/level shifter or a
verified 3.3 V-compatible LCD. Do not use the Pi GPIO to power the LCD or its
backlight; provide the rated supply/current limiting resistor or driver from
the module specification.

The Pi setup example is:

```bash
export PORTAL_LCD_INTERFACE=auto
export PORTAL_LCD_I2C_BUS=1
export PORTAL_LCD_I2C_ADDRESS=auto
export PORTAL_LCD_ROTATION_S=5
export PORTAL_LCD_SCROLL_INTERVAL_S=0.45
export PORTAL_LCD_ALERT_PRIORITY_JSON='{"OUT_OF_STOCK":3,"CRITICAL_STOCK":2,"LOW_STOCK":1}'
python app.py --serve-api
```

`PORTAL_LCD_ROTATION_S` controls how long same-priority products remain on
screen; only the highest active priority is displayed. Long product names
scroll on the second line. Repeated frames do not retrigger the display:
only the active Pi inventory alert state is consumed, so its configured
stable-sample, confidence, confirmation, and cooldown rules remain authoritative.
Cleared/resolved alerts are removed automatically; without an eligible alert
the LCD shows `PORTAL-XLINK` / `System Online`. Camera or display network
connectivity is not needed for local LCD updates.

The authenticated detection snapshot also includes active detection alerts
and recent alert events. Detection alerts fire when a class first appears and
re-arm after it has been absent briefly. Raw per-frame detection counts are
not used to claim low stock or an empty shelf; those alerts require a
configured shelf region and a stabilized inventory estimate. Camera
disconnects, inference failures, and dashboard-to-Pi API connection failures
are also surfaced.

Generate a separate API secret; do not reuse the Pi account password.
The Windows client polls detections every 0.5 seconds by default
(`PORTAL_REMOTE_POLL_INTERVAL_S`), while camera MJPEG frames update independently.

The API provides:

```text
GET https://<discovered-pi-address>:8765/api/v1/health
GET https://<discovered-pi-address>:8765/api/v1/detections
GET https://<discovered-pi-address>:8765/api/v1/alerts/active
GET https://<discovered-pi-address>:8765/api/v1/alerts
GET https://<discovered-pi-address>:8765/api/v1/camera-frame?camera_id=usb-01
GET https://<discovered-pi-address>:8765/api/v1/camera-stream?camera_id=usb-01
```

All endpoints require an `Authorization` bearer token. Camera-frame requests
return JPEG snapshots scaled to at most 640 pixels wide/high by default
(`PORTAL_API_FRAME_MAX_SIZE`). The camera-stream endpoint returns continuous
MJPEG; it is rate-limited by `PORTAL_API_PREVIEW_FPS` (default 15) and displayed
in the dashboard's Cameras page. This target is subject to webcam capture,
Pi CPU, and LAN capacity.

The Windows client discovers the Pi and pins its certificate during pairing.
For scripts, use the HTTPS base URL and the saved DPAPI credential; do not put
the API token in a shared `.env` file. Discovery uses local-subnet UDP
broadcast, so clients on different VLANs must use an administrator-configured
network route or join the Pi's subnet for initial pairing.

When the footfall and queue cameras are connected, check their actual V4L2
device indices on the Pi with `v4l2-ctl --list-devices`, then configure all
desired camera sources in `PORTAL_CAMERA_SOURCES` (for example
`usb:0,usb:1,usb:2`) and restart the Pi service. Keep only connected cameras
in this list. The USB source list order maps to dashboard IDs `usb-01`,
`usb-02`, and `usb-03`. Each feed is captured with OpenCV. Cameras configured
for footfall bypass NCNN inference so the OpenCV counter has the Pi CPU; other
cameras continue to use the configured NCNN detector. `PORTAL_FOOTFALL_CAMERA_IDS`
is a comma-separated list of camera IDs; by default only the first configured
camera is used for footfall. The Footfall and Queue pages each have a camera
selector and show the selected Pi stream when it is online; you can select
different camera IDs on the two pages. No extra stream server is needed—the
authenticated MJPEG endpoint serves each configured camera.

For the two-camera setup with the existing `USB2.0 PC CAMERA` as entry/footfall
and the new `ZEB LIVE PRO` as shelf camera, explicitly order the stable device
paths in the systemd override so the roles do not depend on discovery order:

```ini
[Service]
Environment="PORTAL_CAMERA_SOURCES=usb:/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0,usb:/dev/v4l/by-id/usb-BC-250603-ZW_ZEB_LIVE_PRO-video-index0"
Environment=PORTAL_FOOTFALL_CAMERA_IDS=usb-01
```

This assigns the existing entry camera to `usb-01` and the ZEB shelf camera
to `usb-02`; only `usb-01` runs footfall, while `usb-02` uses the SKU NCNN
model. Shelf stock alerts still require a valid
`PORTAL_INVENTORY_ALERT_RULES_JSON` rule with `"camera_id": "usb-02"`, the
trained SKU class ID, thresholds, and a polygon covering that product's
dedicated shelf region. Capture width, height, FPS, and pixel format settings
can be set per camera slot with `PORTAL_USB_CAMERA_01_WIDTH`,
`PORTAL_USB_CAMERA_01_HEIGHT`, `PORTAL_USB_CAMERA_01_FPS`,
`PORTAL_USB_CAMERA_01_FOURCC`, and corresponding `_02_` variables. These slot
numbers follow the ordered camera sources. For the reported devices, use YUYV
320x240 on `usb-01` and MJPG 640x480 on `usb-02`; both modes are advertised at
30 FPS. Verify each camera's modes with
`v4l2-ctl --device=/dev/v4l/by-id/usb-Generic_USB2.0_PC_CAMERA-video-index0 --list-formats-ext`
and
`v4l2-ctl --device=/dev/v4l/by-id/usb-BC-250603-ZW_ZEB_LIVE_PRO-video-index0 --list-formats-ext`.

The Pi footfall path uses the bundled COCO YOLOv8n NCNN person model by default
for the configured footfall camera. COCO class ID `0` is person. The model path
can be overridden with `PORTAL_FOOTFALL_PERSON_MODEL_PATH`; the product/SKU
model is never used for person counting. If the bundled model or NCNN runtime
is unavailable, the service fails at startup with an explicit error instead of
silently switching to motion-only detection. The OpenCV HOG and motion fallback
remain available as counter modes for configurations that intentionally omit
the NCNN person model.

The bundled model uses class ID `0`, confidence threshold `0.25`, and input size
`320` by default. To use a different export, provide its directory containing
exactly one matching `.param`/`.bin` pair and set the corresponding
`PORTAL_FOOTFALL_PERSON_*` values with `sudo systemctl edit portal-xlink.service`:

```ini
[Service]
Environment=PORTAL_FOOTFALL_PERSON_MODEL_PATH=/home/xlink/PORTAL-XLINK/models/my-person-model
Environment=PORTAL_FOOTFALL_PERSON_CLASS_ID=0
Environment=PORTAL_FOOTFALL_PERSON_CONFIDENCE=0.25
Environment=PORTAL_FOOTFALL_PERSON_IMAGE_SIZE=320
```

For a single configured camera, NCNN inference defaults to up to two CPU
threads when the Pi has enough cores. With multiple configured cameras, each
model defaults to one NCNN thread and OpenCV is limited to one thread to reduce
CPU oversubscription. `PORTAL_NCNN_THREADS_PER_CAMERA` and
`PORTAL_FOOTFALL_NCNN_THREADS` override these settings. Set
`PORTAL_YOLO_IMAGE_SIZE` to the same size used to export the deployed NCNN
model. Changing only this runtime value does not re-export or safely resize a
fixed-shape model; export `best.pt` at 320 before selecting 320, then verify
shelf accuracy before relying on its counts.

The Inventory page reports latest-frame visible class-0 SKU boxes for the
first online non-footfall camera as an estimate, not verified physical stock.
This is distinct from stock alert rules, which still require dedicated shelf
regions and configured thresholds.

For an alternate Ultralytics COCO model, class ID `0` is `person`. Export it
using the supported Ultralytics `yolo export model=<COCO weights> format=ncnn
imgsz=320` command; check the model's license before commercial use. A general
COCO model is only a baseline: its overhead and dense-crowd accuracy must be
measured on representative camera footage before operational use.
This checkout includes a YOLOv8n COCO NCNN export in
`models/footfall-person-ncnn/`; its upstream metadata declares AGPL-3.0.
Review [the model-specific license note](./models/footfall-person-ncnn/README.md)
before commercial deployment. Copy the project and model to the Pi; no person
model override is needed when the bundled model remains at its default path:

```powershell
scp .\integration\pi_service.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/integration/
scp -r .\models\footfall-person-ncnn xlink@storesense.local:/home/xlink/PORTAL-XLINK/models/
ssh -t xlink@storesense.local
```

For the bundled model, no person-model environment setting is required. After
copying the updated service code and model to the Pi, run
`sudo systemctl restart portal-xlink.service`.
The active detector is also reported in the API's per-camera footfall
`processing.detector` field. Person detections or motion blobs are tracked
locally per camera; tracks must persist for 2 frames and move at least 6
pixels before crossing events count. Motion candidates allow aspect ratios
from 0.3 to 3.0 and use a 0.003 minimum frame-area threshold to better retain
wide or partial overhead silhouettes. Unqualified detections are shown as
`BLOB CANDIDATE`; confirmed tracked blobs receive a track ID. Track matching
allows a displacement of up to 70% of frame height between observations to
bridge missed/slow frames. A clear side-to-side jump across the line is counted
on its first observed opposite-side frame; small near-line movements still
require repeated confirmation. The API reports the latest candidate and track
counts per camera. The default counting line is horizontal at the middle of the
image. Set `PORTAL_FOOTFALL_LINE_AXIS=vertical` for left/right movement.
`PORTAL_FOOTFALL_ENTRY_SIDE=negative` means bottom-to-top for a horizontal
line and right-to-left for a vertical line; `positive` means the opposite.
The counter increments entry on the configured entry-direction crossing and
exit on the reverse crossing. `PORTAL_FOOTFALL_LINE_RATIO` adjusts the line position
along its axis from `0.1` through `0.9`. For example, run
`sudo systemctl edit portal-xlink.service` on the Pi and add `[Service]`
followed by `Environment=PORTAL_FOOTFALL_LINE_AXIS=horizontal`,
`Environment=PORTAL_FOOTFALL_ENTRY_SIDE=negative`, then run
`sudo systemctl restart portal-xlink.service`. Tune
`PORTAL_FOOTFALL_MIN_TRACK_FRAMES` and
`PORTAL_FOOTFALL_MIN_TRACK_MOTION` if detections are intermittent. Confirmed
side changes must persist for two frames beyond a 1.5%-of-image-height
deadband, with an eight-frame recrossing cooldown; tune
`PORTAL_FOOTFALL_CROSSING_CONFIRM_FRAMES`,
`PORTAL_FOOTFALL_LINE_DEADBAND_RATIO`, and
`PORTAL_FOOTFALL_CROSSING_COOLDOWN_FRAMES` to adjust this behavior. These
settings affect new events only; existing daily totals are retained and are
not retroactively corrected.
At startup, the Pi prints the configured footfall camera IDs and person-model
path. The Footfall page reports `person_model_state` and any inference error;
`LIVE` confirms an NCNN person inference succeeded, while `NOT CONFIGURED` or
`ERROR` identifies why person detections are not being produced. Changing the
counting line axis affects crossing counts, not person-model inference.
On Raspberry Pi, USB capture requests 320x240 at 30 FPS using YUYV by default.
Confirm that the camera advertises this pixel format and frame interval with
`v4l2-ctl --list-formats-ext`; the USB driver may reject unsupported modes.
Tune `PORTAL_USB_CAMERA_WIDTH`,
`PORTAL_USB_CAMERA_HEIGHT`, `PORTAL_USB_CAMERA_FPS`, and
`PORTAL_USB_CAMERA_FOURCC` if the camera does not support that mode; check
accepted formats with `v4l2-ctl --list-formats-ext`. These settings can be
applied without changing the systemd unit using `sudo systemctl edit
portal-xlink.service`, adding `[Service]` followed by
`Environment=PORTAL_USB_CAMERA_FPS=30`, and restarting the service. Footfall person detection
is resized to at most 320 pixels wide. Pi MJPEG preview targets 15 FPS at a
320-pixel maximum dimension and JPEG quality 40; the Windows dashboard refreshes
previews up to 30 times per second. Tune
`PORTAL_API_PREVIEW_FPS` (1–30, default 15), `PORTAL_API_FRAME_MAX_SIZE`
(minimum 160), and `PORTAL_API_JPEG_QUALITY` (30–90) in a systemd override if network
bandwidth or CPU capacity is limited.
Daily local-time entry and exit totals persist in the Pi SQLite database and
appear on the dashboard Overview and Footfall page. The preview overlays the
counting line and the active detector's person detections or motion blobs.

The Pi installs `opencv-python-headless`; no OpenCV window or display server is
used. HOG is a pretrained person detector optimized for upright, full-body
people. It can fail to recognize people in a straight-down overhead view, at
small scales, or when people overlap; it is not a substitute for validating a
detector trained for the camera's overhead viewpoint. Review the annotated
stream at the actual doorway before relying on the counts. This counter does
not use the SKU model. Queue and other person-specific analytics still require
a separately validated person detector.

To deploy a footfall code update from Windows, stop the Pi service, copy the
changed files, and start the service again:

```powershell
ssh xlink@storesense.local "sudo systemctl stop portal-xlink.service"
scp .\analytics\daily_footfall.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/analytics/
scp .\vision\overhead_footfall.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/vision/
scp .\integration\pi_service.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/integration/
scp .\inference\remote_inference.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/inference/
scp .\gui\main_window.py .\gui\camera_feed_panel.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/gui/
scp .\requirements-pi.txt xlink@storesense.local:/home/xlink/PORTAL-XLINK/
scp .\cameras\camera_manager.py .\cameras\usb_camera.py xlink@storesense.local:/home/xlink/PORTAL-XLINK/cameras/
ssh xlink@storesense.local "sudo systemctl start portal-xlink.service"
```

To use the headless OpenCV wheel on an existing Pi installation, stop the
service, replace the GUI wheel, and restart:

```bash
sudo systemctl stop portal-xlink.service
/home/xlink/PORTAL-XLINK/.venv-ncnn/bin/python -m pip uninstall -y opencv-python opencv-contrib-python
/home/xlink/PORTAL-XLINK/.venv-ncnn/bin/python -m pip install -r /home/xlink/PORTAL-XLINK/requirements-pi.txt
sudo systemctl start portal-xlink.service
```

The detections response is JSON with an overall state, per-camera status,
frame timestamp, a daily `footfall` summary (`date`, `timezone`,
`total_entries`, `total_exits`, and per-camera totals), and a flat detection list. Each detection includes
`camera_id`, `class_id`, `confidence`, and pixel-coordinate `bbox`. The same
response contains current `alerts` and a bounded `alert_events` history:

```json
{
  "schema_version": 1,
  "state": "LIVE",
  "timestamp": "2026-09-27T06:00:00+00:00",
  "detections": [
    {"camera_id": "usb-01", "class_id": 0, "confidence": 0.91, "bbox": [20.0, 35.0, 105.0, 170.0]}
  ],
  "alerts": [
    {"category": "detection", "severity": "info", "camera_id": "usb-01", "class_id": 0, "message": "Class 0 detected on usb-01 (1 item, confidence 91%)."}
  ],
  "alert_events": []
}
```

The dashboard's Cameras page shows the Pi's camera statuses and JPEG previews
with YOLO boxes overlaid. The Inventory page lists current detections for
inspection, but raw boxes are not presented as physical stock quantities; the
overview inventory metric remains unavailable until a configured, stabilized
shelf estimate is provided. The client polls in a background thread so a
temporary network timeout does not block the GUI.
Configure the Pi's firewall to allow the API port only from the PORTAL-XLINK
client. The API uses HTTP, so do not expose it to an untrusted network.

## Train the SKU detector

SKU110K is a single-class object-detection dataset, so its annotations are
converted to the YOLO format with one class (`sku`). Install the separate training dependencies in a training environment where
Ultralytics and the required CUDA/PyTorch version are supported:

```powershell
pip install -r requirements-training.txt
python -m training.prepare_sku110k --source C:\datasets\sku110k
python -m training.train --epochs 100 --imgsz 640 --batch 16 --device 0
```

The preparation command expects the extracted Kaggle download to contain
`train.csv`, `val.csv`, and `test.csv` (or `annotations_train.csv`,
`annotations_val.csv`, and `annotations_test.csv` equivalents).
It writes the generated dataset to `data\sku110k\`, preserving the standard
Ultralytics layout:

```text
data\sku110k\
  data.yaml
  images\train|val|test\
  labels\train|val|test\
```

To validate a trained model, or export it without training again:

```powershell
python -m training.train --validate --weights runs\sku110k\yolov8n\weights\best.pt
python -m training.train --export-only --export --weights runs\sku110k\yolov8n\weights\best.pt --imgsz 416
```

`--export` defaults to NCNN for Raspberry Pi deployment. Use `--format onnx`
only when another deployment runtime needs ONNX.

Training artifacts under `runs\` and the locally generated images/labels are
not source-controlled. Keep `best.pt` on the training computer; copy the
exported `best_ncnn_model` directory to `models/yolo/` on the Pi.

The currently checked-in dataset definition has one class (`sku`). Queue, dwell,
and other person-specific analytics require a separately validated person
detector and camera-specific regions/calibration; SKU detections must not be
used as person observations. Overhead footfall is instead estimated from
OpenCV motion blobs and has the limitations described above. This checkout does
not contain an exported NCNN model pair, so Pi inference remains unavailable
until the trained model is deployed.

Software verification for plug-and-play setup uses mocked GPIO/I2C and camera
devices. Real Pi boot/service startup, physical GPIO/I2C, camera enumeration,
four-camera FPS/latency/RAM, NCNN throughput, and LCD alert presentation remain
`PENDING_REAL_PI_HARDWARE`; they were not tested on this Windows host.

## Qualcomm AI Hub workflow commands

These commands call the real `qai_hub` SDK only when it is installed and
configured. With no SDK, credentials, target, or real source model they report
`NOT CONFIGURED`; they do not create placeholder jobs or artifacts.

```powershell
python app.py --qaihub-status
python app.py --qaihub-devices
python app.py --qaihub-compile
python app.py --qaihub-profile
python app.py --qaihub-inference
```

Configure externally:

```text
PORTAL_QAIHUB_TARGET_DEVICE=<real AI Hub device>
PORTAL_QAIHUB_RUNTIME=<supported runtime>
PORTAL_QAIHUB_MODEL=<model identifier>
PORTAL_QAIHUB_SOURCE_MODEL=<real local model artifact>
```

Generated Qualcomm metadata belongs in
`models/qualcomm/metadata.json`. Unknown fields remain `null` and unrun
operations remain `NOT RUN`.

## Layout

```text
PORTAL-XLINK/
??? app.py
??? config.py
??? requirements.txt
??? .env.example
??? README.md
??? cameras/
??? inference/
??? qaihub/
??? vision/
??? heatmap/
??? analytics/
??? database/
??? gui/
??? hardware/
??? models/
??? data/
??? logs/
??? ...
```

## Notes

- `PORTAL_INFERENCE_BACKEND=ncnn` selects local Pi inference;
  `PORTAL_INFERENCE_BACKEND=yolo` selects the PyTorch/Ultralytics backend;
  `PORTAL_INFERENCE_BACKEND=remote` selects the HTTP/JSON Pi client.
- The trained `.pt` and exported NCNN model are not included in the repository.
  Export the `.pt` on the training computer; copy the NCNN model directory to
  the Pi and configure `PORTAL_NCNN_MODEL_PATH`.
- `requirements.txt` contains desktop application dependencies;
  `requirements-pi.txt` and `requirements-training.txt` are separate install
  sets for the Pi and the training machine.
- Install the required UI dependency with `python -m pip install -r requirements.txt`.
- A local SQLite database is created on first run under `data/retail.db`.
