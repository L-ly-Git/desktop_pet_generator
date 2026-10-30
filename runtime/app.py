# -*- coding: utf-8 -*-
"""Window Pet Generator 运行时入口（1-D）。

用法:
    .venv\\Scripts\\python.exe runtime\\app.py
    .venv\\Scripts\\python.exe runtime\\app.py --action wave
    .venv\\Scripts\\python.exe runtime\\app.py --snapshot artifacts\\bubble.png --bubble-text "你好呀"
    .venv\\Scripts\\python.exe runtime\\app.py --list-actions
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许直接执行 python runtime/app.py
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication

from runtime.action import ActionLibrary
from runtime.contract import load_character
from runtime.desktop import DesktopPetWindow, render_desktop_image
from runtime.puppet import checkerboard_image, position_window, render_to_image
from runtime.transform import make_test_pose

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# DEFAULT_CHARACTER = PROJECT_ROOT / "assets" / "characters" / "demo2"
DEFAULT_CHARACTER = PROJECT_ROOT / "photo_cartoon_instance"/"calib_photo05"
DEFAULT_CONTRACT = PROJECT_ROOT / "contracts" / "rig_contract.json"
try:
    from app_paths import actions_dir as _actions_dir
    DEFAULT_ACTIONS_DIR = _actions_dir()
except Exception:  # pragma: no cover
    DEFAULT_ACTIONS_DIR = PROJECT_ROOT / "assets" / "actions"
DEFAULT_DISPLAY_SCALE = 0.30 #不要修改这个


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Window Pet Generator 运行时（1-D）")
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
        default=DEFAULT_DISPLAY_SCALE,
        help=(
            f"角色显示缩放（默认 {DEFAULT_DISPLAY_SCALE}，"
            "当前默认值；可用 0.76 接近 main.py 的可见高度）"
        ),
    )
    parser.add_argument(
        "--action",
        type=str,
        default=None,
        help="启动时播放的动作 id；不填则使用 idle_breath",
    )
    parser.add_argument(
        "--at",
        type=float,
        default=0.0,
        help="快照采样时间（秒），仅快照模式有效",
    )
    parser.add_argument(
        "--bubble-text",
        type=str,
        default=None,
        help="在快照中或启动时显示一条测试气泡",
    )
    parser.add_argument(
        "--idle-min",
        type=float,
        default=12.0,
        help="待机台词最小间隔（秒）",
    )
    parser.add_argument(
        "--idle-max",
        type=float,
        default=25.0,
        help="待机台词最大间隔（秒）",
    )
    parser.add_argument(
        "--no-idle",
        action="store_true",
        help="关闭待机台词调度",
    )
    parser.add_argument(
        "--no-clickthrough",
        action="store_true",
        help="关闭透明区域点击穿透（调试用）",
    )
    parser.add_argument(
        "--list-actions",
        action="store_true",
        help="列出可用动作后退出",
    )
    parser.add_argument(
        "--debug-pivots",
        action="store_true",
        help="显示部件枢轴与 root 锚点",
    )
    parser.add_argument(
        "--test-pose",
        action="store_true",
        help="使用静态测试姿势，不启动动画",
    )
    parser.add_argument(
        "--snapshot",
        type=Path,
        default=None,
        help="不显示窗口，渲染一张 PNG 快照后退出",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="创建透明窗口并在 1 秒后自动退出",
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

    if args.list_actions:
        try:
            library = ActionLibrary.load(args.actions_dir)
        except (OSError, ValueError) as exc:
            print(f"加载动作失败: {exc}", file=sys.stderr)
            return 1
        print(f"动作目录: {args.actions_dir}")
        for action in library.items():
            kind = "循环" if action.loop else "单次"
            print(
                f"  {action.id:14s} {action.display_name:12s} "
                f"{action.duration:5.2f}s {kind}"
            )
        return 0

    if args.scale <= 0:
        print("--scale 必须大于 0", file=sys.stderr)
        return 2
    if args.at < 0:
        print("--at 不能小于 0", file=sys.stderr)
        return 2
    if args.idle_min < 0 or args.idle_max < 0:
        print("--idle-min/--idle-max 不能小于 0", file=sys.stderr)
        return 2
    if args.idle_max < args.idle_min:
        print("--idle-max 不能小于 --idle-min", file=sys.stderr)
        return 2

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Window Pet Generator")

    try:
        character = load_character(args.character, args.contract)
        action_library = ActionLibrary.load(args.actions_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"加载失败: {exc}", file=sys.stderr)
        return 1

    selected_action = None
    if args.action is not None:
        selected_action = action_library.get(args.action)
        if selected_action is None:
            available = ", ".join(action.id for action in action_library.items())
            print(
                f"未找到动作: {args.action!r}；可用动作: {available}",
                file=sys.stderr,
            )
            return 1

    if args.snapshot is not None:
        if args.test_pose:
            pose = make_test_pose()
        elif selected_action is not None:
            pose = selected_action.sample(args.at)
        else:
            pose = {}

        snapshot_path = args.snapshot
        if snapshot_path.suffix == "":
            snapshot_path = snapshot_path.with_suffix(".png")
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        if args.bubble_text:
            image = render_desktop_image(
                character,
                pose,
                display_scale=args.scale,
                bubble_text=args.bubble_text,
                debug_pivots=args.debug_pivots,
            )
        else:
            image = render_to_image(
                character,
                pose,
                debug_pivots=args.debug_pivots,
                display_scale=args.scale,
            )
        if not image.save(str(snapshot_path), "PNG"):
            print(f"保存快照失败: {snapshot_path}", file=sys.stderr)
            return 1
        checker_path = snapshot_path.with_name(snapshot_path.stem + "_checker.png")
        if not checkerboard_image(image).save(str(checker_path), "PNG"):
            print(f"保存棋盘格预览失败: {checker_path}", file=sys.stderr)
            return 1
        print(f"快照已保存: {snapshot_path}")
        print(f"棋盘格预览: {checker_path}")
        print(f"显示缩放: {args.scale}")
        if selected_action is not None and not args.test_pose:
            print(f"动作: {selected_action.id} @ {args.at:.2f}s")
        return 0

    static_pose = make_test_pose() if args.test_pose else {}
    # 长时记忆文件：放到角色文件夹里
    character_path = Path(args.character)
    character_dir = character_path if character_path.is_dir() else character_path.parent
    history_path = character_dir / "history.json"
    memory_path = character_dir / "memory.json"
    window = DesktopPetWindow(
        character,
        pose=static_pose,
        debug_pivots=args.debug_pivots,
        display_scale=args.scale,
        action_library=action_library,
        initial_action_id=args.action,
        start_animation=not args.test_pose,
        enable_idle=not args.test_pose and not args.no_idle,
        enable_click_through=not args.no_clickthrough,
        idle_min=args.idle_min,
        idle_max=args.idle_max,
        history_path=history_path,
        memory_path=memory_path,
    )
    if args.bubble_text:
        window.show_bubble(args.bubble_text)
    position_window(window)
    window.show()

    if args.smoke_test:
        print("冒烟测试：透明窗口将在 1 秒后自动退出")
        QTimer.singleShot(1000, app.quit)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())