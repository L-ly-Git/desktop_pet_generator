# -*- coding: utf-8 -*-
"""Plan B：SAM 提示式分割 + 部件检测（几何锚点）+ 几何规则 —— 全自动 9 部件分层。

设计（务实版）：
  1) 部件检测：由 A-pose 剪影 + 比例，先求一套「几何带」初始掩码（头/身/臂/腿）。
     这一步不依赖颜色，对黑西装、长裙、皮肤色腿等都稳健。
  2) SAM 提示式分割：每个部件用「正点(该部件锚点) + 负点(其余部件锚点)」跑 MobileSAM，
     得到 4 个候选掩码。
  3) 几何规则判归属：在 4 个候选里，选「与几何带 IoU 最高、且包含正点」的那个；
     若 SAM 与几何差异过大（不可靠），回退几何带掩码。
  4) 收尾：只保留锚点连通域、按带裁剪、按 z 顺序消解重叠、未分配前景按最近部件补齐。

眼睛/嘴仍由 anime_face_seg 单独处理。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.step2.sam_segment import SAMSegmenter

PART_ORDER = ["leg_l", "leg_r", "arm_l", "arm_r", "body", "head"]  # 从下到上（z 顺序）
LABEL_OF = {"head": 1, "body": 2, "arm_l": 3, "arm_r": 4, "leg_l": 5, "leg_r": 6}

# Q版 A-pose 比例带（相对角色高度 fg_h，从头顶 top 起算）
HEAD_BOTTOM = 0.30      # 头/肩分界（脖子）
HIP_Y = 0.58            # 髋（腿起点）
BODY_HALF = 0.18        # 躯干半宽（相对角色宽度 fg_w）


def detect_anchors(foreground: np.ndarray) -> dict:
    ys, xs = np.where(foreground)
    top, bottom = int(ys.min()), int(ys.max())
    left, right = int(xs.min()), int(xs.max())
    fg_h = bottom - top + 1
    fg_w = right - left + 1
    center_x = (left + right) / 2.0
    return {
        "top": top, "bottom": bottom, "left": left, "right": right,
        "fg_h": fg_h, "fg_w": fg_w, "center_x": center_x,
        "head_bottom": top + int(HEAD_BOTTOM * fg_h),
        "shoulder_top": top + int(HEAD_BOTTOM * fg_h),
        "shoulder_bot": top + int(HIP_Y * fg_h),
        "hip_y": top + int(HIP_Y * fg_h),
        "leg_top": top + int(HIP_Y * fg_h),
    }


def _snap_to_fg(mask: np.ndarray, cx: float, cy: float) -> tuple[float, float]:
    """把质心吸附到掩码内最近的像素上（质心可能落在凹形区域外）。"""
    ys, xs = np.where(mask)
    if not len(ys):
        return (cx, cy)
    idx = int(np.argmin((xs - cx) ** 2 + (ys - cy) ** 2))
    return (float(xs[idx]), float(ys[idx]))


def geometric_parts(a: dict, foreground: np.ndarray) -> dict[str, np.ndarray]:
    """几何带初始掩码（不依赖颜色）。"""
    H, W = foreground.shape
    yy, xx = np.mgrid[0:H, 0:W]
    cx = a["center_x"]
    hb, hp = a["head_bottom"], a["hip_y"]
    half = BODY_HALF * a["fg_w"]

    head = foreground & (yy < hb)
    central = (xx >= cx - half) & (xx <= cx + half)
    mid = (yy >= hb) & (yy < hp)
    body = foreground & mid & central
    arm_l = foreground & mid & (~central) & (xx < cx)
    arm_r = foreground & mid & (~central) & (xx >= cx)
    low = (yy >= hp)
    leg_l = foreground & low & (xx < cx)
    leg_r = foreground & low & (xx >= cx)
    return {"head": head, "body": body, "arm_l": arm_l, "arm_r": arm_r,
            "leg_l": leg_l, "leg_r": leg_r}


def part_anchors(a: dict, foreground: np.ndarray) -> dict[str, tuple[float, float]]:
    parts = geometric_parts(a, foreground)
    out = {}
    for name in PART_ORDER:
        m = parts[name]
        ys, xs = np.where(m)
        if len(ys):
            out[name] = _snap_to_fg(m, float(xs.mean()), float(ys.mean()))
        else:
            # 兜底：用带中心
            if name == "head":
                out[name] = (a["center_x"], a["top"] + 0.16 * a["fg_h"])
            elif name == "body":
                out[name] = (a["center_x"], (a["head_bottom"] + a["hip_y"]) / 2.0)
            elif name == "arm_l":
                out[name] = ((a["left"] + a["center_x"]) / 2.0, (a["shoulder_top"] + a["shoulder_bot"]) / 2.0)
            elif name == "arm_r":
                out[name] = ((a["center_x"] + a["right"]) / 2.0, (a["shoulder_top"] + a["shoulder_bot"]) / 2.0)
            elif name == "leg_l":
                out[name] = ((a["left"] + a["center_x"]) / 2.0, (a["leg_top"] + a["bottom"]) / 2.0)
            else:
                out[name] = ((a["center_x"] + a["right"]) / 2.0, (a["leg_top"] + a["bottom"]) / 2.0)
    return out


def build_prompts(name: str, anchors: dict[str, tuple[float, float]], a: dict):
    others = [n for n in PART_ORDER if n != name]
    pos = [anchors[name]]
    neg = [anchors[n] for n in others if anchors[n] is not None]
    if name in ("arm_l", "arm_r"):
        neg.append((a["center_x"], a["shoulder_top"] + 0.12 * a["fg_h"]))
        neg.append((a["center_x"], a["shoulder_top"] + 0.28 * a["fg_h"]))
    return pos, neg


def _iou(m1: np.ndarray, m2: np.ndarray) -> float:
    inter = int((m1 & m2).sum())
    union = int((m1 | m2).sum())
    return inter / union if union else 0.0


def _keep_anchor_component(mask: np.ndarray, anchor: tuple[float, float]) -> np.ndarray:
    if not mask.any():
        return mask
    cnt, comps, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if cnt <= 1:
        return mask
    ax, ay = int(round(anchor[0])), int(round(anchor[1]))
    if 0 <= ay < mask.shape[0] and 0 <= ax < mask.shape[1] and mask[ay, ax]:
        keep = comps[ay, ax]
    else:
        keep = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    return comps == keep


def _refine_with_sam(sam, name, anchors, geo, a, foreground) -> np.ndarray:
    """用 SAM 候选掩码在几何带的指导下细化部件；不可靠则回退几何带。"""
    pos, neg = build_prompts(name, anchors, a)
    try:
        cands, ious = sam.predict_all(pos + neg, [1] * len(pos) + [0] * len(neg))
    except Exception:
        return geo
    best_mask = geo
    best_score = 0.55  # SAM 必须明显优于几何才替换
    ax, ay = int(round(pos[0][0])), int(round(pos[0][1]))
    for m in cands:
        m = m & foreground
        if not m.any():
            continue
        score = _iou(m, geo)
        contains = bool(m[ay, ax]) if 0 <= ay < m.shape[0] and 0 <= ax < m.shape[1] else False
        if contains and score > best_score:
            best_score = score
            best_mask = m
    return best_mask


def segment_parts(rgb: np.ndarray, foreground: np.ndarray, eye_l, eye_r, mouth):
    """返回 (labels, parts, metrics)，与 split_general 的 build_labels* 对齐。"""
    a = detect_anchors(foreground)
    geo = geometric_parts(a, foreground)
    anchors = part_anchors(a, foreground)

    sam_rgb = rgb.copy()
    fg_mean = rgb[foreground].mean()
    sam_rgb[~foreground] = (0, 0, 0) if fg_mean > 128 else (255, 255, 255)
    sam = SAMSegmenter()
    sam.encode(sam_rgb)

    parts = {}
    for name in PART_ORDER:
        if not geo[name].any():
            parts[name] = geo[name]
            continue
        refined = _refine_with_sam(sam, name, anchors, geo[name], a, foreground)
        refined = _keep_anchor_component(refined, anchors[name])
        parts[name] = refined

    # 按带裁剪（几何硬约束，防止 SAM 越界）
    _clip_bands(parts, a)
    labels, parts = _resolve_and_fill(foreground, parts)

    body_ys, body_xs = np.where(parts["body"]) if parts["body"].any() else (np.array([]), np.array([]))
    metrics = {
        "body_start": float(body_ys.min()) if len(body_ys) else float(a["head_bottom"]),
        "body_bottom": float(body_ys.max()) if len(body_ys) else float(a["hip_y"]),
        "center_x": float(a["center_x"]),
    }
    return labels, parts, metrics


def _clip_bands(parts: dict, a: dict) -> None:
    H, W = next(iter(parts.values())).shape
    yy, _ = np.mgrid[0:H, 0:W]
    head_hi = a["hip_y"] + int(0.10 * a["fg_h"])
    body_lo = a["head_bottom"] - int(0.06 * a["fg_h"])
    body_hi = a["hip_y"] + int(0.18 * a["fg_h"])
    arm_lo = a["shoulder_top"] - int(0.08 * a["fg_h"])
    arm_hi = a["hip_y"] + int(0.06 * a["fg_h"])
    leg_lo = a["hip_y"] - int(0.06 * a["fg_h"])

    parts["head"] &= yy < head_hi
    parts["body"] &= (yy >= body_lo) & (yy < body_hi)
    parts["arm_l"] &= (yy >= arm_lo) & (yy < arm_hi)
    parts["arm_r"] &= (yy >= arm_lo) & (yy < arm_hi)
    parts["leg_l"] &= yy >= leg_lo
    parts["leg_r"] &= yy >= leg_lo


def _resolve_and_fill(foreground: np.ndarray, parts: dict) -> tuple[np.ndarray, dict]:
    H, W = foreground.shape
    labels = np.zeros((H, W), np.uint8)
    for name in PART_ORDER:
        if parts[name].any():
            labels[parts[name]] = LABEL_OF[name]
    unassigned = foreground & (labels == 0)
    if unassigned.any():
        seeds = {LABEL_OF[n]: parts[n] for n in parts if parts[n].any()}
        if seeds:
            dists = {}
            for lab, s in seeds.items():
                dists[lab] = cv2.distanceTransform((1 - s.astype(np.uint8)).astype(np.uint8), cv2.DIST_L2, 5)
            stack = np.stack(list(dists.values()), axis=0)
            order = list(dists)
            nearest = np.argmin(stack, axis=0)
            for pos, lab in enumerate(order):
                labels[unassigned & (nearest == pos)] = lab
    final = {n: labels == LABEL_OF[n] for n in LABEL_OF}
    return labels, final


def _debug_vis(rgb, foreground, labels, parts, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    vis = np.zeros((rgb.shape[0], rgb.shape[1], 3), np.uint8)
    palette = {1: (230, 150, 80), 2: (245, 205, 70), 3: (90, 180, 245),
               4: (70, 130, 230), 5: (120, 220, 130), 6: (70, 180, 100)}
    for lab, col in palette.items():
        vis[labels == lab] = col
    from PIL import Image
    Image.fromarray(vis, "RGB").save(out_dir / "debug_labels.png")
    for n in parts:
        Image.fromarray(parts[n].astype(np.uint8) * 255, "L").save(out_dir / f"mask_{n}.png")
    overlay = (rgb * 0.4 + vis * 0.6).astype(np.uint8)
    Image.fromarray(overlay, "RGB").save(out_dir / "debug_overlay.png")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-dir", default=None)
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    from PIL import Image
    from tools.step2.flat_cartoon_split9 import read_rgba, detect_foreground
    from tools.step2.split_general import infer_face_loose

    rgba = read_rgba(Path(args.input))
    rgb = rgba[:, :, :3]
    foreground, used = detect_foreground(rgb, rgba[:, :, 3])
    model = ROOT / "models" / "anime_face_seg" / "anime_face_unet.onnx"
    eye_l, eye_r, mouth = infer_face_loose(rgb, foreground, model)
    labels, parts, metrics = segment_parts(rgb, foreground, eye_l, eye_r, mouth)
    parts["eye_l"], parts["eye_r"], parts["mouth"] = eye_l, eye_r, mouth

    out_dir = Path(args.output_dir) if args.output_dir else Path(args.input).with_name("sam_debug")
    _debug_vis(rgb, foreground, labels, parts, out_dir)
    print("=== sam_auto_parts ===")
    print("input:", args.input)
    print("output:", out_dir)
    for n in PART_ORDER + ["eye_l", "eye_r", "mouth"]:
        print(f"  {n}: {int(parts[n].sum())} px")
    print("metrics:", metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
