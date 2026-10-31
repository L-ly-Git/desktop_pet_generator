# -*- coding: utf-8 -*-
"""本地 ComfyUI 生成后端（Step 2A）。

真人照片 -> A-pose 透明底 Q 版立绘：
  anything-v5 + yuzusoft-chibiV2 LoRA + 双 IP-Adapter(脸/全图) + openpose ControlNet(A-pose)
  生成 3 个 seed -> ISNet 抠图 -> 透明底 RGBA。
"""
from __future__ import annotations

import os
import re
import shutil
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

PROJ = Path(__file__).resolve().parents[3]
if str(PROJ) not in sys.path:
    sys.path.insert(0, str(PROJ))
try:
    from app_paths import data_root
    PROJ = data_root()
except Exception:  # pragma: no cover
    pass

from .base import GenerateBackend  # noqa: E402
from tools.step2.matte_isnet import predict_alpha  # noqa: E402

COMFY = os.environ.get("WPG_COMFY_URL", "http://127.0.0.1:8188")
COMFY_INPUT = Path(os.environ.get(
    "WPG_COMFY_INPUT",
    r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\input",
))

SEEDS = [12345, 777, 2026]
CN = 0.80

# 相似度预设：face=脸部IP权重, full=全图IP权重, lora=chibi LoRA强度, ckpt=底模
CONFIGS = {
    "A": dict(face=0.65, full=0.35, lora=0.90, ckpt="anything-v5-PrtRE.safetensors", label="基线"),
    "B": dict(face=0.80, full=0.45, lora=0.85, ckpt="anything-v5-PrtRE.safetensors", label="增强相似(推荐)"),
    "C": dict(face=0.85, full=0.50, lora=0.80, ckpt="AbyssOrangeMix2_hard.safetensors", label="最大相似"),
}

STYLE = (
    "masterpiece, best quality, chibi, Q版, chibi style, big head small body, 1:2 head body ratio, "
    "flat colors, clean lineart, simple cel shading, full body, standing, front view, A-pose, "
    "arms spread away from body, legs wide apart, big sparkling eyes, wide open eyes, round face, "
    "plain light background"
)
NEG_BASE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, signature, realistic, "
    "photorealistic, 3d, ugly, blurry, deformed, disfigured, bad proportions, extra limbs, cropped, small eyes, "
    "closed eyes, arms down, legs together, wrong colors"
)
GENDER_PROMPTS = {
    "男": (STYLE + ", boy, male, short hair, handsome",
           NEG_BASE + ", female, girl, woman, long hair, ponytail, dress, skirt"),
    "女": (STYLE + ", girl, female, long hair, cute",
           NEG_BASE + ", male, man, boy, short hair, beard"),
}


def detect_gender(photo: Path) -> str:
    from tools.step2.features import extract_profile
    from tools.step2.models import load_detector, load_matting, load_parser
    detector = load_detector()
    parser = load_parser()
    matting = load_matting()
    try:
        from tools.step2.matte_isnet import imread_unicode
        bgr = imread_unicode(photo)
    except Exception:  # noqa: BLE001
        bgr = cv2.imread(str(photo), cv2.IMREAD_COLOR)
    analysis = extract_profile(bgr, detector, parser, matting, photo)
    hl = analysis.profile["hair_length"]
    if hl == "long":
        return "女"
    if hl == "short":
        return "男"
    return "女"


def build_workflow(image_name: str, seed: int, positive: str, negative: str, cfg: dict) -> dict:
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "apose.png"}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": cfg["ckpt"]}},
        "4": {"class_type": "LoraLoader",
              "inputs": {"model": ["3", 0], "clip": ["3", 1], "lora_name": "yuzusoft-chibiV2.safetensors",
                         "strength_model": cfg["lora"], "strength_clip": 0.7}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "6": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "7": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["4", 0], "ipadapter": ["6", 0], "image": ["1", 0], "weight": cfg["face"],
                         "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["5", 0]}},
        "8": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus_sd15.safetensors"}},
        "9": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["7", 0], "ipadapter": ["8", 0], "image": ["1", 0], "weight": cfg["full"],
                         "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["5", 0]}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4", 1]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": negative, "clip": ["4", 1]}},
        "12": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "control_v11p_sd15_openpose_fp16.safetensors"}},
        "13": {"class_type": "ControlNetApplyAdvanced",
               "inputs": {"positive": ["10", 0], "negative": ["11", 0], "control_net": ["12", 0], "image": ["2", 0],
                          "strength": CN, "start_percent": 0.0, "end_percent": 1.0}},
        "14": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "15": {"class_type": "KSampler",
               "inputs": {"model": ["9", 0], "seed": seed, "steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m",
                          "scheduler": "karras", "positive": ["13", 0], "negative": ["13", 1],
                          "latent_image": ["14", 0], "denoise": 1.0}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15", 0], "vae": ["3", 2]}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["16", 0], "filename_prefix": f"step2_{image_name}"}},
    }


class ComfyUIBackend(GenerateBackend):
    name = "comfyui"
    label = "本地 ComfyUI"

    def available(self) -> tuple[bool, str]:
        try:
            r = requests.get(f"{COMFY}/system_stats", timeout=5)
            if r.status_code == 200:
                return True, ""
            return False, f"ComfyUI 响应异常(HTTP {r.status_code})"
        except Exception as exc:  # noqa: BLE001
            return False, f"ComfyUI 未运行({COMFY})：{exc}"

    def generate(self, photo, character_id, *, gender, preset, seeds=None, on_log=None) -> list[Path]:
        seeds = list(seeds or SEEDS)
        cid = re.sub(r"[^A-Za-z0-9_-]+", "_", character_id).strip("_") or "photo"

        def log(msg: str):
            print(msg, flush=True)
            if on_log:
                on_log(msg)

        if gender == "auto":
            log("  [auto] 检测性别…")
            try:
                gender = detect_gender(Path(photo))
            except Exception as exc:  # noqa: BLE001
                log(f"  [auto] 性别检测不可用({exc})，默认按 女 处理")
                gender = "女"
        cfg = CONFIGS.get(preset, CONFIGS["B"])
        positive, negative = GENDER_PROMPTS.get(gender, GENDER_PROMPTS["女"])
        log(f"=== 生成 A-pose 立绘 (性别={gender}, 预设={preset}:{cfg['label']}) ===")

        image_name = f"step2_{cid}.png"
        if not COMFY_INPUT.is_dir():
            raise RuntimeError(f"ComfyUI input 目录不存在：{COMFY_INPUT}")
        shutil.copyfile(photo, COMFY_INPUT / image_name)
        log(f"  已复制照片 {image_name}")

        apose_dir = PROJ / "photo_cartoon_instance" / f"apose_{cid}"
        apose_dir.mkdir(parents=True, exist_ok=True)

        results: list[Path | None] = []
        for seed in seeds:
            wf = build_workflow(image_name, seed, positive, negative, cfg)
            try:
                r = requests.post(f"{COMFY}/prompt", json={"prompt": wf, "client_id": "wpg-step2"}, timeout=30)
            except Exception as exc:  # noqa: BLE001
                log(f"  seed {seed}: 提交失败 {exc}")
                results.append(None)
                continue
            if r.status_code != 200:
                log(f"  seed {seed}: 提交失败 HTTP {r.status_code}")
                results.append(None)
                continue
            pid = r.json().get("prompt_id")
            log(f"  seed {seed}: 已提交 {pid}")

            meta = None
            for _ in range(200):
                time.sleep(3)
                try:
                    h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
                except Exception:
                    continue
                rec = h.get(pid)
                if rec and rec.get("outputs"):
                    meta = rec["outputs"].get("17", {}).get("images", [])
                    if meta:
                        break
                if rec and rec.get("status", {}).get("status_str") == "error":
                    log(f"  seed {seed}: 生成报错")
                    break

            if not meta:
                log(f"  seed {seed}: 超时")
                results.append(None)
                continue

            saved = None
            for im in meta:
                fn = im["filename"]
                sub = im.get("subfolder", "")
                try:
                    img = requests.get(f"{COMFY}/view",
                                       params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
                    bgr = cv2.imdecode(np.frombuffer(img.content, np.uint8), cv2.IMREAD_COLOR)
                    if bgr is None:
                        continue
                    alpha = predict_alpha(bgr)
                    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA)
                    rgba[..., 3] = alpha
                    out = apose_dir / f"rgba_seed{seed}.png"
                    Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(out)
                    saved = out
                    log(f"  seed {seed}: 已保存 rgba_seed{seed}.png")
                except Exception as exc:  # noqa: BLE001
                    log(f"  seed {seed}: 抠图/保存失败 {exc}")
            results.append(saved)

        return results
