# -*- coding: utf-8 -*-
"""Route A Step 2 pipeline: photo -> profile -> chibi character.

Usage:
    python tools/step2/pipeline.py --photo 02.jpg 03.jpg 04.jpg
    python tools/step2/pipeline.py --photo 02.jpg --mode preview
    python tools/step2/pipeline.py --verify-models
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.step2.chibi_renderer import render_chibi
from tools.step2.config import ARTIFACTS_DIR, CELEBAMASK_CLASSES, ROOT
from tools.step2.features import extract_profile
from tools.step2.matte import alpha_to_u8, make_checkerboard_preview
from tools.step2.models import (
    load_detector,
    load_matting,
    load_parser,
    verify_all_models,
)

PARSE_PALETTE = np.zeros((19, 3), dtype=np.uint8)
PARSE_PALETTE[1] = (220, 180, 160)
PARSE_PALETTE[2] = (200, 150, 140)
PARSE_PALETTE[3] = (80, 80, 80)
PARSE_PALETTE[4] = (0, 0, 255)
PARSE_PALETTE[5] = (0, 128, 255)
PARSE_PALETTE[6] = (0, 200, 120)
PARSE_PALETTE[7] = (0, 160, 160)
PARSE_PALETTE[8] = (180, 120, 80)
PARSE_PALETTE[9] = (200, 140, 100)
PARSE_PALETTE[10] = (0, 0, 180)
PARSE_PALETTE[11] = (0, 80, 200)
PARSE_PALETTE[12] = (0, 120, 220)
PARSE_PALETTE[13] = (120, 60, 30)
PARSE_PALETTE[14] = (80, 80, 180)
PARSE_PALETTE[17] = (170, 190, 120)
PARSE_PALETTE[18] = (120, 120, 120)


def read_image(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        image = ImageOps.exif_transpose(image).convert("RGB")
        rgb = np.array(image)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)


def save_image(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix or ".png"
    ok, buffer = cv2.imencode(suffix, image)
    if not ok:
        raise RuntimeError(f"无法编码图片: {path}")
    buffer.tofile(str(path))


def _fit_image(image_bgr: np.ndarray, width: int, height: int) -> np.ndarray:
    h, w = image_bgr.shape[:2]
    scale = min(width / max(1, w), height / max(1, h))
    new_w = max(1, int(round(w * scale)))
    new_h = max(1, int(round(h * scale)))
    interpolation = cv2.INTER_AREA if scale < 1 else cv2.INTER_LANCZOS4
    resized = cv2.resize(image_bgr, (new_w, new_h), interpolation=interpolation)
    canvas = np.full((height, width, 3), (32, 35, 42), dtype=np.uint8)
    x = (width - new_w) // 2
    y = (height - new_h) // 2
    canvas[y : y + new_h, x : x + new_w] = resized
    return canvas


def _load_font(size: int):
    font_path = ROOT.parent / "desktop_dem" / "font" / "msyh.ttc"
    try:
        return ImageFont.truetype(str(font_path), size)
    except OSError:
        return ImageFont.load_default()


def make_contact_sheet(
    original: np.ndarray,
    matte_preview: np.ndarray,
    chibi_preview_path: Path,
    profile: dict,
    output_path: Path,
) -> None:
    cell_w, cell_h = 320, 420
    label_h = 30
    gap = 10
    with Image.open(chibi_preview_path) as image:
        chibi = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
    palette = Image.new("RGB", (cell_w - 8, cell_h - label_h - 8), (32, 35, 42))
    draw = ImageDraw.Draw(palette)
    font = _load_font(15)
    small = _load_font(13)
    labels = [
        ("肤色", "skin"),
        ("发色", "hair"),
        ("眼睛", "eye"),
        ("嘴", "mouth"),
        ("衣服主色", "clothing_primary"),
        ("衣服辅色", "clothing_secondary"),
    ]
    y = 8
    for title, key in labels:
        rgb = profile.get(key, [128, 128, 128])
        color = tuple(int(value) for value in rgb[:3])
        draw.rectangle((12, y + 3, 62, y + 31), fill=color, outline=(220, 220, 220))
        draw.text((76, y + 4), title, fill=(235, 235, 235), font=font)
        draw.text(
            (76, y + 24),
            profile.get("colors_hex", {}).get(key, ""),
            fill=(170, 170, 170),
            font=small,
        )
        y += 52
    draw.text(
        (12, y + 4),
        f"发长: {profile.get('hair_length', '?')}",
        fill=(255, 220, 120),
        font=font,
    )
    draw.text(
        (12, y + 28),
        f"服装轮廓: {profile.get('outfit_style', '?')}",
        fill=(255, 220, 120),
        font=font,
    )
    if profile.get("glasses_detected"):
        draw.text((12, y + 52), "检测到眼镜", fill=(255, 220, 120), font=font)
    palette_panel = palette

    items = [
        ("原图", original),
        ("MODNet matte", matte_preview),
        ("卡通小人预览", chibi),
        ("照片特征", palette_panel),
    ]
    columns = 2
    rows = 2
    canvas = Image.new(
        "RGB",
        (
            columns * cell_w + (columns + 1) * gap,
            rows * cell_h + (rows + 1) * gap,
        ),
        (24, 27, 33),
    )
    draw = ImageDraw.Draw(canvas)
    for index, (label, image) in enumerate(items):
        column = index % columns
        row = index // columns
        x = gap + column * (cell_w + gap)
        y = gap + row * (cell_h + gap)
        draw.text((x + 4, y + 4), label, fill=(255, 220, 120), font=font)
        if index == 3:
            content = image
        else:
            if isinstance(image, Image.Image):
                image = cv2.cvtColor(np.array(image.convert("RGB")), cv2.COLOR_RGB2BGR)
            fitted = _fit_image(image, cell_w - 8, cell_h - label_h - 8)
        if index != 3:
            content = Image.fromarray(cv2.cvtColor(fitted, cv2.COLOR_BGR2RGB))
        canvas.paste(content, (x + 4, y + label_h))
        draw.rectangle(
            (x, y, x + cell_w - 1, y + cell_h - 1),
            outline=(90, 96, 110),
            width=1,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")


def validate_character(character_dir: Path) -> tuple[bool, str]:
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
    output = (result.stdout or "") + (result.stderr or "")
    return result.returncode == 0, output


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route A Step 2 照片 → 卡通小人")
    parser.add_argument(
        "--photo",
        type=Path,
        nargs="+",
        default=[ROOT / "02.jpg", ROOT / "03.jpg", ROOT / "04.jpg"],
        help="输入照片（可多个）",
    )
    parser.add_argument(
        "--mode",
        choices=["profile", "preview", "character"],
        default="character",
        help="profile=只提取特征；preview=生成预览；character=生成并校验角色",
    )
    parser.add_argument(
        "--analysis-root",
        type=Path,
        default=ARTIFACTS_DIR,
        help="分析结果输出根目录",
    )
    parser.add_argument(
        "--character-root",
        type=Path,
        default=ROOT / "assets" / "characters",
        help="最终角色输出根目录",
    )
    parser.add_argument(
        "--id-prefix",
        default="photo_char_",
        help="角色 id 前缀",
    )
    parser.add_argument(
        "--face-margin",
        type=float,
        default=0.35,
        help="人脸裁剪外扩比例",
    )
    parser.add_argument(
        "--verify-models",
        action="store_true",
        help="只校验模型文件后退出",
    )
    return parser
def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    args = build_parser().parse_args(argv)
    if args.verify_models:
        try:
            infos = verify_all_models()
        except Exception as exc:
            print(f"模型校验失败: {exc}", file=sys.stderr)
            return 1
        print("模型校验通过:")
        for info in infos:
            print(
                f"  {info['name']}: {info['path']} "
                f"({info['size']} bytes) sha256={info['sha256']}"
            )
        return 0

    photos = [path if path.is_absolute() else ROOT / path for path in args.photo]
    if not photos:
        print("没有输入照片", file=sys.stderr)
        return 1

    prefix = args.id_prefix
    if not prefix.endswith("_"):
        prefix += "_"

    t0 = time.perf_counter()
    try:
        detector = load_detector()
        parser = load_parser()
        matting = load_matting()
        model_load_s = time.perf_counter() - t0
    except Exception as exc:
        print(f"模型加载失败: {exc}", file=sys.stderr)
        return 1
    print(f"模型加载完成: {model_load_s:.2f}s")

    completed = 0
    for index, photo in enumerate(photos, start=1):
        if not photo.is_file():
            print(f"[跳过] 照片不存在: {photo}", file=sys.stderr)
            continue
        image = read_image(photo)
        if image.size == 0:
            print(f"[跳过] 无法读取照片: {photo}", file=sys.stderr)
            continue
        character_id = f"{prefix}{index:02d}"
        name = f"照片角色 {index:02d}"
        analysis_dir = args.analysis_root / photo.stem
        analysis_dir.mkdir(parents=True, exist_ok=True)

        print(f"\n=== {photo.name} -> {character_id} ({name}) ===")
        t0 = time.perf_counter()
        try:
            analysis = extract_profile(
                image,
                detector,
                parser,
                matting,
                photo,
                face_margin=args.face_margin,
            )
        except Exception as exc:
            print(f"特征提取失败: {exc}", file=sys.stderr)
            continue
        extract_time = time.perf_counter() - t0
        profile = dict(analysis.profile)
        profile["analysis_timing_s"] = {
            "model_load": round(model_load_s, 3),
            "extract": round(extract_time, 3),
        }

        parse_vis = PARSE_PALETTE[analysis.parse_mask].copy()
        matte_u8 = alpha_to_u8(analysis.alpha)
        matte_preview = make_checkerboard_preview(image, analysis.alpha)
        outputs = {
            "original": analysis_dir / "original.jpg",
            "face_crop": analysis_dir / "face_crop.jpg",
            "parse_mask": analysis_dir / "parse_mask.png",
            "matte": analysis_dir / "matte.png",
            "matte_preview": analysis_dir / "matte_preview.png",
            "profile": analysis_dir / "profile.json",
            "report": analysis_dir / "report.json",
        }
        save_image(outputs["original"], image)
        save_image(outputs["face_crop"], analysis.face_crop)
        save_image(outputs["parse_mask"], parse_vis)
        save_image(outputs["matte"], matte_u8)
        save_image(outputs["matte_preview"], matte_preview)
        outputs["profile"].write_text(
            json.dumps(profile, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        chibi_result = None
        validation = None
        if args.mode in ("preview", "character"):
            if args.mode == "preview":
                chibi_dir = analysis_dir / "chibi_preview"
            else:
                chibi_dir = args.character_root / character_id
            try:
                chibi_result = render_chibi(
                    profile,
                    chibi_dir,
                    character_id,
                    name,
                )
            except Exception as exc:
                print(f"卡通小人生成失败: {exc}", file=sys.stderr)
                continue
            if args.mode == "character":
                ok, validation_output = validate_character(chibi_dir)
                validation = {"ok": ok, "output": validation_output}
            contact_path = analysis_dir / "contact_sheet.png"
            make_contact_sheet(
                image,
                matte_preview,
                Path(chibi_result["preview"]),
                profile,
                contact_path,
            )
            outputs["contact_sheet"] = contact_path
            outputs["chibi"] = Path(chibi_result["character_dir"])
        report = {
            "mode": args.mode,
            "photo": str(photo),
            "profile": profile,
            "chibi": chibi_result,
            "validation": validation,
            "outputs": {key: str(value) for key, value in outputs.items()},
        }
        outputs["report"].write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        colors = profile["colors_hex"]
        print(
            "特征: "
            f"skin={colors['skin']} hair={colors['hair']} "
            f"eye={colors['eye']} mouth={colors['mouth']} "
            f"clothes={colors['clothing_primary']}/{colors['clothing_secondary']}"
        )
        print(
            f"发长={profile['hair_length']} "
            f"服装轮廓={profile['outfit_style']} "
            f"眼镜={profile.get('glasses_detected', False)}"
        )
        print(f"特征提取: {extract_time:.2f}s")
        if chibi_result is not None:
            print(f"卡通小人: {chibi_result['character_dir']}")
            print(f"预览: {chibi_result['preview']}")
        if validation is not None:
            print(f"契约校验: {'PASS' if validation['ok'] else 'FAIL'}")
            if not validation["ok"]:
                print(validation["output"].strip())
        print(f"对比预览: {outputs.get('contact_sheet', '未生成')}")
        completed += 1

    print(f"\n完成 {completed}/{len(photos)} 张照片")
    return 0 if completed == len(photos) else 1


if __name__ == "__main__":
    raise SystemExit(main())