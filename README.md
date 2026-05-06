# AI-Based Analog Instrument Monitoring System
## Quick Start

---

### Install dependencies (once)
```bash
pip install opencv-python numpy matplotlib
```

---

### Step 1 — Generate a test gauge (if no physical gauge yet)
```bash
python generate_test_gauge.py --mode video --out gauge_video.mp4
python generate_test_gauge.py --mode image --value 75 --out gauge.jpg
```

---

### Step 2 — Run the gauge reader

**With test video (safest for demo prep):**
```bash
python gauge_reader.py --source gauge_video.mp4
```

**With webcam:**
```bash
python gauge_reader.py --source 0
```

**With static image (loops):**
```bash
python gauge_reader.py --source gauge.jpg
```

On startup, drag a rectangle around the gauge face → press SPACE.

---

### Step 3A — Test TCP without LabVIEW
```bash
# In second terminal:
python tcp_test_client.py
```
You should see timestamped value lines appear.

---

### Step 3B — Run Python fallback HMI (no LabVIEW needed)
```bash
python python_hmi.py
```
Shows live chart, anomaly alerts, saves gauge_log.csv.

---

### Step 4 — LabVIEW integration
Read `LABVIEW_GUIDE.md` for full VI block diagram and MySQL setup.

---

### Key config (top of gauge_reader.py)
```python
GAUGE_MIN_VALUE = 0      # your gauge's minimum
GAUGE_MAX_VALUE = 100    # your gauge's maximum
ANGLE_MIN_DEG   = -135   # needle angle at min (degrees, CCW from 12-o'clock)
ANGLE_MAX_DEG   =  135   # needle angle at max (degrees, CW from 12-o'clock)
TCP_PORT        = 5005   # must match LabVIEW VI
```

---

### File map
| File | Purpose |
|------|---------|
| `gauge_reader.py` | Main vision + TCP sender |
| `anomaly_detector.py` | Rolling σ detector (used by python_hmi + LabVIEW) |
| `python_hmi.py` | Fallback HMI (matplotlib, CSV log) |
| `tcp_test_client.py` | Verify TCP stream without LabVIEW |
| `generate_test_gauge.py` | Synthetic gauge images/video |
| `LABVIEW_GUIDE.md` | LabVIEW VI walkthrough + MySQL schema |
