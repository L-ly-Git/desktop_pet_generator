# -*- coding: utf-8 -*-
"""轻量 SCRFD 人脸检测（直接 onnxruntime，不依赖 uniface 全家桶）。

只用于真人照片的“眼/嘴定位”。模型：models/uniface/scrfd_500m.onnx（约 2.4MB）。
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

ROOT = Path(__file__).resolve().parents[2]
MODEL = ROOT / "models" / "uniface" / "scrfd_500m.onnx"


def _distance2bbox(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    x1 = points[:, 0] - distance[:, 0]
    y1 = points[:, 1] - distance[:, 1]
    x2 = points[:, 0] + distance[:, 2]
    y2 = points[:, 1] + distance[:, 3]
    return np.stack([x1, y1, x2, y2], axis=-1)


def _distance2kps(points: np.ndarray, distance: np.ndarray) -> np.ndarray:
    k = distance.shape[1] // 2
    preds = []
    for i in range(k):
        px = points[:, 0] + distance[:, 2 * i]
        py = points[:, 1] + distance[:, 2 * i + 1]
        preds.append(np.stack([px, py], axis=-1))
    return np.stack(preds, axis=1)  # (N, k, 2)


def _nms(dets: np.ndarray, thresh: float) -> list[int]:
    if len(dets) == 0:
        return []
    x1, y1, x2, y2 = dets[:, 0], dets[:, 1], dets[:, 2], dets[:, 3]
    areas = (x2 - x1 + 1) * (y2 - y1 + 1)
    order = dets[:, 4].argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])
        w = np.maximum(0.0, xx2 - xx1 + 1)
        h = np.maximum(0.0, yy2 - yy1 + 1)
        inter = w * h
        ovr = inter / (areas[i] + areas[order[1:]] - inter)
        inds = np.where(ovr <= thresh)[0]
        order = order[inds + 1]
    return keep


class SCRFDDetector:
    def __init__(self, model_path: Path = MODEL, conf_thresh: float = 0.5, nms_thresh: float = 0.4):
        self.session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        self.input_name = self.session.get_inputs()[0].name
        self.output_names = [o.name for o in self.session.get_outputs()]
        self.conf_thresh = conf_thresh
        self.nms_thresh = nms_thresh
        self._strides = [8, 16, 32]

    def _anchors(self, stride: int, size: int) -> np.ndarray:
        fm = size // stride
        y, x = np.mgrid[:fm, :fm]
        centers = np.stack((x, y), axis=-1).astype(np.float32)
        centers = (centers * stride).reshape(-1, 2)
        # SCRFD-500M：每个位置 2 个 anchor（中心相同）
        return np.tile(centers[:, None, :], (1, 2, 1)).reshape(-1, 2)

    def detect(self, bgr: np.ndarray) -> list[dict]:
        h, w = bgr.shape[:2]
        scale = min(640.0 / w, 640.0 / h)
        nw, nh = int(round(w * scale)), int(round(h * scale))
        resized = cv2.resize(bgr, (nw, nh))
        canvas = np.zeros((640, 640, 3), np.float32)
        canvas[:nh, :nw] = resized.astype(np.float32)
        blob = ((canvas - 127.5) / 127.5).transpose(2, 0, 1)[None].astype(np.float32)
        outs = self.session.run(self.output_names, {self.input_name: blob})

        scores_all, boxes_all, kps_all = [], [], []
        for idx, stride in enumerate(self._strides):
            scores = outs[idx].reshape(-1)
            bbox_preds = outs[3 + idx] * stride
            kps_preds = outs[6 + idx] * stride
            anchors = self._anchors(stride, 640)
            pos = np.where(scores >= self.conf_thresh)[0]
            if len(pos) == 0:
                continue
            scores_all.append(scores[pos])
            boxes_all.append(_distance2bbox(anchors, bbox_preds)[pos])
            kps_all.append(_distance2kps(anchors, kps_preds)[pos])

        if not scores_all:
            return []
        scores = np.concatenate(scores_all)
        boxes = np.concatenate(boxes_all)
        kps = np.concatenate(kps_all)
        pre = np.hstack((boxes, scores[:, None])).astype(np.float32)
        order = scores.argsort()[::-1]
        pre, kps = pre[order], kps[order]

        faces = []
        for i in _nms(pre, self.nms_thresh):
            faces.append({
                "bbox": (pre[i, :4] / scale).astype(np.float32),
                "landmarks": (kps[i] / scale).astype(np.float32),
                "score": float(pre[i, 4]),
            })
        return faces

    def detect_largest(self, bgr: np.ndarray) -> dict | None:
        faces = self.detect(bgr)
        if not faces:
            return None
        return max(faces, key=lambda f: float((f["bbox"][2] - f["bbox"][0]) * (f["bbox"][3] - f["bbox"][1])))
