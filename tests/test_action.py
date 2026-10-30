# -*- coding: utf-8 -*-
"""runtime.action 的关键帧与播放器测试。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from runtime.action import (
    Action,
    ActionLibrary,
    ActionPlayer,
    Keyframe,
    apply_easing,
)


def make_action(loop: bool = False, easing: str = "linear") -> Action:
    return Action(
        id="test",
        display_name="Test",
        duration=1.0,
        loop=loop,
        easing=easing,
        tracks={
            "body": {
                "ty": [
                    Keyframe(0.0, 0.0),
                    Keyframe(1.0, 10.0),
                ]
            }
        },
        source=Path("test.json"),
    )


class EasingTests(unittest.TestCase):
    def test_linear(self) -> None:
        self.assertAlmostEqual(apply_easing("linear", 0.5), 0.5)

    def test_ease_in(self) -> None:
        self.assertAlmostEqual(apply_easing("ease_in", 0.5), 0.125)

    def test_ease_out(self) -> None:
        self.assertAlmostEqual(apply_easing("ease_out", 0.5), 0.875)

    def test_ease_in_out(self) -> None:
        self.assertAlmostEqual(apply_easing("ease_in_out", 0.5), 0.5)

    def test_step(self) -> None:
        self.assertAlmostEqual(apply_easing("step", 0.9), 0.0)


class SamplingTests(unittest.TestCase):
    def test_linear_sampling(self) -> None:
        action = make_action()
        self.assertAlmostEqual(action.sample(0.5)["body"]["ty"], 5.0)

    def test_clamp_before_and_after(self) -> None:
        action = make_action()
        self.assertAlmostEqual(action.sample(-1.0)["body"]["ty"], 0.0)
        self.assertAlmostEqual(action.sample(2.0)["body"]["ty"], 10.0)

    def test_loop_wraps_time(self) -> None:
        action = make_action(loop=True)
        self.assertAlmostEqual(action.sample(1.25)["body"]["ty"], 2.5)

    def test_step_keyframe(self) -> None:
        action = Action(
            id="step",
            display_name="Step",
            duration=1.0,
            loop=False,
            easing="linear",
            tracks={
                "body": {
                    "ty": [
                        Keyframe(0.0, 0.0, "step"),
                        Keyframe(1.0, 10.0),
                    ]
                }
            },
            source=Path("step.json"),
        )
        self.assertAlmostEqual(action.sample(0.9)["body"]["ty"], 0.0)
        self.assertAlmostEqual(action.sample(1.0)["body"]["ty"], 10.0)


class PlayerTests(unittest.TestCase):
    def test_non_loop_finishes(self) -> None:
        player = ActionPlayer(make_action())
        self.assertFalse(player.update(0.5))
        self.assertAlmostEqual(player.pose["body"]["ty"], 5.0)
        self.assertTrue(player.update(0.6))
        self.assertTrue(player.finished)
        self.assertFalse(player.playing)
        self.assertAlmostEqual(player.time, 1.0)
        self.assertAlmostEqual(player.pose["body"]["ty"], 10.0)

    def test_loop_never_finishes(self) -> None:
        player = ActionPlayer(make_action(loop=True))
        self.assertFalse(player.update(1.5))
        self.assertFalse(player.finished)
        self.assertTrue(player.playing)
        self.assertAlmostEqual(player.time, 0.5)
        self.assertAlmostEqual(player.pose["body"]["ty"], 5.0)

    def test_replay_resets_time(self) -> None:
        player = ActionPlayer(make_action())
        player.update(1.2)
        self.assertTrue(player.finished)
        action = make_action()
        player.play(action)
        self.assertAlmostEqual(player.time, 0.0)
        self.assertTrue(player.playing)
        self.assertFalse(player.finished)


class LibraryTests(unittest.TestCase):
    def test_loads_shipped_actions(self) -> None:
        library = ActionLibrary.load(ROOT / "assets" / "actions")
        self.assertEqual(len(library.actions), 8)
        self.assertIsNotNone(library.get("idle_breath"))
        self.assertEqual(library.default_idle_id, "idle_breath")

    def test_rejects_empty_tracks(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "bad.json"
            path.write_text(
                '{"id": "bad", "duration": 1, "loop": false, "tracks": {}}',
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                ActionLibrary.load(Path(temp_dir))


if __name__ == "__main__":
    unittest.main()