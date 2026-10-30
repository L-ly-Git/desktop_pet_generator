# -*- coding: utf-8 -*-
"""Stable photo -> 9-part Q版 chibi converter.

Output:
    out/
      character.json
      parts/head.png, body.png, arm_l.png, arm_r.png,
            leg_l.png, leg_r.png, eye_l.png, eye_r.png, mouth.png
      preview.png

Default style matches the example: twin braids, wide-brim straw hat,
sleeveless dress with five-petal flowers, white socks/shoes.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.step2.chibi_render_style import render_chibi
from tools.step2.config import ROOT
from tools.step2.features import extract_profile
from tools.step2.models import load_detector, load_matting, load_parser

EXAMPLE_HAIR = [36, 30, 32]
EXAMPLE_EYE = [45, 38, 40]
EXAMPLE_MOUTH = [190, 105, 115]
EXAMPLE_PRIMARY = [245, 205, 90]
EXAMPLE_SECONDARY = [205, 160, 70]


def read_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        rgb = np.asarray(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def _hex(rgb) -> str:
    r, g, b = [max(0, min(255, int(round(value)))) for value in rgb[:3]]
    return f"#{r:02x}{g:02x}{b:02x}"


def apply_preset(profile: dict, args) -> dict:
    result = dict(profile)
    result["colors_hex"] = dict(profile.get("colors_hex", {}))

    if args.preset == "example":
        result["outfit_style"] = "dress"
        result["hat_detected"] = True
        result["hair_style"] = "twin_braids"
        result["hair_length"] = "twin_braids"
        result["leg_style"] = "socks"
        result["glasses_detected"] = False
        if not args.keep_photo_colors:
            result["hair_color"] = list(EXAMPLE_HAIR)
            result["eye_color"] = list(EXAMPLE_EYE)
            result["mouth_color"] = list(EXAMPLE_MOUTH)
            result["clothing_primary"] = list(EXAMPLE_PRIMARY)
            result["clothing_secondary"] = list(EXAMPLE_SECONDARY)
    else:
        result["hair_style"] = "auto"
        result["leg_style"] = "auto"

    if args.outfit != "auto":
        result["outfit_style"] = args.outfit
    if args.hat != "auto":
        result["hat_detected"] = args.hat == "on"
    if args.hair_style != "auto":
        result["hair_style"] = args.hair_style

    for key in (
        "skin",
        "hair",
        "eye",
        "mouth",
        "clothing_primary",
        "clothing_secondary",
    ):
        color_key = key + "_color" if key == "skin" else key + "_color"
        if key == "clothing_primary":
            color_key = "clothing_primary"
        elif key == "clothing_secondary":
            color_key = "clothing_secondary"
        value = result.get(color_key)
        if isinstance(value, (list, tuple)) and len(value) >= 3:
            result["colors_hex"][key] = _hex(value)
    return result


def validate_output(character_dir: Path) -> tuple[bool, str]:
    command = [
        sys.executable,
        str(ROOT / "tools" / "validate.py"),
        "character",
        str(character_dir),
        "--actions-dir",
        str(ROOT / "assets" / "actions"),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="照片 → 稳定 9 部件 Q版卡通小人（示例风格）"
    )
    parser.add_argument("--input", "-i", type=Path, required=True, help="输入照片")
    parser.add_argument(
        "--output-dir",
        "-o",
        type=Path,
        default=ROOT / "photo_cartoon_instance" / "out",
        help="输出目录（直接包含 character.json/parts/preview.png）",
    )
    parser.add_argument("--character-id", default="photo_char_01")
    parser.add_argument("--name", default="照片角色 01")
    parser.add_argument(
        "--preset",
        choices=["example", "photo"],
        default="example",
        help="example=示例风格（黑双辫/草帽/黄裙）；photo=照片配色与自动服装",
    )
    parser.add_argument(
        "--outfit",
        choices=["auto", "dress", "tunic"],
        default="auto",
    )
    parser.add_argument(
        "--hat",
        choices=["auto", "on", "off"],
        default="auto",
    )
    parser.add_argument(
        "--hair-style",
        choices=["auto", "long", "medium", "short", "twin_braids"],
        default="auto",
    )
    parser.add_argument(
        "--keep-photo-colors",
        action="store_true",
        help="example 预设下仍使用照片提取的发色/服装色",
    )
    parser.add_argument("--face-margin", type=float, default=0.35)
    parser.add_argument("--no-validate", action="store_true")
    return parser
def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = build_parser().parse_args(argv)
    input_path = args.input if args.input.is_absolute() else ROOT / args.input
    if not input_path.is_file():
        print(f"照片不存在: {input_path}", file=sys.stderr)
        return 1

    character_id = re.sub(
        r"[^A-Za-z0-9_-]+", "_", args.character_id
    ).strip("_") or "photo_char_01"
    if character_id != args.character_id:
        print(
            f"角色 id 已规范化为合法值: {args.character_id!r} -> {character_id!r}"
        )

    out_dir = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    try:
        detector = load_detector()
        parser = load_parser()
        matting = load_matting()
        model_load_s = time.perf_counter() - t0
        image = read_image(input_path)
        analysis = extract_profile(
            image,
            detector,
            parser,
            matting,
            input_path,
            face_margin=args.face_margin,
        )
        profile = apply_preset(analysis.profile, args)
        result = render_chibi(profile, out_dir, character_id, args.name)
    except Exception as exc:
        print(f"生成失败: {exc}", file=sys.stderr)
        return 1

    validation_ok = True
    validation_output = ""
    if not args.no_validate:
        validation_ok, validation_output = validate_output(out_dir)
    elif not (out_dir / "character.json").is_file():
        validation_ok = False
        validation_output = "character.json 未生成"

    colors = profile.get("colors_hex", {})
    print("=== photo_to_chibi9 ===")
    print(f"输入: {input_path}")
    print(f"输出: {out_dir}")
    print(
        "风格: "
        f"preset={args.preset} outfit={profile.get('outfit_style')} "
        f"hat={profile.get('hat_detected')} hair={profile.get('hair_style')} "
        f"legs={profile.get('leg_style')}"
    )
    print(
        "配色: "
        f"skin={colors.get('skin')} hair={colors.get('hair')} "
        f"eye={colors.get('eye')} mouth={colors.get('mouth')} "
        f"clothes={colors.get('clothing_primary')}/{colors.get('clothing_secondary')}"
    )
    print(f"模型加载: {model_load_s:.2f}s")
    print(f"分层目录: {result['parts_dir']}")
    print(f"character.json: {result['character_json']}")
    print(f"preview.png: {result['preview']}")
    print(f"契约校验: {'PASS' if validation_ok else 'FAIL'}")
    if not validation_ok and validation_output:
        print(validation_output.strip())
    return 0 if validation_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())