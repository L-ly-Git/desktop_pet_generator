# -*- coding: utf-8 -*-
"""AnimeGANv2 ONNX inference helpers."""
from __future__ import annotations

import cv2
import numpy as np


def _run_512(session, image_bgr: np.ndarray) -> np.ndarray:
    resized = cv2.resize(image_bgr, (512, 512), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
    tensor = rgb.transpose(2, 0, 1)
    tensor = tensor * 2.0 - 1.0
    tensor = tensor.reshape(-1, 3, 512, 512)
    input_name = session.get_inputs()[0].name
    output_name = session.get_outputs()[0].name
    output = session.run([output_name], {input_name: tensor})[0]
    output = np.asarray(output).squeeze()
    output = (output * 0.5 + 0.5).clip(0.0, 1.0) * 255.0
    output = output.transpose(1, 2, 0).astype(np.uint8)
    return cv2.cvtColor(output, cv2.COLOR_RGB2BGR)


def _pad_to_square(image_bgr: np.ndarray, border_mode: int) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    height, width = image_bgr.shape[:2]
    side = max(height, width)
    top = (side - height) // 2
    bottom = side - height - top
    left = (side - width) // 2
    right = side - width - left
    padded = cv2.copyMakeBorder(
        image_bgr,
        top,
        bottom,
        left,
        right,
        border_mode,
        value=(255, 255, 255),
    )
    return padded, (top, bottom, left, right)


def cartoonize_full(
    session,
    image_bgr: np.ndarray,
    border_mode: int = cv2.BORDER_REPLICATE,
) -> np.ndarray:
    """Cartoonize a whole image while preserving its aspect ratio."""
    padded, (top, bottom, left, right) = _pad_to_square(image_bgr, border_mode)
    output = _run_512(session, padded)
    side = padded.shape[0]
    output = cv2.resize(output, (side, side), interpolation=cv2.INTER_CUBIC)
    height = image_bgr.shape[0]
    width = image_bgr.shape[1]
    return output[top : top + height, left : left + width]


def cartoonize_face(session, face_bgr: np.ndarray) -> np.ndarray:
    """Cartoonize a face crop, returning a 512x512 square image."""
    padded, _ = _pad_to_square(face_bgr, cv2.BORDER_REPLICATE)
    return _run_512(session, padded)