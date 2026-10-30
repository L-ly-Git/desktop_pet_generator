# -*- coding: utf-8 -*-
"""发色鲁棒提取 + 肤色护栏：头发不会取到肤色；若仍疑似肤色则回退深色发。"""
from __future__ import annotations

import cv2
import numpy as np

DARK_HAIR = (72, 56, 52)


def _skin_like(rgb) -> bool:
    r, g, b = [float(v) for v in rgb]
    lum = (r + g + b) / 3.0
    return r > g > b and lum > 140


def hair_color_from_mask(image_bgr: np.ndarray, full_mask: np.ndarray, fallback=DARK_HAIR) -> list[int]:
    mask = np.isin(full_mask, (13, 14)).astype(np.uint8) * 255
    ys, xs = np.where(mask > 0)
    if len(ys) < 20:
        return list(fallback)
    top_y = int(np.percentile(ys, 35))
    crown = mask.copy()
    crown[top_y:, :] = 0
    if int((crown > 0).sum()) < 20:
        crown = mask
    pixels = image_bgr[crown > 0]
    lum = pixels.mean(axis=1)
    k = max(1, len(pixels) // 2)
    darkest = pixels[np.argsort(lum)[:k]]
    median_bgr = np.median(darkest, axis=0)
    rgb = [int(round(float(v))) for v in median_bgr[::-1]]
    if _skin_like(rgb):
        return list(fallback)
    return rgb
