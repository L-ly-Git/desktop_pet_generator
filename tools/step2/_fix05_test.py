# -*- coding: utf-8 -*-
import sys, time, requests, cv2, numpy as np
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.step2.matte_isnet import predict_alpha

COMFY = "http://127.0.0.1:8188"
PROJ = Path(__file__).resolve().parents[2]

POSITIVE = (
    "masterpiece, best quality, chibi, Q版, chibi style, cute, big head small body, 1:2 head body ratio, "
    "flat colors, clean lineart, simple cel shading, full body, standing, front view, A-pose, "
    "arms spread away from body, legs wide apart, big sparkling eyes, wide open eyes, cute round face, "
    "plain light background"
)
NEGATIVE = (
    "lowres, bad anatomy, bad hands, extra fingers, missing fingers, text, watermark, signature, realistic, "
    "photorealistic, 3d, ugly, blurry, deformed, disfigured, bad proportions, extra limbs, cropped, small eyes, "
    "closed eyes, arms down, legs together, wrong colors, dress, skirt, long hair, female, girl"
)

def wf(seed):
    return {
        "1": {"class_type": "LoadImage", "inputs": {"image": "step2_photo05.png"}},
        "2": {"class_type": "LoadImage", "inputs": {"image": "apose.png"}},
        "3": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "anything-v5-PrtRE.safetensors"}},
        "4": {"class_type": "LoraLoader", "inputs": {"model": ["3",0], "clip": ["3",1], "lora_name": "yuzusoft-chibiV2.safetensors", "strength_model": 0.9, "strength_clip": 0.7}},
        "5": {"class_type": "CLIPVisionLoader", "inputs": {"clip_name": "CLIP-ViT-H-14-laion2B-s32B-b79K.safetensors"}},
        "6": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus-face_sd15.safetensors"}},
        "7": {"class_type": "IPAdapterAdvanced", "inputs": {"model": ["4",0], "ipadapter": ["6",0], "image": ["1",0], "weight": 0.65, "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only", "clip_vision": ["5",0]}},
        "8": {"class_type": "IPAdapterModelLoader", "inputs": {"ipadapter_file": "ip-adapter-plus_sd15.safetensors"}},
        "9": {"class_type": "IPAdapterAdvanced", "inputs": {"model": ["7",0], "ipadapter": ["8",0], "image": ["1",0], "weight": 0.35, "weight_type": "linear", "combine_embeds": "concat", "start_at": 0.0, "end_at": 1.0, "embeds_scaling": "V only", "clip_vision": ["5",0]}},
        "10": {"class_type": "CLIPTextEncode", "inputs": {"text": POSITIVE, "clip": ["4",1]}},
        "11": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["4",1]}},
        "12": {"class_type": "ControlNetLoader", "inputs": {"control_net_name": "control_v11p_sd15_openpose_fp16.safetensors"}},
        "13": {"class_type": "ControlNetApplyAdvanced", "inputs": {"positive": ["10",0], "negative": ["11",0], "control_net": ["12",0], "image": ["2",0], "strength": 0.8, "start_percent": 0.0, "end_percent": 1.0}},
        "14": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 768, "batch_size": 1}},
        "15": {"class_type": "KSampler", "inputs": {"model": ["9",0], "seed": seed, "steps": 28, "cfg": 7.0, "sampler_name": "dpmpp_2m", "scheduler": "karras", "positive": ["13",0], "negative": ["13",1], "latent_image": ["14",0], "denoise": 1.0}},
        "16": {"class_type": "VAEDecode", "inputs": {"samples": ["15",0], "vae": ["3",2]}},
        "17": {"class_type": "SaveImage", "inputs": {"images": ["16",0], "filename_prefix": "fix05"}},
    }

for seed in [777, 12345]:
    r = requests.post(f"{COMFY}/prompt", json={"prompt": wf(seed), "client_id": "wpg-fix05"}, timeout=30)
    if r.status_code != 200:
        print("POST failed", r.status_code, r.text[:300]); continue
    pid = r.json()["prompt_id"]
    print(f"seed {seed}: submitted {pid}")
    meta = None
    for _ in range(200):
        time.sleep(3)
        h = requests.get(f"{COMFY}/history/{pid}", timeout=30).json()
        rec = h.get(pid)
        if rec and rec.get("outputs"):
            meta = rec["outputs"].get("17", {}).get("images", [])
            if meta: break
        if rec and rec.get("status", {}).get("status_str") == "error":
            print("ERROR", json.loads("{}") and rec.get("status",{}).get("messages")); break
    if not meta:
        print(f"seed {seed}: timeout"); continue
    for im in meta:
        fn = im["filename"]; sub = im.get("subfolder","")
        img = requests.get(f"{COMFY}/view", params={"filename": fn, "subfolder": sub, "type": "output"}, timeout=60)
        bgr = cv2.imdecode(np.frombuffer(img.content, np.uint8), cv2.IMREAD_COLOR)
        alpha = predict_alpha(bgr)
        rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2BGRA); rgba[...,3] = alpha
        out = PROJ / "photo_cartoon_instance" / f"fix05_seed{seed}.png"
        Image.fromarray(cv2.cvtColor(rgba, cv2.COLOR_BGRA2RGBA)).save(out)
        print(f"seed {seed}: saved {out}")
print("DONE")
