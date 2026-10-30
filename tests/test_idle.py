# -*- coding: utf-8 -*-
"""runtime.idle 的待机台词调度测试。"""
from __future__ import annotations

import json
import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.idle import IdleScheduler


class IdleSchedulerTests(unittest.TestCase):
    def test_empty_lines(self) -> None:
        scheduler = IdleScheduler([])
        self.assertFalse(scheduler.has_lines)
        self.assertIsNone(scheduler.pick_line())

    def test_filters_invalid_lines(self) -> None:
        scheduler = IdleScheduler(
            [
                {"text": "ok", "action": "wave", "weight": 1},
                {"text": "", "action": "wave", "weight": 1},
                {"text": "bad weight", "action": "wave", "weight": 0},
                {"text": "bad action", "action": "", "weight": 1},
                "not a dict",
            ]
        )
        self.assertEqual(len(scheduler.lines), 1)
        self.assertEqual(scheduler.lines[0].text, "ok")

    def test_pick_line_returns_valid(self) -> None:
        scheduler = IdleScheduler(
            [
                {"text": "a", "action": "wave", "weight": 1},
                {"text": "b", "action": "nod", "weight": 2},
            ],
            rng=random.Random(0),
        )
        line = scheduler.pick_line()
        self.assertIsNotNone(line)
        self.assertIn(line.text, {"a", "b"})
        self.assertIn(line.action, {"wave", "nod"})

    def test_next_delay_within_bounds(self) -> None:
        scheduler = IdleScheduler(
            [],
            min_delay=2.0,
            max_delay=3.0,
            rng=random.Random(0),
        )
        for _ in range(20):
            delay = scheduler.next_delay()
            self.assertGreaterEqual(delay, 2.0)
            self.assertLessEqual(delay, 3.0)

    def test_max_delay_clamped(self) -> None:
        scheduler = IdleScheduler([], min_delay=5.0, max_delay=1.0)
        self.assertGreaterEqual(scheduler.max_delay, 5.0)
        self.assertGreaterEqual(scheduler.next_delay(), 5.0)

    def test_demo_idle_lines(self) -> None:
        path = ROOT / "assets" / "characters" / "demo" / "character.json"
        character = json.loads(path.read_text(encoding="utf-8"))
        scheduler = IdleScheduler(character["idle_lines"])
        self.assertTrue(scheduler.has_lines)
        self.assertIsNotNone(scheduler.pick_line())


if __name__ == "__main__":
    unittest.main()