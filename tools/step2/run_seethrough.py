# -*- coding: utf-8 -*-
"""用 See-through 对一张图跑自动分层（LayerDiff + Marigold + PostProcess + SavePSD）。"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

import requests

COMFY = "http://127.0.0.1:8188"
PROJ = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator")
COMFY_INPUT = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\input")
COMFY_OUTPUT = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\output")


def build_workflow(image_name, prefix, seed, resolution, steps, resolution_depth):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "SeeThrough_LoadLayerDiffModel",
              "inputs": {"model": "24yearsold/seethroughv0.0.2_layerdiff3d_nf4",
                         "quant_mode": "nf4", "cache_tag_embeds": True,
                         "group_offload": False, "auto_download": False}},
        "3": {"class_type": "SeeThrough_LoadDepthModel",
              "inputs": {"model": "24yearsold/seethroughv0.0.1_marigold_nf4",
                         "quant_mode": "nf4", "cache_tag_embeds": True,
                         "group_offload": False, "auto_download": False}},
        "4": {"class_type": "SeeThrough_GenerateLayers",
              "inputs": {"image": ["1", 0], "layerdiff_model": ["2", 0],
                         "seed": seed, "resolution": resolution,
                         "num_inference_steps": steps}},
        "5": {"class_type": "SeeThrough_GenerateDepth",
              "inputs": {"layers": ["4", 0], "depth_model": ["3", 0],
                         "seed": seed, "resolution_depth": resolution_depth}},
        "6": {"class_type": "SeeThrough_PostProcess",
              "inputs": {"layers_depth": ["5", 0], "tblr_split": True, "use_lama": True}},
        "7": {"class_type": "SeeThrough_SavePSD",
              "inputs": {"parts": ["6", 0], "filename_prefix": prefix}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--prefix", default="seethrough_seed777")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--resolution", type=int, default=1024)
    ap.add_argument("--steps", type=int, default=25)
    ap.add_argument("--resolution-depth", type=int, default=640)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    src = PROJ / args.input
    image_name = args.prefix + ".png"
    dst = COMFY_INPUT / image_name
    if not (dst.exists() and dst.stat().st_size > 100):
        shutil.copyfile(src, dst)
        print("copied input ->", image_name)
    else:
        print("input already exists ->", image_name)

    wf = build_workflow(image_name, args.prefix, args.seed, args.resolution, args.steps, args.resolution_depth)
    r = requests.post(f"{COMFY}/prompt", json={"prompt": wf, "client_id": "wpg-seethrough"}, timeout=60)
    if r.status_code != 200:
        print("POST failed", r.status_code, r.text[:500]); return 1
    pid = r.json()["prompt_id"]
    print("submitted", pid)

    # 长时间轮询（模型加载 + 扩散 + 深度）
    done = False
    for _ in range(240):
        time.sleep(10)
        h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
        rec = h.get(pid)
        if rec and rec.get("status", {}).get("status_str") == "success":
            done = True
            break
        if rec and rec.get("status", {}).get("status_str") == "error":
            print("ERROR:", json.dumps(rec.get("status", {}), ensure_ascii=False)[:1200])
            return 1
    if not done:
        print("timeout"); return 1

    # 从 log 读取 info 文件路径（SavePSD 写入 seethrough_psd_info.log）
    log = COMFY_OUTPUT / "seethrough_psd_info.log"
    if not log.exists():
        print("no seethrough_psd_info.log"); return 1
    info_rel = log.read_text(encoding="utf-8", errors="replace").strip()
    info_path = (COMFY_OUTPUT / info_rel) if not Path(info_rel).is_absolute() else Path(info_rel)
    print("info_file:", info_path)
    if not info_path.exists():
        print("info file missing:", info_path); return 1
    data = json.loads(info_path.read_text(encoding="utf-8"))
    out_dir = PROJ / "photo_cartoon_instance" / "seethrough_seed777"
    out_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for layer in data["layers"]:
        name = layer["name"]
        fn = layer["filename"]
        srcp = COMFY_OUTPUT / fn
        if srcp.exists():
            shutil.copyfile(srcp, out_dir / f"{name}.png")
            copied.append(name)
    (out_dir / "layers.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print("layers:", copied)
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
