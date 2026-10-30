# -*- coding: utf-8 -*-
"""生成后端注册表。"""
from __future__ import annotations

from .base import GenerateBackend, LogFn
from .comfyui import ComfyUIBackend
from .cloud import CloudBackend

_BACKENDS: dict[str, GenerateBackend] = {
    "comfyui": ComfyUIBackend(),
    "cloud": CloudBackend(),
}


def get_backend(name: str) -> GenerateBackend:
    return _BACKENDS.get(name, _BACKENDS["comfyui"])


def list_backends() -> list[GenerateBackend]:
    return list(_BACKENDS.values())


def default_backend() -> GenerateBackend:
    return _BACKENDS["comfyui"]
