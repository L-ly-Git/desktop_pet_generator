# -*- coding: utf-8 -*-
"""真人照片的眼/嘴提取：用轻量 SCRFD 人脸关键点定位眼睛与嘴，裁剪椭圆区域。

不依赖 uniface 全家桶，打包时只需 scrfd_500m.onnx（约 2.4MB）。
"""
from __future__ import annotations

import cv2
import numpy as np

try:
    from tools.step2.scrfd_onnx import SCRFDDetector
    _HAS_DETECTOR = True
except Exception:  # noqa: BLE001
    _HAS_DETECTOR = False


def _ellipse_mask(h: int, w: int, cx: float, cy: float, rx: int, ry: int) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    cv2.ellipse(m, (int(round(cx)), int(round(cy))), (rx, ry), 0, 0, 360, 255, -1)
    return m.astype(bool)


def infer_face_real(rgb: np.ndarray, foreground: np.ndarray):
    """返回 (eye_l, eye_r, mouth) 布尔掩码（原图尺寸，已与前景取交集）。"""
    h, w = rgb.shape[:2]
    eye_l = np.zeros((h, w), bool)
    eye_r = np.zeros((h, w), bool)
    mouth = np.zeros((h, w), bool)

    if not _HAS_DETECTOR:
        return eye_l, eye_r, mouth

    try:
        detector = SCRFDDetector()
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        face = detector.detect_largest(bgr)
    except Exception:  # noqa: BLE001
        return eye_l, eye_r, mouth

    if face is None or face.get("landmarks") is None or len(face["landmarks"]) < 5:
        return eye_l, eye_r, mouth

    lm = face["landmarks"]
    # 5 点：右眼、左眼、鼻尖、右嘴角、左嘴角（以人物自身左右计）。契约 eye_l/eye_r 是画面左右，按 x 排序。
    eyes = sorted(lm[:2], key=lambda p: float(p[0]))
    (ex_l, ey_l_y) = float(eyes[0][0]), float(eyes[0][1])
    (ex_r, ey_r_y) = float(eyes[1][0]), float(eyes[1][1])
    mx = (float(lm[3][0]) + float(lm[4][0])) / 2.0
    my = (float(lm[3][1]) + float(lm[4][1])) / 2.0

    x1, y1, x2, y2 = [float(v) for v in face["bbox"][:4]]
    fw = max(1.0, x2 - x1)
    fh = max(1.0, y2 - y1)

    eye_rx = max(5, int(round(fw * 0.10)))
    eye_ry = max(5, int(round(fh * 0.055)))
    mouth_rx = max(6, int(round(fw * 0.15)))
    mouth_ry = max(5, int(round(fh * 0.05)))

    eye_l = _ellipse_mask(h, w, ex_l, ey_l_y, eye_rx, eye_ry)
    eye_r = _ellipse_mask(h, w, ex_r, ey_r_y, eye_rx, eye_ry)
    mouth = _ellipse_mask(h, w, mx, my, mouth_rx, mouth_ry)

    eye_l &= foreground
    eye_r &= foreground
    mouth &= foreground
    return eye_l, eye_r, mouth
