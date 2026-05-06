"""
python_hmi.py  (FALLBACK / DEMO TOOL)
---------------------------------------
Pure-Python HMI that receives TCP readings from gauge_reader.py,
displays a live trend, logs to CSV (instead of MySQL), and shows anomaly alerts.

Use this if:
 - You want to demo WITHOUT LabVIEW during testing
 - LabVIEW Database Toolkit is not installed yet
 - Quick end-to-end sanity check

Requires:  pip install matplotlib --break-system-packages
"""

import socket
import json
import threading
import queue
import time
import csv
import os
from datetime import datetime
from collections import deque

# ── Import matplotlib (headless-safe) ──
import matplotlib
matplotlib.use("TkAgg")          # change to "Qt5Agg" if TkAgg not available
import matplotlib.pyplot as plt
import matplotlib.animation as animation

from anomaly_detector import AnomalyDetector  # now correctly defined in anomaly_detector.py

# ── Config ──
TCP_HOST   = "127.0.0.1"
TCP_PORT   = 5005
LOG_FILE   = "gauge_log.csv"
WINDOW     = 60    # samples shown in chart
AD_WINDOW  = 30    # anomaly detector history

# ── Shared state ──
data_q   = queue.Queue()
readings = deque(maxlen=WINDOW)
times    = deque(maxlen=WINDOW)
detector = AnomalyDetector(window=AD_WINDOW, n_sigma=3.0, warmup=5)
anomalies = []   # list of (unix_timestamp, value)


# ── CSV logger ──
def init_csv():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(
                ["timestamp", "value", "mean", "std", "upper", "lower", "anomaly"])

def log_csv(ts, result):
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            ts,
            result["value"],
            result.get("mean",  ""),
            result.get("std",   ""),
            result.get("upper", ""),
            result.get("lower", ""),
            result["anomaly"],
        ])


# ── TCP receiver thread ──
def tcp_receiver():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((TCP_HOST, TCP_PORT))
            print(f"[HMI] Connected to gauge_reader at {TCP_HOST}:{TCP_PORT}")
            buf = ""
            while True:
                chunk = s.recv(1024).decode()
                if not chunk:
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    try:
                        data_q.put_nowait(json.loads(line))
                    except Exception:
                        pass
        except Exception as e:
            print(f"[HMI] TCP error: {e}. Reconnecting in 2 s …")
            time.sleep(2)
        finally:
            try:
                s.close()
            except Exception:
                pass


# ── Matplotlib live chart ──
fig, (ax_trend, ax_info) = plt.subplots(
    2, 1, figsize=(10, 6),
    gridspec_kw={"height_ratios": [4, 1]}
)
fig.patch.set_facecolor("#1e1e2e")
for ax in (ax_trend, ax_info):
    ax.set_facecolor("#1e1e2e")

line_val,  = ax_trend.plot([], [], color="#4fc3f7", lw=2,  label="Value")
line_mean, = ax_trend.plot([], [], color="#a5d6a7", lw=1,  label="Mean",  linestyle="--")
line_up,   = ax_trend.plot([], [], color="#ef9a9a", lw=1,  label="+3σ",   linestyle=":")
line_lo,   = ax_trend.plot([], [], color="#ef9a9a", lw=1,  label="-3σ",   linestyle=":")
scat_anom  = ax_trend.scatter([], [], color="red", zorder=5, s=60, label="Anomaly")

ax_trend.set_ylim(-5, 110)
ax_trend.set_xlim(0, WINDOW)
ax_trend.set_xlabel("Sample", color="white")
ax_trend.set_ylabel("Gauge Value", color="white")
ax_trend.tick_params(colors="white")
ax_trend.legend(loc="upper left", facecolor="#2d2d3f", labelcolor="white", fontsize=8)
ax_trend.set_title("Gauge Monitor — Live Trend", color="white", fontsize=13)
for spine in ax_trend.spines.values():
    spine.set_edgecolor("#444466")

status_text = ax_info.text(0.5, 0.5, "Waiting for data …",
                           ha="center", va="center",
                           fontsize=14, color="white",
                           transform=ax_info.transAxes)
ax_info.set_xticks([]); ax_info.set_yticks([])
for spine in ax_info.spines.values():
    spine.set_visible(False)

plt.tight_layout()

anom_x, anom_y = [], []

def animate(frame):
    # Drain queue
    changed = False
    while not data_q.empty():
        pkt    = data_q.get_nowait()
        val    = pkt["value"]
        ts     = datetime.fromtimestamp(pkt["timestamp"]).strftime("%H:%M:%S")
        result = detector.update(val)
        log_csv(ts, result)

        readings.append(val)
        times.append(len(readings))

        if result["anomaly"]:
            anomalies.append((time.time(), val))
            anom_x.append(len(readings) - 1)
            anom_y.append(val)
            print(f"[⚠ ANOMALY]  {ts}  value={val:.2f}  σ={result['severity']}")

        changed = True

    if not changed:
        return

    xs = list(range(len(readings)))
    ys = list(readings)

    line_val.set_data(xs, ys)

    if result.get("mean") is not None and len(ys) >= 2:
        import statistics
        m = result["mean"]
        s = result["std"] if result["std"] else 0
        flat_m  = [m]        * len(xs)
        flat_up = [m + 3*s]  * len(xs)
        flat_lo = [m - 3*s]  * len(xs)
        line_mean.set_data(xs, flat_m)
        line_up.set_data(xs, flat_up)
        line_lo.set_data(xs, flat_lo)

    # Anomaly scatter
    vis_x = [x for x in anom_x if x >= len(readings) - WINDOW]
    vis_y = [anom_y[i] for i, x in enumerate(anom_x) if x >= len(readings) - WINDOW]
    scat_anom.set_offsets(list(zip(vis_x, vis_y)) if vis_x else [[]])

    ax_trend.set_xlim(max(0, len(readings) - WINDOW), max(WINDOW, len(readings)))

    # Status bar
    last_val = ys[-1] if ys else 0
    anom_flag = "⚠  ANOMALY DETECTED" if (anomalies and
                (time.time() - anomalies[-1][0]) < 5) else "✓  Normal"
    color = "red" if "ANOMALY" in anom_flag else "#a5d6a7"
    status_text.set_text(f"Latest: {last_val:.2f}   |   {anom_flag}")
    status_text.set_color(color)

    return line_val, line_mean, line_up, line_lo, scat_anom, status_text


def main():
    init_csv()
    print(f"[HMI] Logging to {LOG_FILE}")
    t = threading.Thread(target=tcp_receiver, daemon=True)
    t.start()

    ani = animation.FuncAnimation(fig, animate, interval=500, blit=False)
    plt.show()
    print(f"[HMI] Closed. Log saved to {LOG_FILE}")


if __name__ == "__main__":
    main()
