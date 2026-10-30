# -*- coding: utf-8 -*-
"""Step B 遮挡修复：为每个下层部件补齐被上层遮住的区域（用自身可见像素 inpaint）。

可见掩码 ≠ 部件完整掩码。例如身体被头发遮住的肩膀、腿被短裤遮住的大腿顶，
本模块把这些被遮挡区域补进下层部件，并用该部件自己的可见像素填充，
使部件旋转时不会露出透明空洞。
"""
from __future__ import annotations

import cv2
import numpy as np

# 从下到上的绘制顺序（与契约 z 一致）
Z_ORDER = ["leg_l", "leg_r", "arm_l", "arm_r", "body", "head", "eye_l", "eye_r", "mouth"]


def complete_parts(rgb: np.ndarray, parts: dict) -> tuple[dict, dict]:
    """补全各部件掩码，并生成每个部件的 inpaint 源图。

    参数:
        rgb: 源图 (H, W, 3) uint8
        parts: {部件名: 可见掩码(bool)}

    返回:
        (completed_masks, part_sources)
        completed_masks: {部件名: 完整掩码(bool)}（可见 + 被遮挡区域）
        part_sources: {部件名: (H, W, 3) uint8}（可见像素=源图，遮挡区域=inpaint 填充）
    """
    H, W = rgb.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    completed = {name: parts[name].copy() for name in parts if parts[name].any()}

    # 1) 对每个下层部件，把上层部件落在其包围盒内的像素补进去（= 被遮挡区域）
    for i, L in enumerate(Z_ORDER):
        if L not in completed or not completed[L].any():
            continue
        ys, xs = np.where(completed[L])
        y0, y1, x0, x1 = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
        occluded = np.zeros((H, W), bool)
        for H_part in Z_ORDER[i + 1:]:
            if H_part in parts and parts[H_part].any():
                occluded |= parts[H_part] & (yy >= y0) & (yy <= y1) & (xx >= x0) & (xx <= x1)
        occluded &= ~completed[L]
        if occluded.any():
            completed[L] = completed[L] | occluded

    # 2) 为每个部件生成 inpaint 源图（背景用部件平均色，避免黑背景污染 inpaint）
    part_sources = {}
    for name in parts:
        vis = parts[name]
        full = completed.get(name, vis.copy())
        if not full.any():
            part_sources[name] = rgb.copy()
            continue
        occ = full & ~vis
        img = np.zeros_like(rgb)
        img[vis] = rgb[vis]
        avg = rgb[vis].mean(axis=0).astype(np.uint8) if vis.any() else np.zeros(3, np.uint8)
        bg = ~full
        img[bg] = avg
        if occ.any():
            img = cv2.inpaint(img, (occ.astype(np.uint8) * 255), 3, cv2.INPAINT_TELEA)
        part_sources[name] = img

    return completed, part_sources


from tools.step2.flat_cartoon_split9 import CANVAS, PART_NAMES


def render_completed_parts(part_sources, completed, scale, offset_x, offset_y):
    """按完整掩码 + inpaint 源图渲染 9 个部件为 512x512 RGBA。"""
    height, width = next(iter(part_sources.values())).shape[:2]
    new_width = max(1, int(round(width * scale)))
    new_height = max(1, int(round(height * scale)))
    rendered = {}
    for name in PART_NAMES:
        if name not in completed or not completed[name].any():
            rendered[name] = np.zeros((CANVAS, CANVAS, 4), np.uint8)
            continue
        mask = completed[name].astype(np.uint8) * 255
        resized_mask = cv2.resize(mask, (new_width, new_height), interpolation=cv2.INTER_LINEAR)
        resized_mask[resized_mask < 10] = 0
        source = cv2.resize(part_sources[name], (new_width, new_height), interpolation=cv2.INTER_CUBIC)
        rgba = np.zeros((CANVAS, CANVAS, 4), np.uint8)
        x1 = max(0, offset_x)
        y1 = max(0, offset_y)
        x2 = min(CANVAS, offset_x + new_width)
        y2 = min(CANVAS, offset_y + new_height)
        sx1 = x1 - offset_x
        sy1 = y1 - offset_y
        sx2 = sx1 + (x2 - x1)
        sy2 = sy1 + (y2 - y1)
        rgba[y1:y2, x1:x2, :3] = source[sy1:sy2, sx1:sx2]
        rgba[y1:y2, x1:x2, 3] = resized_mask[sy1:sy2, sx1:sx2]
        rendered[name] = rgba
    return rendered
