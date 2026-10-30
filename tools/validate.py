# -*- coding: utf-8 -*-
"""Window Pet Generator 契约校验器。

用法:
    python tools/validate.py character assets/characters/demo --actions-dir assets/actions
    python tools/validate.py action assets/actions/wave.json
    python tools/validate.py actions assets/actions

退出码:
    0 = 通过（可能有警告）
    1 = 存在错误
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "rig_contract.json"

ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_EASINGS = {"linear", "ease_in", "ease_out", "ease_in_out", "step"}
CHANNELS = {"tx", "ty", "rot", "sx", "sy"}
REQUIRED_PARTS = {"head", "body"}


class Report:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def error(self, message: str) -> None:
        self.errors.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def ok(self) -> bool:
        return not self.errors

    def print(self, title: str) -> None:
        print(f"\n=== {title} ===")
        if self.ok and not self.warnings:
            print("OK: 全部检查通过")
            return
        for message in self.errors:
            print(f"[ERROR] {message}")
        for message in self.warnings:
            print(f"[WARN ] {message}")
        if self.ok:
            print(f"通过（{len(self.warnings)} 条警告）")
        else:
            print(f"失败（{len(self.errors)} 个错误，{len(self.warnings)} 条警告）")


def load_json(path: Path, report: Report, label: str) -> Any:
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            return json.load(handle)
    except FileNotFoundError:
        report.error(f"{label}: 文件不存在: {path}")
    except json.JSONDecodeError as exc:
        report.error(
            f"{label}: JSON 解析失败: {path}:{exc.lineno}:{exc.colno}: {exc.msg}"
        )
    except OSError as exc:
        report.error(f"{label}: 读取失败: {path}: {exc}")
    return None


def is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def require_keys(
    obj: dict,
    required: Iterable[str],
    report: Report,
    where: str,
    allowed: Iterable[str] | None = None,
) -> None:
    for key in required:
        if key not in obj:
            report.error(f"{where}: 缺少字段 '{key}'")
    if allowed is not None:
        for key in sorted(set(obj) - set(allowed)):
            report.error(f"{where}: 未知字段 '{key}'")


def check_id(value: Any, where: str, report: Report) -> None:
    if not isinstance(value, str) or not value:
        report.error(f"{where}: id 必须是非空字符串")
    elif not ID_RE.match(value):
        report.error(f"{where}: id 只能包含字母、数字、下划线、连字符: {value!r}")


def load_contract(path: Path, report: Report) -> dict | None:
    data = load_json(path, report, "契约")
    if not isinstance(data, dict):
        return None

    require_keys(
        data,
        ["contract_version", "canvas", "parts", "channels"],
        report,
        "契约",
        allowed={
            "contract_version",
            "description",
            "canvas",
            "parts",
            "virtual_nodes",
            "channels",
            "action",
            "notes",
        },
    )

    version = data.get("contract_version")
    if not isinstance(version, str) or not version.strip():
        report.error("契约.contract_version 必须是非空字符串")

    canvas = data.get("canvas")
    canvas_w = canvas_h = 0
    if not isinstance(canvas, dict):
        report.error("契约.canvas 必须是对象")
    else:
        require_keys(
            canvas,
            ["width", "height", "anchor_point"],
            report,
            "契约.canvas",
            allowed={
                "width",
                "height",
                "coordinate_system",
                "x_axis",
                "y_axis",
                "screen_anchor",
                "anchor_point",
            },
        )
        width = canvas.get("width")
        height = canvas.get("height")
        if not is_number(width) or int(width) <= 0:
            report.error("契约.canvas.width 必须是正数")
        else:
            canvas_w = int(width)
        if not is_number(height) or int(height) <= 0:
            report.error("契约.canvas.height 必须是正数")
        else:
            canvas_h = int(height)
        anchor = canvas.get("anchor_point")
        if not (
            isinstance(anchor, list)
            and len(anchor) == 2
            and all(is_number(item) for item in anchor)
        ):
            report.error("契约.canvas.anchor_point 必须是 [x, y]")
        elif canvas_w and canvas_h:
            x, y = float(anchor[0]), float(anchor[1])
            if not (0 <= x <= canvas_w and 0 <= y <= canvas_h):
                report.error(f"契约.canvas.anchor_point 超出画布: {anchor}")
        if canvas.get("coordinate_system") != "top-left":
            report.error("契约.canvas.coordinate_system 目前只支持 'top-left'")
        if canvas.get("y_axis") != "down":
            report.error("契约.canvas.y_axis 目前只支持 'down'")

    parts = data.get("parts")
    if not isinstance(parts, dict) or not parts:
        report.error("契约.parts 必须是非空对象")
    else:
        for name, spec in parts.items():
            pwhere = f"契约.parts.{name}"
            if not isinstance(spec, dict):
                report.error(f"{pwhere} 必须是对象")
                continue
            require_keys(
                spec,
                ["required", "parent", "z", "default_pivot"],
                report,
                pwhere,
                allowed={"required", "parent", "z", "default_pivot", "description"},
            )
            if not isinstance(spec.get("required"), bool):
                report.error(f"{pwhere}.required 必须是布尔值")
            if not is_number(spec.get("z")):
                report.error(f"{pwhere}.z 必须是数字")
            pivot = spec.get("default_pivot")
            if not (
                isinstance(pivot, list)
                and len(pivot) == 2
                and all(is_number(item) for item in pivot)
            ):
                report.error(f"{pwhere}.default_pivot 必须是 [x, y]")
            elif canvas_w and canvas_h:
                x, y = float(pivot[0]), float(pivot[1])
                if not (0 <= x <= canvas_w and 0 <= y <= canvas_h):
                    report.error(f"{pwhere}.default_pivot 超出画布: {pivot}")
            parent = spec.get("parent")
            if parent not in (None, "root") and parent not in parts:
                report.error(f"{pwhere}.parent 指向未知节点: {parent!r}")

        for required_part in REQUIRED_PARTS:
            if required_part not in parts:
                report.error(f"契约.parts 缺少必需部件 '{required_part}'")

    channels = data.get("channels")
    if not isinstance(channels, dict):
        report.error("契约.channels 必须是对象")
    else:
        for channel in CHANNELS:
            if channel not in channels:
                report.error(f"契约.channels 缺少通道 '{channel}'")
        for channel, spec in channels.items():
            if not isinstance(spec, dict):
                report.error(f"契约.channels.{channel} 必须是对象")
                continue
            if not is_number(spec.get("default")):
                report.error(f"契约.channels.{channel}.default 必须是数字")

    action = data.get("action")
    if isinstance(action, dict):
        easings = action.get("easing")
        if not isinstance(easings, list) or not set(easings).issubset(ALLOWED_EASINGS):
            report.error(f"契约.action.easing 必须只包含: {sorted(ALLOWED_EASINGS)}")
        if easings is not None and set(easings) != ALLOWED_EASINGS:
            report.warn(
                f"契约.action.easing 与校验器内置集合不完全一致: {easings}"
            )
        targets = action.get("allowed_targets")
        if not isinstance(targets, list) or not targets:
            report.error("契约.action.allowed_targets 必须是非空数组")
        elif isinstance(parts, dict):
            for target in targets:
                if target != "root" and target not in parts:
                    report.error(f"契约.action.allowed_targets 指向未知部件: {target!r}")

    return data
def check_image(
    path: Path, canvas_w: int, canvas_h: int, report: Report, where: str
) -> None:
    if Image is None:
        report.warn(f"{where}: 未安装 Pillow，跳过图片检查")
        return
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                report.error(f"{where}: 必须是 PNG，实际为 {image.format}")
            if image.size != (canvas_w, canvas_h):
                report.error(
                    f"{where}: 尺寸必须是 {canvas_w}x{canvas_h}，"
                    f"实际为 {image.width}x{image.height}"
                )
            if image.mode not in ("RGBA", "LA", "P"):
                report.error(
                    f"{where}: 必须带透明通道（RGBA/LA/P），"
                    f"实际模式为 {image.mode}"
                )
            else:
                alpha = image.convert("RGBA").getchannel("A")
                low, high = alpha.getextrema()
                if high == 0:
                    report.warn(f"{where}: 图片完全透明")
                elif low == 255:
                    report.warn(
                        f"{where}: 图片完全不透明（全画布部件通常应有透明区域）"
                    )
    except FileNotFoundError:
        report.error(f"{where}: 图片不存在: {path}")
    except OSError as exc:
        report.error(f"{where}: 无法读取图片: {path}: {exc}")


def validate_character_file(
    path: Path,
    contract: dict,
    report: Report,
    actions: dict[str, dict] | None = None,
) -> None:
    data = load_json(path, report, "角色")
    if not isinstance(data, dict):
        return
    where = f"角色 {path.name}"
    require_keys(
        data,
        ["id", "contract_version", "rig", "persona", "knowledge", "idle_lines"],
        report,
        where,
        allowed={
            "id",
            "contract_version",
            "rig",
            "persona",
            "knowledge",
            "idle_lines",
        },
    )
    check_id(data.get("id"), f"{where}.id", report)
    if data.get("contract_version") != contract.get("contract_version"):
        report.error(
            f"{where}: contract_version 不匹配"
            f"（文件 {data.get('contract_version')!r}，"
            f"契约 {contract.get('contract_version')!r}）"
        )

    rig = data.get("rig")
    if not isinstance(rig, dict):
        report.error(f"{where}.rig 必须是对象")
        return
    require_keys(rig, ["parts"], report, f"{where}.rig", allowed={"parts"})
    parts = rig.get("parts")
    if not isinstance(parts, dict):
        report.error(f"{where}.rig.parts 必须是对象")
        return

    contract_parts = contract.get("parts", {})
    for name in sorted(set(parts) - set(contract_parts)):
        report.error(f"{where}.rig.parts: 未知部件 '{name}'")
    for name, spec in contract_parts.items():
        if spec.get("required") and name not in parts:
            report.error(f"{where}.rig.parts: 缺少必需部件 '{name}'")

    canvas = contract.get("canvas", {})
    canvas_w = int(canvas.get("width", 0))
    canvas_h = int(canvas.get("height", 0))
    for name, part in parts.items():
        if name not in contract_parts:
            continue
        pwhere = f"{where}.rig.parts.{name}"
        if not isinstance(part, dict):
            report.error(f"{pwhere} 必须是对象")
            continue
        require_keys(
            part, ["file", "pivot"], report, pwhere, allowed={"file", "pivot"}
        )
        file_value = part.get("file")
        pivot = part.get("pivot")
        if not isinstance(file_value, str) or not file_value.strip():
            report.error(f"{pwhere}.file 必须是非空字符串")
        else:
            relative = Path(file_value)
            if relative.is_absolute():
                report.error(f"{pwhere}.file 不能是绝对路径")
            elif ".." in relative.parts:
                report.error(f"{pwhere}.file 不能包含 '..'")
            else:
                check_image(
                    path.parent / relative,
                    canvas_w,
                    canvas_h,
                    report,
                    f"{pwhere}.file",
                )
        if not (
            isinstance(pivot, list)
            and len(pivot) == 2
            and all(is_number(item) for item in pivot)
        ):
            report.error(f"{pwhere}.pivot 必须是 [x, y] 数字")
        else:
            x, y = float(pivot[0]), float(pivot[1])
            if not (0 <= x <= canvas_w and 0 <= y <= canvas_h):
                report.error(f"{pwhere}.pivot 超出画布范围: {pivot}")
            default_pivot = contract_parts[name].get("default_pivot")
            if default_pivot and (
                abs(x - default_pivot[0]) > canvas_w * 0.25
                or abs(y - default_pivot[1]) > canvas_h * 0.25
            ):
                report.warn(
                    f"{pwhere}.pivot 与契约默认值 {default_pivot} 偏差较大"
                )

    persona = data.get("persona")
    if not isinstance(persona, dict):
        report.error(f"{where}.persona 必须是对象")
    else:
        require_keys(
            persona,
            ["name", "setting"],
            report,
            f"{where}.persona",
            allowed={"name", "setting"},
        )
        for key in ("name", "setting"):
            value = persona.get(key)
            if not isinstance(value, str) or not value.strip():
                report.error(f"{where}.persona.{key} 必须是非空字符串")

    knowledge = data.get("knowledge")
    if not isinstance(knowledge, list):
        report.error(f"{where}.knowledge 必须是数组")
    else:
        seen_keys: set[str] = set()
        for index, item in enumerate(knowledge):
            kwhere = f"{where}.knowledge[{index}]"
            if not isinstance(item, dict):
                report.error(f"{kwhere} 必须是对象")
                continue
            require_keys(
                item, ["key", "value"], report, kwhere, allowed={"key", "value"}
            )
            for key in ("key", "value"):
                value = item.get(key)
                if not isinstance(value, str) or not value.strip():
                    report.error(f"{kwhere}.{key} 必须是非空字符串")
            key_value = item.get("key")
            if isinstance(key_value, str):
                if key_value in seen_keys:
                    report.warn(f"{kwhere}.key 重复: {key_value!r}")
                seen_keys.add(key_value)

    idle_lines = data.get("idle_lines")
    if not isinstance(idle_lines, list):
        report.error(f"{where}.idle_lines 必须是数组")
    else:
        if not idle_lines:
            report.warn(f"{where}.idle_lines 为空，桌宠不会主动说话")
        for index, item in enumerate(idle_lines):
            lwhere = f"{where}.idle_lines[{index}]"
            if not isinstance(item, dict):
                report.error(f"{lwhere} 必须是对象")
                continue
            require_keys(
                item,
                ["text", "action", "weight"],
                report,
                lwhere,
                allowed={"text", "action", "weight"},
            )
            for key in ("text", "action"):
                value = item.get(key)
                if not isinstance(value, str) or not value.strip():
                    report.error(f"{lwhere}.{key} 必须是非空字符串")
            weight = item.get("weight")
            if not is_number(weight) or float(weight) <= 0:
                report.error(f"{lwhere}.weight 必须是大于 0 的数字")
            action_id = item.get("action")
            if actions is not None and isinstance(action_id, str):
                if action_id not in actions:
                    report.error(
                        f"{lwhere}.action 引用了不存在的动作: {action_id!r}"
                    )
                elif actions[action_id].get("loop") is True:
                    report.warn(
                        f"{lwhere}.action 引用了循环动作 {action_id!r}；"
                        "建议 idle_lines 使用非循环动作"
                    )
def validate_action_file(
    path: Path, contract: dict, report: Report
) -> dict | None:
    data = load_json(path, report, "动作")
    if not isinstance(data, dict):
        return None
    where = f"动作 {path.name}"
    require_keys(
        data,
        ["id", "duration", "loop", "tracks"],
        report,
        where,
        allowed={"id", "display_name", "duration", "loop", "easing", "tracks"},
    )
    check_id(data.get("id"), f"{where}.id", report)

    duration = data.get("duration")
    if not is_number(duration) or float(duration) <= 0:
        report.error(f"{where}.duration 必须是大于 0 的数字")
        duration = None
    if not isinstance(data.get("loop"), bool):
        report.error(f"{where}.loop 必须是布尔值")
    easing = data.get("easing")
    if easing is not None and easing not in ALLOWED_EASINGS:
        report.error(f"{where}.easing 不在允许列表: {easing!r}")

    tracks = data.get("tracks")
    if not isinstance(tracks, dict) or not tracks:
        report.error(f"{where}.tracks 必须是非空对象")
        return data

    allowed_targets = set(contract.get("action", {}).get("allowed_targets", []))
    if not allowed_targets:
        allowed_targets = {"root"} | set(contract.get("parts", {}))

    for target, track in tracks.items():
        twhere = f"{where}.tracks.{target}"
        if target not in allowed_targets:
            report.error(f"{twhere}: 未知动作目标 {target!r}")
        if not isinstance(track, dict) or not track:
            report.error(f"{twhere} 必须是非空对象")
            continue
        for channel in sorted(set(track) - CHANNELS):
            report.error(f"{twhere}: 未知通道 '{channel}'")
        if not any(channel in CHANNELS for channel in track):
            report.error(f"{twhere}: 至少需要一个通道（tx/ty/rot/sx/sy）")
        for channel, frames in track.items():
            if channel not in CHANNELS:
                continue
            cwhere = f"{twhere}.{channel}"
            if not isinstance(frames, list) or not frames:
                report.error(f"{cwhere} 必须是非空关键帧数组")
                continue
            previous_t: float | None = None
            for index, frame in enumerate(frames):
                fwhere = f"{cwhere}[{index}]"
                if not isinstance(frame, dict):
                    report.error(f"{fwhere} 必须是对象")
                    continue
                require_keys(
                    frame,
                    ["t", "v"],
                    report,
                    fwhere,
                    allowed={"t", "v", "ease"},
                )
                t = frame.get("t")
                value = frame.get("v")
                if not is_number(t):
                    report.error(f"{fwhere}.t 必须是数字")
                    continue
                t_value = float(t)
                if t_value < 0:
                    report.error(f"{fwhere}.t 不能小于 0")
                if duration is not None and t_value > float(duration) + 1e-9:
                    report.error(f"{fwhere}.t 超出 duration ({duration})")
                if previous_t is not None and t_value <= previous_t:
                    report.error(
                        f"{fwhere}.t 必须严格递增（前一个为 {previous_t}）"
                    )
                previous_t = t_value
                if not is_number(value):
                    report.error(f"{fwhere}.v 必须是数字")
                elif channel in ("sx", "sy") and float(value) < 0:
                    report.error(f"{fwhere}.v 缩放不能为负数")
                frame_ease = frame.get("ease")
                if frame_ease is not None and frame_ease not in ALLOWED_EASINGS:
                    report.error(f"{fwhere}.ease 不在允许列表: {frame_ease!r}")
            if data.get("loop") is True and len(frames) >= 2:
                first = frames[0].get("v")
                last = frames[-1].get("v")
                if (
                    is_number(first)
                    and is_number(last)
                    and abs(float(first) - float(last)) > 1e-6
                ):
                    report.warn(
                        f"{cwhere}: 循环动作首尾值不一致"
                        f"（{first} -> {last}），可能出现跳变"
                    )
    return data


def validate_actions_dir(
    path: Path, contract: dict, report: Report
) -> dict[str, dict]:
    actions: dict[str, dict] = {}
    if not path.is_dir():
        report.error(f"动作目录不存在: {path}")
        return actions
    files = sorted(path.glob("*.json"))
    if not files:
        report.warn(f"动作目录为空: {path}")
        return actions
    for file_path in files:
        data = validate_action_file(file_path, contract, report)
        if not isinstance(data, dict):
            continue
        action_id = data.get("id")
        if isinstance(action_id, str) and action_id:
            if action_id in actions:
                report.error(f"动作 id 重复: {action_id!r}（{file_path}）")
            actions[action_id] = data
    return actions


def resolve_character_file(path: Path) -> Path:
    if path.is_dir():
        return path / "character.json"
    return path


def _configure_output() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = argparse.ArgumentParser(description="Window Pet Generator 契约校验器")
    parser.add_argument(
        "--contract",
        type=Path,
        default=DEFAULT_CONTRACT,
        help="rig_contract.json 路径",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    character_parser = subparsers.add_parser(
        "character", help="校验一个角色目录或 character.json"
    )
    character_parser.add_argument("path", type=Path)
    character_parser.add_argument(
        "--actions-dir",
        type=Path,
        default=None,
        help="同时校验动作目录，并检查 idle_lines 引用的动作是否存在",
    )

    action_parser = subparsers.add_parser("action", help="校验一个动作 JSON")
    action_parser.add_argument("path", type=Path)

    actions_parser = subparsers.add_parser("actions", help="校验整个动作目录")
    actions_parser.add_argument("path", type=Path)

    args = parser.parse_args(argv)
    report = Report()
    contract = load_contract(args.contract, report)
    if contract is None:
        report.print("契约")
        return 1

    if args.command == "character":
        character_file = resolve_character_file(args.path)
        actions = None
        if args.actions_dir is not None:
            actions = validate_actions_dir(args.actions_dir, contract, report)
        validate_character_file(character_file, contract, report, actions)
        report.print(f"角色校验: {character_file}")
    elif args.command == "action":
        validate_action_file(args.path, contract, report)
        report.print(f"动作校验: {args.path}")
    elif args.command == "actions":
        validate_actions_dir(args.path, contract, report)
        report.print(f"动作目录校验: {args.path}")

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())