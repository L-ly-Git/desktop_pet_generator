# -*- coding: utf-8 -*-
"""1-E 性能/兼容性基准。

用法:
    python tools/benchmark_runtime.py
    python tools/benchmark_runtime.py --duration 60 --output artifacts/1e_benchmark.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt5.QtCore import QEvent, QPointF, Qt, QTimer
from PyQt5.QtGui import QContextMenuEvent, QMouseEvent
from PyQt5.QtWidgets import QApplication

from runtime.action import ActionLibrary
from runtime.contract import load_character
from runtime.desktop import DesktopPetWindow
from runtime.puppet import position_window
from runtime.stats import RuntimeMonitor

DEFAULT_CHARACTER = ROOT / "assets" / "characters" / "demo2"
DEFAULT_CONTRACT = ROOT / "contracts" / "rig_contract.json"
DEFAULT_ACTIONS_DIR = ROOT / "assets" / "actions"
DEFAULT_OUTPUT = ROOT / "artifacts" / "1e_benchmark.json"

THRESHOLDS = {
    "avg_fps_min": 55.0,
    "p95_frame_ms_max": 25.0,
    "avg_cpu_percent_max": 15.0,
    "rss_peak_mb_max": 250.0,
    "rss_growth_mb_max": 20.0,
    "load_time_s_max": 1.0,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Window Pet Generator 1-E 基准")
    parser.add_argument(
        "--character",
        type=Path,
        default=DEFAULT_CHARACTER,
        help="角色目录或 character.json",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="rig_contract.json 路径",
    )
    parser.add_argument(
        "--actions-dir",
        type=Path,
        default=DEFAULT_ACTIONS_DIR,
        help="动作 JSON 目录",
    )
    parser.add_argument(
        "--scale",
        type=float,
        default=0.30,
        help="角色显示缩放",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=30.0,
        help="基准运行时长（秒）",
    )
    parser.add_argument(
        "--action-interval",
        type=float,
        default=2.0,
        help="动作切换间隔（秒）",
    )
    parser.add_argument(
        "--idle-min",
        type=float,
        default=2.0,
        help="待机台词最小间隔（秒）",
    )
    parser.add_argument(
        "--idle-max",
        type=float,
        default=4.0,
        help="待机台词最大间隔（秒）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="JSON 报告输出路径",
    )
    return parser


def _configure_output() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass
def main(argv: list[str] | None = None) -> int:
    _configure_output()
    args = build_parser().parse_args(argv)

    if args.duration <= 0:
        print("--duration 必须大于 0", file=sys.stderr)
        return 2
    if args.scale <= 0:
        print("--scale 必须大于 0", file=sys.stderr)
        return 2
    if args.action_interval <= 0:
        print("--action-interval 必须大于 0", file=sys.stderr)
        return 2
    if args.idle_min < 0 or args.idle_max < args.idle_min:
        print("--idle-min/--idle-max 参数无效", file=sys.stderr)
        return 2

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Window Pet Generator Benchmark")

    load_start = time.perf_counter()
    try:
        character = load_character(args.character, args.contract)
        library = ActionLibrary.load(args.actions_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"加载失败: {exc}", file=sys.stderr)
        return 1
    load_time_s = time.perf_counter() - load_start
    actions = [action.id for action in library.items()]

    window = DesktopPetWindow(
        character,
        display_scale=args.scale,
        action_library=library,
        initial_action_id="idle_breath",
        start_animation=True,
        enable_idle=True,
        enable_click_through=False,
        idle_min=args.idle_min,
        idle_max=args.idle_max,
    )
    position_window(window)
    window.show()
    app.processEvents()

    monitor = RuntimeMonitor(window, interval_s=1.0)
    monitor.start()

    state = {
        "actions_played": [],
        "bubble_seen": False,
        "idle_triggered": False,
        "drag_ok": False,
        "walk_ok": False,
        "menu_ok": False,
        "popup_class": None,
        "walk_start_center": None,
        "walk_target": None,
        "walk_start_pos": None,
    }

    action_index = {"value": 0}
    action_timer = QTimer(window)
    action_timer.setInterval(max(200, int(args.action_interval * 1000)))

    def cycle_action() -> None:
        action_id = actions[action_index["value"] % len(actions)]
        action_index["value"] += 1
        window.play_action(action_id)
        state["actions_played"].append(action_id)
        if window.bubble_text:
            state["bubble_seen"] = True

    action_timer.timeout.connect(cycle_action)
    action_timer.start()

    def test_idle() -> None:
        state["idle_triggered"] = bool(window.trigger_idle_line())
        if window.bubble_text:
            state["bubble_seen"] = True

    def test_drag() -> None:
        rect = window.character_rect()
        center = rect.center()
        global_center = window.mapToGlobal(center)
        before = (window.x(), window.y())
        press = QMouseEvent(
            QEvent.MouseButtonPress,
            QPointF(center.x(), center.y()),
            QPointF(global_center.x(), global_center.y()),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        move = QMouseEvent(
            QEvent.MouseMove,
            QPointF(center.x() + 40, center.y() + 30),
            QPointF(global_center.x() + 40, global_center.y() + 30),
            Qt.NoButton,
            Qt.LeftButton,
            Qt.NoModifier,
        )
        release = QMouseEvent(
            QEvent.MouseButtonRelease,
            QPointF(center.x() + 40, center.y() + 30),
            QPointF(global_center.x() + 40, global_center.y() + 30),
            Qt.LeftButton,
            Qt.NoButton,
            Qt.NoModifier,
        )
        window.mousePressEvent(press)
        window.mouseMoveEvent(move)
        window.mouseReleaseEvent(release)
        state["drag_ok"] = (window.x(), window.y()) != before

    def test_walk() -> None:
        rect = window.character_rect()
        center_global = window.mapToGlobal(rect.center())
        target = (center_global.x() - 100, center_global.y() - 80)
        state["walk_start_center"] = (center_global.x(), center_global.y())
        state["walk_target"] = target
        state["walk_start_pos"] = (window.x(), window.y())
        window.walk_to(target[0], target[1])

    def check_walk() -> None:
        start = state["walk_start_center"]
        target = state["walk_target"]
        if start is None or target is None:
            return
        rect = window.character_rect()
        current = window.mapToGlobal(rect.center())
        start_dist = (
            (start[0] - target[0]) ** 2 + (start[1] - target[1]) ** 2
        ) ** 0.5
        current_dist = (
            (current.x() - target[0]) ** 2 + (current.y() - target[1]) ** 2
        ) ** 0.5
        moved = (window.x(), window.y()) != state["walk_start_pos"]
        state["walk_ok"] = moved and current_dist < start_dist

    def close_menu() -> None:
        popup = QApplication.activePopupWidget()
        state["popup_class"] = type(popup).__name__ if popup is not None else None
        if popup is not None:
            popup.close()

    def test_menu() -> None:
        rect = window.character_rect()
        center = rect.center()
        global_center = window.mapToGlobal(center)
        QTimer.singleShot(200, close_menu)
        event = QContextMenuEvent(
            QContextMenuEvent.Mouse,
            center,
            global_center,
        )
        window.contextMenuEvent(event)
        state["menu_ok"] = state["popup_class"] == "QMenu"

    QTimer.singleShot(1200, test_idle)
    QTimer.singleShot(3000, test_drag)
    QTimer.singleShot(5200, test_walk)
    QTimer.singleShot(6500, check_walk)
    QTimer.singleShot(9000, test_menu)

    def finish() -> None:
        monitor.stop()
        action_timer.stop()
        summary = monitor.summary()
        unique_actions = sorted(set(state["actions_played"]))
        passed = (
            summary.avg_fps >= THRESHOLDS["avg_fps_min"]
            and summary.p95_frame_ms <= THRESHOLDS["p95_frame_ms_max"]
            and summary.avg_cpu_percent <= THRESHOLDS["avg_cpu_percent_max"]
            and 0 < summary.rss_peak_mb <= THRESHOLDS["rss_peak_mb_max"]
            and abs(summary.rss_growth_mb) <= THRESHOLDS["rss_growth_mb_max"]
            and load_time_s <= THRESHOLDS["load_time_s_max"]
            and len(unique_actions) == len(actions)
            and state["idle_triggered"]
            and state["bubble_seen"]
            and state["drag_ok"]
            and state["walk_ok"]
            and state["menu_ok"]
        )
        result = {
            "character": character.id,
            "character_name": character.name,
            "scale": args.scale,
            "duration_s": args.duration,
            "load_time_s": load_time_s,
            "actions_available": actions,
            "actions_played": unique_actions,
            "idle_triggered": state["idle_triggered"],
            "bubble_seen": state["bubble_seen"],
            "drag_ok": state["drag_ok"],
            "walk_ok": state["walk_ok"],
            "menu_ok": state["menu_ok"],
            "popup_class": state["popup_class"],
            "summary": asdict(summary),
            "thresholds": THRESHOLDS,
            "passed": passed,
        }
        output = args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        print("=== 1-E Runtime Benchmark ===")
        print(f"character: {character.id} ({character.name})")
        print(f"scale: {args.scale}")
        print(f"duration: {args.duration:.1f}s")
        print(f"load_time: {load_time_s:.3f}s")
        print(
            f"fps avg/min: {summary.avg_fps:.2f} / {summary.min_fps:.2f}"
        )
        print(
            "frame ms avg/p95/max: "
            f"{summary.avg_frame_ms:.2f} / "
            f"{summary.p95_frame_ms:.2f} / "
            f"{summary.max_frame_ms:.2f}"
        )
        print(
            "cpu avg/max: "
            f"{summary.avg_cpu_percent:.2f}% / "
            f"{summary.max_cpu_percent:.2f}%"
        )
        print(
            "rss start/end/peak/growth MB: "
            f"{summary.rss_start_mb:.1f} / "
            f"{summary.rss_end_mb:.1f} / "
            f"{summary.rss_peak_mb:.1f} / "
            f"{summary.rss_growth_mb:+.1f}"
        )
        print(
            f"actions: {len(unique_actions)}/{len(actions)} "
            f"{unique_actions}"
        )
        print(
            "interactions: "
            f"idle={state['idle_triggered']} "
            f"bubble={state['bubble_seen']} "
            f"drag={state['drag_ok']} "
            f"walk={state['walk_ok']} "
            f"menu={state['menu_ok']}"
        )
        print(f"PASS: {passed}")
        print(f"report: {output}")
        window.close()
        app.quit()

    QTimer.singleShot(int(args.duration * 1000), finish)
    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())