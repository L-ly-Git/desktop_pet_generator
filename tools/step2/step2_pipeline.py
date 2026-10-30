# -*- coding: utf-8 -*-
"""Step 2 完整流程：照片 -> A-pose Q版立绘 -> 自动分层 -> 校验。

生成部分由可插拔后端负责（默认本地 ComfyUI；云端后端后续接入）。
本脚本只做“调度 + 分层”两步。

用法:
    .venv\\Scripts\\python.exe tools\\step2\\step2_pipeline.py --photo 05.png --character-id photo05 --name "照片角色05" --gender 男
    .venv\\Scripts\\python.exe tools\\step2\\step2_pipeline.py --photo 03.jpg --character-id photo03 --gender 女 --preset B --backend comfyui
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

PROJ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJ))

from tools.step2.generate_backends import get_backend, list_backends


def run_split(cid: str, name: str, src: Path) -> Path:
    """调用 split_general 自动分层（SAM+几何），返回输出目录。"""
    split_dir = PROJ / "characters" / cid
    r = subprocess.run(
        [sys.executable, str(PROJ / "tools" / "step2" / "split_general.py"),
         "--input", str(src), "--output-dir", str(split_dir),
         "--character-id", cid, "--name", name],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print(r.stdout.strip())
    if r.returncode != 0:
        print(r.stderr.strip(), file=sys.stderr)
        raise RuntimeError("自动分层失败")
    return split_dir


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", required=True)
    ap.add_argument("--character-id", required=True)
    ap.add_argument("--name", default="照片角色")
    ap.add_argument("--gender", choices=["男", "女", "auto"], default="auto")
    ap.add_argument("--preset", choices=["A", "B", "C"], default="B",
                    help="相似度预设 A基线 / B增强相似(推荐) / C最大相似")
    ap.add_argument("--backend", choices=["comfyui", "cloud"], default="comfyui")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    photo = PROJ / args.photo
    if not photo.is_file():
        print(f"照片不存在: {photo}", file=sys.stderr)
        return 2
    cid = re.sub(r"[^A-Za-z0-9_-]+", "_", args.character_id).strip("_") or "photo"

    backend = get_backend(args.backend)
    ok, reason = backend.available()
    if not ok:
        print(f"后端不可用: {reason}", file=sys.stderr)
        return 1

    print(f"后端: {backend.label}")
    results = backend.generate(photo, cid, gender=args.gender, preset=args.preset)
    src = None
    for seed, path in zip([12345, 777, 2026], results):
        if path is not None and path.is_file():
            src = src or path  # 优先第一个成功的
    if src is None:
        print("没有生成出任何立绘", file=sys.stderr)
        return 1

    # 分层默认用 seed777；若缺失则用第一个成功
    apose_dir = PROJ / "photo_cartoon_instance" / f"apose_{cid}"
    preferred = apose_dir / "rgba_seed777.png"
    src = preferred if preferred.is_file() else src

    print("=== 阶段B: 自动分层(初稿) ===")
    try:
        split_dir = run_split(cid, args.name, src)
    except RuntimeError:
        return 1

    print()
    print("=== 完成 ===")
    print(f"A-pose 立绘: {apose_dir}")
    print(f"拆分初稿:   {split_dir}")
    print(f"下一步(手动校准): .venv\\Scripts\\python.exe tools\\step2\\calibrate_panel.py --dir {split_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
