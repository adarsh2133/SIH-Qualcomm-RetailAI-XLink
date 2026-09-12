# RetailAI Edge System

## Organized layout

```text
src/retailedge/   Edge sensors, health, metrics API, and dashboard
models/            YOLO model files
deploy/            System launcher and deployment assets
runtime/           Local runtime documentation/output location
```

The root scripts remain compatibility entrypoints. The canonical launcher is
`deploy/launch_retailedge.py`, and canonical hardware modules live under
`src/retailedge/`.

Run from the repository root:

```bash
python deploy/launch_retailedge.py --no-dashboard
```

### AI-Powered, Privacy-First Retail Intelligence on the Edge

> **Smart India Hackathon 2026 — Problem Statement ID: 26179**
> **Organization:** Qualcomm Inc.
> **Category:** Hardware
> **Theme:** Miscellaneous

---

## 📌 Problem Statement

India's retail sector includes millions of neighborhood stores, supermarkets, pharmacies, and large-format retail outlets that serve high customer volumes every day.

Retailers commonly face:

* Stock-outs and inefficient inventory monitoring
* Long billing queues
* Poor visibility into shopper behavior
* Inefficient shelf replenishment
* Merchandise shrinkage
* Limited operational analytics
* Unreliable internet connectivity, especially in Tier-2 and Tier-3 cities

Cloud-dependent AI solutions can introduce latency, bandwidth costs, privacy concerns, and operational problems during connectivity outages.

### Our Approach

**RetailAI Edge System** is an **offline-first AI-powered retail intelligence platform** that processes camera streams locally using edge computing and computer vision.

Instead of continuously sending sensitive video data to the cloud, the system performs AI inference locally and converts video into actionable retail intelligence.

---

# 🎯 Objectives

The system aims to help retailers:

* 📊 Understand shopper traffic
* 👥 Count store entries and exits
* 🗺️ Analyze customer movement and dwell time
* 📦 Monitor shelf and inventory availability
* 🚨 Detect low-stock and out-of-stock conditions
* 🛒 Monitor checkout queues
* 🔮 Predict queue congestion
* ⚡ Enable real-time edge inference
* 🔐 Preserve shopper privacy
* 🌐 Continue functioning during internet outages
* 📈 Provide actionable business analytics

---

# 🧠 Core Features

## 1. 👥 Shopper Analytics

The system analyzes customer movement inside the store.

### Capabilities

* Customer detection
* Entry and exit counting
* Footfall analytics
* Zone-wise customer distribution
* Dwell-time estimation
* Customer movement tracking
* Store heatmaps
* Time-based traffic analysis

Example metrics:

```text
Today's Footfall        : 842
Current Customers      : 37
Peak Hour              : 18:00 - 19:00
Average Dwell Time     : 7.4 min
Busiest Zone           : Beverages
```

---

## 2. 📦 Inventory Intelligence

Shelf-facing cameras can continuously monitor product availability.

### Capabilities

* Product detection
* Shelf monitoring
* Low-stock detection
* Out-of-stock detection
* Shelf compliance monitoring
* Product placement analysis
* Replenishment alerts

Example:

```text
⚠ Low Stock
Product: Coca-Cola 500ml
Shelf: A-04
Action: Replenishment Required
```

---

## 3. 🧾 Queue Intelligence

Checkout cameras monitor queues and estimate congestion.

### Capabilities

* Queue detection
* Queue length estimation
* Waiting-time estimation
* Service-time estimation
* Congestion detection
* Additional-counter recommendations

Example:

```text
Counter 1 → 8 customers
Counter 2 → 3 customers
Counter 3 → Closed

Queue Status: HIGH
Recommendation: Open Counter 3
```

---

# ⚡ Edge AI Architecture

The system follows an **Edge-First Architecture**.

```text
                    ┌─────────────────────────┐
                    │       Cameras           │
                    │                         │
                    │ Phone / IP / Pi Camera  │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │   Stream Processing     │
                    │                         │
                    │ RTSP / TCP / GStreamer  │
                    │ Compression & Decoding   │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │      Edge AI Engine     │
                    │                         │
                    │ Object Detection        │
                    │ Tracking                │
                    │ Classification          │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
              ▼                  ▼                  ▼
       ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
       │   Shopper   │    │  Inventory  │    │    Queue    │
       │  Analytics  │    │  Analytics  │    │ Intelligence│
       └──────┬──────┘    └──────┬──────┘    └──────┬──────┘
              │                  │                  │
              └──────────────────┼──────────────────┘
                                 ▼
                    ┌─────────────────────────┐
                    │   Local Data Layer     │
                    │                         │
                    │ SQLite / JSON / Status  │
                    └────────────┬────────────┘
                                 │
                                 ▼
                    ┌─────────────────────────┐
                    │    Retail Dashboard     │
                    │                         │
                    │ KPIs | Alerts | Reports │
                    └─────────────────────────┘
```

---

# 🏗️ System Architecture

RetailAI is divided into multiple functional layers.

### 1. Camera Layer

Supports multiple camera sources:

* Smartphone cameras
* Raspberry Pi cameras
* IP cameras
* Network video streams

During development, smartphones can be used as camera sources for testing.

---

### 2. Streaming Layer

The streaming layer handles:

* Camera connectivity
* Video transport
* Frame acquisition
* Video compression
* Resolution management
* Multi-camera streams

The architecture is designed to minimize unnecessary bandwidth usage.

---

### 3. Edge AI Layer

AI inference runs locally instead of continuously sending raw video to cloud servers.

Possible models include:

* YOLO-based object detection
* Qualcomm-compatible AI models
* Lightweight detection models
* Product detection models
* Person detection and tracking models

The inference layer converts video frames into structured detections.

```text
Video Frame
     │
     ▼
Object Detection
     │
     ▼
Tracking
     │
     ▼
Analytics
     │
     ▼
Business Insight
```

---

# 🔐 Privacy-First Design

RetailAI is designed around privacy-preserving analytics.

The system focuses on **anonymous detection rather than identity recognition**.

### Privacy principles

* No facial recognition required
* No customer identity storage
* No unnecessary raw-video storage
* Local inference
* Anonymous tracking IDs
* Store only required analytics
* Cloud connectivity is optional

Instead of storing:

```text
Customer Face → ❌
Customer Name → ❌
Personal Identity → ❌
```

The system stores:

```text
Person Count → ✅
Tracking ID → ✅
Zone → ✅
Dwell Time → ✅
Queue Length → ✅
Timestamp → ✅
```

---

# 💾 Local-First Data Architecture

RetailAI is designed to remain operational even when internet connectivity is unavailable.

```text
                 Internet Available?
                         │
                 ┌───────┴───────┐
                 │               │
                YES              NO
                 │               │
                 ▼               ▼
        Optional Sync      Local Processing
                 │               │
                 └───────┬───────┘
                         ▼
                  Local Database
```

### Local Storage

The system can use:

* SQLite
* JSON status files
* Local logs
* Cached analytics

Internet connectivity is therefore **not required for core AI inference**.

---

# 📊 Retail Analytics

The system converts detections into business-level KPIs.

### Shopper KPIs

| KPI          | Description                  |
| ------------ | ---------------------------- |
| Footfall     | Number of customers entering |
| Exit Count   | Number of customers leaving  |
| Occupancy    | Current customers inside     |
| Dwell Time   | Time spent in a zone         |
| Zone Traffic | Customers per store section  |
| Peak Hours   | Highest traffic periods      |

### Inventory KPIs

| KPI                  | Description              |
| -------------------- | ------------------------ |
| Available Products   | Detected products        |
| Low Stock            | Products below threshold |
| Out of Stock         | Empty product positions  |
| Shelf Compliance     | Placement correctness    |
| Replenishment Alerts | Required restocking      |

### Queue KPIs

| KPI            | Description              |
| -------------- | ------------------------ |
| Queue Length   | Customers waiting        |
| Waiting Time   | Estimated customer wait  |
| Service Time   | Checkout processing time |
| Congestion     | Current queue severity   |
| Counter Status | Open/closed counters     |

---

# 📁 Project Structure

```text
retail_edge_ai/
│
├── README.md
├── requirements.txt
├── .gitignore
│
├── raspberry_pi/
│   ├── setup_ap.sh
│   └── orchestrator.py
│
├── local_machine/
│   ├── main.py
│   ├── database.py
│   ├── inference.py
│   ├── stream_manager.py
│   ├── start_all_cameras.py
│   │
│   └── analytics/
│       ├── entryCount.py
│       ├── queue.py
│       ├── inventory.py
│       ├── dwell_time.py
│       ├── heatmap.py
│       └── visibility_monetization.py
│
├── dashboard/
│   └── app.py
│
├── models/
│   └── README.md
│
├── data/
│   ├── database/
│   ├── logs/
│   └── status/
│
└── tests/
    ├── test_inference.py
    ├── test_stream.py
    └── test_analytics.py
```

---

# 🔄 End-to-End Workflow

```text
Camera
  │
  ▼
Video Stream
  │
  ▼
Frame Compression
  │
  ▼
Frame Decoder
  │
  ▼
AI Inference
  │
  ▼
Object Detection
  │
  ▼
Object Tracking
  │
  ├──────────────┐
  │              │
  ▼              ▼
Person         Product
Analytics      Analytics
  │              │
  ▼              ▼
Entry/Exit     Inventory
Queue          Shelf
Dwell          Stock
Heatmap
  │              │
  └───────┬──────┘
          ▼
     Local Database
          │
          ▼
       Dashboard
          │
          ▼
     Business Alerts
```

---

# 🖥️ Dashboard

The dashboard provides real-time visibility into store operations.

### Dashboard Sections

```text
┌──────────────────────────────────────────────┐
│             RETAILAI DASHBOARD               │
├──────────────┬──────────────┬────────────────┤
│   Footfall   │   Occupancy  │ Queue Status   │
│     842      │      37      │     HIGH       │
├──────────────┼──────────────┼────────────────┤
│ Inventory    │ Low Stock    │ Out of Stock   │
│    1,248     │      17      │       5        │
├──────────────┴──────────────┴────────────────┤
│              Store Heatmap                   │
│                                              │
│        █████████████████                     │
│        ███ Customer █████                    │
│        █████ Traffic ████                    │
│                                              │
├──────────────────────────────────────────────┤
│               Alerts                         │
│ ⚠ Queue congestion detected                 │
│ ⚠ 5 products out of stock                   │
│ ⚠ Replenishment required                    │
└──────────────────────────────────────────────┘
```

---

# 🧰 Technology Stack

### AI / Computer Vision

* Python
* OpenCV
* PyTorch
* Ultralytics YOLO
* Qualcomm-compatible AI models
* Object tracking

### Edge Hardware

* Raspberry Pi
* Raspberry Pi Camera
* Smartphone cameras for prototyping
* Qualcomm edge AI hardware for deployment

### Streaming

* GStreamer
* RTSP
* TCP/IP
* OpenCV VideoCapture

### Backend

* Python
* SQLite
* JSON
* REST/API-ready architecture

### Dashboard

* Streamlit
* Jupyter-based visualization

---

# 🚀 Installation

Clone the repository:

```bash
git clone <repository-url>
cd retail_edge_ai
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Windows:

```bash
.venv\Scripts\activate
```

Activate it on Linux/Raspberry Pi:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

# ▶️ Running the System

Start the camera streams:

```bash
python local_machine/start_all_cameras.py
```

Start the main processing pipeline:

```bash
python local_machine/main.py
```

Start the dashboard:

```bash
streamlit run dashboard/app.py
```

---

# 📱 Camera Testing Without Dedicated Hardware

During development, a smartphone can be used as a temporary camera source.

```text
Smartphone
    │
    │ Local Network
    ▼
Streaming Endpoint
    │
    ▼
Laptop / Edge Device
    │
    ▼
RetailAI Pipeline
```

This allows the complete software pipeline to be tested before deploying dedicated Raspberry Pi cameras.

---

# 🥧 Raspberry Pi Deployment

The Raspberry Pi can act as an edge gateway for camera connectivity and local communication.

```text
                Raspberry Pi
              ┌──────────────┐
Camera ──────►│              │
              │ Edge Gateway │────► Local AI System
Camera ──────►│              │
              └──────────────┘
```

The system can also be configured to create a local access point for communication between cameras, edge devices, and the processing system.

---

# 🌐 Offline Operation

RetailAI does not depend on continuous cloud connectivity.

### When Internet Is Available

```text
Local AI
   │
   ├──► Dashboard
   ├──► Local Database
   └──► Optional Cloud Sync
```

### When Internet Is Unavailable

```text
Camera
   │
   ▼
Local AI
   │
   ▼
Local Database
   │
   ▼
Dashboard
```

Core analytics continue to operate locally.

---

# ⚡ Why Edge AI?

| Cloud-Only AI                      | RetailAI Edge AI         |
| ---------------------------------- | ------------------------ |
| Requires continuous connectivity   | Offline capable          |
| High bandwidth usage               | Reduced bandwidth        |
| Higher network latency             | Low latency              |
| Raw video may leave store          | Local processing         |
| Cloud dependency                   | Edge-first               |
| Connectivity outages affect system | Continues locally        |
| Recurring cloud processing cost    | Reduced cloud dependency |

---

# 💡 Business Impact

RetailAI converts raw camera feeds into operational decisions.

### Before

```text
Camera
   ↓
Video
   ↓
Manual Monitoring
   ↓
Delayed Action
```

### With RetailAI

```text
Camera
   ↓
Edge AI
   ↓
Analytics
   ↓
Alert
   ↓
Immediate Action
```

### Example

```text
Shelf Camera
     ↓
Product Detection
     ↓
Stock Level Analysis
     ↓
Low Stock Detected
     ↓
Staff Alert
     ↓
Shelf Replenished
     ↓
Reduced Stock-out
```

---

# 📈 Scalability

The architecture is designed to scale from a small neighborhood store to multi-location retail chains.

```text
                 Central Analytics
                       │
          ┌────────────┼────────────┐
          │            │            │
       Store A       Store B      Store C
          │            │            │
       Edge AI      Edge AI      Edge AI
          │            │            │
       Cameras      Cameras      Cameras
```

Possible integrations:

* POS systems
* Inventory Management Systems
* ERP systems
* Centralized store monitoring
* Optional cloud synchronization

---

# 🔮 Future Scope

Potential future improvements include:

* Advanced product recognition
* Automated replenishment prediction
* Sales forecasting
* Demand prediction
* Staff allocation optimization
* POS integration
* ERP integration
* Multi-store centralized analytics
* Qualcomm hardware acceleration
* Federated learning
* Advanced edge model optimization
* Automated business recommendations

---

# 🏆 SIH 2026 Alignment

**Problem Statement:** 26179
**Organization:** Qualcomm Inc.
**Category:** Hardware

RetailAI directly addresses the requirements of the problem statement through:

| Requirement          | RetailAI Implementation                          |
| -------------------- | ------------------------------------------------ |
| Shopper Analytics    | Person detection, tracking, footfall, dwell time |
| Inventory Monitoring | Shelf/product detection and stock alerts         |
| Queue Intelligence   | Queue detection and congestion analytics         |
| Edge AI              | Local inference                                  |
| Privacy              | Anonymous analytics                              |
| Offline Operation    | Local-first architecture                         |
| Dashboard            | Real-time KPI visualization                      |
| Scalability          | Multi-camera and multi-store architecture        |
| Hardware             | Edge device + camera-based deployment            |

---
# 👥 Team XLink

### RetailAI Edge System — SIH 2026

| Team Member                 |
| --------------------------- |
| **Adarsh Kumar Sharma**     |
| **Lavanya Saini**           |
| **Sarvendra Mani Tripathi** |
| **Deepali Raj**             |
| **Charu Mittal**            |
| **Aniket Pal**              |

**Problem Statement:** 26179
**Organization:** Qualcomm Inc.
**Category:** Hardware
**Theme:** Miscellaneous

---
# 📜 License

This project is developed as a prototype for **Smart India Hackathon 2026** and research/development purposes.

---

## 🚀 Vision


XLink aims to transform conventional retail cameras into an intelligent, privacy-preserving operational system that helps retailers make faster and better decisions without depending on continuous cloud connectivity.
