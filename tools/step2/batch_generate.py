# -*- coding: utf-8 -*-
"""Step 2 Route B 批量验证：10 张照片，参数与 v5 一致，每张自动提取特征生成人设提示词。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import requests
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.step2.features import extract_profile
from tools.step2.hair_color import hair_color_from_mask
from tools.step2.models import load_detector, load_matting, load_parser
from tools.step2.matte_isnet import predict_alpha

COMFY = "http://127.0.0.1:8188"
PROJ = Path(r"D:\Python\item\WindowPet\Window_Pet_Generator")

SEEDS = [12345, 777, 2026]
IPA_WEIGHT = 0.70
LORA_STRENGTH = 0.95
CN_STRENGTH = 0.50

STYLE = (
    "masterpiece, best quality, chibi, Q版, chibi style, cute, big head small body, "
    "1:2 head body ratio, flat colors, clean lineart, simple cel shading, "
    "full body, standing, front view, arms down, plain light background, "
    "big sparkling eyes, large detailed eyes, wide open eyes, cute round face"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, "
    "signature, realistic, photorealistic, 3d, ugly, blurry, deformed, disfigured, "
    "bad proportions, extra limbs, cropped, small eyes, closed eyes, wrong colors"
)


def color_name(rgb: list[int]) -> str:
    r, g, b = [float(v) / 255.0 for v in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    v = mx
    s = (mx - mn) / mx if mx > 0 else 0.0
    if mx == mn:
        h = 0.0
    elif mx == r:
        h = (60 * ((g - b) / (mx - mn)) + 360) % 360
    elif mx == g:
        h = 60 * ((b - r) / (mx - mn)) + 120
    else:
        h = 60 * ((r - g) / (mx - mn)) + 240
    if v < 0.30:
        return "black"
    if s < 0.14:
        if v > 0.85:
            return "white"
        if v > 0.45:
            return "gray"
        return "dark gray"
    if h < 15 or h >= 345:
        return "red" if v > 0.45 else "brown"
    if h < 45:
        return "brown" if v < 0.55 else "orange"
    if h < 70:
        return "olive" if v < 0.5 else "yellow"
    if h < 160:
        return "green"
    if h < 200:
        return "cyan"
    if h < 250:
        return "blue"
    if h < 285:
        return "purple"
    if h < 330:
        return "pink"
    return "red"


def hair_len_cn(x: str) -> str:
    return {"long": "long", "medium": "medium-length", "short": "short"}.get(x, "medium-length")


def build_positive(profile: dict) -> str:
    hair = f"{hair_len_cn(profile['hair_length'])} {color_name(profile['hair_color'])} hair"
    primary = color_name(profile["clothing_primary"])
    secondary = color_name(profile["clothing_secondary"])
    outfit = f"wearing a {primary} outfit with {secondary} details"
    glasses = ", wearing glasses" if profile.get("glasses_detected") else ""
    return STYLE + f", {hair}, {outfit}{glasses}"


def submit(workflow: dict) -> str:
    r = requests.post(f"{COMFY}/prompt", json={"prompt": workflow, "client_id": "wpg-batch"}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"POST /prompt {r.status_code}: {r.text[:300]}")
    return r.json()["prompt_id"]


def wait_image(pid: str, node_id: str = "15") -> list:
    for _ in range(300):
        time.sleep(3)
        h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
        rec = h.get(pid)
        if rec and rec.get("outputs"):
            meta = rec["outputs"].get(node_id, {}).get("images", [])
            if meta:
                return meta
        if rec and rec.get("status", {}).get("status_str") == "error":
            raise RuntimeError(json.dumps(rec.get("status", {}), ensure_ascii=False)[:500])
    return []


def build_workflow(image_name: str, canny_name: str, positive: str, seed: int):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": image_name}},
        "2": {"class_type": "LoadImage", "inputs": {"image": canny_name}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "anything-v5-PrtRE.safetensors"}},
        "4": {"class_type": "LoraLoader",
              "inputs": {"model": ["3", 0], "clip": ["3", 1], "lora_name": "yuzusoft-chibiV2.safetensors",
                         "strength_model": LORA_STRENGTH, "strength_clip": 0.7}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "6": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "7": {"class_type": "IPAdapterAdvanced",
              "inputs": {"model": ["4", 0], "ipadapter": ["6", 0], "image": ["1", 0], "weight": IPA_WEIGHT,
                         "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0,
                         "embeds_scaling": "V only", "clip_vision": ["5", 0]}},
        "8": {"class_type": "CLIPTextEncode", "inputs": {"text": positive, "clip": ["4", 1]}},
        "9": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["4", 1]}},
        "10": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "control_v11p_sd15_canny_fp16.safetensors"}},
        "11": {"class_type": "ControlNetApplyAdvanced",
               "inputs": {"positive": ["8", 0], "negative": ["9", 0], "control_net": ["10", 0], "image": ["2", 0],
                          "strength": CN_STRENGTH, "start_percent": 0.0, "end_percent": 1.0}},
        "12": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "13": {"class_type": "KSampler",
               "inputs": {"model": ["7", 0], "seed": seed, "steps": 28, "cfg": 7.0,
                          "sampler_name": "dpmpp_2m", "scheduler": "karras",
                          "positive": ["11", 0], "negative": ["11", 1], "latent_image": ["12", 0], "denoise": 1.0}},
        "14": {"class_type": "VAEDecode", "inputs": {"samples": ["13", 0], "vae": ["3", 2]}},
        "15": {"class_type": "SaveImage", "inputs": {"images": ["14", 0], "filename_prefix": f"batch_{image_name}"}},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs", default="03.jpg,04.jpg,05.png,06.png,07.png,08.png,09.png,10.png,11.png,12.png")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    names = [n.strip() for n in args.inputs.split(",") if n.strip()]
    comfy_input = Path(r"D:\tools\ComfyDesktop\ComfyUI-aki-v3\ComfyUI\input")
    out_root = PROJ / "photo_cartoon_instance" / "batch"
    out_root.mkdir(parents=True, exist_ok=True)

    detector = load_detector()
    parser = load_parser()
    matting = load_matting()

    summary = []
    for name in names:
        src = PROJ / name
        if not src.exists():
            print(f"[skip] {name} not found")
            continue
        stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem)
        try:
            image_bgr = cv2.imread(str(src), cv2.IMREAD_COLOR)
            analysis = extract_profile(image_bgr, detector, parser, matting, src)
            robust_hair = hair_color_from_mask(image_bgr, analysis.full_parse_mask)
            if robust_hair:
                analysis.profile["hair_color"] = robust_hair
            positive = build_positive(analysis.profile)
        except Exception as e:
            print(f"[skip] {name}: feature extract failed: {e}")
            summary.append({"input": name, "status": "FAIL(feature)", "reason": str(e)})
            continue

        # canny 控制图：等比缩放 + 黑边补齐(不拉伸)
        h0, w0 = image_bgr.shape[:2]
        scale = min(512 / w0, 768 / h0)
        nw, nh = int(round(w0 * scale)), int(round(h0 * scale))
        letter = np.zeros((768, 512, 3), dtype=np.uint8)
        resized = cv2.resize(image_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
        letter[(768 - nh) // 2:(768 - nh) // 2 + nh, (512 - nw) // 2:(512 - nw) // 2 + nw] = resized
        gray = cv2.cvtColor(letter, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 100, 200)
        canny_name = f"batch_{stem}_canny.png"
        cv2.imwrite(str(comfy_input / canny_name), edges)
        # 输入图
        input_name = f"batch_{stem}.png"
        cv2.imwrite(str(comfy_input / input_name), image_bgr)

        out_dir = out_root / stem
        out_dir.mkdir(parents=True, exist_ok=True)
        print(f"== {name} -> hair={color_name(analysis.profile['hair_color'])} "
              f"len={analysis.profile['hair_length']} outfit={analysis.profile['outfit_style']} "
              f"c1={color_name(analysis.profile['clothing_primary'])} "
              f"c2={color_name(analysis.profile['clothing_secondary'])} glasses={analysis.profile['glasses_detected']}")

        ok = True
        for seed in SEEDS:
            try:
                wf = build_workflow(input_name, canny_name, positive, seed)
                pid = submit(wf)
                metas = wait_image(pid)
                if not metas:
                    print(f"   seed {seed}: timeout"); ok = False; continue
                for im in metas:
                    fn = im["filename"]; sub = im.get("subfolder", "")
                    img = requests.get(f"{COMFY}/view", params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
                    bgr = cv2.imdecode(np.frombuffer(img.content, np.uint8), cv2.IMREAD_COLOR)
                    alpha = predict_alpha(bgr)
                    rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA); rgba[..., 3] = alpha
                    dest = out_dir / f"rgba_seed{seed}.png"
                    Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(dest)
                    print(f"   seed {seed}: saved {dest}")
            except Exception as e:
                print(f"   seed {seed}: ERROR {e}")
                ok = False
        summary.append({"input": name, "status": "OK" if ok else "PARTIAL"})

    print("===== SUMMARY =====")
    for s in summary:
        print(s)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
