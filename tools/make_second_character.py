# -*- coding: utf-8 -*-
"""生成 1-E 第二角色：长发二次元风格的 demo2（9 张 512x512 全画布透明 PNG）。

用法:
    python tools/make_second_character.py
    python tools/make_second_character.py --force

产物:
    assets/characters/demo2/parts/*.png
    assets/characters/demo2/character.json
    assets/characters/demo2/preview.png
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "rig_contract.json"
OUT_DIR = ROOT / "assets" / "characters" / "demo2"
PARTS_DIR = OUT_DIR / "parts"

SCALE = 4
W, H = 512, 512

HAIR = (178, 170, 216, 255)
HAIR_LIGHT = (224, 219, 244, 255)
HAIR_DARK = (118, 110, 158, 255)
SKIN = (255, 229, 216, 255)
SKIN_SHADOW = (244, 196, 182, 255)
BLUSH = (255, 185, 190, 255)
DRESS = (126, 159, 215, 255)
DRESS_DARK = (91, 116, 173, 255)
DRESS_LIGHT = (181, 205, 238, 255)
WHITE = (250, 249, 255, 255)
RIBBON = (232, 142, 166, 255)
RIBBON_DARK = (192, 101, 128, 255)
EYE_WHITE = (255, 255, 255, 255)
IRIS = (91, 90, 158, 255)
PUPIL = (46, 43, 85, 255)
LASH = (67, 58, 88, 255)
MOUTH = (196, 102, 119, 255)
SHOE = (76, 73, 105, 255)


def canvas() -> Image.Image:
    return Image.new("RGBA", (W * SCALE, H * SCALE), (0, 0, 0, 0))


def scaled(values):
    return tuple(int(round(value * SCALE)) for value in values)


def scaled_points(points):
    return [scaled(point) for point in points]


def ellipse(draw, bbox, fill, outline=None, width=0):
    draw.ellipse(
        scaled(bbox),
        fill=fill,
        outline=outline,
        width=int(width * SCALE),
    )


def rounded(draw, bbox, radius, fill, outline=None, width=0):
    draw.rounded_rectangle(
        scaled(bbox),
        radius=int(radius * SCALE),
        fill=fill,
        outline=outline,
        width=int(width * SCALE),
    )


def polygon(draw, points, fill, outline=None):
    draw.polygon(scaled_points(points), fill=fill, outline=outline)


def thick_line(draw, start, end, width, fill):
    draw.line([scaled(start), scaled(end)], fill=fill, width=int(width * SCALE))
    radius = width / 2
    for x, y in (start, end):
        ellipse(draw, (x - radius, y - radius, x + radius, y + radius), fill)


def arc(draw, bbox, start, end, fill, width):
    draw.arc(
        scaled(bbox),
        start=start,
        end=end,
        fill=fill,
        width=int(width * SCALE),
    )


def finish(image: Image.Image) -> Image.Image:
    return image.resize((W, H), Image.LANCZOS)


def make_head() -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)

    # 后发与两侧长发
    ellipse(draw, (145, 35, 367, 330), HAIR)
    ellipse(draw, (135, 120, 190, 390), HAIR)
    ellipse(draw, (322, 120, 377, 390), HAIR)

    # 脸与耳朵
    ellipse(draw, (185, 85, 327, 300), SKIN)
    ellipse(draw, (176, 200, 194, 230), SKIN)
    ellipse(draw, (318, 200, 336, 230), SKIN)

    # 刘海
    ellipse(draw, (170, 55, 342, 188), HAIR)
    polygon(
        draw,
        [(160, 120), (205, 62), (238, 182), (212, 196), (178, 168)],
        HAIR,
    )
    polygon(
        draw,
        [(352, 120), (307, 62), (274, 182), (300, 196), (334, 168)],
        HAIR,
    )
    polygon(draw, [(238, 62), (274, 62), (256, 150)], HAIR_DARK)

    # 发丝高光
    ellipse(draw, (190, 76, 232, 96), HAIR_LIGHT)
    ellipse(draw, (284, 78, 326, 98), HAIR_LIGHT)
    arc(draw, (150, 150, 190, 370), 250, 290, HAIR_LIGHT, 3)
    arc(draw, (322, 150, 362, 370), 250, 290, HAIR_LIGHT, 3)

    # 发饰：右侧蝴蝶结
    ellipse(draw, (306, 104, 334, 132), RIBBON)
    ellipse(draw, (334, 104, 362, 132), RIBBON)
    ellipse(draw, (324, 108, 344, 128), RIBBON_DARK)

    # 腮红与鼻子（眼睛/嘴是独立部件）
    ellipse(draw, (196, 242, 222, 257), BLUSH)
    ellipse(draw, (290, 242, 316, 257), BLUSH)
    ellipse(draw, (252, 248, 260, 255), SKIN_SHADOW)
    return finish(image)


def make_body() -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)

    # 连衣裙上身
    polygon(draw, [(218, 292), (294, 292), (307, 405), (205, 405)], DRESS)
    ellipse(draw, (202, 292, 238, 338), DRESS)
    ellipse(draw, (274, 292, 310, 338), DRESS)

    # 白色领口与粉色蝴蝶结
    polygon(draw, [(238, 294), (274, 294), (256, 322)], WHITE)
    polygon(draw, [(242, 314), (270, 314), (256, 332)], RIBBON)
    ellipse(draw, (250, 315, 262, 327), RIBBON_DARK)

    # 裙摆
    polygon(
        draw,
        [
            (205, 392),
            (307, 392),
            (334, 456),
            (324, 480),
            (302, 470),
            (282, 490),
            (256, 482),
            (230, 490),
            (210, 470),
            (188, 480),
            (178, 456),
        ],
        DRESS_DARK,
    )
    polygon(
        draw,
        [
            (198, 450),
            (314, 450),
            (324, 480),
            (302, 470),
            (282, 490),
            (256, 482),
            (230, 490),
            (210, 470),
            (188, 480),
        ],
        DRESS_LIGHT,
    )
    # 腰带
    rounded(draw, (208, 390, 304, 406), 8, DRESS_DARK)
    rounded(draw, (246, 392, 266, 404), 5, RIBBON)
    return finish(image)
def make_arm(side: str) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    if side == "l":
        shoulder, hand = (212.0, 320.0), (178.0, 450.0)
    else:
        shoulder, hand = (300.0, 320.0), (334.0, 450.0)
    middle = ((shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2)

    thick_line(draw, shoulder, middle, 28, DRESS)
    ellipse(
        draw,
        (middle[0] - 12, middle[1] - 12, middle[0] + 12, middle[1] + 12),
        WHITE,
    )
    thick_line(draw, middle, hand, 20, SKIN)
    ellipse(draw, (hand[0] - 12, hand[1] - 12, hand[0] + 12, hand[1] + 12), SKIN)
    return finish(image)


def make_leg(side: str) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    if side == "l":
        hip, ankle = (233.0, 465.0), (224.0, 500.0)
        shoe_bbox = (208, 492, 240, 512)
    else:
        hip, ankle = (279.0, 465.0), (288.0, 500.0)
        shoe_bbox = (272, 492, 304, 512)
    thick_line(draw, hip, ankle, 26, WHITE)
    ellipse(draw, shoe_bbox, SHOE)
    return finish(image)


def make_eye(side: str) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    cx = 223 if side == "l" else 289
    cy = 210

    ellipse(draw, (cx - 20, cy - 25, cx + 20, cy + 22), EYE_WHITE)
    ellipse(draw, (cx - 14, cy - 18, cx + 14, cy + 18), IRIS)
    ellipse(draw, (cx - 7, cy - 11, cx + 7, cy + 12), PUPIL)
    ellipse(draw, (cx - 5, cy - 12, cx + 3, cy - 4), EYE_WHITE)
    ellipse(draw, (cx + 5, cy + 6, cx + 9, cy + 10), EYE_WHITE)
    arc(draw, (cx - 22, cy - 28, cx + 22, cy + 18), 200, 340, LASH, 4)
    if side == "l":
        thick_line(draw, (cx - 18, cy - 16), (cx - 25, cy - 22), 3, LASH)
    else:
        thick_line(draw, (cx + 18, cy - 16), (cx + 25, cy - 22), 3, LASH)
    return finish(image)


def make_mouth() -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    arc(draw, (243, 250, 269, 270), 20, 160, MOUTH, 3)
    arc(draw, (247, 254, 265, 268), 20, 160, (255, 170, 180, 255), 1)
    return finish(image)
def save(image: Image.Image, name: str) -> None:
    image.save(PARTS_DIR / name, "PNG")


def build_character_json(contract: dict) -> dict:
    return {
        "id": "demo2",
        "contract_version": contract["contract_version"],
        "rig": {
            "parts": {
                "head": {"file": "parts/head.png", "pivot": [256, 300]},
                "body": {"file": "parts/body.png", "pivot": [256, 320]},
                "arm_l": {"file": "parts/arm_l.png", "pivot": [212, 320]},
                "arm_r": {"file": "parts/arm_r.png", "pivot": [300, 320]},
                "leg_l": {"file": "parts/leg_l.png", "pivot": [233, 465]},
                "leg_r": {"file": "parts/leg_r.png", "pivot": [279, 465]},
                "eye_l": {"file": "parts/eye_l.png", "pivot": [223, 210]},
                "eye_r": {"file": "parts/eye_r.png", "pivot": [289, 210]},
                "mouth": {"file": "parts/mouth.png", "pivot": [256, 260]},
            }
        },
        "persona": {
            "name": "小绘",
            "setting": (
                "你是小绘，一个安静又好奇的二次元桌宠。"
                "你喜欢画画、观察窗边的光，说话温柔简短。"
            ),
        },
        "knowledge": [
            {"key": "身份", "value": "Window Pet Generator 的第二测试角色，长发二次元风格。"},
            {"key": "喜欢", "value": "画画、淡蓝色、窗边的光"},
            {"key": "讨厌", "value": "太吵的环境"},
        ],
        "idle_lines": [
            {"text": "今天的光线很适合画画呢。", "action": "wave", "weight": 2},
            {"text": "要一起看会儿窗外吗？", "action": "nod", "weight": 2},
            {"text": "我刚刚是不是走神了……", "action": "blink", "weight": 1},
            {"text": "袖子好像有点长了。", "action": "shake_head", "weight": 1},
            {"text": "哈——有点困。", "action": "yawn", "weight": 1},
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

    parser = argparse.ArgumentParser(description="生成 1-E 第二角色 demo2")
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

    print(f"已生成第二角色: {OUT_DIR}")
    print(f"  预览: {OUT_DIR / 'preview.png'}")
    print("下一步:")
    print(
        "  python tools/validate.py character "
        f"{OUT_DIR} --actions-dir assets/actions"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())