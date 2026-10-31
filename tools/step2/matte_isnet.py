# -*- coding: utf-8 -*-
"""ISNet-general-use 本地抠图（ONNX，全人像/卡通，不吃腿）。"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "matting" / "isnet-general-use_1024.onnx"

_session = None


def get_session():
    global _session
    if _session is None:
        _session = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _session


def predict_alpha(image_bgr: np.ndarray) -> np.ndarray:
    """返回 0..255 的 alpha（uint8），长边1024+黑边补齐，ISNet 归一化。"""
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    scale = 1024 / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(rgb, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((1024, 1024, 3), dtype=np.float32)
    off_y = (1024 - nh) // 2
    off_x = (1024 - nw) // 2
    canvas[off_y:off_y + nh, off_x:off_x + nw] = resized.astype(np.float32) / 255.0
    x = (canvas - 0.5) / 1.0
    x = x.transpose(2, 0, 1)[None].astype(np.float32)
    session = get_session()
    out = session.run(None, {"input_image": x})[0]
    mask = out[0, 0].astype(np.float32)
    mask = (mask - mask.min()) / (mask.max() - mask.min() + 1e-8)
    # 裁掉黑边区域，映射回原尺寸
    crop = mask[off_y:off_y + nh, off_x:off_x + nw]
    full = cv2.resize(crop, (w, h), interpolation=cv2.INTER_LINEAR)
    # 连通域：保留最大前景块，避免背景残留
    fg = (full > 0.5).astype(np.uint8)
    num, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if num > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (labels == largest).astype(np.uint8)
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    alpha = np.clip(full * 255.0, 0, 255).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.0)
    alpha = np.minimum(alpha, 255 * fg.astype(np.uint8))
    return alpha


def imread_unicode(path) -> np.ndarray | None:
    """读图（支持中文/Unicode 路径）。cv2.imread 在 Windows 上读不了中文路径。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def matte_file(rgb_path: Path, out_path: Path) -> Path:
    bgr = imread_unicode(rgb_path)
    if bgr is None:
        raise FileNotFoundError(f"无法读取图片(可能是中文路径或文件损坏): {rgb_path}")
    alpha = predict_alpha(bgr)
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba[..., 3] = alpha
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(out_path)
    return out_path


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    v4 = ROOT / "photo_cartoon_instance" / "step2_chibi_v4"
    for f in sorted(v4.glob("rgb_seed*.png")):
        out = v4 / f.name.replace("rgb_", "isnet_")
        matte_file(f, out)
        print("matted ->", out)
    print("DONE")
