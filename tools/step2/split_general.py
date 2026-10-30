# -*- coding: utf-8 -*-
"""通用平面卡通 -> 9 部件拆分（不限黄色连衣裙示例）。

复用 flat_cartoon_split9 的底层函数；服装区域用"主体色聚类 + 肤色/发色剔除"泛化。
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
import onnxruntime as ort
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from tools.step2.occlusion import complete_parts, render_completed_parts
from tools.step2.human_parsing import parse_parts
from tools.step2.sam_auto_parts import segment_parts as sam_segment_parts
from tools.step2.flat_cartoon_split9 import (
    CANVAS,
    PART_NAMES,
    read_rgba,
    detect_foreground,
    fill_closed_holes,
    filter_components,
    row_extents,
    infer_face_regions,
    inpaint_face_base,
    transformed_canvas,
    transform_point,
    mask_bbox_center_top,
    mask_centroid,
    render_parts,
    composite,
)

DEFAULT_MODEL = ROOT / "models" / "anime_face_seg" / "anime_face_unet.onnx"


def skin_mask(rgb: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    return (v >= 165) & (h >= 4) & (h <= 19) & (s >= 20) & (s <= 165)


def hair_mask(rgb: np.ndarray) -> np.ndarray:
    """深色/暖色发：暗色(黑/深棕) 或 暖色高饱和。"""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    h, s, v = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    dark = v < 120
    warm = (v < 195) & (h >= 5) & (h <= 35) & (s >= 40)
    return dark | warm


def infer_face_loose(rgb, foreground, model_path):
    """与 flat 版一致的人脸分割，但放宽眼睛位置过滤，适配大眼 Q 版。"""
    ys, xs = np.where(foreground)
    h, w = foreground.shape
    bw = xs.max() - xs.min() + 1
    bh = ys.max() - ys.min() + 1
    side = min(w, h, max(64, int(round(max(bw * 1.08, bh * 0.5)))))
    cx = int(round((xs.min() + xs.max()) / 2.0))
    x0 = max(0, min(w - side, cx - side // 2))
    y0 = max(0, min(h - side, int(ys.min()) - int(side * 0.03)))
    crop = rgb[y0:y0 + side, x0:x0 + side]
    res = cv2.resize(crop, (512, 512), interpolation=cv2.INTER_LINEAR)
    tensor = (res.astype(np.float32) / 255.0).transpose(2, 0, 1)[None]
    session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
    probs = session.run(None, {session.get_inputs()[0].name: tensor})[0][0]
    probs = cv2.resize(probs.transpose(1, 2, 0), (side, side), interpolation=cv2.INTER_LINEAR).transpose(2, 0, 1)
    labels = probs.argmax(axis=0)

    def to_full(cls):
        m = np.zeros((h, w), bool)
        m[y0:y0 + side, x0:x0 + side] = (labels == cls)
        return m & foreground

    eye = to_full(2)
    cnt, comps, stats, centers = cv2.connectedComponentsWithStats(eye.astype(np.uint8), 8)
    cand = []
    for i in range(1, cnt):
        a = int(stats[i, cv2.CC_STAT_AREA])
        _x, cy = centers[i]
        if a < 15 or cy < y0 or cy > y0 + side * 0.9:
            continue
        cand.append((a, i))
    cand.sort(reverse=True)
    sel = cand[:2]
    sel.sort(key=lambda it: centers[it[1]][0])
    k = np.ones((3, 3), np.uint8)
    eye_l = cv2.dilate((comps == sel[0][1]).astype(np.uint8), k, 2).astype(bool) if len(sel) >= 1 else np.zeros((h, w), bool)
    eye_r = cv2.dilate((comps == sel[1][1]).astype(np.uint8), k, 2).astype(bool) if len(sel) >= 2 else np.zeros((h, w), bool)

    mouth = to_full(3)
    cnt, comps, stats, centers = cv2.connectedComponentsWithStats(mouth.astype(np.uint8), 8)
    m = np.zeros((h, w), bool)
    if cnt > 1:
        i = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        if int(stats[i, cv2.CC_STAT_AREA]) >= 8:
            m = cv2.dilate((comps == i).astype(np.uint8), k, 2).astype(bool)
    return eye_l & foreground, eye_r & foreground, m & foreground


def detect_body_region(rgb, foreground, skin, hair):
    """主体服装区域：头部以下、非皮肤非头发的前景中，主体色聚类。"""
    h, w = rgb.shape[:2]
    ys, xs = np.where(foreground)
    top, bottom = int(ys.min()), int(ys.max())
    face_bottom = top + int((bottom - top) * 0.40)
    yy = np.arange(h)[:, None]
    region = foreground & (yy >= face_bottom) & (~skin) & (~hair)
    if int(region.sum()) < 200:
        raise ValueError("Could not locate the main clothing region.")
    px = rgb[region].astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.5)
    _c, labels, centers = cv2.kmeans(px, 3, None, criteria, 3, cv2.KMEANS_PP_CENTERS)
    counts = np.bincount(labels.flatten(), minlength=len(centers))
    main = int(np.argmax(counts))
    color = centers[main]
    dist = np.linalg.norm(rgb.astype(np.float32) - color, axis=2)
    mask = region & (dist < 55)
    mask = filter_components(mask.astype(np.uint8), 120).astype(bool)
    ys2, xs2 = np.where(mask)
    if not len(ys2):
        raise ValueError("Could not locate the main clothing region.")
    x, y, bw, bh = xs2.min(), ys2.min(), xs2.max() - xs2.min() + 1, ys2.max() - ys2.min() + 1
    return mask, (int(x), int(y), int(bw), int(bh))


def build_labels_parser(foreground, parse, eye_l, eye_r, mouth):
    """用人体解析结果构建 9 部件（head/body/arms/legs 来自解析，eyes/mouth 来自人脸分割）。"""
    h, w = foreground.shape
    ys, xs = np.where(foreground)
    center_x = (xs.min() + xs.max()) / 2.0 if len(xs) else 256.0

    parts = {
        "head": parse["head"] & foreground,
        "body": parse["body"] & foreground,
        "arm_l": parse["arm_l"] & foreground,
        "arm_r": parse["arm_r"] & foreground,
        "leg_l": parse["leg_l"] & foreground,
        "leg_r": parse["leg_r"] & foreground,
    }
    # 未分配的前景（解析漏掉的像素，如脖子）按最近部件分配
    assigned = np.zeros((h, w), bool)
    for name in ("head", "body", "arm_l", "arm_r", "leg_l", "leg_r"):
        assigned |= parts[name]
    unassigned = foreground & ~assigned
    if unassigned.any():
        seeds = {n: parts[n] for n in parts if parts[n].any()}
        if seeds:
            dists = {}
            for n, s in seeds.items():
                dists[n] = cv2.distanceTransform((1 - s.astype(np.uint8)).astype(np.uint8), cv2.DIST_L2, 5)
            stack = np.stack(list(dists.values()), axis=0)
            order = list(dists)
            nearest = np.argmin(stack, axis=0)
            for pos, n in enumerate(order):
                parts[n] = parts[n] | (unassigned & (nearest == pos))

    parts["eye_l"] = eye_l
    parts["eye_r"] = eye_r
    parts["mouth"] = mouth

    body_ys, body_xs = np.where(parts["body"]) if parts["body"].any() else (np.array([]), np.array([]))
    metrics = {
        "body_start": float(body_ys.min()) if len(body_ys) else float(foreground.shape[0] * 0.4),
        "body_bottom": float(body_ys.max()) if len(body_ys) else float(foreground.shape[0] * 0.6),
        "center_x": float(center_x),
    }
    labels = np.zeros((h, w), np.uint8)
    for lab, n in {1: "head", 2: "body", 3: "arm_l", 4: "arm_r", 5: "leg_l", 6: "leg_r"}.items():
        labels[parts[n]] = lab
    return labels, parts, metrics


def build_labels(foreground, rgb, skin, hair, body, body_box, eye_l, eye_r, mouth):
    h, w = foreground.shape
    x0, body_start, body_w, body_h = body_box
    body_bottom = min(h - 1, body_start + body_h - 1)
    center_x = x0 + body_w / 2.0
    yy, xx = np.mgrid[0:h, 0:w]

    # 手臂：躯干外侧的肤色，在 body 上段
    left_edge, right_edge = row_extents(body)
    arm_top = max(0, body_start - 6)
    arm_bottom = min(body_bottom, body_start + int(body_h * 0.62))
    arm_zone = (yy >= arm_top) & (yy < arm_bottom)
    outside = (xx < left_edge[:, None] - 1) | (xx > right_edge[:, None] + 1)
    arm_candidates = skin & foreground & arm_zone & outside
    arm_candidates = filter_components(arm_candidates.astype(np.uint8), 12).astype(bool)
    arm_l = arm_candidates & (xx < center_x)
    arm_r = arm_candidates & (xx >= center_x)

    # 身体 = 服装区域 + 其上方的中性/深色贴片 + 中央肤色(领口)
    body_lower = (yy >= body_start) & (yy <= body_bottom)
    body_dilated = cv2.dilate(body.astype(np.uint8), np.ones((5, 5), np.uint8), 1).astype(bool)
    extra = (~skin) & foreground & body_lower & body_dilated
    central_skin = skin & (yy >= body_start) & (yy < body_start + max(8, int(body_h * 0.16))) \
        & (xx >= left_edge[:, None]) & (xx <= right_edge[:, None])
    body = body | extra | central_skin

    # 头 = body_start 以上的前景 + 长发改到 body 上段
    hair_extra_bottom = min(h, body_start + int(body_h * 0.7))
    hair_extra = hair & foreground & (yy >= body_start) & (yy < hair_extra_bottom) \
        & (~body_dilated) & (~arm_l) & (~arm_r)
    head = (foreground & (yy < body_start + 1)) | hair_extra
    head = fill_closed_holes(head.astype(np.uint8).astype(bool))
    head = filter_components(head.astype(np.uint8), 80).astype(bool)

    # 腿 = body 下方，左右按中心轴
    leg_top = max(0, body_bottom - 2)
    lower = foreground & (yy >= leg_top) & (~body_dilated)
    leg_l = lower & (xx < center_x)
    leg_r = lower & (xx >= center_x)

    labels = np.zeros((h, w), dtype=np.uint8)
    seeds = {5: leg_l, 6: leg_r, 3: arm_l, 4: arm_r, 1: head, 2: body}
    for label, seed in seeds.items():
        labels[seed] = label
    unassigned = foreground & (labels == 0)
    if unassigned.any():
        dists = {}
        for label, seed in seeds.items():
            if seed.any():
                dists[label] = cv2.distanceTransform(
                    (1 - seed.astype(np.uint8)).astype(np.uint8), cv2.DIST_L2, 5)
        if dists:
            stack = np.stack(list(dists.values()), axis=0)
            order = list(dists)
            nearest = np.argmin(stack, axis=0)
            for pos, label in enumerate(order):
                labels[unassigned & (nearest == pos)] = label

    parts = {name: labels == lab for lab, name in {
        1: "head", 2: "body", 3: "arm_l", 4: "arm_r", 5: "leg_l", 6: "leg_r"}.items()}
    parts["eye_l"], parts["eye_r"], parts["mouth"] = eye_l, eye_r, mouth
    metrics = {"body_start": float(body_start), "body_bottom": float(body_bottom), "center_x": float(center_x)}
    return labels, parts, metrics


def make_pivots_local(parts, metrics, scale, off_x, off_y):
    pivots = {}
    hx, ht = mask_bbox_center_top(parts["head"])
    bx, bt = mask_bbox_center_top(parts["body"])
    pivots["head"] = transform_point(hx, min(metrics["body_start"], ht + (metrics["body_bottom"] - ht) * 0.45), scale, off_x, off_y)
    pivots["body"] = transform_point(bx, (metrics["body_start"] + metrics["body_bottom"]) / 2.0, scale, off_x, off_y)
    for name in ("arm_l", "arm_r", "leg_l", "leg_r"):
        px, py = mask_bbox_center_top(parts[name])
        pivots[name] = transform_point(px, py, scale, off_x, off_y)
    for name in ("eye_l", "eye_r", "mouth"):
        px, py = mask_centroid(parts[name])
        pivots[name] = transform_point(px, py, scale, off_x, off_y)
    return pivots


def character_doc(character_id, name, source, pivots):
    parts = {n: {"file": f"parts/{n}.png", "pivot": pivots[n]} for n in PART_NAMES}
    return {
        "id": character_id, "contract_version": "1.0", "rig": {"parts": parts},
        "persona": {"name": name, "setting": "由照片生成的 Q 版桌宠。"},
        "knowledge": [{"key": "source", "value": str(source)}],
        "idle_lines": [
            {"text": "你好呀！", "action": "wave", "weight": 2},
            {"text": "嗯……发会儿呆。", "action": "nod", "weight": 2},
            {"text": "哈欠……", "action": "yawn", "weight": 1},
        ],
    }


def validate(out_dir):
    try:
        from app_paths import is_frozen
        if is_frozen():
            return True, "(冻结模式，跳过子进程校验)"
    except Exception:  # noqa: BLE001
        pass
    cmd = [sys.executable, str(ROOT / "tools" / "validate.py"), "character", str(out_dir),
           "--actions-dir", str(ROOT / "assets" / "actions")]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode == 0, (r.stdout or "") + (r.stderr or "")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output-dir", required=True)
    ap.add_argument("--character-id", default="seed777")
    ap.add_argument("--name", default="Seed777")
    ap.add_argument("--fit-ratio", type=float, default=0.94)
    ap.add_argument("--parser", choices=["sam", "segformer", "color"], default="sam",
                    help="自动分层方法: sam=SAM提示式+几何(默认) / segformer=人体解析 / color=颜色启发式")
    ap.add_argument("--no-validate", action="store_true")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    input_path = Path(args.input)
    out_dir = Path(args.output_dir)
    model_path = DEFAULT_MODEL
    cid = re.sub(r"[^A-Za-z0-9_-]+", "_", args.character_id).strip("_") or "seed777"

    rgba = read_rgba(input_path)
    rgb = rgba[:, :, :3]
    foreground, used_alpha = detect_foreground(rgb, rgba[:, :, 3])
    eye_l, eye_r, mouth = infer_face_loose(rgb, foreground, model_path)
    labels = parts = metrics = None
    used_parser = args.parser
    try:
        if args.parser == "sam":
            labels, parts, metrics = sam_segment_parts(rgb, foreground, eye_l, eye_r, mouth)
            parts["eye_l"], parts["eye_r"], parts["mouth"] = eye_l, eye_r, mouth
            print("  使用 SAM 提示式分割 + 几何规则 分层(Plan B)")
        elif args.parser == "segformer":
            parse = parse_parts(rgb)
            labels, parts, metrics = build_labels_parser(foreground, parse, eye_l, eye_r, mouth)
            print("  使用人体解析(SegFormer)分层")
        else:
            raise ValueError("color")
    except Exception as e:
        if args.parser != "sam":
            raise
        print(f"  SAM 分层不可用({e})，回退颜色启发式")
        used_parser = "color"
    if parts is None:
        skin = skin_mask(rgb) & foreground
        hair = hair_mask(rgb) & foreground
        body, body_box = detect_body_region(rgb, foreground, skin, hair)
        labels, parts, metrics = build_labels(foreground, rgb, skin, hair, body, body_box, eye_l, eye_r, mouth)
        print("  使用颜色启发式分层")
    empty = [n for n in PART_NAMES if not parts[n].any()]
    if empty:
        print("WARNING: empty parts:", empty, "(请在校准面板手动补画)")
    # 遮挡修复：补齐被上层遮住的下层部件区域
    completed, part_sources = complete_parts(rgb, parts)
    out_dir.mkdir(parents=True, exist_ok=True)
    canvas_rgb, canvas_alpha, scale, off_x, off_y = transformed_canvas(rgb, foreground, args.fit_ratio)
    Image.fromarray(canvas_rgb, mode="RGB").save(out_dir / "source.png")  # 供校准面板重新渲染用
    rendered = render_completed_parts(part_sources, completed, scale, off_x, off_y)
    preview = composite(rendered)
    pivots = make_pivots_local(parts, metrics, scale, off_x, off_y)
    doc = character_doc(cid, args.name, input_path, pivots)

    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    for n in PART_NAMES:
        Image.fromarray(rendered[n], mode="RGBA").save(parts_dir / f"{n}.png")
    (out_dir / "character.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Image.fromarray(preview, mode="RGB").save(out_dir / "preview.png")

    # debug 图
    vis = np.zeros((rgb.shape[0], rgb.shape[1], 3), np.uint8)
    palette = {1: (230, 150, 80), 2: (245, 205, 70), 3: (90, 180, 245), 4: (70, 130, 230),
               5: (120, 220, 130), 6: (70, 180, 100)}
    for lab, col in palette.items():
        vis[labels == lab] = col
    Image.fromarray(vis, mode="RGB").save(out_dir / "debug_labels.png")

    if args.no_validate:
        ok, txt = True, "(跳过校验)"
    else:
        ok, txt = validate(out_dir)
    print("=== split_general ===")
    print("input:", input_path)
    print("output:", out_dir)
    print("pivots:", json.dumps(pivots, ensure_ascii=False))
    print("validation:", "PASS" if ok else "FAIL")
    if not ok:
        print(txt.strip())
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
