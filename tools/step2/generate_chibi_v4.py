# -*- coding: utf-8 -*-
"""Step 2 Route B v4：
- 颜色锁定：全图 IP-Adapter(plus) 锚定服装/发色 + 强化颜色提示词
- 姿势：Canny ControlNet 锁定正面站立
- 透明背景：品红纯色背景 + 本地色键抠图(连通域，保留完整人形)
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

COMFY = "http://127.0.0.1:8188"
PROJ = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator")

POSITIVE = (
    "masterpiece, best quality, chibi, Q版, chibi style, cute, big head small body, "
    "1:2 head body ratio, flat colors, clean lineart, simple cel shading, "
    "full body, standing, front view, long black hair, white cropped top with fur trim, "
    "light blue denim shorts, white sneakers, arms down, "
    "solid magenta background, flat magenta background, "
    "big sparkling eyes, large detailed eyes, wide open eyes, cute round face, "
    "keep exact colors, white top, black hair"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, "
    "signature, realistic, photorealistic, 3d, ugly, blurry, deformed, disfigured, "
    "bad proportions, extra limbs, cropped, small eyes, closed eyes, "
    "wrong colors, black top, green top, red top, blue hair, blonde hair, green hair"
)

MAGENTA = np.array([255, 0, 255], dtype=np.float32)


def build_prompt(seed, prefix, face_w, plus_w, lora_s, cn_s):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": "input_03.jpg"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "input_03_canny.png"}},
        "3": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "anything-v5-PrtRE.safetensors"}},
        "4": {"class_type": "LoraLoader",
              "inputs": {"model": ["3", 0], "clip": ["3", 1],
                         "lora_name": "yuzusoft-chibiV2.safetensors",
                         "strength_model": lora_s, "strength_clip": 0.7}},
        "5": {"class_type": "CLIPVisionLoader",
              "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "6": {"class_type": "IPAdapterModelLoader",
              "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "7": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["4", 0], "ipadapter": ["6", 0], "image": ["1", 0],
                         "weight": face_w, "weight_type": "linear",
                         "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["5", 0]}},
        "8": {"class_type": "IPAdapterModelLoader",
              "inputs": {"ipadapter_file": "ip-adapter-plus_sd15.safetensors"}},
        "9": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["7", 0], "ipadapter": ["8", 0], "image": ["1", 0],
                         "weight": plus_w, "weight_type": "linear",
                         "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["5", 0]}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": POSITIVE, "clip": ["4", 1]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["4", 1]}},
        "12": {"class_type": "ControlNetLoader",
               "inputs": {"control_net_name": "control_v11p_sd15_canny_fp16.safetensors"}},
        "13": {"class_type": "ControlNetApplyAdvanced",
               "inputs": {"positive": ["10", 0], "negative": ["11", 0],
                          "control_net": ["12", 0], "image": ["2", 0],
                          "strength": cn_s, "start_percent": 0.0, "end_percent": 1.0}},
        "14": {"class_type": "EmptyLatentImage",
               "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "15": {"class_type": "KSampler",
               "inputs": {"model": ["9", 0], "seed": seed, "steps": 28, "cfg": 7.0,
                          "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "positive": ["13", 0], "negative": ["13", 1],
                          "latent_image": ["14", 0], "denoise": 1.0}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["3", 2]}},
        "17": {"class_type": "SaveImage",
               "inputs": {"images": ["16", 0], "filename_prefix": prefix}},
    }


def chroma_key_rgba(rgb_path: Path, dist_thresh: float = 90.0) -> np.ndarray:
    """品红色键抠图：距离品红近=背景，取最大连通域=完整人形。"""
    bgr = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
    dist = np.linalg.norm(rgb - MAGENTA, axis=2)
    bg = (dist < dist_thresh).astype(np.uint8)
    fg = 1 - bg
    # 连通域：保留最大前景块
    num, labels, stats, _ = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if num > 1:
        largest = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        fg = (labels == largest).astype(np.uint8)
    # 形态学清理 + 边缘羽化
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(fg.astype(np.float32), (0, 0), 1.2)
    alpha_u8 = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
    rgba[..., 3] = alpha_u8
    # 清理边缘品红残留
    m = alpha_u8 > 0
    rgba[..., 0:3][m] = np.clip(bgr[m].astype(np.float32), 0, 255).astype(np.uint8)
    return rgba


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="12345,777,2026")
    ap.add_argument("--prefix", default="step2_chibi_v4")
    ap.add_argument("--face-weight", type=float, default=0.70)
    ap.add_argument("--plus-weight", type=float, default=0.50)
    ap.add_argument("--lora-strength", type=float, default=0.95)
    ap.add_argument("--cn-strength", type=float, default=0.60)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = PROJ / "photo_cartoon_instance" / args.prefix
    out_dir.mkdir(parents=True, exist_ok=True)

    for seed in seeds:
        prompt = build_prompt(seed, args.prefix, args.face_weight, args.plus_weight, args.lora_strength, args.cn_strength)
        r = requests.post(f"{COMFY}/prompt", json={"prompt": prompt, "client_id": "wpg-v4"}, timeout=30)
        if r.status_code != 200:
            print(f"seed {seed}: POST failed {r.status_code}: {r.text[:300]}")
            continue
        pid = r.json().get("prompt_id")
        print(f"seed {seed}: submitted {pid}")
        image_meta = None
        for _ in range(300):
            time.sleep(3)
            h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
            rec = h.get(pid)
            if rec and rec.get("outputs"):
                image_meta = rec["outputs"].get("17", {}).get("images", [])
                if image_meta:
                    break
            if rec and rec.get("status", {}).get("status_str") == "error":
                print(f"seed {seed}: ERROR", json.dumps(rec.get("status", {}), ensure_ascii=False)[:500])
                break
        if not image_meta:
            print(f"seed {seed}: timeout")
            continue
        for im in image_meta:
            fn = im["filename"]; sub = im.get("subfolder", "")
            img = requests.get(f"{COMFY}/view", params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
            rgb_dest = out_dir / f"rgb_seed{seed}_{fn}"
            rgb_dest.write_bytes(img.content)
            rgba = chroma_key_rgba(rgb_dest)
            rgba_dest = out_dir / f"rgba_seed{seed}_{Path(fn).stem}.png"
            Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(rgba_dest)
            print(f"seed {seed}: saved {rgba_dest}")
    print("DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
