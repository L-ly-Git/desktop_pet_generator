# -*- coding: utf-8 -*-
"""相似度参数调控实验：3 组参数 x 10 张照片，对比相似度。"""
from __future__ import annotations

import shutil
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
PROJ = Path(__file__).resolve().parents[2]
COMFY_INPUT = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\input")

# 三组参数：face=脸IP权重, full=全图IP权重, lora=chibi LoRA强度, ckpt=底模
CONFIGS = {
    "A_基线":     dict(face=0.65, full=0.35, lora=0.90, ckpt="anything-v5-PrtRE.safetensors"),
    "B_增强相似": dict(face=0.80, full=0.45, lora=0.85, ckpt="anything-v5-PrtRE.safetensors"),
    "C_最大相似": dict(face=0.85, full=0.50, lora=0.80, ckpt="AbyssOrangeMix2_hard.safetensors"),
}
PHOTOS = ["03.jpg","04.jpg","05.png","06.png","07.png","08.png","09.png","10.png","11.png","12.png"]
GENDERS = {"03":"女","04":"女","05":"男","06":"女","07":"男","08":"男","09":"女","10":"女","11":"女","12":"女"}

STYLE = ("masterpiece, best quality, chibi, Q版, chibi style, big head small body, 1:2 head body ratio, "
         "flat colors, clean lineart, simple cel shading, full body, standing, front view, A-pose, "
         "arms spread away from body, legs wide apart, big sparkling eyes, wide open eyes, round face, plain light background")
NEG_BASE = ("lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, signature, realistic, "
            "photorealistic, 3d, ugly, blurry, deformed, disfigured, bad proportions, extra limbs, cropped, small eyes, closed eyes, arms down, legs together, wrong colors")
GENDER_PROMPTS = {
    "男": (STYLE + ", boy, male, short hair, handsome", NEG_BASE + ", female, girl, woman, long hair, ponytail, dress, skirt"),
    "女": (STYLE + ", girl, female, long hair, cute", NEG_BASE + ", male, man, boy, short hair, beard"),
}


def build_workflow(image_name, seed, cfg, positive, negative):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "apose.png"}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": cfg["ckpt"]}},
        "4": {"class_type": "LoraLoader", "inputs": {"model": ["3",0], "clip": ["3",1], "lora_name": "yuzusoft-chibiV2.safetensors", "strength_model": cfg["lora"], "strength_clip": 0.7}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "6": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "7": {"class_type": "IPAdapterAdvanced", "inputs": {"model": ["4",0], "ipadapter": ["6",0], "image": ["1",0], "weight": cfg["face"], "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only", "clip_vision": ["5",0]}},
        "8": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus_sd15.safetensors"}},
        "9": {"class_type": "IPAdapterAdvanced", "inputs": {"model": ["7",0], "ipadapter": ["8",0], "image": ["1",0], "weight": cfg["full"], "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only", "clip_vision": ["5",0]}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4",1]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4",1]}},
        "12": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "control_v11p_sd15_openpose_fp16.safetensors"}},
        "13": {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["10",0], "negative": ["11",0], "control_net": ["12",0], "image": ["2",0], "strength": 0.8, "start_percent": 0.0, "end_percent": 1.0}},
        "14": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "15": {"class_type": "KSampler", "inputs": {"model": ["9",0], "seed": seed, "steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "positive": ["13",0], "negative": ["13",1], "latent_image": ["14",0], "denoise": 1.0}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15",0], "vae": ["3",2]}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["16",0], "filename_prefix": f"tune_{image_name}"}},
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    for cfg_name, cfg in CONFIGS.items():
        out_dir = PROJ / "photo_cartoon_instance" / f"tune_{cfg_name.split('_')[0]}"
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"=== 配置 {cfg_name} ===")
        for photo in PHOTOS:
            pid = photo.split(".")[0]
            gender = GENDERS[pid]
            positive, negative = GENDER_PROMPTS[gender]
            image_name = f"tune_{pid}.png"
            shutil.copyfile(PROJ / photo, COMFY_INPUT / image_name)
            wf = build_workflow(image_name, 777, cfg, positive, negative)
            r = requests.post(f"{COMFY}/prompt", json={"prompt": wf, "client_id": "wpg-tune"}, timeout=30)
            if r.status_code != 200:
                print(f"  {photo}: POST failed {r.status_code}"); continue
            prompt_id = r.json()["prompt_id"]
            meta = None
            for _ in range(200):
                time.sleep(2)
                h = requests.get(f"{COMFY}/history/{prompt_id}", timeout=30).json()
                rec = h.get(prompt_id)
                if rec and rec.get("outputs"):
                    meta = rec["outputs"].get("17", {}).get("images", [])
                    if meta: break
                if rec and rec.get("status", {}).get("status_str") == "error":
                    print(f"  {photo}: ERROR"); break
            if not meta:
                print(f"  {photo}: timeout"); continue
            for im in meta:
                fn = im["filename"]; sub = im.get("subfolder", "")
                img = requests.get(f"{COMFY}/view", params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
                bgr = cv2.imdecode(np.frombuffer(img.content, np.uint8), cv2.IMREAD_COLOR)
                alpha = predict_alpha(bgr)
                rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA); rgba[..., 3] = alpha
                Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(out_dir / f"{pid}.png")
                print(f"  {photo}: saved")
    print("ALL DONE")


if __name__ == "__main__":
    raise SystemExit(main())
