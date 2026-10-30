# -*- coding: utf-8 -*-
"""MODNet portrait-matte helpers."""
from __future__ import annotations

import cv2
import numpy as np


def predict_matte(matting, image_bgr: np.ndarray) -> np.ndarray:
    return matting.predict(image_bgr)


def alpha_to_u8(alpha: np.ndarray) -> np.ndarray:
    return np.clip(alpha * 255.0, 0, 255).astype(np.uint8)


def composite_on_color(
    image_bgr: np.ndarray,
    alpha: np.ndarray,
    color: tuple[int, int, int] = (255, 255, 255),
) -> np.ndarray:
    alpha_3 = alpha[..., None]
    foreground = image_bgr.astype(np.float32) * alpha_3
    background = np.full_like(image_bgr, color, dtype=np.float32) * (1.0 - alpha_3)
    return np.clip(foreground + background, 0, 255).astype(np.uint8)


def make_checkerboard_preview(
    image_bgr: np.ndarray,
    alpha: np.ndarray,
    cell: int = 24,
) -> np.ndarray:
    height, width = image_bgr.shape[:2]
    background = np.zeros_like(image_bgr)
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            if (x // cell + y // cell) % 2 == 0:
                background[y : y + cell, x : x + cell] = (48, 52, 60)
            else:
                background[y : y + cell, x : x + cell] = (34, 38, 46)
    alpha_3 = alpha[..., None]
    return np.clip(
        image_bgr.astype(np.float32) * alpha_3
        + background.astype(np.float32) * (1.0 - alpha_3),
        0,
        255,
    ).astype(np.uint8)