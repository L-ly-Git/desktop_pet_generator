# -*- coding: utf-8 -*-
"""人体解析（SegFormer-B5 human parsing）→ 映射到 9 部件契约的 head/body/arm_l/arm_r/leg_l/leg_r。

用 onnxruntime 本地推理，无需 torch。眼睛/嘴由 anime_face_seg 单独处理。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "human_parsing" / "segformer_b5.onnx"

# 模型 18 类 -> 契约部件
HEAD_CLASSES = {1, 2, 3, 11}          # hat, hair, sunglasses, face
BODY_CLASSES = {4, 5, 6, 7, 8, 17}    # upper-clothes, skirt, pants, dress, belt, scarf
# 模型按"人物自身"左右标注；人物面向镜头时，人物左 = 画面右。故与画面左右互换。
ARM_L_CLASSES = {15}                  # 画面左臂 = 模型 Right-arm
ARM_R_CLASSES = {14}                  # 画面右臂 = 模型 Left-arm
LEG_L_CLASSES = {10, 13}              # 画面左腿 = Right-shoe + Right-leg
LEG_R_CLASSES = {9, 12}               # 画面右腿 = Left-shoe + Left-leg

MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_session = None


def load_session():
    global _session
    if _session is None:
        _session = ort.InferenceSession(str(MODEL), providers=["CPUExecutionProvider"])
    return _session


def _preprocess(rgb: np.ndarray) -> np.ndarray:
    h, w = rgb.shape[:2]
    resized = cv2.resize(rgb, (512, 512), interpolation=cv2.INTER_LINEAR)
    x = resized.astype(np.float32) / 255.0
    x = (x - MEAN) / STD
    return x.transpose(2, 0, 1)[None].astype(np.float32), (h, w)


def parse_parts(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """返回 {head, body, arm_l, arm_r, leg_l, leg_r} 布尔掩码（输入尺寸）。"""
    h, w = rgb.shape[:2]
    x, _ = _preprocess(rgb)
    session = load_session()
    logits = session.run(None, {"pixel_values": x})[0][0]  # [18, 128, 128]
    logits = cv2.resize(logits.transpose(1, 2, 0), (w, h), interpolation=cv2.INTER_LINEAR).transpose(2, 0, 1)
    labels = logits.argmax(axis=0).astype(np.uint8)

    def mask_of(classes):
        return np.isin(labels, list(classes))

    return {
        "head": mask_of(HEAD_CLASSES),
        "body": mask_of(BODY_CLASSES),
        "arm_l": mask_of(ARM_L_CLASSES),
        "arm_r": mask_of(ARM_R_CLASSES),
        "leg_l": mask_of(LEG_L_CLASSES),
        "leg_r": mask_of(LEG_R_CLASSES),
    }


def mask_of_classes(labels: np.ndarray, classes) -> np.ndarray:
    return np.isin(labels, list(classes))
