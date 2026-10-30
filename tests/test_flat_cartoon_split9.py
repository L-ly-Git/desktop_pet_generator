# -*- coding: utf-8 -*-
"""Tests for the flat cartoon to nine-part decomposition tool."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.step2.flat_cartoon_split9 import (
    CANVAS,
    PART_NAMES,
    detect_foreground,
    main,
    row_extents,
    select_dress_component,
    transformed_canvas,
)


class ForegroundTests(unittest.TestCase):
    def test_detects_warm_character_on_teal_background(self) -> None:
        rgb = np.zeros((100, 80, 3), dtype=np.uint8)
        rgb[:, :, 0] = 14
        rgb[:, :, 1] = 34
        rgb[:, :, 2] = 40
        cv2.rectangle(rgb, (25, 20), (55, 85), (245, 220, 135), -1)
        alpha = np.full((100, 80), 255, dtype=np.uint8)
        mask, used_alpha = detect_foreground(rgb, alpha)
        self.assertFalse(used_alpha)
        self.assertTrue(mask[50, 40])
        self.assertFalse(mask[5, 5])

    def test_keeps_existing_alpha(self) -> None:
        rgb = np.zeros((40, 40, 3), dtype=np.uint8)
        alpha = np.zeros((40, 40), dtype=np.uint8)
        alpha[10:30, 12:28] = 255
        mask, used_alpha = detect_foreground(rgb, alpha)
        self.assertTrue(used_alpha)
        self.assertTrue(mask[20, 20])
        self.assertFalse(mask[0, 0])


class LayoutTests(unittest.TestCase):
    def test_row_extents_follow_mask(self) -> None:
        mask = np.zeros((8, 12), dtype=bool)
        mask[2:6, 3:9] = True
        left, right = row_extents(mask)
        np.testing.assert_array_equal(left, np.full(8, 3))
        np.testing.assert_array_equal(right, np.full(8, 8))

    def test_selects_lower_dress_component(self) -> None:
        mask = np.zeros((100, 80), dtype=bool)
        mask[10:25, 10:30] = True
        mask[45:85, 20:65] = True
        selected, bbox = select_dress_component(mask)
        self.assertEqual(bbox, (20, 45, 45, 40))
        self.assertTrue(selected[60, 40])
        self.assertFalse(selected[15, 15])

    def test_canvas_is_bottom_centered(self) -> None:
        rgb = np.zeros((100, 50, 3), dtype=np.uint8)
        foreground = np.zeros((100, 50), dtype=bool)
        foreground[10:90, 5:45] = True
        canvas, alpha, scale, offset_x, offset_y = transformed_canvas(rgb, foreground, 0.94)
        self.assertEqual(canvas.shape, (CANVAS, CANVAS, 3))
        self.assertGreater(scale, 0)
        ys, xs = np.where(alpha > 0)
        self.assertLessEqual(int(ys.max()), CANVAS - 1)
        self.assertGreater(int(ys.max()), CANVAS - 8)
        self.assertLessEqual(abs(int(xs.mean()) - CANVAS // 2), 3)


class SampleIntegrationTests(unittest.TestCase):
    def test_first_flat_sample_end_to_end(self) -> None:
        candidates = [
            path
            for path in (ROOT / "photo_cartoon_instance").glob("*.png")
            if path.stat().st_size == 125666
        ]
        model_path = ROOT / "models" / "anime_face_seg" / "anime_face_unet.onnx"
        if not candidates or not model_path.is_file():
            self.skipTest("First flat sample or face model is not available.")

        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "flat_char_test"
            code = main(
                [
                    "--input",
                    str(candidates[0]),
                    "--output-dir",
                    str(output),
                    "--character-id",
                    "flat_char_test",
                    "--no-validate",
                ]
            )
            self.assertEqual(code, 0)
            document = json.loads((output / "character.json").read_text(encoding="utf-8"))
            self.assertEqual(document["id"], "flat_char_test")
            self.assertEqual(set(document["rig"]["parts"]), set(PART_NAMES))
            for name in PART_NAMES:
                with Image.open(output / "parts" / f"{name}.png") as image:
                    self.assertEqual(image.mode, "RGBA")
                    self.assertEqual(image.size, (CANVAS, CANVAS))
                    alpha = np.asarray(image)[:, :, 3]
                    self.assertGreater(int((alpha > 0).sum()), 0, name)
            with Image.open(output / "parts" / "head.png") as head_image:
                head_alpha = np.asarray(head_image)[:, :, 3]
            component_count, _, component_stats, _ = cv2.connectedComponentsWithStats(
                (head_alpha > 10).astype(np.uint8), connectivity=8
            )
            large_components = [
                int(component_stats[index, cv2.CC_STAT_AREA])
                for index in range(1, component_count)
                if int(component_stats[index, cv2.CC_STAT_AREA]) >= 20
            ]
            self.assertEqual(len(large_components), 1, large_components)
            with Image.open(output / "preview.png") as preview:
                self.assertEqual(preview.size, (CANVAS, CANVAS))


if __name__ == "__main__":
    unittest.main()