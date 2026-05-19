#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NotebookLM-style AI cards
讀取 weekly_video_scene_ai.json
輸出 ai_cards/card_01.png ~ card_06.png
"""

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

CARD_WIDTH = 1920
CARD_HEIGHT = 1080

ORANGE = "#f97316"
TEXT = "#111827"
MUTED = "#6b7280"
LINE = "#e5e7eb"
BG = "#fcfcfb"
PANEL = "#ffffff"

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
]

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]

def find_font_path() -> Optional[str]:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None

def get_font(size: int):
    font_path = find_font_path()
    if font_path:
        return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()

def wrap_text(text: str, max_chars: int, max_lines: Optional[int] = None) -> List[str]:
    lines = []
    for paragraph in str(text or "").split("\n"):
        wrapped = textwrap.wrap(paragraph, width=max_chars) or [""]
        lines.extend(wrapped)
    if max_lines is not None:
        lines = lines[:max_lines]
    return lines

def draw_wrapped_text(draw, text, xy, font, max_chars, line_spacing=8, fill=TEXT, max_lines=None):
    x, y = xy
    for line in wrap_text(text, max_chars, max_lines):
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing
    return y

def draw_grid(draw):
    step = 46
    for x in range(0, CARD_WIDTH, step):
        draw.line((x, 0, x, CARD_HEIGHT), fill="#f1f5f9", width=1)
    for y in range(0, CARD_HEIGHT, step):
        draw.line((0, y, CARD_WIDTH, y), fill="#f1f5f9", width=1)

def draw_doodles(draw):
    draw.arc((1450, 90, 1630, 270), start=210, end=20, fill=TEXT, width=4)
    draw.line((1610, 180, 1670, 160), fill=TEXT, width=4)
    draw.line((1610, 180, 1655, 220), fill=TEXT, width=4)

    draw.ellipse((1470, 730, 1510, 770), outline=ORANGE, width=6)
    draw.ellipse((1530, 760, 1560, 790), fill=ORANGE)
    draw.line((1495, 770, 1578, 835), fill=ORANGE, width=6)

    draw.rounded_rectangle((1580, 860, 1770, 930), radius=24, outline=TEXT, width=4)
    draw.line((1598, 880, 1750, 880), fill=TEXT, width=4)
    draw.line((1598, 900, 1710, 900), fill=TEXT, width=4)

def draw_badge(draw, x, y, text):
    font = get_font(24)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 34
    h = bbox[3] - bbox[1] + 20
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill="#fff7ed", outline="#fdba74", width=2)
    draw.text((x + 17, y + 9), text, font=font, fill=ORANGE)

def create_base(meta: Dict[str, Any], scene: Dict[str, Any]):
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG)
    draw = ImageDraw.Draw(img)

    draw_grid(draw)
    draw_doodles(draw)

    title_font = get_font(64)
    label_font = get_font(24)
    question_font = get_font(52)
    week_font = get_font(23)

    draw.text((105, 80), scene.get("card_title", ""), font=title_font, fill=TEXT)
    draw.line((105, 155, 560, 155), fill=ORANGE, width=8)
    draw.text((105, 185), "WEEKLY MACRO VIDEO", font=label_font, fill=MUTED)

    draw_badge(draw, 1680, 85, scene.get("scene_id", ""))

    draw.text((105, 250), "本段問題", font=get_font(26), fill=MUTED)
    draw_wrapped_text(
        draw,
        scene.get("opening_question", ""),
        (105, 292),
        question_font,
        max_chars=28,
        line_spacing=8,
        fill=TEXT,
        max_lines=2,
    )

    draw.text((105, 1010), f"Weekly Macro Video｜{meta.get('week_label', '')}", font=week_font, fill=MUTED)
    return img, draw

def draw_answer_box(draw, scene: Dict[str, Any]):
    x1, y1, x2, y2 = 105, 430, 1040, 670
    draw.rounded_rectangle((x1, y1, x2, y2), radius=34, fill=PANEL, outline=LINE, width=2)
    draw.line((x1 + 18, y1 + 18, x1 + 18, y2 - 18), fill=ORANGE, width=10)
    draw.text((x1 + 45, y1 + 24), "核心答案", font=get_font(28), fill=MUTED)
    draw_wrapped_text(
        draw,
        scene.get("answer_summary", ""),
        (x1 + 45, y1 + 78),
        get_font(34),
        max_chars=30,
        line_spacing=10,
        fill=TEXT,
        max_lines=4,
    )

def draw_bullets_box(draw, scene: Dict[str, Any]):
    x1, y1, x2, y2 = 1090, 430, 1815, 790
    draw.rounded_rectangle((x1, y1, x2, y2), radius=34, fill=PANEL, outline=LINE, width=2)
    draw.text((x1 + 34, y1 + 24), "本週重點", font=get_font(28), fill=MUTED)

    bullets = scene.get("card_bullets", [])
    if not isinstance(bullets, list):
        bullets = []

    y = y1 + 82
    for idx, bullet in enumerate(bullets[:5], start=1):
        draw.ellipse((x1 + 34, y + 8, x1 + 52, y + 26), fill=ORANGE)
        y = draw_wrapped_text(
            draw,
            str(bullet),
            (x1 + 70, y),
            get_font(29),
            max_chars=28,
            line_spacing=6,
            fill=TEXT,
            max_lines=2,
        ) + 12

def draw_transition_box(draw, scene: Dict[str, Any]):
    x1, y1, x2, y2 = 105, 750, 1040, 940
    draw.rounded_rectangle((x1, y1, x2, y2), radius=34, fill="#fff7ed", outline="#fdba74", width=2)
    draw.text((x1 + 34, y1 + 24), "下一個問題", font=get_font(28), fill=ORANGE)
    draw_wrapped_text(
        draw,
        scene.get("transition_question", ""),
        (x1 + 34, y1 + 76),
        get_font(30),
        max_chars=29,
        line_spacing=7,
        fill=TEXT,
        max_lines=4,
    )

def render_scene(meta: Dict[str, Any], scene: Dict[str, Any]):
    img, draw = create_base(meta, scene)
    draw_answer_box(draw, scene)
    draw_bullets_box(draw, scene)
    draw_transition_box(draw, scene)
    return img

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--scene-file", type=str, default="weekly_video_scene_ai.json")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    scene_path = week_dir / args.scene_file
    data = load_json(scene_path)

    meta = data.get("video_meta", {})
    scenes = data.get("scenes", [])

    cards_dir = week_dir / "ai_cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    for scene in scenes:
        order = int(scene.get("scene_order", 0))
        if order <= 0:
            continue
        img = render_scene(meta, scene)
        out_path = cards_dir / f"card_{order:02d}.png"
        img.save(out_path)
        print(f"[OK] Created {out_path}")

    print(f"[OK] Generated {len(scenes)} AI cards in {cards_dir}")

if __name__ == "__main__":
    main()
