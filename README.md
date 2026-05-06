# AI-Based Analog Instrument Monitoring System

A computer-vision pipeline that reads analog gauge instruments in real time, streams the extracted values over TCP, detects anomalies using a rolling statistical model, and displays live data through either a Python HMI or a LabVIEW VI — with optional MySQL logging.

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage](#usage)
  - [Step 1 — Generate a Test Gauge](#step-1--generate-a-test-gauge)
  - [Step 2 — Run the Gauge Reader](#step-2--run-the-gauge-reader)
  - [Step 3A — Verify TCP Stream](#step-3a--verify-tcp-stream)
  - [Step 3B — Python Fallback HMI](#step-3b--python-fallback-hmi)
  - [Step 4 — LabVIEW Integration](#step-4--labview-integration)
- [Configuration](#configuration)
- [File Reference](#file-reference)
- [TCP Data Protocol](#tcp-data-protocol)
- [Anomaly Detection](#anomaly-detection)
- [LabVIEW VI Architecture](#labview-vi-architecture)
- [MySQL Schema](#mysql-schema)
- [Demo Tips](#demo-tips)

---

## Overview

This system bridges the physical and digital worlds for legacy analog instrumentation. A camera captures a live feed of an analog gauge, computer vision extracts the needle angle and maps it to a real-world value, and that value is broadcast over a TCP socket so any downstream consumer — LabVIEW, a Python dashboard, or any network-connected client — can receive and act on it in near real time.

**Key capabilities:**

- Camera-based needle detection using OpenCV (no hardware modification to the gauge)
- Configurable gauge range and needle arc to support any dial layout
- Real-time anomaly detection via rolling mean ± 3σ
- Dual display path: LabVIEW VI (primary) or Python matplotlib HMI (fallback)
- Persistent logging to MySQL (LabVIEW path) or CSV (Python path)
- Synthetic test-gauge generator for development and demos without physical hardware

---

## System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Physical Layer                        │
│          Analog Gauge  ←──  Camera / Webcam             │
└───────────────────────────┬─────────────────────────────┘
                            │  video frames
                            ▼
┌─────────────────────────────────────────────────────────┐
│                  gauge_reader.py                         │
│  ┌─────────────────┐    ┌──────────────────────────┐    │
│  │ ROI Selection   │───▶│ Needle Angle Detection   │    │
│  │ (drag & SPACE)  │    │ (OpenCV Hough / contour) │    │
│  └─────────────────┘    └────────────┬─────────────┘    │
│                                      │ angle → value    │
│                                      ▼                  │
│                         ┌────────────────────────┐      │
│                         │  TCP Server  :5005     │      │
│                         │  JSON stream per frame │      │
│                         └──────────┬─────────────┘      │
└────────────────────────────────────┼────────────────────┘
                                     │
              ┌──────────────────────┼──────────────────────┐
              │                      │                       │
              ▼                      ▼                       ▼
  ┌─────────────────┐   ┌────────────────────┐   ┌──────────────────┐
  │ tcp_test_client │   │   python_hmi.py    │   │  LabVIEW Main.vi │
  │   (debug)       │   │  matplotlib chart  │   │  TCP Receiver    │
  └─────────────────┘   │  CSV log           │   │  Anomaly SubVI   │
                        │  anomaly alerts    │   │  MySQL Logger    │
                        └────────────────────┘   │  Front Panel     │
                                                 └──────────────────┘
```

---

## Requirements

### Python

| Package | Purpose |
|---------|---------|
| `opencv-python` | Gauge frame capture and needle detection |
| `numpy` | Numerical operations and angle mapping |
| `matplotlib` | Python HMI live chart (`python_hmi.py`) |

Python 3.8 or later is recommended.

### LabVIEW (optional — for VI path)

- LabVIEW 2019 or later
- **NI Database Connectivity Toolkit** (for MySQL logging)
- **JSON VI** built into LabVIEW 2016+ (`Unflatten from JSON`)

### MySQL (optional — for database logging)

- MySQL 5.7+ or MariaDB 10.3+
- An ODBC DSN named `GaugeDB` configured on the LabVIEW host

---

## Installation

```bash
# 1. Clone the repository
git clone https://github.com/Ashika005/AI-based-Analog-Instrument-Monitoring-System.git
cd AI-based-Analog-Instrument-Monitoring-System

# 2. Install Python dependencies
pip install opencv-python numpy matplotlib
```

No additional build steps are required. All Python scripts are self-contained.

---

## Quick Start

```bash
# Generate a test video (no physical gauge needed)
python generate_test_gauge.py --mode video --out gauge_video.mp4

# Run the gauge reader against the test video
python gauge_reader.py --source gauge_video.mp4

# In a second terminal — verify TCP data is flowing
python tcp_test_client.py

# Or launch the full Python HMI instead
python python_hmi.py
```

---

## Usage

### Step 1 — Generate a Test Gauge

Use `generate_test_gauge.py` to create synthetic gauge media when no physical camera is available. The generated gauge mirrors the same arc parameters as `gauge_reader.py`.

**Static image at a specific value:**
```bash
python generate_test_gauge.py --mode image --value 75 --out gauge.jpg
```

**20-second sine-sweep video (loops smoothly for demos):**
```bash
python generate_test_gauge.py --mode video --out gauge_video.mp4
```

| Argument | Default | Description |
|----------|---------|-------------|
| `--mode` | `image` | `image` or `video` |
| `--value` | `60.0` | Needle value for static image |
| `--out` | `gauge.jpg` / `gauge_video.mp4` | Output filename |

---

### Step 2 — Run the Gauge Reader

`gauge_reader.py` opens the video source, starts a TCP server on port 5005, and broadcasts JSON readings.

**From test video:**
```bash
python gauge_reader.py --source gauge_video.mp4
```

**From webcam (device index 0):**
```bash
python gauge_reader.py --source 0
```

**From a static image (loops):**
```bash
python gauge_reader.py --source gauge.jpg
```

On first launch, draw a rectangle around the gauge face and press **SPACE** to confirm the region of interest (ROI). The reader uses this crop for all subsequent frames.

---

### Step 3A — Verify TCP Stream

Run `tcp_test_client.py` in a second terminal to confirm that `gauge_reader.py` is streaming correctly before connecting LabVIEW.

```bash
python tcp_test_client.py
# Optional flags:
python tcp_test_client.py --host 127.0.0.1 --port 5005
```

Expected output:
```
Connected! Receiving readings:

  [14:32:01]  value = 62.418
  [14:32:01]  value = 63.005
  [14:32:02]  value = 64.112
  ...
```

If you see `Connection refused`, `gauge_reader.py` is not yet running or is using a different port.

---

### Step 3B — Python Fallback HMI

`python_hmi.py` is a full standalone HMI that requires no LabVIEW installation. It connects to the same TCP port, runs the anomaly detector, renders a live matplotlib chart, and writes every reading to `gauge_log.csv`.

```bash
python python_hmi.py
```

**What it shows:**

- Live value trend (blue line)
- Rolling mean (dashed green)
- ±3σ bands (dotted red)
- Anomaly markers (red dots on chart)
- Status bar: current value + normal / anomaly flag

**CSV log columns:** `timestamp, value, mean, std, upper, lower, anomaly`

> **Note:** `python_hmi.py` uses the `TkAgg` matplotlib backend by default. If Tk is unavailable on your system, change `matplotlib.use("TkAgg")` to `"Qt5Agg"` at the top of the file.

---

### Step 4 — LabVIEW Integration

See [`LABVIEW_GUIDE.md`](LABVIEW_GUIDE.md) for the full block diagram walkthrough, JSON parsing instructions, MySQL subVI setup, anomaly detection subVI, and a demo-day checklist.

**High-level flow:**

```
TCP Receive → Parse JSON → Display → Anomaly SubVI → MySQL Log
```

---

## Configuration

All key parameters live at the top of `gauge_reader.py`:

```python
GAUGE_MIN_VALUE = 0       # Physical minimum of the gauge scale
GAUGE_MAX_VALUE = 100     # Physical maximum of the gauge scale
ANGLE_MIN_DEG   = -135    # Needle angle (degrees) at minimum value
                          # Negative = counter-clockwise from 12 o'clock
ANGLE_MAX_DEG   =  135    # Needle angle (degrees) at maximum value
TCP_PORT        = 5005    # Must match LabVIEW VI and python_hmi.py
```

The same `GAUGE_MIN_VALUE`, `GAUGE_MAX_VALUE`, `ANGLE_MIN_DEG`, and `ANGLE_MAX_DEG` constants are mirrored in `generate_test_gauge.py`. If you change the gauge range, update both files.

---

## File Reference

| File | Role |
|------|------|
| `gauge_reader.py` | Main vision pipeline — frame capture, needle detection, TCP server |
| `anomaly_detector.py` | Rolling σ detector — shared by `python_hmi.py` and LabVIEW |
| `python_hmi.py` | Fallback HMI — live matplotlib chart, anomaly alerts, CSV logging |
| `tcp_test_client.py` | Debug TCP consumer — prints raw JSON stream to terminal |
| `generate_test_gauge.py` | Synthetic gauge generator — static images and sweep videos |
| `model.vi` | LabVIEW VI — main front panel and block diagram |
| `LABVIEW_GUIDE.md` | LabVIEW integration guide — VI walkthrough and MySQL schema |

---

## TCP Data Protocol

`gauge_reader.py` acts as a TCP **server**. Clients connect to it (not the other way around). Each reading is sent as a newline-terminated JSON object:

```json
{"value": 63.418, "timestamp": 1746518721.043}
```

| Field | Type | Description |
|-------|------|-------------|
| `value` | `float` | Mapped gauge reading in engineering units |
| `timestamp` | `float` | Unix epoch seconds (UTC) |

Messages are delimited by `\n`. Receivers should buffer and split on newline. See `tcp_test_client.py` and `python_hmi.py` for reference implementations of the receive loop.

---

## Anomaly Detection

`anomaly_detector.py` implements a **rolling mean ± N·σ** detector. It is used identically by both `python_hmi.py` and the LabVIEW anomaly subVI.

**Algorithm:**

1. Maintain a sliding window of the last *W* readings (default W = 30).
2. Compute window mean (μ) and standard deviation (σ).
3. A new value is flagged as an anomaly if it falls outside [μ − 3σ, μ + 3σ].
4. A configurable warmup period (default 5 samples) suppresses false positives while the window fills.

**Constructor parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `window` | `30` | Number of historical samples to retain |
| `n_sigma` | `3.0` | Threshold multiplier |
| `warmup` | `5` | Samples before anomaly detection activates |

**`update(value)` return dict:**

```python
{
    "value":   63.4,
    "mean":    60.1,
    "std":     2.3,
    "upper":   67.0,
    "lower":   53.2,
    "anomaly": False,
    "severity": 0.0   # |value - mean| / std
}
```

---

## LabVIEW VI Architecture

```
Main.vi
├── TCPReceiver.vi       — loops, outputs value + timestamp each iteration
├── AnomalyDetector.vi   — subVI with shift-register history array
├── MySQLLogger.vi       — subVI, inserts one row per iteration
└── Front Panel
    ├── Waveform Chart   — 4 plots: value, mean, +3σ, -3σ
    ├── Numeric          — large current-value indicator
    ├── Boolean LED      — red when anomaly = TRUE
    ├── String           — last anomaly timestamp
    └── Stop Button
```

For the complete block diagram pseudocode, JSON parsing tips, and MySQL connection string, see [`LABVIEW_GUIDE.md`](LABVIEW_GUIDE.md).

---

## MySQL Schema

Run the following once in MySQL Workbench or a terminal before starting the LabVIEW VI:

```sql
CREATE DATABASE IF NOT EXISTS gauge_monitor;
USE gauge_monitor;

CREATE TABLE IF NOT EXISTS readings (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    ts        DATETIME NOT NULL,
    value     DOUBLE NOT NULL,
    anomaly   TINYINT DEFAULT 0
);
```

The LabVIEW `MySQLLogger.vi` inserts one row per TCP reading using the NI Database Connectivity Toolkit. Ensure an ODBC DSN named `GaugeDB` pointing to this database is configured on the LabVIEW host machine.

---

## Demo Tips

- **No camera / bad lighting?** Use the pre-generated test video:
  ```bash
  python gauge_reader.py --source gauge_video.mp4
  ```
- **No LabVIEW?** Keep `python_hmi.py` running as the primary display — it is functionally equivalent for demo purposes.
- **Show logging evidence** — open `gauge_log.csv` to demonstrate that every reading is persisted, even without MySQL.
- **Pre-populate MySQL** — insert 50–100 rows before the demo so the LabVIEW waveform chart shows a rich trend on launch.
- **Trigger an anomaly on demand** — partially cover the gauge lens to cause a sharp value spike; the anomaly LED and `python_hmi.py` alert will fire within seconds.
- **Run the testing checklist** (from `LABVIEW_GUIDE.md`):
  - [ ] Start MySQL service
  - [ ] `python gauge_reader.py --source gauge_video.mp4`
  - [ ] `python tcp_test_client.py` — confirm JSON lines appear
  - [ ] Open `Main.vi` in LabVIEW and run it
  - [ ] Confirm value updates on chart
  - [ ] `SELECT * FROM readings ORDER BY id DESC LIMIT 10;`
  - [ ] Cover gauge partially to trigger anomaly LED

---

## License

This project is intended for academic and educational use.
