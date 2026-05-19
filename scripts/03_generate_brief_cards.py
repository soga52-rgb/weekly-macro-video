#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 03
Generate NotebookLM-style brief cards from weekly_video_brief.json.

Input:
- output/weekly/YYYY-MM-DD/weekly_video_brief.json

Output:
- output/weekly/YYYY-MM-DD/brief_cards/card_01.png ~ card_06.png

Card structure:
1. Executive Summary
2. Market Signals
3. Macro Chain
4. News Evidence
5. Transmission Steps
6. Next Week Watch
"""

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

W, H = 1920, 1080

BG = "#fcfcfb"
TEXT = "#111827"
MUTED = "#6b7280"
LINE = "#e5e7eb"
ORANGE = "#f97316"
SOFT_ORANGE = "#fff7ed"
PANEL = "#ffffff"
SOFT_GRAY = "#f9fafb"

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/System/Library/Fonts/PingFang.ttc",
    "C:/Windows/Fonts/msjh.ttc",
    "C:/Windows/Fonts/mingliu.ttc",
]


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
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


def font(size: int):
    fp = find_font_path()
    if fp:
        return ImageFont.truetype(fp, size=size)
    return ImageFont.load_default()


def wrap(text: str, max_chars: int, max_lines: Optional[int] = None) -> List[str]:
    lines: List[str] = []
    for paragraph in str(text or "").split("\n"):
        lines.extend(textwrap.wrap(paragraph, width=max_chars) or [""])
    if max_lines is not None:
        lines = lines[:max_lines]
    return lines


def draw_text(draw, text, xy, fnt, max_chars, fill=TEXT, line_gap=8, max_lines=None):
    x, y = xy
    for line in wrap(text, max_chars, max_lines):
        draw.text((x, y), line, font=fnt, fill=fill)
        bbox = draw.textbbox((x, y), line, font=fnt)
        y += (bbox[3] - bbox[1]) + line_gap
    return y


def draw_grid(draw):
    step = 46
    for x in range(0, W, step):
        draw.line((x, 0, x, H), fill="#f1f5f9", width=1)
    for y in range(0, H, step):
        draw.line((0, y, W, y), fill="#f1f5f9", width=1)


def draw_badge(draw, text):
    draw.rounded_rectangle((1650, 70, 1810, 122), radius=18, fill=SOFT_ORANGE, outline="#fdba74", width=2)
    draw.text((1682, 82), text, font=font(25), fill=ORANGE)


def draw_footer(draw, week_label):
    draw.text((90, 1010), f"Weekly Macro Video｜{week_label}", font=font(23), fill=MUTED)


def draw_base(title: str, scene: str, week_label: str):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    draw_grid(draw)

    draw.text((90, 65), title, font=font(60), fill=TEXT)
    draw.line((90, 138, 560, 138), fill=ORANGE, width=8)
    draw.text((90, 165), "NOTEBOOKLM-STYLE MACRO BRIEF", font=font(23), fill=MUTED)
    draw_badge(draw, scene)
    draw_footer(draw, week_label)
    return img, draw


def card_01(data, week_label):
    es = data.get("executive_summary", {})
    img, draw = draw_base("Executive Summary", "card_01", week_label)

    draw.text((90, 250), es.get("headline", ""), font=font(56), fill=TEXT)

    draw.rounded_rectangle((95, 390, 1260, 615), radius=34, fill=PANEL, outline=LINE, width=2)
    draw.line((125, 420, 125, 585), fill=ORANGE, width=10)
    draw.text((155, 420), "本週主線", font=font(30), fill=MUTED)
    draw_text(draw, es.get("summary", ""), (155, 480), font(34), 38, TEXT, 10, 4)

    # Doodle / key question
    draw.rounded_rectangle((1320, 395, 1815, 760), radius=34, fill=SOFT_GRAY, outline=LINE, width=2)
    draw.text((1370, 435), "核心問題", font=font(30), fill=MUTED)
    draw_text(draw, data.get("key_question", ""), (1370, 500), font(34), 17, TEXT, 10, 6)
    draw.ellipse((1540, 690, 1630, 780), outline=ORANGE, width=8)
    draw.text((1564, 696), "?", font=font(62), fill=ORANGE)

    return img


def card_02(data, week_label):
    signals = data.get("market_signals", [])
    img, draw = draw_base("今日市場訊號", "card_02", week_label)

    draw.text((90, 245), "三個訊號，決定本週總經主線", font=font(48), fill=TEXT)

    x_positions = [115, 705, 1295]
    for i, sig in enumerate(signals[:3]):
        x = x_positions[i]
        draw.rounded_rectangle((x, 365, x + 500, 780), radius=36, fill=PANEL, outline=LINE, width=2)
        draw.text((x + 40, 410), sig.get("icon", "📊"), font=font(62), fill=TEXT)
        draw.text((x + 40, 500), sig.get("label", ""), font=font(38), fill=TEXT)
        draw.line((x + 40, 560, x + 390, 560), fill=ORANGE, width=5)
        draw_text(draw, sig.get("meaning", ""), (x + 40, 600), font(30), 18, TEXT, 8, 4)

    return img


def draw_arrow(draw, x1, y1, x2, y2, color=ORANGE, width=6):
    draw.line((x1, y1, x2, y2), fill=color, width=width)
    draw.polygon([(x2, y2), (x2 - 18, y2 - 11), (x2 - 18, y2 + 11)], fill=color)


def card_03(data, week_label):
    chain = data.get("macro_chain", {})
    img, draw = draw_base("總經傳導鏈", "card_03", week_label)

    draw.text((90, 245), chain.get("title", ""), font=font(48), fill=TEXT)

    draw.rounded_rectangle((95, 350, 900, 590), radius=34, fill=PANEL, outline=LINE, width=2)
    draw.line((125, 380, 125, 560), fill=ORANGE, width=10)
    draw.text((155, 380), "傳導解讀", font=font(30), fill=MUTED)
    draw_text(draw, chain.get("explanation", ""), (155, 440), font(31), 27, TEXT, 8, 4)

    # Chain diagram from steps, simplified
    steps = [s.replace("1. ", "").replace("2. ", "").replace("3. ", "").replace("4. ", "").replace("5. ", "") for s in data.get("transmission_steps", [])]
    boxes = [(980, 390), (1230, 390), (1480, 390), (1110, 660), (1360, 660)]
    for i, step in enumerate(steps[:5]):
        x, y = boxes[i]
        draw.rounded_rectangle((x, y, x + 220, y + 105), radius=26, fill=SOFT_ORANGE if i in (0, 4) else SOFT_GRAY, outline="#fdba74" if i in (0, 4) else LINE, width=2)
        draw.text((x + 18, y + 14), str(i + 1), font=font(26), fill=ORANGE)
        draw_text(draw, step, (x + 55, y + 18), font(24), 8, TEXT, 4, 2)

    draw_arrow(draw, 1200, 442, 1230, 442)
    draw_arrow(draw, 1450, 442, 1480, 442)
    draw_arrow(draw, 1590, 500, 1220, 660, color="#64748b", width=4)
    draw_arrow(draw, 1330, 715, 1360, 715)

    return img


def card_04(data, week_label):
    ev = data.get("news_evidence", {})
    img, draw = draw_base("新聞佐證", "card_04", week_label)

    draw.text((90, 245), "這條傳導鏈，有哪些新聞可以佐證？", font=font(48), fill=TEXT)

    draw.rounded_rectangle((95, 360, 1815, 720), radius=38, fill=PANEL, outline=LINE, width=2)
    draw.text((145, 410), ev.get("title", "資料不足，暫不判斷"), font=font(42), fill=TEXT)
    draw.line((145, 475, 1000, 475), fill=ORANGE, width=6)
    draw_text(draw, ev.get("summary", ""), (145, 540), font(34), 50, TEXT, 10, 4)

    url = ev.get("url", "")
    if url and url != "資料不足，暫不判斷":
        source = f"來源：{url}"
    else:
        source = "來源：資料不足，暫不判斷"
    draw.text((145, 760), source, font=font(26), fill=MUTED)

    return img


def card_05(data, week_label):
    steps = [s.replace("1. ", "").replace("2. ", "").replace("3. ", "").replace("4. ", "").replace("5. ", "") for s in data.get("transmission_steps", [])]
    img, draw = draw_base("五步傳導圖解", "card_05", week_label)

    draw.text((90, 245), "從訊號到資產反應，市場是這樣走的", font=font(46), fill=TEXT)

    y = 360
    for i, step in enumerate(steps[:5], start=1):
        x = 150 + (i - 1) * 335
        draw.rounded_rectangle((x, y, x + 270, y + 190), radius=34, fill=PANEL, outline=LINE, width=2)
        draw.ellipse((x + 25, y + 25, x + 75, y + 75), fill=ORANGE)
        draw.text((x + 42, y + 30), str(i), font=font(28), fill="#ffffff")
        draw_text(draw, step, (x + 25, y + 95), font(30), 11, TEXT, 8, 3)
        if i < 5:
            draw_arrow(draw, x + 270, y + 95, x + 330, y + 95)

    draw.rounded_rectangle((150, 655, 1770, 815), radius=34, fill=SOFT_ORANGE, outline="#fdba74", width=2)
    draw.text((190, 690), "關鍵問題", font=font(30), fill=ORANGE)
    draw_text(draw, data.get("key_question", ""), (190, 745), font(32), 48, TEXT, 8, 2)

    return img


def card_06(data, week_label):
    nw = data.get("next_week_watch", {})
    img, draw = draw_base("下週觀察", "card_06", week_label)

    draw.text((90, 245), nw.get("headline", ""), font=font(52), fill=TEXT)

    points = nw.get("watchpoints", [])
    y = 390
    for i, p in enumerate(points[:3], start=1):
        draw.rounded_rectangle((120, y, 1780, y + 120), radius=32, fill=PANEL, outline=LINE, width=2)
        draw.ellipse((160, y + 35, 210, y + 85), fill=ORANGE)
        draw.text((177, y + 40), str(i), font=font(28), fill="#ffffff")
        draw_text(draw, p, (250, y + 35), font(36), 40, TEXT, 8, 2)
        y += 150

    draw.rounded_rectangle((120, 850, 1780, 930), radius=30, fill=SOFT_ORANGE, outline="#fdba74", width=2)
    draw.text((160, 872), "下一支影片要驗證：這條傳導鏈是否延續，或出現新的背離。", font=font(32), fill=TEXT)

    return img


CARD_RENDERERS = [card_01, card_02, card_03, card_04, card_05, card_06]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--brief-file", type=str, default="weekly_video_brief.json")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    data = load_json(week_dir / args.brief_file)

    week_label = ""
    # Try to infer week label from existing facts or output folder
    facts_path = week_dir / "weekly_facts.json"
    if facts_path.exists():
        facts = load_json(facts_path)
        week_label = facts.get("week_meta", {}).get("week_label", "")
    if not week_label:
        week_label = week_dir.name

    out_dir = week_dir / "brief_cards"
    out_dir.mkdir(parents=True, exist_ok=True)

    for i, renderer in enumerate(CARD_RENDERERS, start=1):
        img = renderer(data, week_label)
        out_path = out_dir / f"card_{i:02d}.png"
        img.save(out_path)
        print(f"[OK] Created {out_path}")

    print(f"[OK] Generated 6 brief cards in {out_dir}")


if __name__ == "__main__":
    main()
