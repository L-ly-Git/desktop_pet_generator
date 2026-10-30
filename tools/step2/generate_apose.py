# -*- coding: utf-8 -*-
"""生成 A-pose 易拆版 Q版立绘（openpose ControlNet + 脸 IP-Adapter + chibi LoRA），ISNet 抠图。"""
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.step2.matte_isnet import predict_alpha

COMFY = "http://127.0.0.1:8188"
PROJ = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator")

POSITIVE = (
    "masterpiece, best quality, chibi, Q版, chibi style, cute, big head small body, "
    "1:2 head body ratio, flat colors, clean lineart, simple cel shading, "
    "full body, standing, front view, A-pose, arms spread away from body, legs wide apart, feet apart, "
    "long black hair, pure white cropped top with fur trim, light blue denim shorts, white sneakers, "
    "big sparkling eyes, large detailed eyes, wide open eyes, cute round face, plain light background"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, "
    "signature, realistic, photorealistic, 3d, ugly, blurry, deformed, disfigured, "
    "bad proportions, extra limbs, cropped, small eyes, closed eyes, "
    "arms down, arms touching body, legs together, feet together, wrong colors, black top"
)


def build_prompt(seed, prefix, ipa_weight, lora_strength, cn_strength):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": "input_03.jpg"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "apose.png"}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "anything-v5-PrtRE.safetensors"}},
        "4": {"class_type": "LoraLoader",
              "inputs": {"model": ["3", 0], "clip": ["3", 1], "lora_name": "yuzusoft-chibiV2.safetensors",
                         "strength_model": lora_strength, "strength_clip": 0.7}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "6": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "7": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["4", 0], "ipadapter": ["6", 0], "image": ["1", 0], "weight": ipa_weight,
                         "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["5", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": POSITIVE, "clip": ["4", 1]}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["4", 1]}},
        "10": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "control_v11p_sd15_openpose_fp16.safetensors"}},
        "11": {"class_type": "ControlNetApplyAdvanced",
               "inputs": {"positive": ["8", 0], "negative": ["9", 0], "control_net": ["10", 0], "image": ["2", 0],
                          "strength": cn_strength, "start_percent": 0.0, "end_percent": 1.0}},
        "12": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "13": {"class_type": "KSampler",
               "inputs": {"model": ["7", 0], "seed": seed, "steps": 28, "cfg": 7.0,
                          "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "positive": ["11", 0], "negative": ["11", 1], "latent_image": ["12", 0], "denoise": 1.0}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 2]}},
        "15": {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": prefix}},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="12345,777,2026")
    ap.add_argument("--prefix", default="apose_chibi")
    ap.add_argument("--ipa-weight", type=float, default=0.70)
    ap.add_argument("--lora-strength", type=float, default=0.95)
    ap.add_argument("--cn-strength", type=float, default=0.80)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    out_dir = PROJ / "photo_cartoon_instance" / "apose_chibi"
    out_dir.mkdir(parents=True, exist_ok=True)

    for seed in [int(s) for s in args.seeds.split(",")]:
        wf = build_prompt(seed, args.prefix, args.ipa_weight, args.lora_strength, args.cn_strength)
        r = requests.post(f"{COMFY}/prompt", json={"prompt": wf, "client_id": "wpg-apose"}, timeout=30)
        if r.status_code != 200:
            print(f"seed {seed}: POST failed {r.status_code}: {r.text[:300]}"); continue
        pid = r.json()["prompt_id"]
        print(f"seed {seed}: submitted {pid}")
        meta = None
        for _ in range(200):
            time.sleep(3)
            h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
            rec = h.get(pid)
            if rec and rec.get("outputs"):
                meta = rec["outputs"].get("15", {}).get("images", [])
                if meta: break
            if rec and rec.get("status", {}).get("status_str") == "error":
                print(f"seed {seed}: ERROR", json.dumps(rec.get("status", {}), ensure_ascii=False)[:500]); break
        if not meta:
            print(f"seed {seed}: timeout"); continue
        for im in meta:
            fn = im["filename"]; sub = im.get("subfolder", "")
            img = requests.get(f"{COMFY}/view", params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
            rgb = out_dir / f"rgb_seed{seed}.png"
            rgb.write_bytes(img.content)
            bgr = cv2.imdecode(np.frombuffer(img.content, np.uint8), cv2.IMREAD_COLOR)
            alpha = predict_alpha(bgr)
            rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA); rgba[..., 3] = alpha
            dest = out_dir / f"rgba_seed{seed}.png"
            Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(dest)
            print(f"seed {seed}: saved {dest}")
    print("DONE")


if __name__ == "__main__":
    main()
