# Retail AI Software — Backend, Analytics, Storage, Dashboards

The software side of an SIH retail-intelligence project: real-time shopper
analytics, inventory visibility, and queue management, designed to run
entirely offline/local (no cloud dependency).

This repo covers analytics, storage, alerts, a CustomTkinter BI dashboard, and
a PySide6 live control room — all built and tested against mock
video/inference/tracking, so it runs completely standalone right now, with
clean seams for the hardware/AI team's real camera stream and Qualcomm
Detectron2 inference engine to plug in later without any of this code
changing.

## Prerequisites

- Python 3.11 or newer
- Git
  runs locally with SQLite.

### Verify what you have

```powershell
python --version
python -m pip --version
python -c "import venv; print('venv module OK')"
git --version
```

All four should return a version number (Python 3.11+) or `venv module OK`
with no errors. If anything's missing, install it with the commands below.

### Install anything missing (Windows, via winget)

`winget` comes built into Windows 10/11 — these install straight from the
terminal, no browser needed:

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Git.Git
```

**Close and reopen your terminal after installing** — PATH changes from a
fresh install don't apply to an already-open terminal window. Then re-run
the verify commands above to confirm.

If `winget` itself isn't recognized, it ships with the "App Installer"
package from the Microsoft Store — install that first, or fall back to
downloading manually from python.org/downloads (check **"Add python.exe to
PATH"** during install) and git-scm.com/download/win.

Once installed, bring pip itself up to date (avoids occasional install
failures from an outdated resolver):

```powershell
python -m pip install --upgrade pip
```

**Note on the PySide6 control room:** it needs an actual display to open a
window — not a concern on a normal desktop/laptop, but it won't run
headless (e.g. over SSH) without extra configuration.

## Setup

```bash
git clone <repo-url>
cd retail-ai-software

python -m venv venv
```

Activate it:

```bash
# Windows (PowerShell)
venv\Scripts\Activate.ps1

# macOS/Linux
source venv/bin/activate
```

If PowerShell blocks the activation script:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Install dependencies:

```bash
pip install -r requirements.txt
```

## Run StoreSense

The unified launcher coordinates the existing edge launcher, JSON bridge,
SQLite storage, and software dashboard. It uses `.runtime-dev` by default so
development runs do not write into the hardware repository's runtime folder.

```powershell
python start_storesense.py --no-hardware
```

For a complete local run without physical cameras, use the development
runtime simulator. It writes the same runtime JSON files as the hardware
services, so the existing bridge, database, API, and dashboard receive real
application data through the normal path:

```powershell
python start_storesense.py --dev-mode --no-hardware
```

The primary dashboard is a native CustomTkinter window. It does not have a
browser URL; the launcher reports `DASHBOARD READY` when its process is alive.
The API is available separately at `http://127.0.0.1:8080/health` and
`http://127.0.0.1:8080/api/metrics`.

For live RTSP and YOLO processing, install the optional live dependencies:

```powershell
pip install -r requirements-live.txt
python start_storesense.py --no-hardware --live-ai
```

Camera URLs are environment-driven. For the four-phone setup, copy
`.env.example` to `.env` on the Ubuntu server, then start MediaMTX:

```bash
docker compose -f deploy/mediamtx/docker-compose.yml up -d
```

With the MediaMTX workflow, use an RTMP broadcaster on each phone and publish
to these server paths:

```text
rtmp://<server-lan-ip>:1935/entry-cam
rtmp://<server-lan-ip>:1935/queue-cam-1
rtmp://<server-lan-ip>:1935/queue-cam-2
rtmp://<server-lan-ip>:1935/shelf-cam-1
```

An RTSP viewer such as OctoStream cannot publish the phone camera. The server
then reads each active path locally through RTSP on port 8554.

The server app then reads them locally with:

```powershell
$env:STORESENSE_CAMERA_IDS = "entry-cam,queue-cam-1,queue-cam-2,shelf-cam-1"
$env:STORESENSE_RTSP_BASE_URL = "rtsp://127.0.0.1:8554"
$env:STORESENSE_MODEL_PATH = "yolo11n.pt"
python scripts/check_live_cameras.py
python start_storesense.py --no-hardware --live-ai
```

If your phone app exposes direct HTTP/MJPEG/RTSP URLs instead of publishing
to MediaMTX, set `STORESENSE_RTSP_URL_ENTRY_CAM`,
`STORESENSE_RTSP_URL_QUEUE_CAM_1`, `STORESENSE_RTSP_URL_QUEUE_CAM_2`, and
`STORESENSE_RTSP_URL_SHELF_CAM_1` in `.env`. OpenCV accepts those stream URLs
through the same live adapter.

The StoreSense API is available at `/health` and `/api/metrics` on port 8080
by default. Set `STORESENSE_API_HOST` and `STORESENSE_API_PORT` to change it.
The server architecture and Raspberry Pi queue contract are documented in
[`docs/server-architecture.md`](docs/server-architecture.md). For the ASUS
ExpertBook LAN deployment, bind the API to `0.0.0.0` and set the actual phone,
MediaMTX, and gateway addresses in `.env`; no phone, Pi, or ESP32 address is
assumed by the application.

For the real hardware runtime, configure the existing paths instead of
hardcoding machine-specific values:

```powershell
$env:STORESENSE_HARDWARE_ROOT = "<hardware-repository>"
$env:RETAIL_EDGE_RUNTIME_DIR = "<shared-runtime-directory>"
python start_storesense.py
```

Press `Ctrl+C` to stop only the processes started by StoreSense.

## Verify it works

```bash
pytest tests/ -v
```

Expected: **92+ passed**. This includes tests proving the single-writer/WAL
SQLite design is genuinely enforced (not just documented), the alert
cooldown mechanism actually suppresses repeat alerts, and the PySide6
control room genuinely receives live data from its background thread —
not just that things import without errors.

## Run it — existing component commands

All three read/write the same local SQLite file (`data/retail_ai.db`,
created automatically on first run — nothing to set up manually).

**Terminal 1 — continuous demo data generator:**

```bash
python -m simulation.demo_mode --seed 42
```

Leave running. Simulates all 6 cameras (3 shelf, entrance, 2 queue) with
varying footfall and occasional queue spikes, so there's always live data
to look at.

**Terminal 2 — CustomTkinter BI dashboard:**

```bash
python -m dashboard.app
```

Opens a native desktop window with 7 pages: overview, traffic, occupancy,
queue, shelf, alerts, and reports.

**Terminal 3 — PySide6 live control room:**

```bash
python -m control_room.main
```

A desktop window with live KPIs and an active-alerts list, updating every
~2 seconds, with an audio beep on new critical alerts.

Remember to activate the venv (`venv\Scripts\Activate.ps1` /
`source venv/bin/activate`) in each new terminal — it's the same one
environment, just needs activating per terminal session.

## Project structure and architecture

```
core/          # Pydantic data contracts (Frame, Detection, Track, Event, Alert, ...)
interfaces/    # Protocol definitions — the seams hardware plugs into
adapters/      # Mock implementations now; real GStreamer/Qualcomm adapters plug in later
analytics/     # Pure Python business logic — people counting, entry/exit, occupancy,
               # queue, shelf, visibility, monetization, event engine
alerts/        # Alert manager with cooldown
storage/       # SQLAlchemy + SQLite, single-writer/WAL enforced, Alembic migrations
services/      # Orchestration layer — the only thing UIs/pipeline call directly
pipeline/      # The real-time loop (currently driven by mock adapters)
file_management/  # Export/report file handling
dashboard/     # CustomTkinter BI dashboard
control_room/  # PySide6 live desktop view
simulation/    # Demo data generator
tests/         # 79 tests — unit (pure logic, no I/O) + integration (full chains)
```

**Core rule this whole codebase follows:** `interfaces/` defines contracts,
`adapters/` implements them, and nothing outside `adapters/` ever knows
which concrete implementation it's talking to. This is what lets the
hardware/AI team's real `GStreamerVideoSource` and
`QualcommInferenceEngine` get built independently and plug in later
without touching `analytics/`, `storage/`, `services/`, `control_room/`,
or `dashboard/` at all.

**Zero cloud dependency, by design:** SQLite is local, the event bus is
in-process (RabbitMQ — self-hosted only when it's wired in later), and
Streamlit/PySide6 both run purely on your own machine. Nothing here talks
to the internet at runtime.

## Team split

- **Software side (this repo):** backend, database, analytics, alerts,
  both dashboards — built here
  GStreamer streaming, Qualcomm Detectron2 inference, object tracking

## Optional: Alembic migrations

The schema is stable, but Alembic is set up for when it needs to change:

```bash
# after editing storage/models.py
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```
