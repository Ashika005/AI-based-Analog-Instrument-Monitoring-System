"""
gauge_reader.py — FINAL VERSION
=================================
AI-Based Analog Instrument Monitoring System
Fixes all critical issues from v1:
  ✅ Threaded TCP server (camera never freezes)
  ✅ HSV color-based red needle detection
  ✅ Correct 12-o'clock angle reference
  ✅ Rolling average smoothing
  ✅ ROI selection
  ✅ ntfy mobile push notifications
  ✅ 3-sigma anomaly detection integrated
  ✅ CSV data logging
  ✅ Command-line arguments (no hardcoded paths)

Usage:
  python gauge_reader.py --source 0               # webcam
  python gauge_reader.py --source gauge_video.mp4 # video file
  python gauge_reader.py --source 0 --ntfy YOUR_TOPIC
"""

import cv2
import numpy as np
import socket
import threading
import queue
import math
import time
import csv
import os
import argparse
import sys
import urllib.request
import urllib.parse
from collections import deque
from datetime import datetime

# ════════════════════════════════════════════
# CONFIGURATION — edit these for your gauge
# ════════════════════════════════════════════
GAUGE_MIN_VALUE = 0      # physical minimum
GAUGE_MAX_VALUE = 100    # physical maximum
ANGLE_MIN_DEG   = -135   # needle angle at min (from 12-o'clock, CCW)
ANGLE_MAX_DEG   =  135   # needle angle at max (from 12-o'clock, CW)

TCP_HOST        = "0.0.0.0"
TCP_PORT        = 5005
READ_FPS        = 2
SMOOTH_WINDOW   = 5      # rolling average window
ANOMALY_WINDOW  = 30     # sigma detection window
ANOMALY_SIGMA   = 2.0    # standard deviations threshold
LOG_FILE        = "gauge_log.csv"

# ntfy config — set your topic name
NTFY_TOPIC      = "viproject2026"  # override with --ntfy flag
NTFY_SERVER     = "https://ntfy.sh"
NTFY_COOLDOWN   = 10    # seconds between repeat alerts


# ════════════════════════════════════════════
# MOBILE NOTIFICATION (ntfy.sh)
# ════════════════════════════════════════════

_last_ntfy_time = 0

def send_ntfy(topic, title, message, priority="high"):
    """Send a push notification to your phone via ntfy.sh (free, no signup)."""
    global _last_ntfy_time
    now = time.time()
    if now - _last_ntfy_time < NTFY_COOLDOWN:
        return  # cooldown — don't spam
    try:
        url  = f"{NTFY_SERVER}/{urllib.parse.quote(topic)}"
        data = message.encode("utf-8")
        req  = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Title",    title)
        req.add_header("Priority", priority)
        req.add_header("Tags",     "warning,chart_with_upwards_trend")
        urllib.request.urlopen(req, timeout=5)
        _last_ntfy_time = now
        print(f"[NTFY] Alert sent → {topic}: {title}")
    except Exception as e:
        print(f"[NTFY] Failed to send: {e}")


from anomaly_detector import AnomalyDetector


# ════════════════════════════════════════════
# CSV LOGGER
# ════════════════════════════════════════════

def init_csv(path):
    if not os.path.exists(path):
        with open(path, "w", newline="") as f:
            csv.writer(f).writerow(
                ["timestamp", "value", "mean", "std", "upper", "lower", "anomaly", "severity"])

def log_csv(path, ts, r):
    with open(path, "a", newline="") as f:
        csv.writer(f).writerow([
            ts, r["value"], r.get("mean",""), r.get("std",""),
            r.get("upper",""), r.get("lower",""),
            int(r["anomaly"]), r.get("severity",0)
        ])


# ════════════════════════════════════════════
# TCP SERVER (background thread)
# ════════════════════════════════════════════

import json as _json

class TCPServer:
    """Threaded TCP server — camera loop never blocks waiting for LabVIEW."""
    def __init__(self, host, port):
        self._q = queue.Queue(maxsize=20)
        self._t = threading.Thread(target=self._run, args=(host, port), daemon=True)
        self._t.start()
        print(f"[TCP] Server listening on {host}:{port}")

    def send(self, value):
        try:
            payload = _json.dumps({"value": value, "timestamp": time.time()}) + "\n"
            self._q.put_nowait(payload)
        except queue.Full:
            pass

    def _run(self, host, port):
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind((host, port))
        except OSError as e:
            print(f"[TCP] Cannot bind port {port}: {e}")
            print(f"[TCP] Try a different port with --port XXXX")
            return
        srv.listen(1)
        srv.settimeout(1.0)
        conn = None
        while True:
            if conn is None:
                try:
                    conn, addr = srv.accept()
                    conn.settimeout(2.0)
                    print(f"[TCP] LabVIEW connected from {addr}")
                except socket.timeout:
                    continue
            try:
                msg = self._q.get(timeout=0.5)
                conn.sendall(msg.encode())
            except queue.Empty:
                pass
            except Exception:
                print("[TCP] Client disconnected. Waiting for reconnect...")
                try: conn.close()
                except: pass
                conn = None


# ════════════════════════════════════════════
# COMPUTER VISION
# ════════════════════════════════════════════

def find_gauge_circle(gray):
    """Auto-detect the circular gauge bezel using Hough Circles."""
    h, w = gray.shape
    circles = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2,
        minDist=int(min(h, w) * 0.4),
        param1=60, param2=40,
        minRadius=int(min(h, w) * 0.2),
        maxRadius=int(min(h, w) * 0.6),
    )
    if circles is not None:
        c = np.round(circles[0, 0]).astype(int)
        return int(c[0]), int(c[1]), int(c[2])
    return w//2, h//2, min(h,w)//2 - 5


def extract_needle_angle(frame, cx, cy, r):
    """
    HSV color-based needle detection.
    Finds the RED needle, ignores all other gauge elements.
    Returns angle in degrees (0° = 12-o'clock, CW positive).
    """
    hsv   = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # Red has two HSV ranges (wraps around 0/180)
    mask1 = cv2.inRange(hsv, np.array([0,  100, 100]), np.array([10, 255, 255]))
    mask2 = cv2.inRange(hsv, np.array([160,100, 100]), np.array([180,255, 255]))
    mask  = cv2.bitwise_or(mask1, mask2)

    # Only search inside gauge circle (80% radius) — ignore outer red zone
    circ_mask = np.zeros(mask.shape, dtype=np.uint8)
    cv2.circle(circ_mask, (cx, cy), int(r * 0.80), 255, -1)
    mask = cv2.bitwise_and(mask, circ_mask)

    # Remove noise
    kernel = np.ones((3,3), np.uint8)
    mask   = cv2.erode(mask, kernel, iterations=1)
    mask   = cv2.dilate(mask, kernel, iterations=1)

    lines = cv2.HoughLinesP(mask, 1, np.pi/180, 10,
                             minLineLength=int(r*0.15), maxLineGap=10)
    if lines is None:
        return None

    best_score, best_angle = -1, None
    for line in lines:
        x1, y1, x2, y2 = line[0]
        d1  = math.hypot(x1-cx, y1-cy)
        d2  = math.hypot(x2-cx, y2-cy)
        near, far = min(d1,d2), max(d1,d2)
        length = math.hypot(x2-x1, y2-y1)

        # Needle: one end near centre, other end reaching outward
        if near > r * 0.35: continue
        if far  < r * 0.20: continue
        if length > best_score:
            best_score = length
            # Tip = far end
            dx, dy = (x1-cx, y1-cy) if d1 > d2 else (x2-cx, y2-cy)
            # Correct angle reference: 0° = 12-o'clock (up), CW positive
            best_angle = math.degrees(math.atan2(dx, -dy))

    return best_angle


def angle_to_value(angle_deg):
    """Map needle angle to physical gauge value."""
    if angle_deg is None:
        return None
    angle_deg = max(ANGLE_MIN_DEG, min(ANGLE_MAX_DEG, angle_deg))
    ratio = (angle_deg - ANGLE_MIN_DEG) / (ANGLE_MAX_DEG - ANGLE_MIN_DEG)
    return round(GAUGE_MIN_VALUE + ratio * (GAUGE_MAX_VALUE - GAUGE_MIN_VALUE), 2)


def draw_overlay(frame, cx, cy, r, angle_deg, value, anomaly, roi=None):
    """Draw detection overlay on frame for visual feedback."""
    vis  = frame.copy()
    ox   = roi[0] if roi else 0
    oy   = roi[1] if roi else 0

    # Gauge circle — green normal, red anomaly
    color = (0, 0, 255) if anomaly else (0, 255, 0)
    cv2.circle(vis, (ox+cx, oy+cy), r, color, 2)
    cv2.circle(vis, (ox+cx, oy+cy), 5, (0, 0, 255), -1)

    # Detected needle line
    if angle_deg is not None:
        rad   = math.radians(angle_deg)
        tip_x = int(ox + cx + r * 0.85 * math.sin(rad))
        tip_y = int(oy + cy - r * 0.85 * math.cos(rad))
        cv2.line(vis, (ox+cx, oy+cy), (tip_x, tip_y), (0, 0, 255), 3)

    # Value display
    val_str   = f"Value: {value:.1f}" if value is not None else "Value: N/A"
    angle_str = f"Angle: {angle_deg:.1f} deg" if angle_deg else "Angle: N/A"
    status    = "!! ANOMALY !!" if anomaly else "Normal"
    s_color   = (0, 0, 255) if anomaly else (0, 255, 0)

    cv2.putText(vis, val_str,   (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,0), 2)
    cv2.putText(vis, angle_str, (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (200,200,0), 2)
    cv2.putText(vis, status,    (10, 95), cv2.FONT_HERSHEY_SIMPLEX, 0.8, s_color,     2)

    return vis


# ════════════════════════════════════════════
# ROI SELECTOR
# ════════════════════════════════════════════

_roi_rect  = []
_selecting = False
_start_pt  = None

def _mouse_cb(event, x, y, flags, param):
    global _roi_rect, _selecting, _start_pt
    if event == cv2.EVENT_LBUTTONDOWN:
        _selecting = True; _start_pt = (x,y); _roi_rect = []
    elif event == cv2.EVENT_LBUTTONUP and _selecting:
        _selecting = False
        x0, y0 = _start_pt
        _roi_rect = [min(x0,x), min(y0,y), abs(x-x0), abs(y-y0)]

def select_roi(frame):
    global _roi_rect, _selecting, _start_pt
    _roi_rect = []; _selecting = False; _start_pt = None
    win = "Draw box around gauge → SPACE  |  ESC = full frame"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, _mouse_cb)
    while True:
        disp = frame.copy()
        if len(_roi_rect) == 4:
            x,y,w,h = _roi_rect
            cv2.rectangle(disp, (x,y), (x+w,y+h), (0,255,0), 2)
        cv2.imshow(win, disp)
        key = cv2.waitKey(20) & 0xFF
        if key == ord(' ') and len(_roi_rect) == 4: break
        if key == 27: _roi_rect = []; break
    cv2.destroyWindow(win)
    return _roi_rect if len(_roi_rect) == 4 else None


# ════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="AI Gauge Reader")
    parser.add_argument("--source", default="gauge_video.mp4",
                        help="Camera index (0,1) or video/image path")
    parser.add_argument("--host",   default=TCP_HOST)
    parser.add_argument("--port",   type=int, default=TCP_PORT)
    parser.add_argument("--fps",    type=int, default=READ_FPS)
    parser.add_argument("--ntfy",   default=NTFY_TOPIC,
                        help="ntfy.sh topic for mobile alerts")
    parser.add_argument("--no-gui", action="store_true")
    args = parser.parse_args()

    # Open source
    try:    src = int(args.source)
    except: src = args.source

    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        print(f"[ERROR] Cannot open: {src}")
        sys.exit(1)

    ret, first_frame = cap.read()
    if not ret:
        print("[ERROR] Cannot read first frame")
        sys.exit(1)

    # ROI selection
    roi = None
    if not args.no_gui:
        print("[INFO] Draw a box around the gauge face, then press SPACE.")
        print("[INFO] Press ESC to use the full frame.")
        roi = select_roi(first_frame)
        print(f"[INFO] ROI: {roi or 'full frame'}")

    # Init subsystems
    tcp      = TCPServer(args.host, args.port)
    detector = AnomalyDetector(window=ANOMALY_WINDOW,
                                n_sigma=ANOMALY_SIGMA, warmup=10)
    smoother = deque(maxlen=SMOOTH_WINDOW)
    init_csv(LOG_FILE)

    print(f"[INFO] ntfy topic: {args.ntfy}")
    print(f"[INFO] Log file: {LOG_FILE}")
    print(f"[INFO] Running — press Q to quit")

    if not args.no_gui:
        cv2.namedWindow("Gauge Reader", cv2.WINDOW_NORMAL)

    interval  = 1.0 / args.fps
    last_read = 0.0

    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ret, frame = cap.read()
            if not ret: break

        now    = time.time()
        value  = None
        anomaly = False

        if now - last_read >= interval:
            last_read = now

            # Crop to ROI
            crop = frame
            if roi:
                x,y,w,h = roi
                crop = frame[y:y+h, x:x+w]

            # Detect gauge circle
            gray     = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            blur     = cv2.GaussianBlur(gray, (5,5), 0)
            cx,cy,r  = find_gauge_circle(blur)

            # Detect needle
            angle_deg = extract_needle_angle(crop, cx, cy, r)
            raw_val   = angle_to_value(angle_deg)

            if raw_val is not None:
                # Smooth
                smoother.append(raw_val)
                value = round(sum(smoother)/len(smoother), 2)

                # Anomaly detection
                result  = detector.update(value)
                anomaly = result["anomaly"]

                # Log to CSV
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_csv(LOG_FILE, ts, result)

                # Send to LabVIEW
                tcp.send(value)

                # Console output
                flag = " ⚠ ANOMALY" if anomaly else ""
                print(f"[READ] {ts}  angle={angle_deg:+.1f}°  "
                      f"value={value:.2f}  mean={result.get('mean','?')}{flag}")

                # Mobile notification
                if anomaly:
                    send_ntfy(
                        args.ntfy,
                        title=f"⚠ Gauge Anomaly Detected!",
                        message=(f"Value: {value:.1f} | "
                                 f"Mean: {result['mean']} | "
                                 f"Deviation: {result['severity']}σ | "
                                 f"Time: {ts}"),
                        priority="high"
                    )
            else:
                print("[READ] Needle not detected")

            if not args.no_gui:
                angle_draw = angle_deg if raw_val is not None else None
                vis = draw_overlay(frame, cx, cy, r,
                                   angle_draw, value, anomaly, roi)
                cv2.imshow("Gauge Reader", vis)

        if not args.no_gui:
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break

    cap.release()
    cv2.destroyAllWindows()
    print(f"[DONE] Log saved to {LOG_FILE}")


if __name__ == "__main__":
    main()
