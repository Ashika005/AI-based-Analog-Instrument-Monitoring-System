"""
anomaly_detector.py
--------------------
Rolling-window statistical anomaly detector.
Used by python_hmi.py and gauge_reader.py.

Algorithm: flag if value deviates > n_sigma * std from rolling mean (3-Sigma Rule).
"""

import numpy as np
from collections import deque


class AnomalyDetector:
    def __init__(self, window=20, n_sigma=3.0, warmup=5):
        self.window  = window
        self.n_sigma = n_sigma
        self.warmup  = warmup
        self._buf    = deque(maxlen=window)

    def update(self, value):
        """
        Add a new value and check for anomaly.
        Returns a dict with keys:
          value, mean, std, upper, lower, anomaly (bool), severity (float sigma)
        """
        self._buf.append(value)
        result = {
            "value":    value,
            "mean":     None,
            "std":      None,
            "upper":    None,
            "lower":    None,
            "anomaly":  False,
            "severity": 0.0,
        }
        if len(self._buf) < self.warmup:
            return result

        arr  = np.array(self._buf)
        mean = float(np.mean(arr))
        std  = float(np.std(arr))

        result["mean"]  = round(mean, 3)
        result["std"]   = round(std,  3)
        result["upper"] = round(mean + self.n_sigma * std, 3)
        result["lower"] = round(mean - self.n_sigma * std, 3)

        if std > 0:
            sev = abs(value - mean) / std
            result["severity"] = round(sev, 2)
            result["anomaly"]  = sev >= self.n_sigma

        return result