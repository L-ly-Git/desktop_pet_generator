# -*- coding: utf-8 -*-
"""runtime.transform 的基础单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.transform import (
    Affine,
    build_local_transform,
    compute_global_transforms,
    scale_around,
)


class TransformTests(unittest.TestCase):
    def test_pivot_stays_under_rotation_and_scale(self) -> None:
        transform = build_local_transform(
            (100, 200),
            {"rot": 37, "sx": 1.3, "sy": 0.8, "tx": 5, "ty": -6},
        )
        x, y = transform.map_point(100, 200)
        self.assertAlmostEqual(x, 105)
        self.assertAlmostEqual(y, 194)

    def test_parent_translation_propagates(self) -> None:
        parents = {"root": None, "body": "root", "head": "body"}
        pivots = {"root": (256, 512), "body": (256, 310), "head": (256, 276)}
        transforms = compute_global_transforms(
            parents, pivots, {"root": {"tx": 10, "ty": -8}}
        )
        x, y = transforms["head"].map_point(256, 276)
        self.assertAlmostEqual(x, 266)
        self.assertAlmostEqual(y, 268)

    def test_clockwise_rotation(self) -> None:
        transform = build_local_transform((100, 100), {"rot": 90})
        x, y = transform.map_point(200, 100)
        self.assertAlmostEqual(x, 100)
        self.assertAlmostEqual(y, 200)

    def test_translation_composition_order(self) -> None:
        translate = Affine.translate(10, 0)
        scale = Affine.scale(2, 2)
        x, y = translate.multiply(scale).map_point(1, 0)
        self.assertAlmostEqual(x, 12)
        self.assertAlmostEqual(y, 0)

    def test_scale_around_pivot(self) -> None:
        transform = build_local_transform((100, 100), {"sx": 2, "sy": 2})
        x, y = transform.map_point(150, 100)
        self.assertAlmostEqual(x, 200)
        self.assertAlmostEqual(y, 100)

    def test_scale_around_anchor(self) -> None:
        transform = scale_around((256, 512), 0.5)
        x, y = transform.map_point(256, 512)
        self.assertAlmostEqual(x, 256)
        self.assertAlmostEqual(y, 512)
        x, y = transform.map_point(256, 412)
        self.assertAlmostEqual(x, 256)
        self.assertAlmostEqual(y, 462)


if __name__ == "__main__":
    unittest.main()