# -*- coding: utf-8 -*-
"""加载契约、角色档案和部件图片。"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt5.QtGui import QPixmap


@dataclass(frozen=True)
class PartSpec:
    name: str
    file: Path
    pivot: tuple[float, float]
    z: int
    parent: str | None
    required: bool


@dataclass
class Character:
    id: str
    name: str
    contract_version: str
    canvas_width: int
    canvas_height: int
    anchor: tuple[float, float]
    parts: dict[str, PartSpec]
    pixmaps: dict[str, QPixmap]
    persona: dict[str, Any]
    knowledge: list[dict[str, Any]]
    idle_lines: list[dict[str, Any]]
    root_dir: Path
    contract: dict[str, Any]

    @property
    def parts_by_z(self) -> list[PartSpec]:
        return sorted(self.parts.values(), key=lambda part: (part.z, part.name))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 顶层必须是对象: {path}")
    return data


def resolve_character_file(path: Path) -> Path:
    return path / "character.json" if path.is_dir() else path


def build_node_graph(
    character: Character,
) -> tuple[dict[str, str | None], dict[str, tuple[float, float]]]:
    """构造 root + 所有已加载部件的父子关系与枢轴表。"""
    parents: dict[str, str | None] = {"root": None}
    pivots: dict[str, tuple[float, float]] = {"root": character.anchor}
    for name, part in character.parts.items():
        parent = part.parent
        if parent not in (None, "root") and parent not in character.parts:
            raise ValueError(f"部件 {name!r} 的父级 {parent!r} 缺失")
        parents[name] = parent if parent is not None else "root"
        pivots[name] = part.pivot
    return parents, pivots


def load_character(character_path: Path, contract_path: Path) -> Character:
    """加载一个角色；调用前必须先创建 QApplication。"""
    character_file = resolve_character_file(character_path)
    contract = load_json(contract_path)
    data = load_json(character_file)

    version = data.get("contract_version")
    contract_version = contract.get("contract_version")
    if version != contract_version:
        raise ValueError(
            f"contract_version 不匹配: 角色 {version!r}, 契约 {contract_version!r}"
        )

    canvas = contract.get("canvas", {})
    width = int(canvas.get("width", 0))
    height = int(canvas.get("height", 0))
    anchor_raw = canvas.get("anchor_point")
    if not (isinstance(anchor_raw, list) and len(anchor_raw) == 2):
        raise ValueError("契约 canvas.anchor_point 必须是 [x, y]")
    anchor = (float(anchor_raw[0]), float(anchor_raw[1]))

    contract_parts = contract.get("parts", {})
    rig = data.get("rig", {})
    rig_parts = rig.get("parts", {}) if isinstance(rig, dict) else {}
    if not isinstance(rig_parts, dict):
        raise ValueError("角色 rig.parts 必须是对象")

    parts: dict[str, PartSpec] = {}
    pixmaps: dict[str, QPixmap] = {}
    character_dir = character_file.parent

    for name, spec in contract_parts.items():
        if not isinstance(spec, dict):
            continue
        required = bool(spec.get("required", False))
        if name not in rig_parts:
            if required:
                raise ValueError(f"缺少必需部件: {name}")
            continue
        part_data = rig_parts[name]
        if not isinstance(part_data, dict):
            raise ValueError(f"部件 {name!r} 必须是对象")
        file_value = part_data.get("file")
        pivot_value = part_data.get("pivot")
        if not isinstance(file_value, str) or not file_value:
            raise ValueError(f"部件 {name!r} 缺少 file")
        if not (isinstance(pivot_value, list) and len(pivot_value) == 2):
            raise ValueError(f"部件 {name!r} 的 pivot 必须是 [x, y]")

        image_path = character_dir / file_value
        pixmap = QPixmap(str(image_path))
        if pixmap.isNull():
            raise ValueError(f"无法加载部件图片: {image_path}")
        if pixmap.width() != width or pixmap.height() != height:
            raise ValueError(
                f"部件 {name!r} 尺寸必须是 {width}x{height}，"
                f"实际为 {pixmap.width()}x{pixmap.height()}"
            )

        parts[name] = PartSpec(
            name=name,
            file=image_path,
            pivot=(float(pivot_value[0]), float(pivot_value[1])),
            z=int(spec.get("z", 0)),
            parent=spec.get("parent"),
            required=required,
        )
        pixmaps[name] = pixmap

    persona = data.get("persona")
    if not isinstance(persona, dict):
        raise ValueError("角色 persona 必须是对象")
    knowledge = data.get("knowledge", [])
    idle_lines = data.get("idle_lines", [])
    if not isinstance(knowledge, list) or not isinstance(idle_lines, list):
        raise ValueError("角色 knowledge/idle_lines 必须是数组")

    character_id = str(data.get("id", ""))
    return Character(
        id=character_id,
        name=str(persona.get("name", character_id or "character")),
        contract_version=str(version),
        canvas_width=width,
        canvas_height=height,
        anchor=anchor,
        parts=parts,
        pixmaps=pixmaps,
        persona=persona,
        knowledge=knowledge,
        idle_lines=idle_lines,
        root_dir=character_dir,
        contract=contract,
    )