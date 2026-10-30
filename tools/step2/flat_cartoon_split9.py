# -*- coding: utf-8 -*-
"""Decompose one flat cartoon image into the contract v1 nine-part rig.

The tool never redraws the character. It removes the background, finds
semantic regions with a small local anime-face model plus color/layout rules,
then copies the original pixels into nine full-canvas RGBA layers.

Default output:
    out/
      character.json
      parts/head.png ... mouth.png
      preview.png
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "models" / "anime_face_seg" / "anime_face_unet.onnx"
CANVAS = 512
PART_NAMES = (
    "head",
    "body",
    "arm_l",
    "arm_r",
    "leg_l",
    "leg_r",
    "eye_l",
    "eye_r",
    "mouth",
)
LABEL_TO_PART = {
    1: "head",
    2: "body",
    3: "arm_l",
    4: "arm_r",
    5: "leg_l",
    6: "leg_r",
}
DEBUG_PALETTE = np.array(
    [
        [0, 0, 0],
        [230, 150, 80],
        [245, 205, 70],
        [90, 180, 245],
        [70, 130, 230],
        [120, 220, 130],
        [70, 180, 100],
    ],
    dtype=np.uint8,
)


def read_rgba(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = image.convert("RGBA")
        return np.asarray(image).copy()


def fill_closed_holes(mask: np.ndarray) -> np.ndarray:
    """Fill background-colored regions enclosed by a binary mask."""
    inverse = (mask == 0).astype(np.uint8)
    count, labels = cv2.connectedComponents(inverse, connectivity=8)
    if count <= 1:
        return mask.copy()
    border_labels = set(labels[0, :].tolist())
    border_labels.update(labels[-1, :].tolist())
    border_labels.update(labels[:, 0].tolist())
    border_labels.update(labels[:, -1].tolist())
    holes = (labels > 0) & ~np.isin(labels, list(border_labels))
    return mask | holes


def detect_foreground(rgb: np.ndarray, alpha: np.ndarray) -> tuple[np.ndarray, bool]:
    """Return a character mask and whether an existing alpha channel was used."""
    if int((alpha < 250).sum()) > max(16, alpha.size // 200):
        return alpha > 16, True

    data = rgb.astype(np.int16)
    red, green, blue = data[:, :, 0], data[:, :, 1], data[:, :, 2]
    warm = (red > blue + 8) & (red > 60)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        warm.astype(np.uint8), connectivity=8
    )
    if count <= 1:
        raise ValueError(
            "Could not detect a warm/light character body. "
            "Use an image with transparent background or provide --masks-dir."
        )
    core_index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    core = labels == core_index

    spread = data.max(axis=2) - data.min(axis=2)
    brightness = data.mean(axis=2)
    neutral = (spread < 35) & (brightness > 130)
    neutral_count, neutral_labels, neutral_stats, _ = cv2.connectedComponentsWithStats(
        neutral.astype(np.uint8), connectivity=8
    )
    distance_to_core = cv2.distanceTransform(
        (1 - core.astype(np.uint8)).astype(np.uint8), cv2.DIST_L2, 5
    )
    selected_neutral = np.zeros_like(core)
    for index in range(1, neutral_count):
        area = int(neutral_stats[index, cv2.CC_STAT_AREA])
        if area < 8:
            continue
        component = neutral_labels == index
        if float(distance_to_core[component].min()) <= 1.5:
            selected_neutral |= component

    mask = (core | selected_neutral).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    mask = fill_closed_holes(mask.astype(bool)).astype(np.uint8)
    return mask.astype(bool), False


def color_masks(rgb: np.ndarray) -> dict[str, np.ndarray]:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    hue, saturation, value = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    skin = (
        (value >= 165)
        & (hue >= 4)
        & (hue <= 19)
        & (saturation >= 20)
        & (saturation <= 165)
    )
    yellow = (value >= 140) & (hue >= 20) & (hue <= 36) & (saturation >= 65)
    neutral = (value >= 130) & (saturation <= 65)
    hair = (value < 190) & (hue >= 5) & (hue <= 35) & (saturation >= 40)
    return {
        "skin": skin,
        "yellow": yellow,
        "neutral": neutral,
        "hair": hair,
    }


def select_dress_component(yellow: np.ndarray) -> tuple[np.ndarray, tuple[int, int, int, int]]:
    height, width = yellow.shape
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        yellow.astype(np.uint8), connectivity=8
    )
    candidates: list[tuple[float, int]] = []
    for index in range(1, count):
        x, y, w, h, area = [int(value) for value in stats[index]]
        if area < 100:
            continue
        if y + h < height * 0.50:
            continue
        center_x = x + w / 2.0
        center_penalty = abs(center_x - width / 2.0) / max(1.0, width)
        score = float(area) * (1.0 + y / max(1.0, height)) * (1.0 - 0.25 * center_penalty)
        candidates.append((score, index))
    if not candidates:
        raise ValueError("Could not locate the main clothing region.")
    index = max(candidates)[1]
    x, y, w, h, _ = [int(value) for value in stats[index]]
    return labels == index, (x, y, w, h)


def row_extents(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height = mask.shape[0]
    left = np.full(height, -1, dtype=np.int32)
    right = np.full(height, -1, dtype=np.int32)
    for y in range(height):
        xs = np.flatnonzero(mask[y])
        if len(xs):
            left[y] = int(xs[0])
            right[y] = int(xs[-1])
    known = np.flatnonzero(left >= 0)
    if not len(known):
        return left, right
    all_rows = np.arange(height)
    left[left < 0] = np.interp(all_rows[left < 0], known, left[known]).astype(np.int32)
    right[right < 0] = np.interp(all_rows[right < 0], known, right[known]).astype(np.int32)
    return left, right


def filter_components(mask: np.ndarray, min_area: int) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(
        mask.astype(np.uint8), connectivity=8
    )
    result = np.zeros_like(mask)
    for index in range(1, count):
        if int(stats[index, cv2.CC_STAT_AREA]) >= min_area:
            result |= labels == index
    return result


def infer_face_regions(
    rgb: np.ndarray,
    foreground: np.ndarray,
    model_path: Path,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, tuple[int, int, int, int], dict[int, int]]:
    """Run the local anime-face U-Net and return eye/mouth/face full-image masks."""
    if not model_path.is_file():
        raise FileNotFoundError(f"Face segmentation model not found: {model_path}")

    ys, xs = np.where(foreground)
    height, width = foreground.shape
    bbox_width = int(xs.max() - xs.min() + 1)
    bbox_height = int(ys.max() - ys.min() + 1)
    side = min(width, height, max(64, int(round(max(bbox_width * 1.08, bbox_height * 0.50)))))
    center_x = int(round((xs.min() + xs.max()) / 2.0))
    x0 = max(0, min(width - side, center_x - side // 2))
    y0 = max(0, min(height - side, int(ys.min()) - int(side * 0.03)))
    crop = rgb[y0 : y0 + side, x0 : x0 + side]
    resized = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_LINEAR)
    tensor = (resized.astype(np.float32) / 255.0).transpose(2, 0, 1)[None, ...]

    try:
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("onnxruntime is required for face segmentation.") from exc
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    probabilities = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
    probabilities = cv2.resize(
        probabilities.transpose(1, 2, 0),
        (side, side),
        interpolation=cv2.INTER_LINEAR,
    ).transpose(2, 0, 1)
    labels = probabilities.argmax(axis=0).astype(np.uint8)

    eye_raw = np.zeros_like(foreground)
    eye_raw[y0 : y0 + side, x0 : x0 + side] = labels == 2
    eye_raw &= foreground

    count, components, stats, centers = cv2.connectedComponentsWithStats(
        eye_raw.astype(np.uint8), connectivity=8
    )
    candidates: list[tuple[int, int]] = []
    for index in range(1, count):
        area = int(stats[index, cv2.CC_STAT_AREA])
        cx, cy = centers[index]
        if area < 20:
            continue
        if cy < y0 + side * 0.30 or cy > y0 + side * 0.85:
            continue
        candidates.append((area, index))
    candidates.sort(reverse=True)
    selected = candidates[:2]
    selected.sort(key=lambda item: centers[item[1]][0])

    kernel = np.ones((3, 3), np.uint8)
    eye_l = np.zeros_like(foreground)
    eye_r = np.zeros_like(foreground)
    if len(selected) >= 1:
        eye_l = cv2.dilate((components == selected[0][1]).astype(np.uint8), kernel, iterations=2).astype(bool)
    if len(selected) >= 2:
        eye_r = cv2.dilate((components == selected[1][1]).astype(np.uint8), kernel, iterations=2).astype(bool)
    eye_l &= foreground
    eye_r &= foreground

    mouth_raw = np.zeros_like(foreground)
    mouth_raw[y0 : y0 + side, x0 : x0 + side] = labels == 3
    mouth_raw &= foreground
    count, components, stats, centers = cv2.connectedComponentsWithStats(
        mouth_raw.astype(np.uint8), connectivity=8
    )
    mouth = np.zeros_like(foreground)
    if count > 1:
        index = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if int(stats[index, cv2.CC_STAT_AREA]) >= 10:
            mouth = cv2.dilate((components == index).astype(np.uint8), kernel, iterations=2).astype(bool)
    mouth &= foreground

    face = np.zeros_like(foreground)
    face[y0 : y0 + side, x0 : x0 + side] = labels == 4
    face &= foreground
    class_counts = {
        index: int((labels == index).sum()) for index in range(labels.max() + 1)
    }
    return eye_l, eye_r, mouth, (x0, y0, side, side), class_counts


def build_semantic_labels(
    foreground: np.ndarray,
    colors: dict[str, np.ndarray],
    dress: np.ndarray,
    dress_box: tuple[int, int, int, int],
    eye_l: np.ndarray,
    eye_r: np.ndarray,
    mouth: np.ndarray,
) -> tuple[np.ndarray, dict[str, np.ndarray], dict[str, float]]:
    height, width = foreground.shape
    x0, body_start, dress_width, dress_height = dress_box
    body_bottom = min(height - 1, body_start + dress_height - 1)
    center_x = x0 + dress_width / 2.0
    left_edge, right_edge = row_extents(dress)

    skin = colors["skin"] & foreground
    hair = colors["hair"] & foreground
    neutral = colors["neutral"] & foreground
    yellow = colors["yellow"] & foreground

    arm_top = max(0, body_start - 6)
    arm_bottom = min(body_bottom, body_start + int(dress_height * 0.62))
    yy, xx = np.mgrid[0:height, 0:width]
    arm_zone = (yy >= arm_top) & (yy < arm_bottom)
    outside_dress = (xx < left_edge[:, None] - 1) | (xx > right_edge[:, None] + 1)
    arm_candidates = skin & arm_zone & outside_dress
    arm_candidates = filter_components(arm_candidates.astype(np.uint8), 12).astype(bool)
    arm_l = arm_candidates & (xx < center_x)
    arm_r = arm_candidates & (xx >= center_x)

    body_lower = (yy >= body_start) & (yy <= body_bottom)
    dress_dilated = cv2.dilate(dress.astype(np.uint8), np.ones((5, 5), np.uint8), iterations=1).astype(bool)
    flowers = neutral & body_lower & dress_dilated
    central_skin = (
        skin
        & (yy >= body_start)
        & (yy < body_start + max(8, int(dress_height * 0.16)))
        & (xx >= left_edge[:, None])
        & (xx <= right_edge[:, None])
    )
    body = dress | flowers | central_skin

    hair_extra_bottom = min(height, body_start + int(dress_height * 0.66))
    hair_extra = (
        hair
        & (yy >= body_start)
        & (yy < hair_extra_bottom)
        & (~dress_dilated)
        & (~arm_l)
        & (~arm_r)
    )
    head = (foreground & (yy < body_start + 1)) | hair_extra
    # Long hair may touch the arms. Keep the head's main connected body and
    # let detached dark fragments near the torso fall back to the nearest
    # arm/body seed instead of leaking arm outlines into head.png.
    head_count, head_labels, head_stats, _ = cv2.connectedComponentsWithStats(
        head.astype(np.uint8), connectivity=8
    )
    if head_count > 1:
        head_index = 1 + int(np.argmax(head_stats[1:, cv2.CC_STAT_AREA]))
        head = head_labels == head_index

    leg_top = max(0, body_bottom - 2)
    lower = foreground & (yy >= leg_top)
    lower &= ~dress_dilated
    leg_l = lower & (xx < center_x)
    leg_r = lower & (xx >= center_x)

    labels = np.zeros((height, width), dtype=np.uint8)
    seeds = {
        5: leg_l,
        6: leg_r,
        3: arm_l,
        4: arm_r,
        1: head,
        2: body,
    }
    for label, seed in seeds.items():
        labels[seed] = label

    unassigned = foreground & (labels == 0)
    if unassigned.any():
        distances: dict[int, np.ndarray] = {}
        for label, seed in seeds.items():
            if seed.any():
                distances[label] = cv2.distanceTransform(
                    (1 - seed.astype(np.uint8)).astype(np.uint8),
                    cv2.DIST_L2,
                    5,
                )
        if distances:
            stack = np.stack([distances[label] for label in distances], axis=0)
            order = list(distances)
            nearest = np.argmin(stack, axis=0)
            for position, label in enumerate(order):
                labels[unassigned & (nearest == position)] = label

    parts = {name: labels == label for label, name in LABEL_TO_PART.items()}
    parts["eye_l"] = eye_l
    parts["eye_r"] = eye_r
    parts["mouth"] = mouth
    metrics = {
        "body_start": float(body_start),
        "body_bottom": float(body_bottom),
        "center_x": float(center_x),
    }
    return labels, parts, metrics


def inpaint_face_base(rgb: np.ndarray, eyes: np.ndarray) -> np.ndarray:
    mask = eyes.astype(np.uint8) * 255
    if not mask.any():
        return rgb.copy()
    return cv2.inpaint(rgb, mask, 3, cv2.INPAINT_TELEA)


def transformed_canvas(
    rgb: np.ndarray,
    foreground: np.ndarray,
    fit_ratio: float,
) -> tuple[np.ndarray, np.ndarray, float, int, int]:
    ys, xs = np.where(foreground)
    bbox_width = max(1, int(xs.max() - xs.min() + 1))
    bbox_height = max(1, int(ys.max() - ys.min() + 1))
    scale = min(
        (CANVAS * fit_ratio) / bbox_width,
        (CANVAS * fit_ratio) / bbox_height,
    )
    new_width = max(1, int(round(rgb.shape[1] * scale)))
    new_height = max(1, int(round(rgb.shape[0] * scale)))
    bbox_center_x = (float(xs.min()) + float(xs.max()) + 1.0) / 2.0
    offset_x = int(round(CANVAS / 2.0 - bbox_center_x * scale))
    offset_y = int(round(CANVAS - 2 - (float(ys.max()) + 1.0) * scale))

    resized_rgb = cv2.resize(rgb, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    resized_alpha = cv2.resize(
        foreground.astype(np.uint8) * 255,
        (new_width, new_height),
        interpolation=cv2.INTER_LINEAR,
    )
    canvas = np.zeros((CANVAS, CANVAS, 3), dtype=np.uint8)
    alpha = np.zeros((CANVAS, CANVAS), dtype=np.uint8)
    x1 = max(0, offset_x)
    y1 = max(0, offset_y)
    x2 = min(CANVAS, offset_x + new_width)
    y2 = min(CANVAS, offset_y + new_height)
    sx1 = x1 - offset_x
    sy1 = y1 - offset_y
    sx2 = sx1 + (x2 - x1)
    sy2 = sy1 + (y2 - y1)
    canvas[y1:y2, x1:x2] = resized_rgb[sy1:sy2, sx1:sx2]
    alpha[y1:y2, x1:x2] = resized_alpha[sy1:sy2, sx1:sx2]
    return canvas, alpha, scale, offset_x, offset_y


def transform_point(x: float, y: float, scale: float, offset_x: int, offset_y: int) -> list[int]:
    return [
        int(round(offset_x + x * scale)),
        int(round(offset_y + y * scale)),
    ]


def mask_bbox_center_top(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.where(mask)
    if not len(xs):
        return 0.0, 0.0
    return float((xs.min() + xs.max()) / 2.0), float(ys.min())


def mask_centroid(mask: np.ndarray) -> tuple[float, float]:
    ys, xs = np.where(mask)
    if not len(xs):
        return 0.0, 0.0
    return float(xs.mean()), float(ys.mean())


def make_pivots(
    parts: dict[str, np.ndarray],
    metrics: dict[str, float],
    scale: float,
    offset_x: int,
    offset_y: int,
) -> dict[str, list[int]]:
    pivots: dict[str, list[int]] = {}
    head_x, head_top = mask_bbox_center_top(parts["head"])
    body_x, body_top = mask_bbox_center_top(parts["body"])
    pivots["head"] = transform_point(
        head_x,
        min(metrics["body_start"], head_top + (metrics["body_bottom"] - head_top) * 0.45),
        scale,
        offset_x,
        offset_y,
    )
    pivots["body"] = transform_point(
        body_x,
        (metrics["body_start"] + metrics["body_bottom"]) / 2.0,
        scale,
        offset_x,
        offset_y,
    )
    for name in ("arm_l", "arm_r", "leg_l", "leg_r"):
        pivot_x, pivot_y = mask_bbox_center_top(parts[name])
        pivots[name] = transform_point(pivot_x, pivot_y, scale, offset_x, offset_y)
    for name in ("eye_l", "eye_r", "mouth"):
        pivot_x, pivot_y = mask_centroid(parts[name])
        pivots[name] = transform_point(pivot_x, pivot_y, scale, offset_x, offset_y)
    return pivots


def render_parts(
    rgb: np.ndarray,
    base_rgb: np.ndarray,
    parts: dict[str, np.ndarray],
    scale: float,
    offset_x: int,
    offset_y: int,
) -> dict[str, np.ndarray]:
    height, width = rgb.shape[:2]
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    rendered: dict[str, np.ndarray] = {}
    source_original = cv2.resize(rgb, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    source_base = cv2.resize(base_rgb, (new_width, new_height), interpolation=cv2.INTER_CUBIC)
    for name in PART_NAMES:
        mask = parts[name].astype(np.uint8) * 255
        resized_mask = cv2.resize(mask, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        resized_mask[resized_mask < 10] = 0
        rgba = np.zeros((CANVAS, CANVAS, 4), dtype=np.uint8)
        x1 = max(0, offset_x)
        y1 = max(0, offset_y)
        x2 = min(CANVAS, offset_x + new_width)
        y2 = min(CANVAS, offset_y + new_height)
        sx1 = x1 - offset_x
        sy1 = y1 - offset_y
        sx2 = sx1 + (x2 - x1)
        sy2 = sy1 + (y2 - y1)
        source = source_base if name == "head" else source_original
        rgba[y1:y2, x1:x2, :3] = source[sy1:sy2, sx1:sx2]
        rgba[y1:y2, x1:x2, 3] = resized_mask[sy1:sy2, sx1:sx2]
        rendered[name] = rgba
    return rendered


def composite(parts: dict[str, np.ndarray]) -> np.ndarray:
    height = width = CANVAS
    checker = np.zeros((height, width, 3), dtype=np.uint8)
    cell = 24
    for y in range(0, height, cell):
        for x in range(0, width, cell):
            value = 52 if ((x // cell + y // cell) % 2 == 0) else 36
            checker[y : y + cell, x : x + cell] = value
    result = checker.astype(np.float32)
    order = ("leg_l", "leg_r", "arm_l", "arm_r", "body", "head", "eye_l", "eye_r", "mouth")
    for name in order:
        rgba = parts[name]
        alpha = rgba[:, :, 3:4].astype(np.float32) / 255.0
        result = rgba[:, :, :3].astype(np.float32) * alpha + result * (1.0 - alpha)
    return np.clip(result, 0, 255).astype(np.uint8)


def load_manual_masks(
    directory: Path | None,
    shape: tuple[int, int],
) -> dict[str, np.ndarray]:
    if directory is None:
        return {}
    result: dict[str, np.ndarray] = {}
    for name in PART_NAMES:
        path = directory / f"{name}.png"
        if not path.is_file():
            continue
        with Image.open(path) as image:
            mask = np.asarray(image.convert("L"))
        if mask.shape != shape:
            mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
        result[name] = mask > 16
    return result


def character_document(
    character_id: str,
    name: str,
    source_path: Path,
    pivots: dict[str, list[int]],
) -> dict:
    parts = {}
    for part_name in PART_NAMES:
        parts[part_name] = {
            "file": f"parts/{part_name}.png",
            "pivot": pivots[part_name],
        }
    return {
        "id": character_id,
        "contract_version": "1.0",
        "rig": {"parts": parts},
        "persona": {
            "name": name,
            "setting": "\u4f60\u662f\u4e00\u4e2a\u7531\u5e73\u9762\u5361\u901a\u56fe\u62c6\u5206\u751f\u6210\u7684\u684c\u9762\u5ba0\u7269\u3002",
        },
        "knowledge": [
            {"key": "source", "value": str(source_path)},
            {"key": "decomposition", "value": "flat image to nine contract parts"},
        ],
        "idle_lines": [
            {"text": "\u4eca\u5929\u4e5f\u8981\u4e00\u8d77\u5199\u4ee3\u7801\u5417\uff1f", "action": "wave", "weight": 2},
            {"text": "\u55ef\u2026\u2026\u53d1\u4f1a\u513f\u5446\u3002", "action": "nod", "weight": 2},
            {"text": "\u6211\u521a\u521a\u662f\u4e0d\u662f\u7728\u773c\u4e86\uff1f", "action": "blink", "weight": 1},
            {"text": "\u4f38\u4e2a\u61d2\u8170\uff5e", "action": "yawn", "weight": 1},
            {"text": "\u522b\u4e00\u76f4\u76ef\u7740\u5c4f\u5e55\u5566\u3002", "action": "shake_head", "weight": 1},
        ],
    }


def validate_character(output_dir: Path) -> tuple[bool, str]:
    command = [
        sys.executable,
        str(ROOT / "tools" / "validate.py"),
        "character",
        str(output_dir),
        "--actions-dir",
        str(ROOT / "assets" / "actions"),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def save_debug(
    debug_dir: Path,
    foreground: np.ndarray,
    labels: np.ndarray,
    parts: dict[str, np.ndarray],
) -> None:
    debug_dir.mkdir(parents=True, exist_ok=True)
    Image.fromarray((foreground.astype(np.uint8) * 255)).save(debug_dir / "foreground.png")
    palette = DEBUG_PALETTE[labels]
    Image.fromarray(palette).save(debug_dir / "semantic_labels.png")
    for name in PART_NAMES:
        mask = (parts[name].astype(np.uint8) * 255)
        Image.fromarray(mask).save(debug_dir / f"{name}_mask.png")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Decompose a flat cartoon image into nine contract v1 parts."
    )
    parser.add_argument("--input", "-i", type=Path, required=True, help="Input image path.")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=ROOT / "photo_cartoon_instance" / "flat_char_01",
        help="Output character directory.",
    )
    parser.add_argument("--character-id", default="flat_char_01")
    parser.add_argument("--name", default="\u5e73\u9762\u89d2\u8272 01")
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--masks-dir", type=Path, default=None)
    parser.add_argument("--fit-ratio", type=float, default=0.94)
    parser.add_argument("--debug-dir", type=Path, default=None)
    parser.add_argument("--no-validate", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = build_parser().parse_args(argv)
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    if not input_path.is_file():
        print(f"Input image not found: {input_path}", file=sys.stderr)
        return 1

    output_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    model_path = args.model if args.model.is_absolute() else ROOT / args.model
    masks_dir = None if args.masks_dir is None else (args.masks_dir if args.masks_dir.is_absolute() else ROOT / args.masks_dir)
    debug_dir = None if args.debug_dir is None else (args.debug_dir if args.debug_dir.is_absolute() else ROOT / args.debug_dir)

    character_id = re.sub(r"[^A-Za-z0-9_-]+", "_", args.character_id).strip("_")
    if not character_id:
        character_id = "flat_char_01"

    try:
        rgba = read_rgba(input_path)
        rgb = rgba[:, :, :3]
        foreground, used_alpha = detect_foreground(rgb, rgba[:, :, 3])
        colors = color_masks(rgb)
        dress, dress_box = select_dress_component(colors["yellow"] & foreground)
        eye_l, eye_r, mouth, face_crop_box, face_counts = infer_face_regions(
            rgb, foreground, model_path
        )
        labels, parts, metrics = build_semantic_labels(
            foreground,
            colors,
            dress,
            dress_box,
            eye_l,
            eye_r,
            mouth,
        )
        manual = load_manual_masks(masks_dir, foreground.shape)
        parts.update(manual)
        empty_parts = [name for name in PART_NAMES if not parts[name].any()]
        if empty_parts:
            raise ValueError(
                "Missing or empty semantic parts: "
                + ", ".join(empty_parts)
                + ". Provide corrected masks with --masks-dir."
            )
        base_rgb = inpaint_face_base(rgb, parts["eye_l"] | parts["eye_r"] | parts["mouth"])
        canvas_rgb, canvas_alpha, scale, offset_x, offset_y = transformed_canvas(
            rgb, foreground, args.fit_ratio
        )
        base_canvas, _, _, _, _ = transformed_canvas(base_rgb, foreground, args.fit_ratio)
        rendered = render_parts(rgb, base_rgb, parts, scale, offset_x, offset_y)
        preview = composite(rendered)
        pivots = make_pivots(parts, metrics, scale, offset_x, offset_y)
        document = character_document(character_id, args.name, input_path, pivots)

        parts_dir = output_dir / "parts"
        parts_dir.mkdir(parents=True, exist_ok=True)
        for name in PART_NAMES:
            Image.fromarray(rendered[name], mode="RGBA").save(parts_dir / f"{name}.png")
        (output_dir / "character.json").write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        Image.fromarray(preview, mode="RGB").save(output_dir / "preview.png")

        if debug_dir is not None:
            save_debug(debug_dir, foreground, labels, parts)
            Image.fromarray(canvas_rgb, mode="RGB").save(debug_dir / "canvas_rgb.png")
            Image.fromarray(base_canvas, mode="RGB").save(debug_dir / "inpainted_base.png")
            (debug_dir / "stats.json").write_text(
                json.dumps(
                    {
                        "used_existing_alpha": used_alpha,
                        "face_crop_box": face_crop_box,
                        "face_class_pixels": face_counts,
                        "dress_box": dress_box,
                        "scale": scale,
                        "offset": [offset_x, offset_y],
                        "foreground_pixels": int(foreground.sum()),
                        "pivots": pivots,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
    except Exception as exc:
        print(f"Decomposition failed: {exc}", file=sys.stderr)
        return 1

    validation_ok = True
    validation_output = ""
    if not args.no_validate:
        validation_ok, validation_output = validate_character(output_dir)

    print("=== flat_cartoon_split9 ===")
    print(f"Input: {input_path}")
    print(f"Output: {output_dir}")
    print(f"Character id: {character_id}")
    print(f"Existing alpha used: {used_alpha}")
    print(f"Scale: {scale:.5f}, offset: ({offset_x}, {offset_y})")
    print("Pivots: " + json.dumps(pivots, ensure_ascii=False))
    print(f"Contract validation: {'PASS' if validation_ok else 'FAIL'}")
    if not validation_ok and validation_output:
        print(validation_output.strip())
    return 0 if validation_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())