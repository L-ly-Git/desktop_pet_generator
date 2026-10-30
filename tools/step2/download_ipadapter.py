# -*- coding: utf-8 -*-
"""Step 2 Route B 前置：下载 IP-Adapter(SD1.5) + CLIP Vision + Q版 LoRA 到本机 ComfyUI。"""
import os
import shutil
import sys
import time
from pathlib import Path

import requests

COMFY = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI")
PROJ = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator")

# (目标相对 ComfyUI 目录, 下载 URL, 本地名称)
DOWNLOADS = [
    ("models/ipadapter/ip-adapter-plus_sd15.safetensors",
     "https://hf-mirror.com/h94/IP-Adapter/resolve/main/models/ip-adapter-plus_sd15.safetensors"),
    ("models/ipadapter/ip-adapter-plus-face_sd15.safetensors",
     "https://hf-mirror.com/h94/IP-Adapter/resolve/main/models/ip-adapter-plus-face_sd15.safetensors"),
    ("models/clip_vision/CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors",
     "https://hf-mirror.com/h94/IP-Adapter/resolve/main/models/image_encoder/model.safetensors"),
    ("models/loras/yuzusoft-chibiV2.safetensors",
     "https://civitai.com/api/download/models/14467"),
]

# 输入图片：复制到 ComfyUI input/
INPUTS = [
    (PROJ / "03.jpg", "input_03.jpg"),
    (PROJ / "photo_cartoon_instance" / "屏幕截图 2026-10-25 225137.png", "ref_style_1.png"),
    (PROJ / "photo_cartoon_instance" / "屏幕截图 2026-10-27 190335.png", "ref_style_2.png"),
]


def download(url: str, dest: Path, retries: int = 4) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            headers = {}
            if tmp.exists():
                headers["Range"] = f"bytes={tmp.stat().st_size}-"
            with requests.get(url, headers=headers, stream=True, timeout=60) as r:
                if r.status_code in (200, 206):
                    total = int(r.headers.get("Content-Length") or 0)
                    mode = "ab" if r.status_code == 206 else "wb"
                    got = tmp.stat().st_size if mode == "ab" else 0
                    with open(tmp, mode) as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                            got += len(chunk)
                            if total:
                                print(f"\r  {dest.name}: {got/1e6:6.1f}/{total/1e6:.1f} MB", end="", flush=True)
                    tmp.replace(dest)
                    print(f"\r  OK {dest.name}  ({dest.stat().st_size/1e6:.1f} MB)   ")
                    return True
                elif r.status_code == 302 or r.status_code == 301:
                    url = r.headers["Location"]
                    continue
                else:
                    print(f"\n  HTTP {r.status_code} for {url}")
            time.sleep(3)
        except Exception as e:
            print(f"\n  attempt {attempt+1} failed: {e}")
            time.sleep(5)
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    # 1) 复制输入图
    input_dir = COMFY / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    for src, name in INPUTS:
        if src.exists():
            shutil.copyfile(src, input_dir / name)
            print(f"copy input -> {name}")
        else:
            print(f"WARN missing input {src}")

    # 2) 下载模型
    ok = True
    for rel, url in DOWNLOADS:
        dest = COMFY / rel
        if dest.exists() and dest.stat().st_size > 100_000:
            print(f"skip exists {rel}")
            continue
        print(f"download {rel}")
        if not download(url, dest):
            print(f"FAILED {rel}")
            ok = False
    print("ALL OK" if ok else "SOME FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
