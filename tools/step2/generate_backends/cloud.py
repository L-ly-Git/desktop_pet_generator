# -*- coding: utf-8 -*-
"""云端生成后端（占位）：后续接入在线图片生成服务。

接口与 ComfyUIBackend 一致；未接入时 available() 返回 False。
"""
from __future__ import annotations

from .base import GenerateBackend


class CloudBackend(GenerateBackend):
    name = "cloud"
    label = "云端生成（待接入）"

    def available(self) -> tuple[bool, str]:
        return False, "云端生成后端尚未接入，请先使用本地 ComfyUI。"

    def generate(self, photo, character_id, *, gender, preset, seeds=None, on_log=None) -> list:
        raise NotImplementedError("云端生成后端尚未接入")
