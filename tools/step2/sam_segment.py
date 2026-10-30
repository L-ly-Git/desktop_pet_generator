# -*- coding: utf-8 -*-
"""SAM（MobileSAM ONNX）提示式分割：给定点，分割出该点所属的完整区域。

用于校准面板的“智能套索/魔术棒”：点击角色某部位，自动分割该部位。
也用于自动分层（Plan B）：正点 + 负点 + 几何规则。

注意：该 MobileSAM ONNX 导出器的 point_coords 直接使用“原图像素坐标”，
不做 1024 缩放（orig_im_size 会告诉解码器原始尺寸）。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
ENC = ROOT / "models" / "mobilesam" / "mobilesam.encoder.onnx"
DEC = ROOT / "models" / "mobilesam" / "mobile_sam.onnx"


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


class SAMSegmenter:
    """MobileSAM 提示式分割。图像编码一次，之后每个提示只跑解码器。"""

    def __init__(self):
        self.encoder = ort.InferenceSession(str(ENC), providers=["CPUExecutionProvider"])
        self.decoder = ort.InferenceSession(str(DEC), providers=["CPUExecutionProvider"])
        self.embedding = None
        self.size = (512, 512)

    def encode(self, rgb: np.ndarray) -> None:
        h, w = rgb.shape[:2]
        self.size = (h, w)
        img1024 = cv2.resize(rgb, (1024, 1024), interpolation=cv2.INTER_LINEAR)
        self.embedding = self.encoder.run(None, {"input_image": img1024.astype(np.float32)})[0]

    def _run_decoder(self, point_coords, point_labels):
        h, w = self.size
        inputs = {
            "image_embeddings": self.embedding,
            "point_coords": np.array([point_coords], dtype=np.float32),
            "point_labels": np.array([point_labels], dtype=np.float32),
            "mask_input": np.zeros((1, 1, 256, 256), np.float32),
            "has_mask_input": np.array([0], dtype=np.float32),
            "orig_im_size": np.array([h, w], dtype=np.float32),
        }
        return self.decoder.run(None, inputs)

    def predict(self, point_xy) -> np.ndarray:
        """单点提示（智能套索用）：point_xy 为原图像素坐标。

        返回点击点所属的「最紧子部件」掩码，而不是整块角色：
        在包含点击点的候选掩码里选面积最小者（跳过过小碎片）。
        """
        masks, iou, _ = self._run_decoder([list(point_xy)], [1])
        probs = [_sigmoid(masks[0][i]) > 0.5 for i in range(masks.shape[1])]
        H, W = self.size
        x, y = int(round(point_xy[0])), int(round(point_xy[1]))

        def area(m):
            return int(m.sum())

        contain = [m for m in probs if 0 <= y < H and 0 <= x < W and m[y, x]]
        if contain:
            contain.sort(key=area)
            min_area = max(1, int(H * W * 0.005))  # 0.5% 图像面积，跳过碎片
            for m in contain:
                if area(m) >= min_area:
                    return m
            return contain[-1]

        # 没有候选包含点击点：取质心离点击点最近的候选
        def dist(m):
            ys, xs = np.where(m)
            if not len(ys):
                return 1e18
            return float((xs.mean() - x) ** 2 + (ys.mean() - y) ** 2)

        return min(probs, key=dist)

    def predict_multi(self, points_xy, labels) -> np.ndarray:
        """多点提示：points_xy 为原图像素坐标列表，labels 为 1(正)/0(负)。

        返回 4 个候选掩码中预测 IoU 最高者。
        """
        masks, iou, _ = self._run_decoder([list(p) for p in points_xy], list(labels))
        best = int(np.argmax(iou[0]))
        probs = _sigmoid(masks[0][best])
        return probs > 0.5

    def predict_all(self, points_xy, labels):
        """返回全部 4 个候选掩码（原图尺寸）+ IoU 分数。"""
        masks, iou, _ = self._run_decoder([list(p) for p in points_xy], list(labels))
        out = [_sigmoid(masks[0][i]) > 0.5 for i in range(masks.shape[1])]
        return out, iou[0]
