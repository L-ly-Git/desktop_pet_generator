# -*- coding: utf-8 -*-
"""Extract a stylized character profile from a photo for the chibi template."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from .face import class_counts, crop_face, detect_largest_face, parse_face
from .matte import predict_matte


@dataclass
class PhotoAnalysis:
    profile: dict
    face_crop: np.ndarray
    parse_mask: np.ndarray
    alpha: np.ndarray
    crop_box: tuple[int, int, int, int]
    full_parse_mask: np.ndarray
    class_counts: dict[int, int]


def _rgb_to_hex(rgb) -> str:
    r, g, b = [max(0, min(255, int(round(value)))) for value in rgb]
    return f"#{r:02x}{g:02x}{b:02x}"


def _bgr_to_rgb(bgr) -> list[int]:
    return [int(bgr[2]), int(bgr[1]), int(bgr[0])]


def _median_color(
    image_bgr: np.ndarray,
    mask: np.ndarray,
    fallback_rgb,
    min_pixels: int = 20,
    brightness_max: float | None = None,
) -> list[int]:
    if mask is None or int((mask > 0).sum()) < min_pixels:
        return [int(value) for value in fallback_rgb]
    pixels = image_bgr[mask > 0]
    if brightness_max is not None:
        gray = pixels.mean(axis=1)
        filtered = pixels[gray < brightness_max]
        if len(filtered) >= min_pixels:
            pixels = filtered
    median_bgr = np.median(pixels, axis=0)
    return _bgr_to_rgb(median_bgr)


def _color_distance(a, b) -> float:
    return float(np.linalg.norm(np.asarray(a, dtype=np.float32) - np.asarray(b, dtype=np.float32)))


def _clothing_colors(
    image_bgr: np.ndarray,
    alpha: np.ndarray,
    face_bottom: float,
    skin_rgb,
    hair_rgb,
    fallback_primary=(116, 150, 205),
    fallback_secondary=(75, 96, 140),
) -> tuple[list[int], list[int]]:
    height, width = image_bgr.shape[:2]
    yy, xx = np.mgrid[0:height, 0:width]
    region = (alpha > 0.6) & (yy > face_bottom + 10)
    if int(region.sum()) < 100:
        return list(fallback_primary), list(fallback_secondary)
    pixels_bgr = image_bgr[region]
    if len(pixels_bgr) > 20000:
        step = max(1, len(pixels_bgr) // 20000)
        pixels_bgr = pixels_bgr[::step]
    pixels_rgb = pixels_bgr[:, ::-1].astype(np.float32)
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.5,
    )
    try:
        _compactness, labels, centers = cv2.kmeans(
            pixels_rgb,
            4,
            None,
            criteria,
            3,
            cv2.KMEANS_PP_CENTERS,
        )
    except cv2.error:
        return list(fallback_primary), list(fallback_secondary)
    counts = np.bincount(labels.flatten(), minlength=len(centers))
    order = np.argsort(counts)[::-1]
    chosen: list[list[int]] = []
    for index in order:
        center = [int(round(value)) for value in centers[index]]
        brightness = sum(center) / 3.0
        if brightness < 20 or brightness > 248:
            continue
        if _color_distance(center, skin_rgb) < 38:
            continue
        if _color_distance(center, hair_rgb) < 38:
            continue
        if any(_color_distance(center, existing) < 22 for existing in chosen):
            continue
        chosen.append(center)
        if len(chosen) == 2:
            break
    if not chosen:
        chosen = [list(fallback_primary)]
    if len(chosen) == 1:
        chosen.append(list(fallback_secondary))
    return chosen[0], chosen[1]


def _hair_length(
    full_mask: np.ndarray,
    face_crop: np.ndarray,
    face_bbox,
    image_bgr: np.ndarray,
    alpha: np.ndarray,
    hair_rgb,
) -> str:
    face_height = max(1.0, float(face_bbox[3] - face_bbox[1]))
    hair_mask = np.isin(full_mask, (13, 14)).astype(np.uint8) * 255
    bbox = cv2.boundingRect(hair_mask)
    ratio = 0.0
    if bbox[2] > 0 and bbox[3] > 0:
        ratio = bbox[3] / face_height

    h, w = image_bgr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    face_bottom = float(face_bbox[3])
    lower_limit = min(h, int(face_bottom + (h - face_bottom) * 0.45))
    region = (alpha > 0.6) & (yy > face_bottom + 2) & (yy < lower_limit)
    below_fraction = 0.0
    if int(region.sum()) > 100:
        pixels_rgb = image_bgr[region][:, ::-1].astype(np.float32)
        distance = np.linalg.norm(pixels_rgb - np.asarray(hair_rgb, dtype=np.float32), axis=1)
        below_fraction = float((distance < 55).mean())

    if ratio > 0.95 or below_fraction > 0.12:
        return "long"
    if ratio > 0.62 or below_fraction > 0.045:
        return "medium"
    return "short"


def _outfit_style(alpha: np.ndarray, face_bbox) -> str:
    person = (alpha > 0.5).astype(np.uint8)
    x, y, w, h = cv2.boundingRect(person)
    if w <= 0 or h <= 0 or h < 180:
        return "tunic"
    face_bottom = int(face_bbox[3])
    shoulder_y = min(y + h - 1, max(y + 1, face_bottom + int(h * 0.08)))
    hip_y = min(y + h - 1, max(y + 1, y + int(h * 0.65)))

    def row_width(row: int) -> int:
        xs = np.where(person[row] > 0)[0]
        return int(xs[-1] - xs[0] + 1) if len(xs) else 0

    shoulder_width = max(1, row_width(shoulder_y))
    hip_width = row_width(hip_y)
    if hip_width > shoulder_width * 1.25:
        return "dress"
    return "tunic"


def extract_profile(
    image_bgr: np.ndarray,
    detector,
    parser,
    matting,
    photo_path: Path,
    face_margin: float = 0.35,
) -> PhotoAnalysis:
    face = detect_largest_face(detector, image_bgr)
    if face is None:
        raise ValueError("未检测到人脸")
    face_crop, crop_box = crop_face(image_bgr, face.bbox, margin_ratio=face_margin)
    mask = parse_face(parser, face_crop)
    counts = class_counts(mask)
    alpha = predict_matte(matting, image_bgr)

    height, width = image_bgr.shape[:2]
    full_mask = np.zeros((height, width), dtype=np.uint8)
    x1, y1, x2, y2 = crop_box
    full_mask[y1:y2, x1:x2] = mask

    skin_rgb = _median_color(
        image_bgr,
        np.isin(full_mask, (1, 2)).astype(np.uint8) * 255,
        (255, 224, 210),
        min_pixels=20,
    )
    hair_rgb = _median_color(
        image_bgr,
        np.isin(full_mask, (13, 14)).astype(np.uint8) * 255,
        (72, 56, 52),
        min_pixels=20,
    )
    eye_rgb = _median_color(
        image_bgr,
        np.isin(full_mask, (4, 5)).astype(np.uint8) * 255,
        (72, 60, 86),
        min_pixels=8,
        brightness_max=180,
    )
    mouth_rgb = _median_color(
        image_bgr,
        np.isin(full_mask, (10, 11, 12)).astype(np.uint8) * 255,
        (190, 105, 118),
        min_pixels=8,
    )
    clothing_primary, clothing_secondary = _clothing_colors(
        image_bgr, alpha, float(face.bbox[3]), skin_rgb, hair_rgb
    )
    hair_length = _hair_length(
        full_mask, face_crop, face.bbox, image_bgr, alpha, hair_rgb
    )
    outfit_style = _outfit_style(alpha, face.bbox)
    glasses_detected = counts.get(3, 0) >= 20

    profile = {
        "photo": str(photo_path),
        "width": int(width),
        "height": int(height),
        "face_bbox": [float(value) for value in face.bbox[:4]],
        "face_confidence": float(face.confidence),
        "face_crop_box": [int(value) for value in crop_box],
        "skin_color": skin_rgb,
        "hair_color": hair_rgb,
        "eye_color": eye_rgb,
        "mouth_color": mouth_rgb,
        "clothing_primary": clothing_primary,
        "clothing_secondary": clothing_secondary,
        "hair_length": hair_length,
        "outfit_style": outfit_style,
        "glasses_detected": bool(glasses_detected),
        "colors_hex": {
            "skin": _rgb_to_hex(skin_rgb),
            "hair": _rgb_to_hex(hair_rgb),
            "eye": _rgb_to_hex(eye_rgb),
            "mouth": _rgb_to_hex(mouth_rgb),
            "clothing_primary": _rgb_to_hex(clothing_primary),
            "clothing_secondary": _rgb_to_hex(clothing_secondary),
        },
        "class_counts": {
            str(key): int(value) for key, value in sorted(counts.items())
        },
        "alpha_coverage_0_5": float((alpha > 0.5).mean()),
    }
    return PhotoAnalysis(
        profile=profile,
        face_crop=face_crop,
        parse_mask=mask,
        alpha=alpha,
        crop_box=crop_box,
        full_parse_mask=full_mask,
        class_counts=counts,
    )