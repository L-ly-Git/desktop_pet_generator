# -*- coding: utf-8 -*-
"""画一个 A-pose 的 openpose 骨架控制图（手臂张开、腿略分），喂 openpose ControlNet。"""
from __future__ import annotations

import math
from collections import namedtuple
from pathlib import Path

import cv2
import numpy as np

Keypoint = namedtuple("Keypoint", ["x", "y"])

# COCO 18 点顺序: nose, neck, R-shoulder, R-elbow, R-wrist, L-shoulder, L-elbow, L-wrist,
#                 R-hip, R-knee, R-ankle, L-hip, L-knee, L-ankle, R-eye, L-eye, R-ear, L-ear
APOSE = [
    Keypoint(0.50, 0.15),  # nose
    Keypoint(0.50, 0.24),  # neck
    Keypoint(0.41, 0.27),  # R-shoulder
    Keypoint(0.27, 0.33),  # R-elbow
    Keypoint(0.16, 0.40),  # R-wrist
    Keypoint(0.59, 0.27),  # L-shoulder
    Keypoint(0.73, 0.33),  # L-elbow
    Keypoint(0.84, 0.40),  # L-wrist
    Keypoint(0.42, 0.52),  # R-hip
    Keypoint(0.37, 0.70),  # R-knee
    Keypoint(0.33, 0.88),  # R-ankle
    Keypoint(0.58, 0.52),  # L-hip
    Keypoint(0.63, 0.70),  # L-knee
    Keypoint(0.67, 0.88),  # L-ankle
    Keypoint(0.45, 0.11),  # R-eye
    Keypoint(0.55, 0.11),  # L-eye
    Keypoint(0.40, 0.15),  # R-ear
    Keypoint(0.60, 0.15),  # L-ear
]

LIMB_SEQ = [
    [2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10],
    [10, 11], [2, 12], [12, 13], [13, 14], [2, 1], [1, 15], [15, 17],
    [1, 16], [16, 18],
]
COLORS = [
    [255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0],
    [85, 255, 0], [0, 255, 0], [0, 255, 85], [0, 255, 170], [0, 255, 255],
    [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255], [170, 0, 255],
    [255, 0, 255], [255, 0, 170], [255, 0, 85],
]


def draw_bodypose(canvas, keypoints):
    H, W, _ = canvas.shape
    stickwidth = 4
    for (k1, k2), color in zip(LIMB_SEQ, COLORS):
        p1 = keypoints[k1 - 1]
        p2 = keypoints[k2 - 1]
        if p1 is None or p2 is None:
            continue
        Y = np.array([p1.x, p2.x]) * float(W)
        X = np.array([p1.y, p2.y]) * float(H)
        mX = np.mean(X)
        mY = np.mean(Y)
        length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
        angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
        poly = cv2.ellipse2Poly((int(mY), int(mX)), (int(length / 2), stickwidth), int(angle), 0, 360, 1)
        cv2.fillConvexPoly(canvas, poly, [int(float(c) * 0.6) for c in color])
    for kp, color in zip(keypoints, COLORS):
        if kp is None:
            continue
        cv2.circle(canvas, (int(kp.x * W), int(kp.y * H)), 4, color, thickness=-1)
    return canvas


def main():
    W, H = 512, 768
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    draw_bodypose(canvas, APOSE)
    out = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\input\apose.png")
    cv2.imwrite(str(out), canvas)
    print("saved", out, canvas.shape)


if __name__ == "__main__":
    main()
