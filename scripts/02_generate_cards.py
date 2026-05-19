#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Step 02
Generate 6 PNG cards from weekly_video_scene.json.

MVP scope:
1. Find latest output/weekly/YYYY-MM-DD/weekly_video_scene.json
2. Read six scene definitions
3. Generate one 1920x1080 PNG card per scene
4. Save cards to output/weekly/YYYY-MM-DD/cards/
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


def get_font(size: int) -> ImageFont.FreeTypeFont:
    font_path = find_font_path()
    if font_path:
        return ImageFont.truetype(font_path, size=size)
    return ImageFont.load_default()


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: tuple,
    font: ImageFont.FreeTypeFont,
    max_chars: int,
    line_spacing: int,
    fill: str = "#1f2937",
    max_lines: Optional[int] = None,
) -> int:
    """Draw wrapped text and return the next y position."""
    x, y = xy
    if not text:
        return y

    lines = []
    for paragraph in str(text).split("\n"):
        wrapped = textwrap.wrap(paragraph, width=max_chars) or [""]
        lines.extend(wrapped)

    if max_lines is not None:
        lines = lines[:max_lines]

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        y += (bbox[3] - bbox[1]) + line_spacing

    return y


def draw_header(draw: ImageDraw.ImageDraw, scene: Dict[str, Any], meta: Dict[str, Any]) -> None:
    title_font = get_font(58)
    subtitle_font = get_font(30)
    meta_font = get_font(24)

    draw.text((90, 70), scene.get("card_title", ""), font=title_font, fill="#111827")
    draw.text((94, 145), scene.get("card_subtitle", ""), font=subtitle_font, fill="#4b5563")

    week_label = meta.get("week_label", "")
    draw.text((90, 990), f"Weekly Macro Video｜{week_label}", font=meta_font, fill="#6b7280")

    # thin divider
    draw.line((90, 205, 1830, 205), fill="#e5e7eb", width=3)


def draw_badge(draw: ImageDraw.ImageDraw, xy: tuple, text: str, fill: str = "#f3f4f6") -> None:
    x, y = xy
    font = get_font(26)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 36
    h = bbox[3] - bbox[1] + 22
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=fill, outline="#e5e7eb", width=2)
    draw.text((x + 18, y + 10), text, font=font, fill="#374151")


def create_base_card(scene: Dict[str, Any], meta: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), "#fbfbfd")
    draw = ImageDraw.Draw(img)

    # main white panel
    draw.rounded_rectangle((60, 45, 1860, 1035), radius=36, fill="#ffffff", outline="#e5e7eb", width=2)
    draw_header(draw, scene, meta)
    draw_badge(draw, (1570, 80), scene.get("scene_id", ""))

    return img


def render_scene_01(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    assets = scene.get("data_summary", {}).get("assets", [])
    font_h = get_font(30)
    font = get_font(25)
    small = get_font(22)

    x0, y0 = 105, 250
    col = [x0, x0 + 410, x0 + 620, x0 + 900]

    headers = ["資產", "週變化", "週內路徑", "解讀"]
    for i, h in enumerate(headers):
        draw.text((col[i], y0), h, font=font_h, fill="#111827")
    draw.line((x0, y0 + 48, 1810, y0 + 48), fill="#d1d5db", width=2)

    y = y0 + 75
    for item in assets[:7]:
        draw.text((col[0], y), str(item.get("asset_name", "")), font=font, fill="#111827")
        draw.text((col[1], y), str(item.get("weekly_change", "")), font=font, fill="#374151")
        draw.text((col[2], y), str(item.get("path_type", "")), font=font, fill="#374151")
        comment = str(item.get("path_comment", ""))
        draw_wrapped_text(draw, comment, (col[3], y), small, max_chars=34, line_spacing=6, fill="#4b5563", max_lines=2)
        y += 90


def render_scene_02(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    events = scene.get("data_summary", {}).get("events", [])
    title_font = get_font(34)
    body_font = get_font(26)
    y = 255

    for idx, event in enumerate(events[:5], start=1):
        x = 110
        draw.rounded_rectangle((x, y, 1810, y + 120), radius=22, fill="#f9fafb", outline="#e5e7eb", width=2)
        draw.text((x + 28, y + 22), f"{idx}. {event.get('event_title', '')}", font=title_font, fill="#111827")
        category = event.get("event_category", "")
        impact = event.get("impact_direction", "")
        draw.text((x + 950, y + 28), f"{category}｜{impact}", font=body_font, fill="#374151")
        draw_wrapped_text(draw, event.get("event_summary", ""), (x + 28, y + 70), body_font, 58, 5, "#4b5563", max_lines=1)
        y += 138


def render_scene_03(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    data = scene.get("data_summary", {})
    logic = scene.get("analysis_logic", {})
    title_font = get_font(34)
    body_font = get_font(28)
    verdict_font = get_font(50)

    left = (110, 270, 820, 760)
    right = (1100, 270, 1810, 760)
    center = (820, 380, 1100, 650)

    draw.rounded_rectangle(left, radius=28, fill="#f9fafb", outline="#e5e7eb", width=2)
    draw.rounded_rectangle(right, radius=28, fill="#f9fafb", outline="#e5e7eb", width=2)
    draw.rounded_rectangle(center, radius=28, fill="#f3f4f6", outline="#d1d5db", width=2)

    draw.text((145, 305), "推升通膨預期", font=title_font, fill="#111827")
    draw.text((1135, 305), "壓低通膨預期", font=title_font, fill="#111827")

    y = 370
    for item in data.get("inflation_up_factors", [])[:5]:
        draw.text((150, y), f"• {item}", font=body_font, fill="#374151")
        y += 58

    y = 370
    for item in data.get("inflation_down_factors", [])[:5]:
        draw.text((1140, y), f"• {item}", font=body_font, fill="#374151")
        y += 58

    verdict = logic.get("inflation_expectation_direction", "待判斷")
    draw.text((880, 455), "本週判斷", font=body_font, fill="#6b7280")
    draw.text((870, 510), verdict, font=verdict_font, fill="#111827")

    draw_wrapped_text(draw, logic.get("reasoning", ""), (150, 815), body_font, 58, 8, "#4b5563", max_lines=3)


def render_scene_04(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    logic = scene.get("analysis_logic", {})
    us10y = scene.get("data_summary", {}).get("us10y", {})
    title_font = get_font(34)
    body_font = get_font(28)

    draw.rounded_rectangle((110, 255, 1810, 355), radius=26, fill="#f3f4f6", outline="#e5e7eb", width=2)
    summary = f"美國10年期公債殖利率：{us10y.get('path_type', '待判斷')}｜週變化 {us10y.get('weekly_change', '')}"
    draw.text((150, 290), summary, font=title_font, fill="#111827")

    boxes = [
        (110, 410, 900, 800, "通膨驅動", logic.get("inflation_driven_factors", [])),
        (1020, 410, 1810, 800, "非通膨驅動", logic.get("non_inflation_rate_factors", [])),
    ]

    for x1, y1, x2, y2, title, items in boxes:
        draw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill="#f9fafb", outline="#e5e7eb", width=2)
        draw.text((x1 + 35, y1 + 32), title, font=title_font, fill="#111827")
        y = y1 + 105
        for item in items[:5]:
            draw.text((x1 + 45, y), f"• {item}", font=body_font, fill="#374151")
            y += 58

    verdict = f"利率與通膨一致性：{logic.get('rate_vs_inflation_consistency', '待判斷')}｜主要驅動：{logic.get('main_rate_driver', '待判斷')}"
    draw_wrapped_text(draw, verdict, (130, 850), body_font, 64, 8, "#111827", max_lines=2)


def render_scene_05(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    logic = scene.get("analysis_logic", {})
    assets = scene.get("data_summary", {}).get("assets", [])
    body_font = get_font(30)
    small = get_font(24)
    title_font = get_font(36)

    chain = ["利率", "美元", "亞洲貨幣", "黃金"]
    x_positions = [170, 580, 1010, 1460]
    y = 330

    for i, label in enumerate(chain):
        x = x_positions[i]
        draw.rounded_rectangle((x, y, x + 260, y + 120), radius=28, fill="#f3f4f6", outline="#d1d5db", width=2)
        draw.text((x + 85, y + 40), label, font=title_font, fill="#111827")
        if i < len(chain) - 1:
            draw.line((x + 285, y + 60, x_positions[i + 1] - 25, y + 60), fill="#9ca3af", width=6)
            draw.polygon([(x_positions[i + 1] - 25, y + 60), (x_positions[i + 1] - 55, y + 45), (x_positions[i + 1] - 55, y + 75)], fill="#9ca3af")

    y2 = 535
    comments = [
        f"利率 → 美元：{logic.get('dollar_vs_rate_consistency', '待判斷')}",
        f"美元 → 亞洲貨幣：{logic.get('asia_fx_vs_dollar_consistency', '待判斷')}",
        f"黃金邏輯：{logic.get('gold_logic', '待判斷')}",
        f"油價回饋通膨：{logic.get('oil_to_inflation_feedback', '')}",
    ]
    for comment in comments:
        draw.text((150, y2), f"• {comment}", font=body_font, fill="#374151")
        y2 += 62

    draw.line((110, 810, 1810, 810), fill="#e5e7eb", width=2)
    draw.text((150, 845), "主要資產週內路徑", font=title_font, fill="#111827")
    x = 150
    y3 = 910
    for item in assets[:4]:
        txt = f"{item.get('asset_name', '')}：{item.get('path_type', '')}"
        draw.text((x, y3), txt, font=small, fill="#4b5563")
        x += 420


def render_scene_06(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    data = scene.get("data_summary", {})
    logic = scene.get("analysis_logic", {})
    title_font = get_font(34)
    body_font = get_font(27)
    verdict_font = get_font(58)

    verdict = logic.get("transmission_verdict", "待判斷")
    draw.rounded_rectangle((110, 245, 1810, 365), radius=30, fill="#f3f4f6", outline="#d1d5db", width=2)
    draw.text((150, 275), "本週總經傳導", font=title_font, fill="#374151")
    draw.text((520, 260), verdict, font=verdict_font, fill="#111827")

    chain = data.get("macro_chain", [])
    y = 430
    for item in chain[:5]:
        step = item.get("step", "")
        direction = item.get("direction", "")
        comment = item.get("comment", "")
        draw.text((150, y), f"{step}：{direction}", font=title_font, fill="#111827")
        draw_wrapped_text(draw, comment, (620, y + 4), body_font, 46, 6, "#4b5563", max_lines=1)
        y += 75

    draw.line((110, 810, 1810, 810), fill="#e5e7eb", width=2)
    draw.text((150, 850), "下週三個驗證點", font=title_font, fill="#111827")
    x = 150
    y2 = 910
    for item in logic.get("next_week_watchpoints", [])[:3]:
        draw.text((x, y2), f"• {item}", font=body_font, fill="#374151")
        y2 += 48


def render_generic(draw: ImageDraw.ImageDraw, scene: Dict[str, Any]) -> None:
    body_font = get_font(30)
    headline = scene.get("visual_content", {}).get("headline", "")
    draw_wrapped_text(draw, headline, (120, 280), body_font, 42, 10, "#111827", max_lines=4)


def render_scene(scene: Dict[str, Any], meta: Dict[str, Any]) -> Image.Image:
    img = create_base_card(scene, meta)
    draw = ImageDraw.Draw(img)

    visual_type = scene.get("visual_type", "")

    if visual_type == "market_path_card":
        render_scene_01(draw, scene)
    elif visual_type == "event_cluster_card":
        render_scene_02(draw, scene)
    elif visual_type == "inflation_factor_card":
        render_scene_03(draw, scene)
    elif visual_type == "rate_driver_card":
        render_scene_04(draw, scene)
    elif visual_type == "asset_reaction_card":
        render_scene_05(draw, scene)
    elif visual_type == "macro_chain_verdict_card":
        render_scene_06(draw, scene)
    else:
        render_generic(draw, scene)

    return img


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="", help="Optional weekly output folder, e.g. output/weekly/2026-05-21")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    scene_path = week_dir / "weekly_video_scene.json"
    if not scene_path.exists():
        raise FileNotFoundError(f"weekly_video_scene.json not found: {scene_path}")

    data = load_json(scene_path)
    meta = data.get("video_meta", {})
    scenes = data.get("scenes", [])

    cards_dir = week_dir / "cards"
    cards_dir.mkdir(parents=True, exist_ok=True)

    for scene in scenes:
        order = int(scene.get("scene_order", 0))
        if order <= 0:
            continue

        img = render_scene(scene, meta)
        out_path = cards_dir / f"card_{order:02d}.png"
        img.save(out_path)
        print(f"[OK] Created {out_path}")

    print(f"[OK] Generated {len(scenes)} cards in {cards_dir}")


if __name__ == "__main__":
    main()
