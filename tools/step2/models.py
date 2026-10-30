# -*- coding: utf-8 -*-
"""Load and verify the local Step 2 models."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from .config import MODEL_SPECS, UNIFACE_CACHE_DIR

# Force UniFace to use the project-local cache.
os.environ["UNIFACE_CACHE_DIR"] = str(UNIFACE_CACHE_DIR)

from uniface import BiSeNet, MODNet, SCRFD
from uniface.constants import MODNetWeights, ParsingWeights, SCRFDWeights
import onnxruntime as ort


class ModelVerificationError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_model(name: str) -> dict:
    spec = MODEL_SPECS[name]
    path: Path = spec["path"]
    if not path.is_file():
        raise ModelVerificationError(f"模型不存在: {path}")
    size = path.stat().st_size
    if size != spec["size"]:
        raise ModelVerificationError(
            f"模型大小不匹配: {path}（{size} != {spec['size']}）"
        )
    digest = sha256_file(path)
    if digest.lower() != spec["sha256"].lower():
        raise ModelVerificationError(
            f"模型 SHA-256 不匹配: {path}（{digest}）"
        )
    return {
        "name": name,
        "path": str(path),
        "size": size,
        "sha256": digest,
        "purpose": spec["purpose"],
    }


def verify_all_models() -> list[dict]:
    return [verify_model(name) for name in MODEL_SPECS]


def model_info() -> list[dict]:
    result = []
    for name, spec in MODEL_SPECS.items():
        path: Path = spec["path"]
        result.append(
            {
                "name": name,
                "path": str(path),
                "exists": path.is_file(),
                "size": path.stat().st_size if path.is_file() else 0,
                "expected_size": spec["size"],
                "sha256": spec["sha256"],
                "purpose": spec["purpose"],
            }
        )
    return result


def load_detector() -> SCRFD:
    verify_model("scrfd_500m")
    return SCRFD(
        model_name=SCRFDWeights.SCRFD_500M_KPS,
        providers=["CPUExecutionProvider"],
    )


def load_parser() -> BiSeNet:
    verify_model("parsing_resnet18")
    return BiSeNet(
        model_name=ParsingWeights.RESNET18,
        providers=["CPUExecutionProvider"],
    )


def load_matting() -> MODNet:
    verify_model("modnet_photographic")
    return MODNet(
        model_name=MODNetWeights.PHOTOGRAPHIC,
        providers=["CPUExecutionProvider"],
    )


def load_animgan_session() -> ort.InferenceSession:
    verify_model("animeganv2")
    return ort.InferenceSession(
        str(MODEL_SPECS["animeganv2"]["path"]),
        providers=["CPUExecutionProvider"],
    )