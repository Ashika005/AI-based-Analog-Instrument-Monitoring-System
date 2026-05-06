"""
generate_test_gauge.py
-----------------------
Generates a synthetic analog gauge image (or video) for testing
when you don't have a physical gauge or camera yet.

Usage:
    python generate_test_gauge.py --mode image --value 60 --out gauge.jpg
    python generate_test_gauge.py --mode video --out gauge_video.mp4
"""

import cv2
import numpy as np
import math
import argparse


# ── Gauge parameters (must match gauge_reader.py) ──
GAUGE_MIN_VALUE = 0
GAUGE_MAX_VALUE = 100
ANGLE_MIN_DEG   = -135
ANGLE_MAX_DEG   =  135


def value_to_angle(value):
    ratio = (value - GAUGE_MIN_VALUE) / (GAUGE_MAX_VALUE - GAUGE_MIN_VALUE)
    return ANGLE_MIN_DEG + ratio * (ANGLE_MAX_DEG - ANGLE_MIN_DEG)


def draw_gauge(value, size=400):
    img = np.ones((size, size, 3), dtype=np.uint8) * 40  # dark bg

    cx, cy = size // 2, size // 2
    r = int(size * 0.42)

    # Bezel
    cv2.circle(img, (cx, cy), r + 8, (180, 180, 180), 3)
    cv2.circle(img, (cx, cy), r,     (60, 60, 60),    -1)

    # Tick marks
    for v in range(GAUGE_MIN_VALUE, GAUGE_MAX_VALUE + 1, 10):
        a   = math.radians(value_to_angle(v))
        r1  = r - 5
        r2  = r - 20 if v % 20 == 0 else r - 12
        x1  = int(cx + r1 * math.sin(a))
        y1  = int(cy - r1 * math.cos(a))
        x2  = int(cx + r2 * math.sin(a))
        y2  = int(cy - r2 * math.cos(a))
        color = (200, 200, 200) if v % 20 == 0 else (120, 120, 120)
        cv2.line(img, (x1, y1), (x2, y2), color, 2 if v % 20 == 0 else 1)

        # Label every 20 units
        if v % 20 == 0:
            lx = int(cx + (r - 35) * math.sin(a))
            ly = int(cy - (r - 35) * math.cos(a))
            cv2.putText(img, str(v), (lx - 10, ly + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)

    # Red zone (80–100)
    for v in range(80, 101):
        a1 = math.radians(value_to_angle(v - 1))
        a2 = math.radians(value_to_angle(v))
        x1 = int(cx + (r - 8) * math.sin(a1))
        y1 = int(cy - (r - 8) * math.cos(a1))
        x2 = int(cx + (r - 8) * math.sin(a2))
        y2 = int(cy - (r - 8) * math.cos(a2))
        cv2.line(img, (x1, y1), (x2, y2), (0, 0, 200), 5)

    # Needle
    angle_deg = value_to_angle(value)
    a = math.radians(angle_deg)
    tip_x = int(cx + (r - 20) * math.sin(a))
    tip_y = int(cy - (r - 20) * math.cos(a))
    tail_x = int(cx - 20 * math.sin(a))
    tail_y = int(cy + 20 * math.cos(a))
    cv2.line(img, (tail_x, tail_y), (tip_x, tip_y), (0, 0, 255), 3)
    cv2.circle(img, (cx, cy), 8, (100, 100, 100), -1)

    # Value label
    cv2.putText(img, f"{value:.1f}", (cx - 25, cy + 50),
                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

    return img


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode",  choices=["image", "video"], default="image")
    parser.add_argument("--value", type=float, default=60.0,
                        help="Gauge value for static image")
    parser.add_argument("--out",   default=None,
                        help="Output filename. Default: gauge.jpg or gauge_video.mp4")
    args = parser.parse_args()

    if args.mode == "image":
        out = args.out or "gauge.jpg"
        img = draw_gauge(args.value)
        cv2.imwrite(out, img)
        print(f"Saved: {out}  (value={args.value})")

    else:  # video
        out = args.out or "gauge_video.mp4"
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        fps    = 10
        writer = cv2.VideoWriter(out, fourcc, fps, (400, 400))

        # Sweep: 0→100→0, smooth sine
        import numpy as np
        frames = fps * 20   # 20-second loop
        for i in range(frames):
            t   = i / frames
            val = 50 + 50 * math.sin(2 * math.pi * t)
            writer.write(draw_gauge(val))
        writer.release()
        print(f"Saved: {out}  ({frames} frames @ {fps} fps)")


if __name__ == "__main__":
    main()
