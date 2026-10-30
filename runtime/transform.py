# -*- coding: utf-8 -*-
"""契约 v1 的仿射变换与父子层级计算。

变换约定：
    x' = a*x + c*y + e
    y' = b*x + d*y + f

局部变换：
    T(pivot) * T(tx, ty) * R(rot) * S(sx, sy) * T(-pivot)

父子组合：
    G_child = G_parent * L_child
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Mapping

Pose = Mapping[str, Mapping[str, float]]


@dataclass(frozen=True)
class Affine:
    a: float = 1.0
    b: float = 0.0
    c: float = 0.0
    d: float = 1.0
    e: float = 0.0
    f: float = 0.0

    @classmethod
    def identity(cls) -> "Affine":
        return cls()

    @classmethod
    def translate(cls, tx: float, ty: float) -> "Affine":
        return cls(e=float(tx), f=float(ty))

    @classmethod
    def scale(cls, sx: float, sy: float) -> "Affine":
        return cls(a=float(sx), d=float(sy))

    @classmethod
    def rotate(cls, degrees: float) -> "Affine":
        radians = math.radians(float(degrees))
        cos_value = math.cos(radians)
        sin_value = math.sin(radians)
        # 屏幕坐标 y 向下，因此该矩阵在视觉上是顺时针旋转。
        return cls(a=cos_value, b=sin_value, c=-sin_value, d=cos_value)

    def multiply(self, other: "Affine") -> "Affine":
        """返回 self * other；映射时先应用 other，再应用 self。"""
        return Affine(
            a=self.a * other.a + self.c * other.b,
            b=self.b * other.a + self.d * other.b,
            c=self.a * other.c + self.c * other.d,
            d=self.b * other.c + self.d * other.d,
            e=self.a * other.e + self.c * other.f + self.e,
            f=self.b * other.e + self.d * other.f + self.f,
        )

    def map_point(self, x: float, y: float) -> tuple[float, float]:
        return (
            self.a * x + self.c * y + self.e,
            self.b * x + self.d * y + self.f,
        )

    def to_qtransform(self):
        """转换为 QTransform；仅在 Qt 可用时调用。"""
        from PyQt5.QtGui import QTransform

        return QTransform(self.a, self.b, self.c, self.d, self.e, self.f)


def build_local_transform(
    pivot: tuple[float, float] | list[float],
    channels: Mapping[str, float] | None = None,
) -> Affine:
    px, py = float(pivot[0]), float(pivot[1])
    values = channels or {}
    tx = float(values.get("tx", 0.0))
    ty = float(values.get("ty", 0.0))
    rot = float(values.get("rot", 0.0))
    sx = float(values.get("sx", 1.0))
    sy = float(values.get("sy", 1.0))
    return (
        Affine.translate(px, py)
        .multiply(Affine.translate(tx, ty))
        .multiply(Affine.rotate(rot))
        .multiply(Affine.scale(sx, sy))
        .multiply(Affine.translate(-px, -py))
    )


def compute_global_transforms(
    parents: Mapping[str, str | None],
    pivots: Mapping[str, tuple[float, float]],
    pose: Pose | None = None,
) -> dict[str, Affine]:
    """按父子层级计算每个节点从画布坐标到渲染坐标的全局变换。"""
    pose = pose or {}
    cache: dict[str, Affine] = {}

    def resolve(node: str) -> Affine:
        if node in cache:
            return cache[node]
        parent = parents.get(node)
        if parent is None:
            parent_transform = Affine.identity()
        else:
            if parent not in parents:
                raise ValueError(f"节点 {node!r} 的父级 {parent!r} 不存在")
            parent_transform = resolve(parent)
        pivot = pivots.get(node)
        if pivot is None:
            raise ValueError(f"节点 {node!r} 缺少枢轴")
        local = build_local_transform(pivot, pose.get(node, {}))
        result = parent_transform.multiply(local)
        cache[node] = result
        return result

    for node in parents:
        resolve(node)
    return cache


def make_test_pose() -> dict[str, dict[str, float]]:
    """用于 1-B 验证枢轴与父子层级的测试姿势。"""
    return {
        "root": {"ty": -8.0},
        "body": {"rot": 2.0, "ty": -2.0},
        "head": {"rot": 8.0, "ty": -2.0},
        "arm_l": {"rot": 12.0},
        "arm_r": {"rot": -45.0},
        "leg_l": {"rot": -5.0},
        "leg_r": {"rot": 5.0},
        "eye_l": {"sy": 0.8},
        "eye_r": {"sy": 0.8},
        "mouth": {"sy": 1.3},
    }
def scale_around(
    pivot: tuple[float, float] | list[float],
    scale: float,
) -> Affine:
    """绕指定枢轴整体缩放。用于运行时显示大小调整。"""
    px, py = float(pivot[0]), float(pivot[1])
    factor = float(scale)
    return (
        Affine.translate(px, py)
        .multiply(Affine.scale(factor, factor))
        .multiply(Affine.translate(-px, -py))
    )