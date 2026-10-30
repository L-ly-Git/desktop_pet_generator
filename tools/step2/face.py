# -*- coding: utf-8 -*-
"""Face detection and BiSeNet face-parsing helpers."""
from __future__ import annotations

import cv2
import numpy as np


def detect_largest_face(detector, image_bgr: np.ndarray):
    faces = detector.detect(image_bgr)
    if not faces:
        return None
    return max(
        faces,
        key=lambda face: float(
            (face.bbox[2] - face.bbox[0]) * (face.bbox[3] - face.bbox[1])
        ),
    )


def expand_bbox(
    bbox,
    image_width: int,
    image_height: int,
    margin_ratio: float = 0.25,
) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = [float(value) for value in bbox[:4]]
    margin_x = int((x2 - x1) * margin_ratio)
    margin_y = int((y2 - y1) * margin_ratio)
    return (
        max(0, int(round(x1)) - margin_x),
        max(0, int(round(y1)) - margin_y),
        min(image_width, int(round(x2)) + margin_x),
        min(image_height, int(round(y2)) + margin_y),
    )


def crop_face(
    image_bgr: np.ndarray,
    bbox,
    margin_ratio: float = 0.25,
) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    height, width = image_bgr.shape[:2]
    crop_box = expand_bbox(bbox, width, height, margin_ratio)
    x1, y1, x2, y2 = crop_box
    return image_bgr[y1:y2, x1:x2].copy(), crop_box


def parse_face(parser, face_crop: np.ndarray) -> np.ndarray:
    return parser.parse(face_crop)


def class_counts(mask: np.ndarray) -> dict[int, int]:
    values, counts = np.unique(mask, return_counts=True)
    return {int(value): int(count) for value, count in zip(values, counts)}


def mask_for_classes(mask: np.ndarray, classes: tuple[int, ...]) -> np.ndarray:
    return np.isin(mask, classes).astype(np.uint8) * 255