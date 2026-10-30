# -*- coding: utf-8 -*-
"""Step 2 Route B：通过本机 ComfyUI API 生成 Q版立绘（最小验证，可调参数）。"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import requests

COMFY = "http://127.0.0.1:8188"
PROJ = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator")

POSITIVE_BASE = (
    "masterpiece, best quality, chibi, Q版, chibi style, cute, big head small body, "
    "1:2 head body ratio, flat colors, clean lineart, simple cel shading, "
    "full body, standing, front view, long black hair, white cropped top with fur trim, "
    "blue denim shorts, white sneakers, arms down, plain light brown background"
)
EYE_BOOST = "big sparkling eyes, large detailed eyes, wide open eyes, cute round face"
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, "
    "signature, realistic, photorealistic, 3d, ugly, blurry, deformed, disfigured, "
    "bad proportions, extra limbs, cropped, small eyes, closed eyes"
)


def build_prompt(seed, prefix, ipa_weight, lora_strength, eye_boost):
    positive = POSITIVE_BASE + ((", " + EYE_BOOST) if eye_boost else "")
    p = {
        "1": {"class_type": "LoadImage", "inputs": {"image": "input_03.jpg"}},
        "2": {"class_type": "CheckpointLoaderSimple",
              "inputs": {"ckpt_name": "anything-v5-PrtRE.safetensors"}},
        "3": {"class_type": "LoraLoader",
              "inputs": {"model": ["2", 0], "clip": ["2", 1],
                         "lora_name": "yuzusoft-chibiV2.safetensors",
                         "strength_model": lora_strength, "strength_clip": 0.7}},
        "4": {"class_type": "CLIPVisionLoader",
              "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "5": {"class_type": "IPAdapterModelLoader",
              "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "6": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["3", 0], "ipadapter": ["5", 0], "image": ["1", 0],
                         "weight": ipa_weight, "weight_type": "linear",
                         "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["4", 0]}},
        "7": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["3", 1]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["3", 1]}},
        "9": {"class_type": "EmptyLatentImage",
              "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "10": {"class_type": "KSampler",
               "inputs": {"model": ["6", 0], "seed": seed, "steps": 28, "cfg": 7.0,
                          "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "positive": ["7", 0], "negative": ["8", 0],
                          "latent_image": ["9", 0], "denoise": 1.0}},
        "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["2", 2]}},
        "12": {"class_type": "SaveImage", "inputs": {"images": ["11", 0], "filename_prefix": prefix}},
    }
    return p


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="12345,777,2026")
    ap.add_argument("--prefix", default="step2_chibi_v2")
    ap.add_argument("--ipa-weight", type=float, default=0.70)
    ap.add_argument("--lora-strength", type=float, default=0.95)
    ap.add_argument("--eye-boost", action="store_true", default=True)
    ap.add_argument("--width", type=int, default=512)
    ap.add_argument("--height", type=int, default=768)
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    seeds = [int(s) for s in args.seeds.split(",")]
    out_dir = PROJ / "photo_cartoon_instance" / args.prefix
    out_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for seed in seeds:
        prompt = build_prompt(seed, args.prefix, args.ipa_weight, args.lora_strength, args.eye_boost)
        prompt["9"]["inputs"]["width"] = args.width
        prompt["9"]["inputs"]["height"] = args.height
        r = requests.post(f"{COMFY}/prompt", json={"prompt": prompt, "client_id": "wpg-step2"}, timeout=30)
        if r.status_code != 200:
            print(f"seed {seed}: POST /prompt failed {r.status_code}: {r.text[:300]}")
            continue
        prompt_id = r.json().get("prompt_id")
        print(f"seed {seed}: submitted {prompt_id}")

        image_meta = None
        for _ in range(240):
            time.sleep(3)
            h = requests.get(f"{COMFY}/history/{prompt_id}", timeout=30).json()
            rec = h.get(prompt_id)
            if rec and rec.get("outputs"):
                image_meta = rec["outputs"].get("12", {}).get("images", [])
                if image_meta:
                    break
            if rec and rec.get("status", {}).get("status_str") == "error":
                print(f"seed {seed}: ERROR", json.dumps(rec, ensure_ascii=False)[:500])
                break
        if not image_meta:
            print(f"seed {seed}: timeout / no image")
            continue
        for im in image_meta:
            fn = im["filename"]
            sub = im.get("subfolder", "")
            img = requests.get(f"{COMFY}/view", params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
            dest = out_dir / f"seed{seed}_{fn}"
            dest.write_bytes(img.content)
            print(f"seed {seed}: saved {dest} ({len(img.content)} bytes)")
            results.append(dest)
    print("DONE", [str(x) for x in results])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
