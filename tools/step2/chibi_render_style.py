# -*- coding: utf-8 -*-
"""Render a demo/demo2-style chibi character from a PhotoProfile."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = ROOT / "contracts" / "rig_contract.json"
SCALE = 4
W = H = 512
WHITE = (250, 249, 255, 255)


def _rgb(value, fallback):
    try:
        r, g, b = [int(value[0]), int(value[1]), int(value[2])]
        return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))
    except (TypeError, ValueError, IndexError):
        return fallback


def _shade(rgb, factor):
    return tuple(max(0, min(255, int(round(channel * factor)))) for channel in rgb)


def _mix(a, b, t):
    t = max(0.0, min(1.0, float(t)))
    return tuple(int(round(a[i] * (1.0 - t) + b[i] * t)) for i in range(3))


def _distance(a, b):
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def _ensure_contrast(color, reference, min_distance=40.0):
    if _distance(color, reference) >= min_distance:
        return color
    brightness = sum(color) / 3.0
    if brightness > 150:
        return _shade(color, 0.72)
    return _mix(color, WHITE[:3], 0.22)


def _ensure_hair_contrast(hair, skin):
    if _distance(hair, skin) < 50.0:
        return _shade(hair, 0.65)
    return hair


def build_palette(profile: dict) -> dict:
    skin = _rgb(profile.get("skin_color"), (255, 224, 210))
    hair = _rgb(profile.get("hair_color"), (72, 56, 52))
    eye = _rgb(profile.get("eye_color"), (72, 60, 86))
    mouth = _rgb(profile.get("mouth_color"), (190, 105, 118))
    primary = _rgb(profile.get("clothing_primary"), (116, 150, 205))
    secondary = _rgb(profile.get("clothing_secondary"), (75, 96, 140))

    skin = _mix(skin, (255, 255, 255), 0.08) if sum(skin) / 3 < 70 else skin
    hair = _ensure_hair_contrast(hair, skin)
    eye = _ensure_contrast(eye, skin, 55.0)
    mouth = _ensure_contrast(mouth, skin, 35.0)
    primary = _ensure_contrast(primary, skin, 35.0)
    secondary = _ensure_contrast(secondary, primary, 28.0)
    if _distance(secondary, primary) < 28.0:
        secondary = _shade(secondary, 0.68)

    return {
        "skin": skin + (255,),
        "skin_shadow": _mix(skin, (175, 110, 95), 0.22) + (255,),
        "blush": _mix(skin, (255, 120, 130), 0.38) + (255,),
        "hair": hair + (255,),
        "hair_light": _mix(hair, (255, 255, 255), 0.32) + (255,),
        "hair_dark": _shade(hair, 0.62) + (255,),
        "eye": eye + (255,),
        "eye_light": _mix(eye, (255, 255, 255), 0.35) + (255,),
        "pupil": _shade(eye, 0.35) + (255,),
        "lash": _shade(hair, 0.50) + (255,),
        "mouth": mouth + (255,),
        "mouth_light": _mix(mouth, (255, 255, 255), 0.35) + (255,),
        "primary": primary + (255,),
        "primary_light": _mix(primary, (255, 255, 255), 0.28) + (255,),
        "primary_dark": _shade(primary, 0.72) + (255,),
        "secondary": secondary + (255,),
        "secondary_light": _mix(secondary, (255, 255, 255), 0.22) + (255,),
        "secondary_dark": _shade(secondary, 0.60) + (255,),
        "white": WHITE,
        "hat": _mix(primary, (255, 226, 140), 0.35) + (255,),
        "hat_dark": _shade(_mix(primary, (255, 226, 140), 0.35), 0.72) + (255,),
        "hat_band": _shade(secondary, 0.85) + (255,),
        "shoe": ((250, 249, 255) if str(profile.get("outfit_style", "tunic")) == "dress" else _shade(secondary, 0.45)) + (255,),
    }


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


def make_head(profile: dict, palette: dict) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    hair_values = {
        "short": (300, 300, 280),
        "medium": (360, 360, 340),
        "long": (440, 440, 380),
    }
    side_bottom, lock_bottom, back_bottom = hair_values.get(
        str(profile.get("hair_length", "medium")), hair_values["medium"]
    )
    if str(profile.get("hair_style", "")) == "twin_braids":
        side_bottom, lock_bottom, back_bottom = 290, 290, 300

    ellipse(draw, (145, 35, 367, back_bottom), palette["hair"])
    ellipse(draw, (135, 120, 190, side_bottom), palette["hair"])
    ellipse(draw, (322, 120, 377, side_bottom), palette["hair"])
    ellipse(draw, (185, 85, 327, 300), palette["skin"])
    ellipse(draw, (176, 200, 194, 230), palette["skin"])
    ellipse(draw, (318, 200, 336, 230), palette["skin"])

    ellipse(draw, (170, 55, 342, 188), palette["hair"])
    polygon(
        draw,
        [(160, 120), (205, 62), (238, 182), (212, 196), (178, 168)],
        palette["hair"],
    )
    polygon(
        draw,
        [(352, 120), (307, 62), (274, 182), (300, 196), (334, 168)],
        palette["hair"],
    )
    polygon(draw, [(238, 62), (274, 62), (256, 150)], palette["hair_dark"])
    ellipse(draw, (190, 76, 232, 96), palette["hair_light"])
    ellipse(draw, (284, 78, 326, 98), palette["hair_light"])
    arc(draw, (150, 150, 190, side_bottom - 10), 250, 290, palette["hair_light"], 3)
    arc(draw, (322, 150, 362, side_bottom - 10), 250, 290, palette["hair_light"], 3)

    if str(profile.get("hair_style", "")) == "twin_braids":
        braid_sets = [
            ([162, 154, 148, 143, 138], [245, 290, 335, 380, 420]),
            ([350, 358, 364, 369, 374], [245, 290, 335, 380, 420]),
        ]
        for xs, ys in braid_sets:
            for index, (bx, by) in enumerate(zip(xs, ys)):
                radius = 20 - index * 2
                ellipse(
                    draw,
                    (bx - radius, by - radius, bx + radius, by + radius),
                    palette["hair"],
                )
                inner = radius * 0.42
                ellipse(
                    draw,
                    (bx - inner, by - inner, bx + inner, by + inner),
                    palette["hair_light"] if index % 2 == 0 else palette["hair_dark"],
                )
                if index > 0:
                    thick_line(
                        draw,
                        (xs[index - 1], ys[index - 1] + radius),
                        (bx, by - radius),
                        3,
                        palette["hair_dark"],
                    )
            ellipse(
                draw,
                (xs[-1] - 10, ys[-1] + 8, xs[-1] + 10, ys[-1] + 24),
                palette["secondary"],
            )

    # 小发饰：使用服装辅色
    ellipse(draw, (306, 104, 334, 132), palette["secondary"])
    ellipse(draw, (334, 104, 362, 132), palette["secondary"])
    ellipse(draw, (324, 108, 344, 128), palette["secondary_dark"])

    ellipse(draw, (196, 242, 222, 257), palette["blush"])
    ellipse(draw, (290, 242, 316, 257), palette["blush"])
    ellipse(draw, (252, 248, 260, 255), palette["skin_shadow"])

    if profile.get("glasses_detected"):
        line_color = palette["lash"]
        ellipse(draw, (198, 184, 246, 236), None, line_color, 2)
        ellipse(draw, (266, 184, 314, 236), None, line_color, 2)
        thick_line(draw, (246, 208), (266, 208), 2, line_color)

    if profile.get("hat_detected"):
        # 宽边草帽
        ellipse(draw, (126, 34, 386, 98), palette["hat"])
        rounded(draw, (190, 6, 322, 78), 30, palette["hat"])
        rounded(draw, (190, 54, 322, 76), 9, palette["hat_band"])
        arc(draw, (138, 42, 374, 100), 200, 340, palette["hat_dark"], 3)
    return finish(image)
def make_body(profile: dict, palette: dict) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    outfit = str(profile.get("outfit_style", "tunic"))

    if outfit == "dress":
        polygon(draw, [(218, 292), (294, 292), (307, 405), (205, 405)], palette["primary"])
        ellipse(draw, (202, 292, 238, 338), palette["primary"])
        ellipse(draw, (274, 292, 310, 338), palette["primary"])
        polygon(draw, [(238, 294), (274, 294), (256, 322)], palette["white"])
        polygon(draw, [(242, 314), (270, 314), (256, 332)], palette["secondary"])
        ellipse(draw, (250, 315, 262, 327), palette["secondary_dark"])
        polygon(
            draw,
            [
                (205, 392), (307, 392), (334, 456), (324, 480), (302, 470),
                (282, 490), (256, 482), (230, 490), (210, 470), (188, 480),
                (178, 456),
            ],
            palette["primary_dark"],
        )
        polygon(
            draw,
            [
                (198, 450), (314, 450), (324, 480), (302, 470), (282, 490),
                (256, 482), (230, 490), (210, 470), (188, 480),
            ],
            palette["primary_light"],
        )
        rounded(draw, (208, 390, 304, 406), 8, palette["secondary_dark"])
        rounded(draw, (246, 392, 266, 404), 5, palette["secondary"])
    else:
        polygon(draw, [(216, 292), (296, 292), (310, 430), (202, 430)], palette["primary"])
        ellipse(draw, (202, 292, 238, 338), palette["primary"])
        ellipse(draw, (274, 292, 310, 338), palette["primary"])
        polygon(draw, [(238, 294), (274, 294), (256, 322)], palette["white"])
        polygon(draw, [(242, 314), (270, 314), (256, 332)], palette["secondary"])
        ellipse(draw, (250, 315, 262, 327), palette["secondary_dark"])
        rounded(draw, (204, 400, 308, 424), 10, palette["secondary_dark"])
        rounded(draw, (246, 402, 266, 420), 6, palette["secondary"])
        polygon(draw, [(210, 424), (302, 424), (306, 438), (206, 438)], palette["primary_dark"])
    if outfit == "dress":
        # 裙摆五瓣小花装饰
        for fx, fy in ((204, 454), (232, 474), (260, 486), (290, 474), (316, 450)):
            for k in range(5):
                ang = math.radians(k * 72 - 90)
                px = fx + 8 * math.cos(ang)
                py = fy + 8 * math.sin(ang)
                ellipse(draw, (px - 5, py - 5, px + 5, py + 5), palette["white"])
            ellipse(draw, (fx - 3, fy - 3, fx + 3, fy + 3), palette["secondary"])
    return finish(image)


def make_arm(side: str, palette: dict, profile: dict | None = None) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    is_dress = profile is not None and str(profile.get("outfit_style", "tunic")) == "dress"
    if side == "l":
        shoulder, hand = (212.0, 320.0), (178.0, 450.0)
    else:
        shoulder, hand = (300.0, 320.0), (334.0, 450.0)
    middle = ((shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2)
    thick_line(draw, shoulder, middle, 28, palette["skin"] if is_dress else palette["primary"])
    if not is_dress:
        ellipse(
            draw,
            (middle[0] - 12, middle[1] - 12, middle[0] + 12, middle[1] + 12),
            palette["white"],
        )
    thick_line(draw, middle, hand, 20, palette["skin"])
    ellipse(draw, (hand[0] - 12, hand[1] - 12, hand[0] + 12, hand[1] + 12), palette["skin"])
    return finish(image)


def make_leg(side: str, profile: dict, palette: dict) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    if side == "l":
        hip, ankle = (233.0, 465.0), (224.0, 500.0)
        shoe_bbox = (208, 492, 240, 512)
    else:
        hip, ankle = (279.0, 465.0), (288.0, 500.0)
        shoe_bbox = (272, 492, 304, 512)
    if str(profile.get("outfit_style", "tunic")) == "tunic":
        leg_color = palette["secondary"]
    elif str(profile.get("leg_style", "")) == "socks":
        leg_color = palette["white"]
    else:
        leg_color = palette["skin"]
    thick_line(draw, hip, ankle, 26, leg_color)
    ellipse(draw, shoe_bbox, palette["shoe"])
    return finish(image)


def make_eye(side: str, palette: dict) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    cx = 223 if side == "l" else 289
    cy = 210
    ellipse(draw, (cx - 20, cy - 25, cx + 20, cy + 22), palette["white"])
    ellipse(draw, (cx - 14, cy - 18, cx + 14, cy + 18), palette["eye"])
    ellipse(draw, (cx - 7, cy - 11, cx + 7, cy + 12), palette["pupil"])
    ellipse(draw, (cx - 5, cy - 12, cx + 3, cy - 4), palette["white"])
    ellipse(draw, (cx + 5, cy + 6, cx + 9, cy + 10), palette["eye_light"])
    arc(draw, (cx - 22, cy - 28, cx + 22, cy + 18), 200, 340, palette["lash"], 4)
    if side == "l":
        thick_line(draw, (cx - 18, cy - 16), (cx - 25, cy - 22), 3, palette["lash"])
    else:
        thick_line(draw, (cx + 18, cy - 16), (cx + 25, cy - 22), 3, palette["lash"])
    return finish(image)


def make_mouth(palette: dict) -> Image.Image:
    image = canvas()
    draw = ImageDraw.Draw(image)
    arc(draw, (243, 250, 269, 270), 20, 160, palette["mouth"], 3)
    arc(draw, (247, 254, 265, 268), 20, 160, palette["mouth_light"], 1)
    return finish(image)
def save(image: Image.Image, parts_dir: Path, name: str) -> None:
    image.save(parts_dir / name, "PNG")


def build_character_json(
    contract: dict,
    profile: dict,
    character_id: str,
    name: str,
) -> dict:
    return {
        "id": character_id,
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
            "name": name,
            "setting": (
                "你是由本地照片生成的卡通桌宠角色，"
                "性格活泼、说话简短，喜欢陪人工作。"
            ),
        },
        "knowledge": [
            {"key": "来源", "value": f"由本地照片生成：{profile.get('photo', '')}"},
            {"key": "发色", "value": profile.get("colors_hex", {}).get("hair", "")},
            {"key": "服装", "value": profile.get("colors_hex", {}).get("clothing_primary", "")},
            {"key": "发型", "value": str(profile.get("hair_length", "medium"))},
        ],
        "idle_lines": [
            {"text": "今天也要一起写代码吗？", "action": "wave", "weight": 2},
            {"text": "呼……发会儿呆。", "action": "nod", "weight": 2},
            {"text": "我刚刚是不是眨眼了？", "action": "blink", "weight": 1},
            {"text": "伸个懒腰～", "action": "yawn", "weight": 1},
            {"text": "别一直盯着屏幕啦。", "action": "shake_head", "weight": 1},
        ],
    }


def composite_preview(parts_dir: Path, output_path: Path) -> None:
    layers = [
        "leg_l", "leg_r", "arm_l", "arm_r", "body", "head",
        "eye_l", "eye_r", "mouth",
    ]
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    for name in layers:
        with Image.open(parts_dir / f"{name}.png") as part:
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
    background.convert("RGB").save(output_path, "PNG")


def render_chibi(
    profile: dict,
    out_dir: Path,
    character_id: str,
    name: str,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    parts_dir = out_dir / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    palette = build_palette(profile)

    save(make_head(profile, palette), parts_dir, "head.png")
    save(make_body(profile, palette), parts_dir, "body.png")
    save(make_arm("l", palette, profile), parts_dir, "arm_l.png")
    save(make_arm("r", palette, profile), parts_dir, "arm_r.png")
    save(make_leg("l", profile, palette), parts_dir, "leg_l.png")
    save(make_leg("r", profile, palette), parts_dir, "leg_r.png")
    save(make_eye("l", palette), parts_dir, "eye_l.png")
    save(make_eye("r", palette), parts_dir, "eye_r.png")
    save(make_mouth(palette), parts_dir, "mouth.png")

    character = build_character_json(contract, profile, character_id, name)
    character_json = out_dir / "character.json"
    character_json.write_text(
        json.dumps(character, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    preview = out_dir / "preview.png"
    composite_preview(parts_dir, preview)
    return {
        "character_dir": str(out_dir),
        "character_json": str(character_json),
        "preview": str(preview),
        "parts_dir": str(parts_dir),
        "character": character,
        "palette": {
            key: list(value[:3])
            for key, value in palette.items()
            if isinstance(value, tuple) and len(value) >= 3
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="根据 PhotoProfile 渲染卡通小人")
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--id", default="photo_char_01")
    parser.add_argument("--name", default="照片角色 01")
    args = parser.parse_args(argv)
    profile = json.loads(args.profile.read_text(encoding="utf-8"))
    result = render_chibi(profile, args.out_dir, args.id, args.name)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())