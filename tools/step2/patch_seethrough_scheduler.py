# -*- coding: utf-8 -*-
"""Patch See-through 的 LayerDiff 管道：调度器改本地直接构造，不联网下载。"""
from pathlib import Path

TARGET = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\custom_nodes\ComfyUI-See-through\see-through\common\modules\layerdiffuse\diffusers_kdiffusion_sdxl.py")

old = '''            scheduler = scheduler_configs[scheduler_config_name][0].from_pretrained(
                    model_id,
                    subfolder="scheduler",
                    **scheduler_configs[scheduler_config_name][1],
            )'''

new = '''            scheduler = scheduler_configs[scheduler_config_name][0](
                    **scheduler_configs[scheduler_config_name][1],
            )'''

t = TARGET.read_text(encoding="utf-8")
if old not in t:
    print("ERROR: target block not found")
    raise SystemExit(1)
t = t.replace(old, new)
TARGET.write_text(t, encoding="utf-8")
print("PATCHED:", TARGET)
