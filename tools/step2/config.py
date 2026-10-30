# -*- coding: utf-8 -*-
"""Step 2 paths, model manifest and constants."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODELS_DIR = ROOT / "models"
UNIFACE_CACHE_DIR = MODELS_DIR / "uniface"
ANIMEGAN_DIR = MODELS_DIR / "animeganv2"
ARTIFACTS_DIR = ROOT / "artifacts" / "step2"
CANVAS_SIZE = 512

ANIMEGAN_MODEL = ANIMEGAN_DIR / "face_paint_512_v2_0.onnx"
SCRFD_MODEL = UNIFACE_CACHE_DIR / "scrfd_500m.onnx"
PARSING_MODEL = UNIFACE_CACHE_DIR / "parsing_resnet18.onnx"
MODNET_MODEL = UNIFACE_CACHE_DIR / "modnet_photographic.onnx"

MODEL_SPECS = {
    "animeganv2": {
        "path": ANIMEGAN_MODEL,
        "size": 8594990,
        "sha256": "1381b17ed988e14a1f3cf8954d88073c0884ff4b70128ebe599f0d6021bca63e",
        "purpose": "AnimeGANv2 face_paint_512_v2 ONNX cartoonization",
    },
    "scrfd_500m": {
        "path": SCRFD_MODEL,
        "size": 2524817,
        "sha256": "5e4447f50245bbd7966bd6c0fa52938c61474a04ec7def48753668a9d8b4ea3a",
        "purpose": "SCRFD 500M face detection",
    },
    "parsing_resnet18": {
        "path": PARSING_MODEL,
        "size": 53205364,
        "sha256": "0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f",
        "purpose": "BiSeNet ResNet18 face parsing",
    },
    "modnet_photographic": {
        "path": MODNET_MODEL,
        "size": 25969398,
        "sha256": "5069a5e306b9f5e9f4f2b0360264c9f8ea13b257c7c39943c7cf6a2ec3a102ae",
        "purpose": "MODNet photographic portrait matting",
    },
}

CELEBAMASK_CLASSES = {
    0: "background",
    1: "skin",
    2: "nose",
    3: "eye_g",
    4: "l_eye",
    5: "r_eye",
    6: "l_brow",
    7: "r_brow",
    8: "l_ear",
    9: "r_ear",
    10: "mouth",
    11: "u_lip",
    12: "l_lip",
    13: "hair",
    14: "hat",
    15: "ear_r",
    16: "neck_l",
    17: "neck",
    18: "cloth",
}