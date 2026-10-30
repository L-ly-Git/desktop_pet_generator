# -*- coding: utf-8 -*-
"""路径工具：区分“开发模式”与“PyInstaller 冻结模式”。"""
from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def data_root() -> Path:
    """可写/外部数据根目录。开发时=项目根，冻结时=exe 所在目录。"""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def actions_dir() -> Path:
    """动作库目录：优先外部(exe旁 assets/actions)，否则项目内置。"""
    ext = data_root() / "assets" / "actions"
    if ext.is_dir():
        return ext
    return Path(__file__).resolve().parent / "assets" / "actions"
