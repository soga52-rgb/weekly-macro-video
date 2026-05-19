#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
NotebookLM-style + Macro Transmission Diagram cards
讀取 weekly_video_scene_ai.json
輸出 ai_cards/card_01.png ~ card_06.png

版型：
- Scene 01 / 02 / 06：NotebookLM 解說卡
- Scene 03 / 04 / 05：傳導圖解卡
"""

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
SOFT_ORANGE = "#fff7ed"
SOFT_GREEN = "#ecfdf5"
SOFT_BLUE = "#eff6ff"
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
    lines: List[str] = []
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

def draw_badge(draw, x, y, text):
    font = get_font(24)
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0] + 34
    h = bbox[3] - bbox[1] + 20
    draw.rounded_rectangle((x, y, x + w, y + h), radius=18, fill=SOFT_ORANGE, outline="#fdba74", width=2)
    draw.text((x + 17, y + 9), text, font=font, fill=ORANGE)

def draw_arrow(draw, start: Tuple[int, int], end: Tuple[int, int], color=TEXT, width=4, dashed=False):
    x1, y1 = start
    x2, y2 = end

    if dashed:
        segments = 12
        for i in range(segments):
            if i % 2 == 0:
                sx = x1 + (x2 - x1) * i / segments
                sy = y1 + (y2 - y1) * i / segments
                ex = x1 + (x2 - x1) * (i + 1) / segments
                ey = y1 + (y2 - y1) * (i + 1) / segments
                draw.line((sx, sy, ex, ey), fill=color, width=width)
    else:
        draw.line((x1, y1, x2, y2), fill=color, width=width)

    # simple arrow head
    if x2 >= x1:
        draw.polygon([(x2, y2), (x2 - 16, y2 - 10), (x2 - 16, y2 + 10)], fill=color)
    else:
        draw.polygon([(x2, y2), (x2 + 16, y2 - 10), (x2 + 16, y2 + 10)], fill=color)

def draw_node(draw, box, label, group="neutral"):
    x1, y1, x2, y2 = box
    fill = {
        "up": SOFT_ORANGE,
        "down": SOFT_BLUE,
        "neutral": SOFT_GRAY,
        "driver": SOFT_GRAY,
        "result": SOFT_GREEN,
        "divergence": "#fef2f2",
        "asset": "#f8fafc",
    }.get(group, SOFT_GRAY)

    outline = {
        "up": "#fdba74",
        "down": "#93c5fd",
        "neutral": LINE,
        "driver": LINE,
        "result": "#86efac",
        "divergence": "#fca5a5",
        "asset": "#cbd5e1",
    }.get(group, LINE)

    draw.rounded_rectangle((x1, y1, x2, y2), radius=24, fill=fill, outline=outline, width=3)
    draw_wrapped_text(draw, label, (x1 + 24, y1 + 25), get_font(29), max_chars=10, line_spacing=6, fill=TEXT, max_lines=2)

def base_card(meta: Dict[str, Any], scene: Dict[str, Any]):
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw_grid(draw)

    # top
    draw.text((90, 62), scene.get("card_title", ""), font=get_font(56), fill=TEXT)
    draw.line((90, 132, 520, 132), fill=ORANGE, width=8)
    draw.text((90, 158), "WEEKLY MACRO VIDEO", font=get_font(24), fill=MUTED)
    draw_badge(draw, 1660, 74, scene.get("scene_id", ""))

    # question
    draw.text((90, 210), "本段問題", font=get_font(25), fill=MUTED)
    draw_wrapped_text(draw, scene.get("opening_question", ""), (90, 246), get_font(43), 31, 8, TEXT, 2)

    # footer
    draw.text((90, 1012), f"Weekly Macro Video｜{meta.get('week_label', '')}", font=get_font(23), fill=MUTED)

    return img, draw

def draw_small_transition(draw, scene: Dict[str, Any]):
    x1, y1, x2, y2 = 90, 888, 1830, 970
    draw.rounded_rectangle((x1, y1, x2, y2), radius=26, fill=SOFT_ORANGE, outline="#fdba74", width=2)
    draw.text((x1 + 28, y1 + 24), "下一個問題：", font=get_font(28), fill=ORANGE)
    draw_wrapped_text(draw, scene.get("transition_question", ""), (x1 + 250, y1 + 24), get_font(28), 48, 5, TEXT, 2)

def render_explainer_card(meta, scene):
    img, draw = base_card(meta, scene)

    # answer
    draw.rounded_rectangle((90, 405, 980, 640), radius=30, fill=PANEL, outline=LINE, width=2)
    draw.line((115, 430, 115, 615), fill=ORANGE, width=10)
    draw.text((145, 430), "核心答案", font=get_font(27), fill=MUTED)
    draw_wrapped_text(draw, scene.get("answer_summary", ""), (145, 482), get_font(31), 28, 8, TEXT, 4)

    # bullets
    draw.rounded_rectangle((1030, 405, 1830, 775), radius=30, fill=PANEL, outline=LINE, width=2)
    draw.text((1062, 430), "本週重點", font=get_font(27), fill=MUTED)
    bullets = scene.get("card_bullets", [])
    y = 492
    for bullet in bullets[:4]:
        draw.ellipse((1062, y + 10, 1080, y + 28), fill=ORANGE)
        y = draw_wrapped_text(draw, str(bullet), (1100, y), get_font(30), 29, 6, TEXT, 2) + 12

    draw_small_transition(draw, scene)
    return img

def layout_nodes_for_scene(scene):
    scene_id = scene.get("scene_id", "")
    nodes = scene.get("diagram_nodes", []) or []
    positions = {}

    if scene_id == "scene_03":
        # left factors -> right result
        inputs = [n for n in nodes if n.get("group") != "result"]
        results = [n for n in nodes if n.get("group") == "result"] or nodes[-1:]
        y_values = [430, 560, 690, 800]
        for i, n in enumerate(inputs[:4]):
            positions[n["id"]] = (1060, y_values[i], 1365, y_values[i] + 86)
        if results:
            positions[results[0]["id"]] = (1510, 575, 1810, 675)

    elif scene_id == "scene_04":
        # two-side drivers -> center rate
        results = [n for n in nodes if n.get("group") == "result"] or nodes[-1:]
        drivers = [n for n in nodes if n.get("group") != "result"]
        for i, n in enumerate(drivers[:2]):
            positions[n["id"]] = (1020, 470 + i * 145, 1320, 560 + i * 145)
        for i, n in enumerate(drivers[2:4]):
            positions[n["id"]] = (1510, 470 + i * 145, 1810, 560 + i * 145)
        if results:
            positions[results[0]["id"]] = (1265, 720, 1570, 815)

    else:
        # scene_05 chain layout
        x_values = [1010, 1230, 1450, 1670]
        y = 505
        for i, n in enumerate(nodes[:4]):
            positions[n["id"]] = (x_values[i], y, x_values[i] + 190, y + 92)
        for i, n in enumerate(nodes[4:6]):
            positions[n["id"]] = (1230 + i * 260, 705, 1450 + i * 260, 800)

    return positions

def render_diagram_card(meta, scene):
    img, draw = base_card(meta, scene)

    # left answer box
    draw.rounded_rectangle((90, 405, 925, 620), radius=30, fill=PANEL, outline=LINE, width=2)
    draw.line((115, 430, 115, 595), fill=ORANGE, width=10)
    draw.text((145, 430), "核心答案", font=get_font(27), fill=MUTED)
    draw_wrapped_text(draw, scene.get("answer_summary", ""), (145, 482), get_font(30), 26, 8, TEXT, 4)

    # left verdict/support
    draw.rounded_rectangle((90, 650, 925, 835), radius=30, fill=SOFT_GRAY, outline=LINE, width=2)
    verdict = scene.get("verdict_label", "") or "待判斷"
    draw.text((125, 675), f"判斷：{verdict}", font=get_font(32), fill=TEXT)
    support = scene.get("supporting_factors", []) or scene.get("card_bullets", [])
    y = 730
    for item in support[:2]:
        draw.text((130, y), "•", font=get_font(28), fill=ORANGE)
        y = draw_wrapped_text(draw, str(item), (165, y), get_font(26), 28, 5, TEXT, 1) + 8

    # diagram area
    draw.rounded_rectangle((980, 390, 1830, 835), radius=34, fill=PANEL, outline=LINE, width=2)
    draw.text((1015, 420), "傳導圖解", font=get_font(28), fill=MUTED)

    nodes = scene.get("diagram_nodes", []) or []
    edges = scene.get("diagram_edges", []) or []

    # fallback nodes from bullets
    if not nodes:
        bullets = scene.get("card_bullets", [])[:4]
        nodes = [{"id": f"n{i+1}", "label": b, "group": "driver"} for i, b in enumerate(bullets)]
        nodes.append({"id": "result", "label": scene.get("verdict_label", "結果"), "group": "result"})
        edges = [{"from": n["id"], "to": "result", "type": "mixed"} for n in nodes[:-1]]

    positions = layout_nodes_for_scene({**scene, "diagram_nodes": nodes})

    # draw edges first
    for e in edges:
        from_box = positions.get(e.get("from"))
        to_box = positions.get(e.get("to"))
        if not from_box or not to_box:
            continue

        sx = from_box[2]
        sy = (from_box[1] + from_box[3]) // 2
        tx = to_box[0]
        ty = (to_box[1] + to_box[3]) // 2

        edge_type = e.get("type", "mixed")
        color = ORANGE if edge_type == "positive" else "#64748b"
        dashed = edge_type in ("negative", "divergence", "mixed")
        draw_arrow(draw, (sx, sy), (tx, ty), color=color, width=4, dashed=dashed)

    # draw nodes
    for n in nodes:
        box = positions.get(n.get("id"))
        if not box:
            continue
        draw_node(draw, box, n.get("label", ""), n.get("group", "neutral"))

    # divergence note
    note = scene.get("divergence_note", "")
    if note:
        draw.text((1015, 800), f"註：{note}", font=get_font(22), fill=MUTED)

    draw_small_transition(draw, scene)
    return img

def render_scene(meta, scene):
    if scene.get("scene_id") in ("scene_03", "scene_04", "scene_05"):
        return render_diagram_card(meta, scene)
    return render_explainer_card(meta, scene)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--scene-file", type=str, default="weekly_video_scene_ai.json")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    data = load_json(week_dir / args.scene_file)
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
