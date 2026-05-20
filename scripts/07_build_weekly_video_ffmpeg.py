#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 07 V6
Build weekly macro video with:
- left: macro transmission diagram + spotlight
- right: evidence panel with mini market charts + news cards + key bullets

Input:
- output/weekly/YYYY-MM-DD/narration/weekly_narration.json
- output/weekly/YYYY-MM-DD/audio/scene_01.wav ... scene_06.wav
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png
- output/weekly/YYYY-MM-DD/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_news_context.json

Output:
- output/weekly/YYYY-MM-DD/video_assets/scene_01.png ... scene_06.png
- output/weekly/YYYY-MM-DD/final/weekly_macro_video.mp4
"""

import argparse
import json
import math
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

WIDTH = 1920
HEIGHT = 1080
BG = (248, 250, 252)
WHITE = (255, 255, 255)
NAVY = (15, 42, 68)
ORANGE = (245, 158, 11)
GRAY = (100, 116, 139)
DARK = (31, 41, 55)
LIGHT_LINE = (226, 232, 240)
SOFT_ORANGE = (255, 243, 209)

SPOTLIGHT_PRESETS = {
    "overview": (0.04, 0.06, 0.96, 0.88),
    "drivers": (0.04, 0.08, 0.43, 0.34),
    "yields": (0.28, 0.20, 0.62, 0.49),
    "dollar_fx": (0.50, 0.18, 0.92, 0.64),
    "gold_risk": (0.48, 0.52, 0.94, 0.88),
    "next_watch": (0.06, 0.60, 0.46, 0.90),
}

ASSET_LABELS = {
    "US10Y": "美國10年債",
    "DXY": "美元指數",
    "Gold": "黃金",
    "WTI": "WTI原油",
    "Brent": "布蘭特原油",
    "USDJPY": "美元/日圓",
    "USDTWD": "美元/台幣",
    "USDKRW": "美元/韓元",
}


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    text = " ".join(str(text or "").split())
    lines: List[str] = []
    current = ""
    for char in text:
        test = current + char
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def rounded(draw: ImageDraw.ImageDraw, xy: Tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def slide_base() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.ellipse((-240, -240, 760, 360), fill=SOFT_ORANGE)
    draw.ellipse((1280, -260, 2220, 360), fill=(236, 242, 248))
    return img


def draw_top_meta(draw: ImageDraw.ImageDraw, scene_title: str, visual_direction: str = "") -> None:
    small = find_font(26, bold=True)
    title_font = find_font(48, bold=True)
    sub_font = find_font(24)
    draw.text((60, 34), "WEEKLY MACRO VIDEO", fill=ORANGE, font=small)
    draw.text((60, 72), scene_title, fill=NAVY, font=title_font)
    if visual_direction:
        y = 132
        for line in wrap_text(visual_direction, sub_font, 1080)[:2]:
            draw.text((60, y), line, fill=GRAY, font=sub_font)
            y += 30


def apply_spotlight(diagram: Image.Image, target: str) -> Image.Image:
    rgba = diagram.convert("RGBA")
    w, h = rgba.size
    preset = SPOTLIGHT_PRESETS.get(target, SPOTLIGHT_PRESETS["overview"])
    x1 = int(preset[0] * w)
    y1 = int(preset[1] * h)
    x2 = int(preset[2] * w)
    y2 = int(preset[3] * h)

    overlay = Image.new("RGBA", (w, h), (8, 22, 38, 145))
    hole_mask = Image.new("L", (w, h), 255)
    hdraw = ImageDraw.Draw(hole_mask)
    hdraw.rounded_rectangle((x1, y1, x2, y2), radius=28, fill=0)
    overlay.putalpha(hole_mask)

    glow_mask = Image.new("L", (w, h), 0)
    gdraw = ImageDraw.Draw(glow_mask)
    gdraw.rounded_rectangle((x1 - 12, y1 - 12, x2 + 12, y2 + 12), radius=34, fill=220)
    glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(22))
    glow = Image.new("RGBA", (w, h), (255, 176, 64, 90))
    glow.putalpha(glow_mask)

    rgba = Image.alpha_composite(rgba, glow)
    rgba = Image.alpha_composite(rgba, overlay)
    d = ImageDraw.Draw(rgba)
    d.rounded_rectangle((x1, y1, x2, y2), radius=28, outline=(255, 168, 54, 255), width=6)
    return rgba.convert("RGB")


def prepare_diagram_canvas(week_dir: Path, scene: Dict[str, Any]) -> Image.Image:
    diagram_path = week_dir / "weekly_macro_diagram.png"
    if not diagram_path.exists():
        raise FileNotFoundError(f"Missing weekly_macro_diagram.png in {week_dir}")

    img = slide_base()
    draw = ImageDraw.Draw(img)
    draw_top_meta(draw, scene.get("scene_title", ""), scene.get("visual_direction", ""))

    diagram = Image.open(diagram_path).convert("RGB")
    diagram.thumbnail((1160, 720), Image.LANCZOS)
    x, y = 50, 230
    rounded(draw, (x - 16, y - 16, x + diagram.width + 16, y + diagram.height + 16), 32, WHITE, outline=(231, 231, 226), width=2)
    diagram = apply_spotlight(diagram, scene.get("spotlight_target", "overview"))
    img.paste(diagram, (x, y))
    return img


def market_series_map(market: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    output = {}
    for item in market.get("series") or []:
        if isinstance(item, dict) and item.get("asset_key"):
            output[str(item["asset_key"])] = item
    return output


def clean_points(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    points = []
    for p in item.get("points") or []:
        if not isinstance(p, dict):
            continue
        try:
            value = float(p.get("value"))
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            points.append({"date": str(p.get("date") or ""), "value": value})
    return points


def fmt_value(value: float, unit: str = "") -> str:
    if abs(value) >= 1000:
        text = f"{value:,.1f}"
    elif abs(value) >= 100:
        text = f"{value:.2f}"
    else:
        text = f"{value:.3f}"
    return f"{text} {unit}".strip()


def draw_mini_chart(draw: ImageDraw.ImageDraw, item: Dict[str, Any], x: int, y: int, w: int, h: int) -> None:
    points = clean_points(item)
    font_label = find_font(22, bold=True)
    font_small = find_font(18)
    label = ASSET_LABELS.get(str(item.get("asset_key") or ""), str(item.get("asset") or "資產"))
    unit = str(item.get("unit") or "")

    rounded(draw, (x, y, x + w, y + h), 20, (255, 255, 255), outline=LIGHT_LINE, width=1)
    draw.text((x + 16, y + 12), label, fill=NAVY, font=font_label)

    if len(points) < 2:
        draw.text((x + 16, y + 56), "資料不足", fill=GRAY, font=font_small)
        return

    values = [p["value"] for p in points]
    first, last = values[0], values[-1]
    change = last - first
    pct = (change / first * 100) if first else 0
    sign = "+" if change > 0 else ""
    direction = "上行" if change > 0 else "下行" if change < 0 else "持平"
    draw.text((x + 16, y + 44), fmt_value(last, unit), fill=DARK, font=font_label)
    draw.text((x + 16, y + 74), f"{direction} {sign}{pct:.2f}%", fill=ORANGE if change > 0 else GRAY, font=font_small)

    cx1, cy1 = x + 18, y + 108
    cx2, cy2 = x + w - 18, y + h - 18
    min_v, max_v = min(values), max(values)
    span = max(max_v - min_v, 1e-9)
    coords = []
    for i, p in enumerate(points):
        px = cx1 + (i / (len(points) - 1)) * (cx2 - cx1)
        py = cy1 + (1 - ((p["value"] - min_v) / span)) * (cy2 - cy1)
        coords.append((px, py))
    if len(coords) >= 2:
        draw.line(coords, fill=NAVY, width=4, joint="curve")
        for px, py in coords:
            draw.ellipse((px - 4, py - 4, px + 4, py + 4), fill=WHITE, outline=NAVY, width=2)


def get_news_by_category(news: Dict[str, Any], category: str, limit: int = 2) -> List[Dict[str, Any]]:
    categories = news.get("news_categories")
    items: List[Dict[str, Any]] = []
    if isinstance(categories, dict):
        items = [x for x in (categories.get(category) or []) if isinstance(x, dict)]
    if not items:
        items = [x for x in (news.get("top_news") or []) if isinstance(x, dict)]
    return items[:limit]


def draw_news_card(draw: ImageDraw.ImageDraw, item: Dict[str, Any], x: int, y: int, w: int, h: int) -> None:
    font_source = find_font(17, bold=True)
    font_title = find_font(22, bold=True)
    font_why = find_font(18)
    rounded(draw, (x, y, x + w, y + h), 18, (255, 255, 255), outline=LIGHT_LINE, width=1)
    source = str(item.get("source") or "News")[:18]
    title = str(item.get("title") or "新聞佐證")
    why = str(item.get("why_it_matters") or item.get("theme") or "")
    draw.text((x + 14, y + 10), source, fill=ORANGE, font=font_source)
    ty = y + 38
    for line in wrap_text(title, font_title, w - 28)[:2]:
        draw.text((x + 14, ty), line, fill=NAVY, font=font_title)
        ty += 29
    ty += 3
    for line in wrap_text(why, font_why, w - 28)[:2]:
        draw.text((x + 14, ty), line, fill=GRAY, font=font_why)
        ty += 24


def draw_bullets(draw: ImageDraw.ImageDraw, bullets: List[str], x: int, y: int, w: int) -> int:
    font = find_font(24, bold=True)
    current_y = y
    for bullet in bullets[:5]:
        text = str(bullet).strip()
        if not text:
            continue
        draw.ellipse((x, current_y + 10, x + 12, current_y + 22), fill=ORANGE)
        for line in wrap_text(text, font, w - 30)[:2]:
            draw.text((x + 24, current_y), line, fill=DARK, font=font)
            current_y += 32
        current_y += 8
    return current_y


def draw_evidence_panel(base: Image.Image, scene: Dict[str, Any], market: Dict[str, Any], news: Dict[str, Any]) -> Image.Image:
    img = base.copy()
    draw = ImageDraw.Draw(img)
    panel_x, panel_y, panel_w, panel_h = 1240, 205, 620, 770

    shadow = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(shadow)
    sdraw.rounded_rectangle((panel_x + 8, panel_y + 12, panel_x + panel_w + 8, panel_y + panel_h + 12), radius=34, fill=(15, 42, 68, 55))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img.convert("RGBA"), shadow).convert("RGB")
    draw = ImageDraw.Draw(img)

    rounded(draw, (panel_x, panel_y, panel_x + panel_w, panel_y + panel_h), 34, WHITE, outline=(233, 232, 228), width=2)
    draw.rectangle((panel_x, panel_y, panel_x + 12, panel_y + panel_h), fill=ORANGE)

    title_font = find_font(34, bold=True)
    small_font = find_font(20, bold=True)
    draw.text((panel_x + 36, panel_y + 28), str(scene.get("on_screen_title") or scene.get("scene_title") or "證據面板"), fill=NAVY, font=title_font)
    draw.text((panel_x + 38, panel_y + 76), str(scene.get("evidence_panel_title") or "走勢與新聞驗證"), fill=GRAY, font=small_font)

    y = panel_y + 112
    y = draw_bullets(draw, scene.get("on_screen_bullets") or [], panel_x + 42, y, panel_w - 80)

    series = market_series_map(market)
    assets = scene.get("evidence_assets") or []
    chart_items = [series[a] for a in assets if a in series]
    if not chart_items:
        chart_items = list(series.values())[:1]

    y += 10
    chart_w = (panel_w - 88) // 2
    chart_h = 185
    for idx, item in enumerate(chart_items[:4]):
        col = idx % 2
        row = idx // 2
        cx = panel_x + 38 + col * (chart_w + 16)
        cy = y + row * (chart_h + 14)
        draw_mini_chart(draw, item, cx, cy, chart_w, chart_h)

    y = y + ((min(len(chart_items), 4) + 1) // 2) * (chart_h + 14) + 2

    news_items = get_news_by_category(news, str(scene.get("evidence_news_category") or "其他"), 2)
    news_h = 132
    for item in news_items[:2]:
        if y + news_h > panel_y + panel_h - 28:
            break
        draw_news_card(draw, item, panel_x + 38, y, panel_w - 76, news_h)
        y += news_h + 12

    draw.text((panel_x + 38, panel_y + panel_h - 32), "資料來源：Yahoo財經、Google News RSS", fill=GRAY, font=find_font(17))
    return img


def render_scene(week_dir: Path, scene: Dict[str, Any], market: Dict[str, Any], news: Dict[str, Any], out_path: Path) -> None:
    canvas = prepare_diagram_canvas(week_dir, scene)
    final_img = draw_evidence_panel(canvas, scene, market, news)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final_img.save(out_path)


def build_images(week_dir: Path, narration: Dict[str, Any], market: Dict[str, Any], news: Dict[str, Any]) -> List[Path]:
    scenes = narration.get("scenes") or []
    assets_dir = week_dir / "video_assets"
    paths: List[Path] = []
    for i, scene in enumerate(scenes, start=1):
        scene_id = scene.get("scene_id") or f"scene_{i:02d}"
        out_path = assets_dir / f"{scene_id}.png"
        render_scene(week_dir, scene, market, news, out_path)
        paths.append(out_path)
    return paths


def probe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_video(week_dir: Path, image_paths: List[Path], narration: Dict[str, Any]) -> Path:
    scenes = narration.get("scenes") or []
    audio_dir = week_dir / "audio"
    segment_dir = week_dir / "video_segments"
    final_dir = week_dir / "final"
    segment_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)
    segments: List[Path] = []

    for scene, image_path in zip(scenes, image_paths):
        scene_id = scene.get("scene_id")
        audio_path = audio_dir / f"{scene_id}.wav"
        if not audio_path.exists():
            raise FileNotFoundError(f"Missing scene audio: {audio_path}")
        duration = max(1.0, probe_duration(audio_path))
        segment_path = segment_dir / f"{scene_id}.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1",
                "-t", f"{duration:.3f}",
                "-i", str(image_path),
                "-i", str(audio_path),
                "-vf", "scale=1920:1080,format=yuv420p",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(segment_path),
            ],
            check=True,
        )
        segments.append(segment_path)

    concat_file = segment_dir / "concat_list.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in segments), encoding="utf-8")
    out_path = final_dir / "weekly_macro_video.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(out_path)], check=True)
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="")
    args = parser.parse_args()
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    narration = load_json(week_dir / "narration" / "weekly_narration.json")
    market = load_json(week_dir / "weekly_market_series.json")
    news = load_json(week_dir / "weekly_news_context.json")
    if not narration:
        raise FileNotFoundError(f"Missing narration JSON in {week_dir / 'narration'}")

    print("[INFO] Rendering V6 evidence-panel scene images")
    images = build_images(week_dir, narration, market, news)
    print("[INFO] Building video")
    out = build_video(week_dir, images, narration)
    print(f"[OK] Created {out}")


if __name__ == "__main__":
    main()
