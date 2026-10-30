# -*- coding: utf-8 -*-
"""生成后端接口定义（Step 2A 的可插拔后端）。

每个后端负责把「真人照片」变成「A-pose 透明底 Q 版立绘 RGBA」，
输出产物一致，下游 2B/2C/3/5 不关心后端是谁。
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

LogFn = Callable[[str], None]


class GenerateBackend:
    """生成后端基类。"""

    name: str = "base"
    label: str = "基础后端"

    def available(self) -> tuple[bool, str]:
        """返回 (是否可用, 不可用原因或空串)。"""
        raise NotImplementedError

    def generate(
        self,
        photo: Path,
        character_id: str,
        *,
        gender: str,
        preset: str,
        seeds: list[int],
        on_log: LogFn | None = None,
    ) -> list[Path]:
        """生成 A-pose 透明底 Q 版立绘。

        返回与 seeds 对齐的 RGBA PNG 路径列表（失败项为 None）。
        """
        raise NotImplementedError
