# -*- coding: utf-8 -*-
"""生成 1-A 用的占位角色（9 张 512x512 全画布透明 PNG）。

用法:
    python tools/make_placeholder_character.py
    python tools/make_placeholder_character.py --force

产物:
    assets/characters/demo/parts/*.png
    assets/characters/demo/character.json
    assets/characters/demo/preview.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "rig_contract.json"
OUT_DIR = ROOT / "assets" / "characters" / "demo"
PARTS_DIR = OUT_DIR / "parts"

SCALE = 4
W, H = 512, 512

SKIN = (255, 219, 190, 255)
SKIN_SHADOW = (245, 190, 160, 255)
HAIR = (74, 54, 48, 255)
HAIR_LIGHT = (102, 76, 66, 255)
SHIRT = (126, 200, 178, 255)
SHIRT_DARK = (94, 164, 146, 255)
PANTS = (90, 108, 150, 255)
SHOES = (70, 74, 92, 255)
EYE_WHITE = (255, 255, 255, 255)
EYE_DARK = (55, 48, 48, 255)
MOUTH = (150, 82, 76, 255)
BLUSH = (255, 185, 175, 255)


def canvas() -> Image.Image:
    return Image.new("RGBA", (W * SCALE, H * SCALE), (0, 0, 0, 0))


def scaled(values):
    return tuple(int(round(value * SCALE)) for value in values)


def scaled_points(points):
    return [scaled(point) for point in points]


def ellipse(draw, bbox, fill):
    draw.ellipse(scaled(bbox), fill=fill)


def rounded(draw, bbox, radius, fill):
    draw.rounded_rectangle(scaled(bbox), radius=int(radius * SCALE), fill=fill)


def thick_line(draw, start, end, width, fill):
    draw.line([scaled(start), scaled(end)], fill=fill, width=int(width * SCALE))
    radius = width / 2
    for x, y in (start, end):
        ellipse(draw, (x - radius, y - radius, x + radius, y + radius), fill)


def finish(image: Image.Image) -> Image.Image:
    return image.resize((W, H), Image.LANCZOS)


def make_head() -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    ellipse(draw, (148, 62, 364, 296), HAIR)
    ellipse(draw, (164, 96, 348, 286), SKIN)
    ellipse(draw, (150, 178, 184, 224), SKIN)
    ellipse(draw, (328, 178, 362, 224), SKIN)
    ellipse(draw, (158, 72, 354, 166), HAIR)
    ellipse(draw, (150, 120, 250, 196), HAIR)
    ellipse(draw, (262, 120, 362, 196), HAIR)
    ellipse(draw, (250, 216, 262, 224), SKIN_SHADOW)
    ellipse(draw, (186, 220, 218, 238), BLUSH)
    ellipse(draw, (294, 220, 326, 238), BLUSH)
    ellipse(draw, (190, 88, 232, 108), HAIR_LIGHT)
    return finish(image)


def make_body() -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    rounded(draw, (202, 268, 310, 424), 42, SHIRT)
    rounded(draw, (206, 392, 306, 430), 18, SHIRT_DARK)
    draw.polygon(scaled_points([(236, 272), (276, 272), (256, 300)]), fill=SKIN)
    rounded(draw, (246, 300, 266, 320), 10, SHIRT_DARK)
    return finish(image)


def make_arm(side: str) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    if side == "l":
        shoulder, hand = (204, 302), (174, 396)
    else:
        shoulder, hand = (308, 302), (338, 396)
    middle = ((shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2)
    thick_line(draw, shoulder, middle, 34, SHIRT)
    thick_line(draw, middle, hand, 24, SKIN)
    ellipse(draw, (hand[0] - 14, hand[1] - 14, hand[0] + 14, hand[1] + 14), SKIN)
    return finish(image)


def make_leg(side: str) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    if side == "l":
        hip, foot = (235, 410), (224, 496)
    else:
        hip, foot = (277, 410), (288, 496)
    thick_line(draw, hip, foot, 34, PANTS)
    ellipse(draw, (foot[0] - 22, foot[1] - 6, foot[0] + 22, foot[1] + 18), SHOES)
    return finish(image)


def make_eye(side: str) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    center_x = 230 if side == "l" else 282
    center_y = 200
    ellipse(
        draw,
        (center_x - 17, center_y - 22, center_x + 17, center_y + 22),
        EYE_WHITE,
    )
    ellipse(
        draw,
        (center_x - 10, center_y - 14, center_x + 10, center_y + 14),
        EYE_DARK,
    )
    ellipse(
        draw,
        (center_x + 1, center_y - 10, center_x + 7, center_y - 4),
        EYE_WHITE,
    )
    return finish(image)


def make_mouth() -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    draw.arc(
        scaled((242, 230, 270, 252)),
        start=20,
        end=160,
        fill=MOUTH,
        width=int(4 * SCALE),
    )
    return finish(image)


def save(image: Image.Image, name: str) -> None:
    image.save(PARTS_DIR / name, "PNG")
def build_character_json(contract: dict) -> dict:
    return {
        "id": "demo",
        "contract_version": contract["contract_version"],
        "rig": {
            "parts": {
                "head": {"file": "parts/head.png", "pivot": [256, 276]},
                "body": {"file": "parts/body.png", "pivot": [256, 310]},
                "arm_l": {"file": "parts/arm_l.png", "pivot": [200, 300]},
                "arm_r": {"file": "parts/arm_r.png", "pivot": [312, 300]},
                "leg_l": {"file": "parts/leg_l.png", "pivot": [230, 420]},
                "leg_r": {"file": "parts/leg_r.png", "pivot": [282, 420]},
                "eye_l": {"file": "parts/eye_l.png", "pivot": [230, 200]},
                "eye_r": {"file": "parts/eye_r.png", "pivot": [282, 200]},
                "mouth": {"file": "parts/mouth.png", "pivot": [256, 240]},
            }
        },
        "persona": {
            "name": "小占位",
            "setting": (
                "你是小占位，一个用于测试契约与动作系统的桌宠角色。"
                "你性格活泼、说话简短，喜欢陪人写代码。"
            ),
        },
        "knowledge": [
            {"key": "身份", "value": "Window Pet Generator 的占位测试角色"},
            {"key": "喜欢", "value": "被拖动到屏幕各处"},
            {"key": "口头禅", "value": "今天也要一起写代码吗？"},
        ],
        "idle_lines": [
            {"text": "今天也要一起写代码吗？", "action": "wave", "weight": 2},
            {"text": "呼……发会儿呆。", "action": "nod", "weight": 2},
            {"text": "我刚刚是不是眨眼了？", "action": "blink", "weight": 1},
            {"text": "伸个懒腰～", "action": "yawn", "weight": 1},
            {"text": "别一直盯着屏幕啦。", "action": "shake_head", "weight": 1},
        ],
    }


def composite_preview() -> None:
    layers = [
        "leg_l",
        "leg_r",
        "arm_l",
        "arm_r",
        "body",
        "head",
        "eye_l",
        "eye_r",
        "mouth",
    ]
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for name in layers:
        with Image.open(PARTS_DIR / f"{name}.png") as part:
            base.alpha_composite(part.convert("RGBA"))

    background = Image.new("RGBA", (W, H), (34, 38, 46, 255))
    draw = ImageDraw.Draw(background)
    cell = 32
    for y in range(0, H, cell):
        for x in range(0, W, cell):
            if (x // cell + y // cell) % 2 == 0:
                draw.rectangle(
                    (x, y, x + cell - 1, y + cell - 1),
                    fill=(44, 49, 59, 255),
                )
    background.alpha_composite(base)
    background.convert("RGB").save(OUT_DIR / "preview.png", "PNG")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="生成 1-A 占位角色")
    parser.add_argument("--force", action="store_true", help="覆盖已存在的文件")
    args = parser.parse_args()

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    width = contract["canvas"]["width"]
    height = contract["canvas"]["height"]
    if width != W or height != H:
        raise SystemExit(
            f"本生成器只支持 {W}x{H} 画布，当前契约是 {width}x{height}"
        )

    if OUT_DIR.exists() and not args.force:
        existing = list(OUT_DIR.rglob("*.png")) + list(OUT_DIR.rglob("*.json"))
        if existing:
            print(f"输出已存在: {OUT_DIR}")
            print("如需重新生成，请加 --force")
            return 0

    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    save(make_head(), "head.png")
    save(make_body(), "body.png")
    save(make_arm("l"), "arm_l.png")
    save(make_arm("r"), "arm_r.png")
    save(make_leg("l"), "leg_l.png")
    save(make_leg("r"), "leg_r.png")
    save(make_eye("l"), "eye_l.png")
    save(make_eye("r"), "eye_r.png")
    save(make_mouth(), "mouth.png")

    character = build_character_json(contract)
    (OUT_DIR / "character.json").write_text(
        json.dumps(character, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    composite_preview()

    print(f"已生成占位角色: {OUT_DIR}")
    print(f"  预览: {OUT_DIR / 'preview.png'}")
    print("下一步:")
    print(
        "  python tools/validate.py character "
        f"{OUT_DIR} --actions-dir assets/actions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())