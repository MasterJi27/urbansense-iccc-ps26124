"""Homography speed estimation for a calibrated, mostly static camera.

Moving dashcams (bus phones) make metric speed unreliable without IMU fusion.
Default calibration is a placeholder — ai_status is EXPERIMENTAL and
extra.calibrated is false until a real homography is supplied.
Speed estimate is experimental for moving-camera footage; never evidence-grade.
"""

from __future__ import annotations

import math
from collections import defaultdict, deque

import numpy as np

from urbansense_ai.status import EXPERIMENTAL


class HomographySpeedEstimator:
    def __init__(self, image_pts=None, world_pts=None, fps: float = 15.0):
        self.fps = float(fps)
        self.calibrated = image_pts is not None and world_pts is not None
        if not self.calibrated:
            image_pts = [[300, 400], [980, 400], [1100, 700], [180, 700]]
            world_pts = [[0, 0], [10, 0], [10, 30], [0, 30]]
        src = np.array(image_pts, dtype=np.float32)
        dst = np.array(world_pts, dtype=np.float32)
        try:
            import cv2

            self.H, _ = cv2.findHomography(src, dst)
        except Exception:
            self.H = None
        self.hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=12))

    def img_to_world(self, x: float, y: float) -> tuple[float, float] | None:
        if self.H is None:
            return None
        import cv2

        pt = np.array([[[x, y]]], dtype=np.float32)
        wp = cv2.perspectiveTransform(pt, self.H)[0, 0]
        return float(wp[0]), float(wp[1])

    def update(self, track_id: str, cx_px: float, cy_px: float, t: float) -> float | None:
        w = self.img_to_world(cx_px, cy_px)
        if w is None:
            return None
        self.hist[track_id].append((t, w[0], w[1]))
        hist = self.hist[track_id]
        if len(hist) < 3:
            return None
        t0, x0, y0 = hist[0]
        t1, x1, y1 = hist[-1]
        dt = t1 - t0
        if dt <= 0.05:
            return None
        kmh = (math.hypot(x1 - x0, y1 - y0) / dt) * 3.6
        if kmh > 200:
            return None
        return kmh

    def meta(self) -> dict:
        return {
            "ai_status": EXPERIMENTAL,
            "calibrated": self.calibrated,
            "note": "Speed estimate is experimental for moving-camera footage; "
            "uncalibrated homography is a demo placeholder and dashcam "
            "ego-motion is not compensated. Not evidence-grade.",
        }
