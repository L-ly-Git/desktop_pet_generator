# -*- coding: utf-8 -*-
"""下载 See-through 的 NF4 模型到本机 ComfyUI（走 hf-mirror，带断点续传）。"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

COMFY_SEETHROUGH = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\models\SeeThrough")
REPOS = [
    ("24yearsold/seethroughv0.0.2_layerdiff3d_nf4", "seethroughv0.0.2_layerdiff3d_nf4"),
    ("24yearsold/seethroughv0.0.1_marigold_nf4", "seethroughv0.0.1_marigold_nf4"),
]


def repo_files(repo: str) -> list[tuple[str, int]]:
    r = requests.get(f"https://huggingface.co/api/models/{repo}/tree/main?recursive=true", timeout=60)
    r.raise_for_status()
    files = []
    for item in r.json():
        if item.get("type") == "file":
            files.append((item["path"], item.get("size") or 0))
    return files


def download(url: str, dest: Path, retries: int = 4) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            headers = {}
            if tmp.exists():
                headers["Range"] = f"bytes={tmp.stat().st_size}-"
            with requests.get(url, headers=headers, stream=True, timeout=120) as r:
                if r.status_code in (200, 206):
                    total = int(r.headers.get("Content-Length") or 0)
                    mode = "ab" if r.status_code == 206 else "wb"
                    got = tmp.stat().st_size if mode == "ab" else 0
                    with open(tmp, mode) as f:
                        for chunk in r.iter_content(1 << 20):
                            f.write(chunk)
                            got += len(chunk)
                    tmp.replace(dest)
                    return True
                elif r.status_code in (301, 302):
                    url = r.headers["Location"]
                    continue
                else:
                    print(f"  HTTP {r.status_code} {url}")
        except Exception as e:
            print(f"  retry {attempt + 1}: {e}")
        import time
        time.sleep(4)
    return False


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for repo, local_name in REPOS:
        files = repo_files(repo)
        total = sum(sz for _, sz in files)
        print(f"=== {repo} -> {local_name}  ({len(files)} files, {total/1e9:.2f} GB) ===")
        base = COMFY_SEETHROUGH / local_name
        done = 0
        for rel, size in files:
            dest = base / rel
            if dest.exists() and dest.stat().st_size == size and size > 0:
                done += size
                continue
            url = f"https://hf-mirror.com/{repo}/resolve/main/{rel}"
            if not download(url, dest):
                print(f"  FAILED {rel}")
                return 1
            done += size
            print(f"  [{done/1e9:.2f}/{total/1e9:.2f} GB] {rel}")
        # 校验 model_index.json 存在
        if not (base / "model_index.json").exists():
            print(f"  WARN: model_index.json missing in {base}")
    print("ALL DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
