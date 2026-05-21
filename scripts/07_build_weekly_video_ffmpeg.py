#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 07 V8.5
Build weekly macro video with scene-level visual guidance.

V8.5 direction:
- Replace single spotlight-only layout with:
  1) overview minimap (full diagram + highlighted region)
  2) large cropped focus panel (local zoom)
- Keep the existing scene-based workflow.
- One scene image corresponds to one scene audio clip.

Input:
- output/weekly/YYYY-MM-DD/narration/weekly_narration.json
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png
- output/weekly/YYYY-MM-DD/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_news_context.json
- output/weekly/YYYY-MM-DD/audio/scene_01.wav ... scene_06.wav

Output:
- output/weekly/YYYY-MM-DD/video_assets/scene_01_focus.png ... scene_06_focus.png
- output/weekly/YYYY-MM-DD/final/weekly_macro_video.mp4
"""

import json
import math
import subprocess
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

VIDEO_W = 1920
VIDEO_H = 1080
FPS = 30

# Layout
PAGE_BG = (246, 247, 249)
NAVY = (17, 43, 70)
NAVY_2 = (43, 58, 80)
MUTED = (91, 111, 135)
ORANGE = (245, 157, 36)
ORANGE_LIGHT = (255, 243, 222)
BORDER = (228, 218, 198)
CARD_BG = (255, 255, 255)
SOFT_GREY = (238, 241, 245)
GREEN = (27, 158, 119)
RED = (214, 82, 82)

LEFT_X = 48
LEFT_Y = 112
LEFT_W = 1180
LEFT_H = 820

RIGHT_X = 1260
RIGHT_Y = 112
RIGHT_W = 610
RIGHT_H = 820

HEADER_Y = 34

# ratios: x, y, w, h on the original diagram image.
FOCUS_PRESETS: Dict[str, Tuple[float, float, float, float]] = {
    "overview": (0.00, 0.00, 1.00, 1.00),
    "drivers": (0.02, 0.12, 0.37, 0.42),
    "yields": (0.30, 0.10, 0.34, 0.42),
    "dollar_fx": (0.53, 0.11, 0.35, 0.43),
    "gold_risk": (0.62, 0.12, 0.28, 0.43),
    "next_watch": (0.79, 0.04, 0.20, 0.72),
    "correction": (0.25, 0.43, 0.46, 0.38),
}

TARGET_LABELS = {
    "overview": "全圖總覽",
    "drivers": "驅動因子",
    "yields": "通膨 / 利率",
    "dollar_fx": "美元 / 亞洲貨幣",
    "gold_risk": "黃金 / 風險資產",
    "next_watch": "下週驗證",
    "correction": "修正因子",
}

ASSET_LABELS = {
    "US10Y": "美國10年期公債殖利率",
    "DXY": "美元指數",
    "Gold": "黃金",
    "WTI": "西德州原油",
    "Brent": "布蘭特原油",
    "USDJPY": "美元 / 日圓",
    "USDTWD": "美元 / 台幣",
    "USDKRW": "美元 / 韓元",
}

ASSET_UNITS = {
    "US10Y": "%",
    "DXY": "",
    "Gold": "USD/oz",
    "WTI": "USD/bbl",
    "Brent": "USD/bbl",
    "USDJPY": "JPY",
    "USDTWD": "TWD",
    "USDKRW": "KRW",
}


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run(cmd: List[str]) -> None:
    print("[CMD]", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def audio_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def find_font() -> str:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Regular.otf",
        "/System/Library/Fonts/PingFang.ttc",
        "C:/Windows/Fonts/msjh.ttc",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return ""


FONT_PATH = find_font()


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    if FONT_PATH:
        try:
            return ImageFont.truetype(FONT_PATH, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt: ImageFont.ImageFont) -> Tuple[int, int]:
    if not text:
        return (0, 0)
    box = draw.textbbox((0, 0), text, font=fnt)
    return (box[2] - box[0], box[3] - box[1])


def draw_round_rect(
    draw: ImageDraw.ImageDraw,
    box: Tuple[int, int, int, int],
    radius: int,
    fill: Tuple[int, int, int],
    outline: Optional[Tuple[int, int, int]] = None,
    width: int = 1,
) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def wrap_text(text: str, max_chars: int) -> List[str]:
    text = str(text or "").strip()
    if not text:
        return []
    lines = []
    for raw in text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        while len(raw) > max_chars:
            lines.append(raw[:max_chars])
            raw = raw[max_chars:]
        if raw:
            lines.append(raw)
    return lines


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    xy: Tuple[int, int],
    fnt: ImageFont.ImageFont,
    fill: Tuple[int, int, int],
    max_chars: int,
    line_gap: int = 8,
    max_lines: Optional[int] = None,
) -> int:
    x, y = xy
    lines = wrap_text(text, max_chars)
    if max_lines is not None:
        lines = lines[:max_lines]
    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        y += text_size(draw, line, fnt)[1] + line_gap
    return y


def fit_image(img: Image.Image, box_w: int, box_h: int, fill: bool = False) -> Image.Image:
    img = img.convert("RGB")
    ratio = max(box_w / img.width, box_h / img.height) if fill else min(box_w / img.width, box_h / img.height)
    new_size = (max(1, int(img.width * ratio)), max(1, int(img.height * ratio)))
    return img.resize(new_size, Image.LANCZOS)


def paste_center(base: Image.Image, img: Image.Image, box: Tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    x = x1 + (x2 - x1 - img.width) // 2
    y = y1 + (y2 - y1 - img.height) // 2
    base.paste(img, (x, y))


def ratio_box_to_pixels(img: Image.Image, target: str, pad: float = 0.0) -> Tuple[int, int, int, int]:
    x, y, w, h = FOCUS_PRESETS.get(target, FOCUS_PRESETS["overview"])
    x1 = max(0.0, x - pad)
    y1 = max(0.0, y - pad)
    x2 = min(1.0, x + w + pad)
    y2 = min(1.0, y + h + pad)
    return (
        int(img.width * x1),
        int(img.height * y1),
        int(img.width * x2),
        int(img.height * y2),
    )


def crop_focus_image(original: Image.Image, target: str) -> Image.Image:
    if target == "overview":
        return original.copy()
    crop_box = ratio_box_to_pixels(original, target, pad=0.03)
    return original.crop(crop_box)


def render_minimap(
    base: Image.Image,
    original: Image.Image,
    target: str,
    box: Tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    draw = ImageDraw.Draw(base)

    # panel bg
    draw_round_rect(draw, box, 24, (252, 252, 253), outline=(232, 235, 239), width=1)

    inner = (x1 + 16, y1 + 16, x2 - 16, y2 - 16)
    preview = fit_image(original, inner[2] - inner[0], inner[3] - inner[1], fill=False)

    px = inner[0] + ((inner[2] - inner[0]) - preview.width) // 2
    py = inner[1] + ((inner[3] - inner[1]) - preview.height) // 2
    base.paste(preview, (px, py))

    if target != "overview":
        rx, ry, rw, rh = FOCUS_PRESETS.get(target, FOCUS_PRESETS["overview"])
        scale_x = preview.width / original.width
        scale_y = preview.height / original.height
        hx1 = px + int(original.width * rx * scale_x)
        hy1 = py + int(original.height * ry * scale_y)
        hx2 = px + int(original.width * (rx + rw) * scale_x)
        hy2 = py + int(original.height * (ry + rh) * scale_y)

        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        for i, alpha in enumerate([42, 28]):
            grow = 6 + i * 8
            od.rounded_rectangle(
                (hx1 - grow, hy1 - grow, hx2 + grow, hy2 + grow),
                radius=18 + grow // 2,
                outline=(*ORANGE, alpha),
                width=6,
            )
        od.rounded_rectangle((hx1, hy1, hx2, hy2), radius=16, outline=(*ORANGE, 240), width=4)
        base.alpha_composite(overlay)


def render_focus_panel(
    base: Image.Image,
    original: Image.Image,
    target: str,
    box: Tuple[int, int, int, int],
    scene_title: str,
) -> None:
    x1, y1, x2, y2 = box
    draw = ImageDraw.Draw(base)

    draw_round_rect(draw, box, 28, CARD_BG, outline=(232, 235, 239), width=1)

    crop = crop_focus_image(original, target)
    inner = (x1 + 18, y1 + 18, x2 - 18, y2 - 18)
    focus_img = fit_image(crop, inner[2] - inner[0], inner[3] - inner[1], fill=False)
    paste_center(base, focus_img, inner)

    label = TARGET_LABELS.get(target, target)
    chip_text = f"目前焦點｜{label}"
    chip_font = font(23, True)
    tw, th = text_size(draw, chip_text, chip_font)
    chip = (x1 + 26, y2 - 60, x1 + 62 + tw, y2 - 18)
    draw_round_rect(draw, chip, 20, ORANGE_LIGHT, outline=(245, 196, 118), width=1)
    draw.text((chip[0] + 18, chip[1] + 8), chip_text, font=chip_font, fill=(132, 72, 16))

    if scene_title:
        title_font = font(20, True)
        st = scene_title[:26]
        sw, _ = text_size(draw, st, title_font)
        tag = (x2 - 26 - sw - 26, y1 + 18, x2 - 26, y1 + 50)
        draw_round_rect(draw, tag, 16, (245, 247, 250), outline=(223, 228, 234), width=1)
        draw.text((tag[0] + 13, tag[1] + 6), st, font=title_font, fill=MUTED)


def render_diagram_panel(base: Image.Image, diagram_path: Path, target: str, title: str) -> None:
    draw = ImageDraw.Draw(base)
    panel = (LEFT_X, LEFT_Y, LEFT_X + LEFT_W, LEFT_Y + LEFT_H)
    draw_round_rect(draw, panel, radius=32, fill=CARD_BG, outline=BORDER, width=2)

    draw.rounded_rectangle((LEFT_X + 32, LEFT_Y + 28, LEFT_X + 42, LEFT_Y + 66), radius=5, fill=ORANGE)
    draw.text((LEFT_X + 56, LEFT_Y + 25), "總經傳導圖解", font=font(34, True), fill=NAVY)

    if not diagram_path.exists():
        draw.text((LEFT_X + 56, LEFT_Y + 150), "找不到 weekly_macro_diagram.png", font=font(28), fill=RED)
        return

    original = Image.open(diagram_path).convert("RGB")
    if target not in FOCUS_PRESETS:
        target = "overview"

    # V8.5 layout: minimap + cropped focus panel
    minimap_box = (LEFT_X + 34, LEFT_Y + 88, LEFT_X + LEFT_W - 34, LEFT_Y + 306)
    focus_box = (LEFT_X + 34, LEFT_Y + 326, LEFT_X + LEFT_W - 34, LEFT_Y + LEFT_H - 34)

    rgba = base.convert("RGBA")
    render_minimap(rgba, original, target, minimap_box)
    base.paste(rgba.convert("RGB"))

    render_focus_panel(base, original, target, focus_box, title)


def normalize_asset_series(market: Dict[str, Any]) -> List[Dict[str, Any]]:
    series = market.get("series")
    if isinstance(series, list):
        return series
    return []


def get_asset_item(market: Dict[str, Any], asset_key: str) -> Optional[Dict[str, Any]]:
    for item in normalize_asset_series(market):
        key = str(item.get("asset_key") or item.get("key") or "").strip()
        if key == asset_key:
            return item
    return None


def get_points(item: Dict[str, Any]) -> List[float]:
    candidates = [
        item.get("values"),
        item.get("series"),
        item.get("data"),
        item.get("points"),
    ]

    for arr in candidates:
        if isinstance(arr, list):
            vals = []
            for x in arr:
                if isinstance(x, dict):
                    v = x.get("value", x.get("close", x.get("price")))
                else:
                    v = x
                try:
                    if v is not None:
                        vals.append(float(v))
                except Exception:
                    pass
            if vals:
                return vals

    vals = []
    for key in ("previous_value", "prev_value", "prev", "last", "value"):
        try:
            v = item.get(key)
            if v is not None:
                vals.append(float(v))
        except Exception:
            pass
    return vals[-4:] if vals else []


def fmt_num(v: Any, decimals: int = 3) -> str:
    try:
        f = float(v)
    except Exception:
        return "-"
    if abs(f) >= 1000:
        return f"{f:,.1f}"
    if abs(f) >= 100:
        return f"{f:,.2f}"
    return f"{f:,.3f}".rstrip("0").rstrip(".")


def asset_value(item: Optional[Dict[str, Any]]) -> str:
    if not item:
        return "-"
    for key in ("value", "last", "latest", "close", "price"):
        if item.get(key) is not None:
            return fmt_num(item.get(key))
    pts = get_points(item)
    return fmt_num(pts[-1]) if pts else "-"


def asset_change_text(item: Optional[Dict[str, Any]]) -> str:
    if not item:
        return ""
    ch = item.get("change", item.get("delta"))
    pct = item.get("change_pct", item.get("pct", item.get("percent")))
    parts = []
    if ch is not None:
        try:
            sign = "+" if float(ch) >= 0 else ""
            parts.append(f"{sign}{fmt_num(ch)}")
        except Exception:
            pass
    if pct is not None:
        try:
            sign = "+" if float(pct) >= 0 else ""
            parts.append(f"{sign}{float(pct):.2f}%")
        except Exception:
            pass
    return " | ".join(parts)


def draw_sparkline(draw: ImageDraw.ImageDraw, points: List[float], box: Tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    if len(points) < 2:
        draw.line((x1, (y1 + y2) // 2, x2, (y1 + y2) // 2), fill=NAVY_2, width=3)
        return
    lo, hi = min(points), max(points)
    if math.isclose(lo, hi):
        hi = lo + 1
    coords = []
    for idx, v in enumerate(points):
        x = x1 + int(idx * (x2 - x1) / (len(points) - 1))
        y = y2 - int((v - lo) * (y2 - y1) / (hi - lo))
        coords.append((x, y))
    draw.line(coords, fill=NAVY_2, width=4, joint="curve")
    for x, y in coords:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=CARD_BG, outline=NAVY_2, width=3)


def render_asset_card(
    draw: ImageDraw.ImageDraw,
    market: Dict[str, Any],
    asset_key: str,
    box: Tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    item = get_asset_item(market, asset_key)
    draw_round_rect(draw, box, 24, CARD_BG, outline=(232, 225, 215), width=1)

    label = ASSET_LABELS.get(asset_key, asset_key)
    unit = ASSET_UNITS.get(asset_key, "")
    value = asset_value(item)
    change = asset_change_text(item)
    pts = get_points(item) or [1, 1.05, 1.02, 1.1]

    title_f = font(22, True)
    value_f = font(34, True)
    small_f = font(17)

    chip_w = min(210, text_size(draw, label, title_f)[0] + 44)
    chip = (x1 + 18, y1 + 18, x1 + 18 + chip_w, y1 + 58)
    draw_round_rect(draw, chip, 20, ORANGE_LIGHT, outline=(244, 204, 139), width=1)
    draw.ellipse((chip[0] + 14, chip[1] + 15, chip[0] + 24, chip[1] + 25), fill=ORANGE)
    draw.text((chip[0] + 32, chip[1] + 9), label[:12], font=title_f, fill=(143, 77, 17))

    draw.text((x1 + 22, y1 + 78), f"{value} {unit}".strip(), font=value_f, fill=NAVY)
    if change:
        draw.text((x1 + 24, y1 + 124), change, font=small_f, fill=MUTED)

    draw_sparkline(draw, pts[-6:], (x1 + 28, y1 + 160, x2 - 28, y2 - 28))


def extract_news_items(news: Dict[str, Any], category: str, limit: int = 2) -> List[Dict[str, Any]]:
    candidates = []
    for key in ("categories", "news_by_category", "classified", "by_category"):
        obj = news.get(key)
        if isinstance(obj, dict) and isinstance(obj.get(category), list):
            candidates = obj.get(category) or []
            break

    if not candidates:
        for key in ("items", "news", "articles"):
            arr = news.get(key)
            if isinstance(arr, list):
                candidates = [x for x in arr if str(x.get("category") or x.get("macro_category") or "").strip() == category]
                if candidates:
                    break

    return [x for x in candidates if isinstance(x, dict)][:limit]


def render_news_card(
    draw: ImageDraw.ImageDraw,
    item: Dict[str, Any],
    box: Tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box
    draw_round_rect(draw, box, 22, CARD_BG, outline=(232, 225, 215), width=1)
    source = str(item.get("source") or item.get("publisher") or item.get("site") or "").strip()
    title = str(item.get("title") or item.get("headline") or "").strip()
    summary = str(item.get("summary") or item.get("description") or item.get("reason") or "").strip()

    small = font(16, True)
    title_f = font(21, True)
    body_f = font(17)

    if source:
        draw.text((x1 + 18, y1 + 14), source[:28], font=small, fill=(147, 92, 16))
    y = y1 + 44
    y = draw_wrapped_text(draw, title, (x1 + 18, y), title_f, NAVY, max_chars=17, line_gap=6, max_lines=3)
    if summary:
        y += 6
        draw_wrapped_text(draw, summary, (x1 + 18, y), body_f, MUTED, max_chars=18, line_gap=5, max_lines=2)


def render_evidence_panel(
    base: Image.Image,
    scene: Dict[str, Any],
    market: Dict[str, Any],
    news: Dict[str, Any],
) -> None:
    draw = ImageDraw.Draw(base)
    panel = (RIGHT_X, RIGHT_Y, RIGHT_X + RIGHT_W, RIGHT_Y + RIGHT_H)
    draw_round_rect(draw, panel, radius=32, fill=(250, 251, 253), outline=(230, 232, 236), width=2)

    title = str(scene.get("evidence_panel_title") or "證據面板")
    draw.rounded_rectangle((RIGHT_X + 28, RIGHT_Y + 28, RIGHT_X + 38, RIGHT_Y + 64), radius=5, fill=ORANGE)
    draw.text((RIGHT_X + 52, RIGHT_Y + 24), title[:18], font=font(31, True), fill=NAVY)

    assets = scene.get("evidence_assets") or []
    if not isinstance(assets, list):
        assets = []
    assets = [str(x) for x in assets[:4]]

    y = RIGHT_Y + 88
    card_gap = 18

    if len(assets) == 1:
        render_asset_card(draw, market, assets[0], (RIGHT_X + 28, y, RIGHT_X + RIGHT_W - 28, y + 270))
        y += 290
    elif len(assets) == 2:
        card_w = (RIGHT_W - 28 * 2 - card_gap) // 2
        render_asset_card(draw, market, assets[0], (RIGHT_X + 28, y, RIGHT_X + 28 + card_w, y + 230))
        render_asset_card(draw, market, assets[1], (RIGHT_X + 28 + card_w + card_gap, y, RIGHT_X + RIGHT_W - 28, y + 230))
        y += 250
    else:
        card_w = (RIGHT_W - 28 * 2 - card_gap) // 2
        card_h = 205
        for idx, key in enumerate(assets[:4]):
            col = idx % 2
            row = idx // 2
            x1 = RIGHT_X + 28 + col * (card_w + card_gap)
            y1 = y + row * (card_h + card_gap)
            render_asset_card(draw, market, key, (x1, y1, x1 + card_w, y1 + card_h))
        y += 2 * card_h + card_gap + 18

    bullets = scene.get("on_screen_bullets") or []
    if isinstance(bullets, list) and bullets:
        bullet_box = (RIGHT_X + 28, y, RIGHT_X + RIGHT_W - 28, y + 130)
        draw_round_rect(draw, bullet_box, 22, (255, 253, 248), outline=(240, 224, 197), width=1)
        by = y + 18
        for b in bullets[:3]:
            draw.ellipse((RIGHT_X + 48, by + 8, RIGHT_X + 58, by + 18), fill=ORANGE)
            draw_wrapped_text(draw, str(b), (RIGHT_X + 70, by), font(19, True), NAVY_2, max_chars=23, line_gap=5, max_lines=1)
            by += 34
        y += 150

    category = str(scene.get("evidence_news_category") or "其他")
    news_items = extract_news_items(news, category, limit=2)
    if news_items:
        draw.text((RIGHT_X + 30, y), f"新聞佐證｜{category}", font=font(24, True), fill=NAVY)
        y += 40
        news_h = min(150, RIGHT_Y + RIGHT_H - 36 - y)
        if news_h > 90:
            if len(news_items) == 1:
                render_news_card(draw, news_items[0], (RIGHT_X + 28, y, RIGHT_X + RIGHT_W - 28, y + news_h))
            else:
                card_w = (RIGHT_W - 28 * 2 - card_gap) // 2
                render_news_card(draw, news_items[0], (RIGHT_X + 28, y, RIGHT_X + 28 + card_w, y + news_h))
                render_news_card(draw, news_items[1], (RIGHT_X + 28 + card_w + card_gap, y, RIGHT_X + RIGHT_W - 28, y + news_h))
    else:
        draw_round_rect(draw, (RIGHT_X + 28, y, RIGHT_X + RIGHT_W - 28, y + 88), 22, CARD_BG, outline=(232, 225, 215), width=1)
        draw.text((RIGHT_X + 48, y + 28), f"{category}｜本週暫無明確新聞佐證", font=font(20), fill=MUTED)


def render_scene_image(
    week_dir: Path,
    scene: Dict[str, Any],
    market: Dict[str, Any],
    news: Dict[str, Any],
    out_path: Path,
) -> None:
    rgba = Image.new("RGBA", (VIDEO_W, VIDEO_H), (*PAGE_BG, 255))

    glow = Image.new("RGBA", (VIDEO_W, VIDEO_H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse((-300, -360, 900, 560), fill=(255, 214, 132, 85))
    glow = glow.filter(ImageFilter.GaussianBlur(70))
    rgba = Image.alpha_composite(rgba, glow)

    base = rgba.convert("RGB")
    draw = ImageDraw.Draw(base)

    scene_title = str(scene.get("scene_title") or "")
    on_title = str(scene.get("on_screen_title") or scene_title or "本週總經週報")
    draw.text((LEFT_X, HEADER_Y), "WEEKLY MACRO VIDEO", font=font(20, True), fill=(158, 95, 13))
    draw.text((LEFT_X, HEADER_Y + 26), on_title[:32], font=font(40, True), fill=NAVY)

    scene_id = str(scene.get("scene_id") or "")
    draw.text((RIGHT_X, HEADER_Y + 42), scene_id.upper(), font=font(22, True), fill=MUTED)

    diagram_path = week_dir / "weekly_macro_diagram.png"
    render_diagram_panel(base, diagram_path, str(scene.get("spotlight_target") or "overview"), scene_title)
    render_evidence_panel(base, scene, market, news)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path, "PNG")
    print(f"[OK] Rendered scene image: {out_path}")


def build_scene_video(image_path: Path, audio_path: Path, out_path: Path) -> None:
    duration = audio_duration_seconds(audio_path)
    ensure_dir(out_path.parent)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(image_path),
        "-i", str(audio_path),
        "-t", f"{duration:.3f}",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    run(cmd)


def concat_videos(paths: List[Path], out_path: Path) -> None:
    list_path = out_path.parent / "video_concat_list.txt"
    list_path.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in paths),
        encoding="utf-8",
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(out_path),
    ]
    run(cmd)


def main() -> None:
    week_dir = find_latest_week_dir()
    narration_path = week_dir / "narration" / "weekly_narration.json"
    narration = load_json(narration_path, {})
    scenes = narration.get("scenes") or []
    if not scenes:
        raise RuntimeError(f"No scenes found in {narration_path}")

    market = load_json(week_dir / "weekly_market_series.json", {})
    news = load_json(week_dir / "weekly_news_context.json", {})

    video_assets_dir = week_dir / "video_assets"
    scene_video_dir = video_assets_dir / "scene_videos"
    final_dir = week_dir / "final"
    ensure_dir(video_assets_dir)
    ensure_dir(scene_video_dir)
    ensure_dir(final_dir)

    print("[INFO] Rendering V8.5 minimap + focus scene images")
    scene_video_paths: List[Path] = []

    for scene in scenes:
        scene_id = str(scene.get("scene_id") or "").strip()
        if not scene_id:
            continue

        audio_path = week_dir / "audio" / f"{scene_id}.wav"
        if not audio_path.exists():
            print(f"[WARN] Missing scene audio, skip {scene_id}: {audio_path}")
            continue

        image_path = video_assets_dir / f"{scene_id}_focus.png"
        video_path = scene_video_dir / f"{scene_id}.mp4"

        render_scene_image(week_dir, scene, market, news, image_path)
        build_scene_video(image_path, audio_path, video_path)
        scene_video_paths.append(video_path)

    if not scene_video_paths:
        raise RuntimeError("No scene videos generated.")

    final_path = final_dir / "weekly_macro_video.mp4"
    print("[INFO] Building final weekly video")
    concat_videos(scene_video_paths, final_path)
    print(f"[OK] Created {final_path}")


if __name__ == "__main__":
    main()
