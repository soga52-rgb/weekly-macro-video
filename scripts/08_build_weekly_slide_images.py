#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 08 (V3 Notebook Single Visual)

Design goals from latest discussion:
- Scene 01: full-page weekly macro diagram
- Scene 02~05: NO minimap, NO frame-heavy layout, NO observation bullets
- Scene 02~05: only show the key visual(s) needed for that scene
- bottom area shows asset mini-cards + related news links
- Scene 06: full-page next-week watch page with ultra-minimal icons/text
- all panels use soft paper blocks without visible borders
- data cards emphasize the number; units stay very small

Replace:
- scripts/08_build_weekly_slide_images.py
"""

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

CANVAS_W = 1920
CANVAS_H = 1080
BG = (251, 250, 247)
GRID = (238, 234, 227)
TEXT = (33, 41, 56)
SUBTEXT = (89, 102, 123)
MUTED = (138, 149, 165)
ORANGE = (239, 138, 37)
NAVY = (42, 58, 81)
RED = (222, 86, 64)
WHITE = (255, 255, 255)

MARGIN_X = 72
MARGIN_TOP = 58
TITLE_Y = 48

DIAGRAM_PRESETS: Dict[str, List[Tuple[float, float, float, float]]] = {
    # only the essential visual pieces, not whole panels
    "scene_02": [
        (0.02, 0.48, 0.16, 0.80),  # 再通膨預期
        (0.16, 0.48, 0.30, 0.80),  # 油價高檔
    ],
    "scene_03": [
        (0.30, 0.48, 0.44, 0.80),  # 通膨黏性
        (0.44, 0.48, 0.59, 0.80),  # 長債利率飆升
    ],
    "scene_04": [
        (0.58, 0.48, 0.71, 0.80),  # 美元偏強
        (0.72, 0.48, 0.85, 0.80),  # 亞幣承壓
    ],
    "scene_05": [
        (0.84, 0.48, 0.96, 0.80),  # 黃金壓力
        (0.27, 0.72, 0.54, 0.96),  # 修正因子
        (0.55, 0.76, 0.73, 0.90),  # 美元短暫走弱
    ],
}

SCENE_CONFIG = {
    "scene_02": {
        "title": "起點：能源價格推升通膨預期",
        "assets": ["WTI", "Brent"],
        "news_category": "通膨預期",
        "news_keywords": ["油價", "原油", "能源", "通膨", "再通膨", "物價"],
        "news_heading": "通膨預期",
    },
    "scene_03": {
        "title": "利率：長債殖利率重新定價",
        "assets": ["US10Y"],
        "news_category": "利率",
        "news_keywords": ["殖利率", "美債", "利率", "Fed", "升息", "降息"],
        "news_heading": "利率",
    },
    "scene_04": {
        "title": "美元與亞洲貨幣：利差壓力外溢",
        "assets": ["DXY", "USDJPY", "USDTWD", "USDKRW"],
        "news_category": "貨幣",
        "news_keywords": ["美元", "亞幣", "日圓", "台幣", "韓元", "匯率", "央行干預"],
        "news_heading": "貨幣",
    },
    "scene_05": {
        "title": "黃金與修正因子：高利率下的避險拉鋸",
        "assets": ["Gold", "DXY"],
        "news_category": "其他",
        "news_keywords": ["黃金", "避險", "房市", "成長", "修正", "衰退", "美元"],
        "news_heading": "黃金／修正因子",
    },
}

ASSET_LABELS = {
    "US10Y": "美債10Y",
    "DXY": "美元指數",
    "Gold": "黃金",
    "WTI": "WTI",
    "Brent": "Brent",
    "USDJPY": "美元／日圓",
    "USDTWD": "美元／台幣",
    "USDKRW": "美元／韓元",
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


def find_json(week_dir: Path, filename: str) -> Dict[str, Any]:
    for path in [week_dir / filename, week_dir / "data" / filename, week_dir / "final" / filename]:
        if path.exists():
            return load_json(path, {})
    return {}


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def find_font_path(bold: bool = False) -> str:
    candidates = []
    if bold:
        candidates.extend([
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/msjhbd.ttc",
        ])
    candidates.extend([
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/msjh.ttc",
        "/System/Library/Fonts/PingFang.ttc",
    ])
    for fp in candidates:
        if Path(fp).exists():
            return fp
    return ""


FONT_REG_PATH = find_font_path(False)
FONT_BOLD_PATH = find_font_path(True)


def font(size: int, bold: bool = False):
    fp = FONT_BOLD_PATH if bold and FONT_BOLD_PATH else FONT_REG_PATH
    if fp:
        try:
            return ImageFont.truetype(fp, size=size)
        except Exception:
            pass
    return ImageFont.load_default()


FONT_H1 = font(44, True)
FONT_H2 = font(28, True)
FONT_H3 = font(22, True)
FONT_BODY = font(21, False)
FONT_SMALL = font(18, False)
FONT_XS = font(14, False)
FONT_LINK = font(16, False)
FONT_NUM_BIG = font(56, True)
FONT_NUM_MID = font(48, True)
FONT_UNIT = font(13, False)
FONT_WATCH_BIG = font(34, True)
FONT_WATCH_SMALL = font(22, False)
FONT_SYMBOL = font(54, True)


def make_canvas() -> Image.Image:
    img = Image.new("RGB", (CANVAS_W, CANVAS_H), BG)
    draw = ImageDraw.Draw(img)
    step = 28
    for x in range(0, CANVAS_W, step):
        draw.line((x, 0, x, CANVAS_H), fill=GRID, width=1)
    for y in range(0, CANVAS_H, step):
        draw.line((0, y, CANVAS_W, y), fill=GRID, width=1)
    return img


def text_size(draw: ImageDraw.ImageDraw, text: str, fnt) -> Tuple[int, int]:
    if not text:
        return 0, 0
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> List[str]:
    text = str(text or "").strip()
    if not text:
        return []
    lines: List[str] = []
    current = ""
    for ch in text:
        trial = current + ch
        w, _ = text_size(draw, trial, fnt)
        if w <= max_width or not current:
            current = trial
        else:
            lines.append(current)
            current = ch
    if current:
        lines.append(current)
    return lines


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, fnt, fill, max_width: int, line_gap: int = 7, max_lines: Optional[int] = None) -> int:
    lines = wrap_text(draw, text, fnt, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=fnt, fill=fill)
        _, h = text_size(draw, line, fnt)
        cur_y += h + line_gap
    return cur_y


def draw_soft_paper_bg(base: Image.Image, box: Tuple[int, int, int, int], alpha: int = 168, radius: int = 28) -> None:
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(0.4))
    base.alpha_composite(overlay)


def fit_contain(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    tw, th = target_size
    iw, ih = image.size
    ratio = min(tw / iw, th / ih)
    nw, nh = max(1, int(iw * ratio)), max(1, int(ih * ratio))
    img = image.resize((nw, nh), Image.LANCZOS)
    bg = Image.new("RGBA", target_size, (0, 0, 0, 0))
    bg.alpha_composite(img.convert("RGBA"), ((tw - nw) // 2, (th - nh) // 2))
    return bg


def normalize_asset_series(market: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result = {}
    series = market.get("series") if isinstance(market, dict) else []
    if not isinstance(series, list):
        return result
    for item in series:
        if not isinstance(item, dict):
            continue
        key = str(item.get("asset_key") or item.get("key") or "").strip()
        if key:
            result[key] = item
    return result


def get_points(item: Dict[str, Any]) -> List[float]:
    candidates = [item.get("points"), item.get("values"), item.get("series"), item.get("data")]
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
    return []


def latest_and_prev(item: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    pts = get_points(item)
    if not pts:
        return None, None
    return pts[-1], (pts[-2] if len(pts) >= 2 else None)


def format_value(value: Optional[float], key: str) -> str:
    if value is None:
        return "--"
    if key in ("USDTWD", "USDJPY"):
        return f"{value:,.2f}"
    if key == "USDKRW":
        return f"{value:,.1f}"
    if key in ("US10Y", "DXY"):
        return f"{value:.3f}"
    if key in ("WTI", "Brent", "Gold"):
        return f"{value:,.1f}"
    return f"{value:,.2f}"


def format_delta(latest: Optional[float], prev: Optional[float]) -> str:
    if latest is None or prev is None:
        return ""
    diff = latest - prev
    sign = "+" if diff > 0 else ""
    return f"{sign}{diff:.2f}"


def draw_sparkline(draw: ImageDraw.ImageDraw, points: List[float], box: Tuple[int, int, int, int]) -> None:
    x1, y1, x2, y2 = box
    if len(points) < 2:
        draw.line((x1, (y1 + y2) // 2, x2, (y1 + y2) // 2), fill=NAVY, width=3)
        return
    lo, hi = min(points), max(points)
    if math.isclose(lo, hi):
        hi = lo + 1
    coords = []
    for i, v in enumerate(points):
        x = x1 + int(i * (x2 - x1) / (len(points) - 1))
        y = y2 - int((v - lo) * (y2 - y1) / (hi - lo))
        coords.append((x, y))
    draw.line(coords, fill=NAVY, width=3)
    for x, y in coords:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=ORANGE)


def flatten_news(news: Dict[str, Any]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for key in ("top_news", "items", "news", "articles"):
        arr = news.get(key)
        if isinstance(arr, list):
            result.extend([x for x in arr if isinstance(x, dict)])
    for key in ("categories", "news_by_category", "classified", "by_category"):
        obj = news.get(key)
        if isinstance(obj, dict):
            for cat, arr in obj.items():
                if isinstance(arr, list):
                    for item in arr:
                        if isinstance(item, dict):
                            item2 = dict(item)
                            item2.setdefault("category", cat)
                            result.append(item2)
    seen = set()
    out = []
    for item in result:
        title = str(item.get("title") or item.get("headline") or "").strip()
        if not title:
            continue
        key = title[:80]
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def search_news(news: Dict[str, Any], category: str, keywords: List[str], limit: int = 2) -> List[Dict[str, Any]]:
    items = flatten_news(news)
    ranked = []
    for item in items:
        blob = " ".join([
            str(item.get("title") or item.get("headline") or ""),
            str(item.get("summary") or item.get("description") or item.get("why_it_matters") or item.get("reason") or ""),
            str(item.get("theme") or item.get("category") or item.get("macro_category") or ""),
        ])
        cat_text = str(item.get("category") or item.get("macro_category") or item.get("theme") or "")
        score = (4 if category and category in cat_text else 0) + sum(1 for kw in keywords if kw.lower() in blob.lower())
        ranked.append((score, item))
    ranked.sort(key=lambda x: x[0], reverse=True)
    selected = [item for score, item in ranked if score > 0][:limit]
    return selected if selected else items[:limit]


def draw_main_title(draw: ImageDraw.ImageDraw, title: str) -> None:
    draw.text((MARGIN_X, TITLE_Y), title, font=FONT_H1, fill=TEXT)


def find_diagram(week_dir: Path) -> Path:
    for p in [week_dir / "weekly_macro_diagram.png", week_dir / "final" / "weekly_macro_diagram.png", week_dir / "data" / "weekly_macro_diagram.png"]:
        if p.exists():
            return p
    raise FileNotFoundError("Cannot find weekly_macro_diagram.png")


def crop_box(img: Image.Image, preset: Tuple[float, float, float, float]) -> Image.Image:
    w, h = img.size
    x1, y1, x2, y2 = preset
    return img.crop((int(w * x1), int(h * y1), int(w * x2), int(h * y2)))


def trim_transparent(im: Image.Image) -> Image.Image:
    if im.mode != "RGBA":
        im = im.convert("RGBA")
    bg = Image.new("RGBA", im.size, (0, 0, 0, 0))
    diff = ImageChops.difference(im, bg)
    bbox = diff.getbbox()
    return im.crop(bbox) if bbox else im


# Pillow lazy import workaround for ImageChops
from PIL import ImageChops


def compose_key_visual(diagram: Image.Image, scene_id: str) -> Image.Image:
    parts = [crop_box(diagram, p).convert("RGBA") for p in DIAGRAM_PRESETS[scene_id]]
    processed = []
    for p in parts:
        p = trim_transparent(p)
        processed.append(p)

    if scene_id in ("scene_02", "scene_03", "scene_04"):
        gap = 48
        heights = [p.size[1] for p in processed]
        widths = [p.size[0] for p in processed]
        canvas = Image.new("RGBA", (sum(widths) + gap * (len(processed) - 1), max(heights)), (0, 0, 0, 0))
        x = 0
        for p in processed:
            y = (canvas.size[1] - p.size[1]) // 2
            canvas.alpha_composite(p, (x, y))
            x += p.size[0] + gap
        return canvas

    # scene_05: top row + bottom row
    if len(processed) >= 3:
        top_gap = 40
        top_w = processed[0].size[0] + processed[1].size[0] + top_gap
        top_h = max(processed[0].size[1], processed[1].size[1])
        bottom_w = processed[2].size[0]
        bottom_h = processed[2].size[1]
        canvas_w = max(top_w, bottom_w)
        canvas_h = top_h + 28 + bottom_h
        canvas = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        x0 = (canvas_w - top_w) // 2
        canvas.alpha_composite(processed[0], (x0, (top_h - processed[0].size[1]) // 2))
        canvas.alpha_composite(processed[1], (x0 + processed[0].size[0] + top_gap, (top_h - processed[1].size[1]) // 2))
        canvas.alpha_composite(processed[2], ((canvas_w - processed[2].size[0]) // 2, top_h + 28))
        return canvas

    return processed[0]


def draw_asset_strip(base: Image.Image, series_map: Dict[str, Any], asset_keys: List[str], box: Tuple[int, int, int, int]) -> None:
    draw_soft_paper_bg(base, box, 154)
    draw = ImageDraw.Draw(base)
    x1, y1, x2, y2 = box
    gap = 18
    count = max(1, len(asset_keys))
    cols = count
    card_w = (x2 - x1 - 32 - (cols - 1) * gap) // cols
    card_h = y2 - y1 - 24

    for idx, key in enumerate(asset_keys):
        cx = x1 + 16 + idx * (card_w + gap)
        cy = y1 + 12
        item = series_map.get(key, {})
        latest, prev = latest_and_prev(item)
        value_str = format_value(latest, key)
        delta_str = format_delta(latest, prev)
        unit = str(item.get("unit") or ASSET_UNITS.get(key, "")).strip()

        label_y = cy + 6
        draw.text((cx + 14, label_y), ASSET_LABELS.get(key, key), font=FONT_SMALL, fill=SUBTEXT)

        num_font = FONT_NUM_BIG if count <= 2 else FONT_NUM_MID
        num_y = cy + 36
        draw.text((cx + 14, num_y), value_str, font=num_font, fill=TEXT)
        num_w, _ = text_size(draw, value_str, num_font)
        if unit:
            draw.text((cx + 22 + num_w, num_y + 26), unit, font=FONT_UNIT, fill=MUTED)

        if delta_str:
            draw.text((cx + 14, num_y + 74), delta_str, font=FONT_XS, fill=ORANGE if delta_str.startswith("+") else SUBTEXT)

        pts = get_points(item)
        if pts:
            spark_y1 = cy + card_h - 54
            spark_y2 = cy + card_h - 12
            draw_sparkline(draw, pts[-6:], (cx + 12, spark_y1, cx + card_w - 16, spark_y2))


def draw_news_list(base: Image.Image, news_items: List[Dict[str, Any]], box: Tuple[int, int, int, int], heading: str) -> None:
    draw_soft_paper_bg(base, box, 150)
    draw = ImageDraw.Draw(base)
    x1, y1, x2, y2 = box
    draw.text((x1 + 22, y1 + 18), heading, font=FONT_H3, fill=TEXT)
    cur_y = y1 + 58
    max_w = x2 - x1 - 44
    for item in news_items[:2]:
        source = str(item.get("source") or item.get("publisher") or item.get("site") or "news").strip()
        title = str(item.get("title") or item.get("headline") or "").strip()
        summary = str(item.get("summary") or item.get("description") or item.get("why_it_matters") or item.get("reason") or "").strip()
        draw.text((x1 + 22, cur_y), source[:34], font=FONT_XS, fill=ORANGE)
        cur_y += 20
        cur_y = draw_wrapped(draw, title, x1 + 22, cur_y, FONT_LINK, NAVY, max_w, 5, max_lines=2)
        if summary:
            cur_y = draw_wrapped(draw, summary, x1 + 22, cur_y + 3, FONT_XS, SUBTEXT, max_w, 4, max_lines=1)
        cur_y += 22


def render_scene_01(diagram_path: Path, out_path: Path) -> None:
    base = make_canvas().convert("RGBA")
    diagram = Image.open(diagram_path).convert("RGBA")
    fitted = fit_contain(diagram, (CANVAS_W - 120, CANVAS_H - 120))
    base.alpha_composite(fitted, (60, 60))
    base.convert("RGB").save(out_path, "PNG")


def render_focus_scene(scene_id: str, scene: Dict[str, Any], diagram_path: Path, news: Dict[str, Any], market: Dict[str, Any], out_path: Path) -> None:
    cfg = SCENE_CONFIG[scene_id]
    base = make_canvas().convert("RGBA")
    draw = ImageDraw.Draw(base)
    title = str(scene.get("on_screen_title") or scene.get("scene_title") or cfg["title"]).strip()
    draw_main_title(draw, title)

    diagram = Image.open(diagram_path).convert("RGBA")
    visual = compose_key_visual(diagram, scene_id)

    visual_box = (72, 138, 1090, 690)
    draw_soft_paper_bg(base, visual_box, 112)
    fitted_visual = fit_contain(visual, (visual_box[2] - visual_box[0] - 24, visual_box[3] - visual_box[1] - 24))
    base.alpha_composite(fitted_visual, (visual_box[0] + 12, visual_box[1] + 12))

    series_map = normalize_asset_series(market)
    draw_asset_strip(base, series_map, cfg["assets"], (72, 740, 1090, 980))
    news_items = search_news(news, cfg["news_category"], cfg["news_keywords"], 2)
    draw_news_list(base, news_items, (1150, 270, 1848, 980), cfg["news_heading"])

    base.convert("RGB").save(out_path, "PNG")


def get_next_watch_points(narration: Dict[str, Any], forest: Dict[str, Any], news: Dict[str, Any]) -> List[str]:
    scenes = narration.get("scenes") if isinstance(narration, dict) else []
    if isinstance(scenes, list):
        for scene in scenes:
            if str(scene.get("scene_id")) == "scene_06":
                bullets = scene.get("on_screen_bullets")
                if isinstance(bullets, list) and bullets:
                    return [str(x).strip() for x in bullets if str(x).strip()][:3]
    vp = forest.get("video_planning", {}) if isinstance(forest, dict) else {}
    points = vp.get("next_week_questions", []) if isinstance(vp, dict) else []
    if points:
        return [str(x).strip() for x in points if str(x).strip()][:3]
    points = news.get("watch_points", []) if isinstance(news, dict) else []
    if points:
        return [str(x).strip() for x in points if str(x).strip()][:3]
    return [
        "30Y 美債 5.5%？",
        "勞動力轉弱？",
        "央行出手？",
    ]


def render_scene_06(narration: Dict[str, Any], forest: Dict[str, Any], news: Dict[str, Any], out_path: Path) -> None:
    base = make_canvas().convert("RGBA")
    draw = ImageDraw.Draw(base)
    title = "下週觀察重點"
    tw, _ = text_size(draw, title, FONT_H1)
    draw.text(((CANVAS_W - tw) // 2, 86), title, font=FONT_H1, fill=TEXT)

    points = get_next_watch_points(narration, forest, news)
    cards = [
        ("?", points[0] if len(points) > 0 else "30Y 美債 5.5%？"),
        ("↑↓", points[1] if len(points) > 1 else "勞動力轉弱？"),
        ("✦", points[2] if len(points) > 2 else "央行出手？"),
    ]

    start_x = 120
    gap = 34
    card_w = (CANVAS_W - start_x * 2 - gap * 2) // 3
    card_h = 530
    y = 280

    for idx, (symbol, label) in enumerate(cards):
        x = start_x + idx * (card_w + gap)
        draw_soft_paper_bg(base, (x, y, x + card_w, y + card_h), 138)
        sw, sh = text_size(draw, symbol, FONT_SYMBOL)
        draw.text((x + (card_w - sw) // 2, y + 84), symbol, font=FONT_SYMBOL, fill=ORANGE)
        cur_y = y + 214
        cur_y = draw_wrapped(draw, label, x + 42, cur_y, FONT_WATCH_BIG, TEXT, card_w - 84, 10, max_lines=2)
        draw.text((x + 42, cur_y + 34), "下週驗證", font=FONT_WATCH_SMALL, fill=MUTED)

    base.convert("RGB").save(out_path, "PNG")


def main() -> None:
    week_dir = find_latest_week_dir()
    slides_dir = week_dir / "slides"
    ensure_dir(slides_dir)

    narration = load_json(week_dir / "narration" / "weekly_narration.json", {})
    forest = find_json(week_dir, "weekly_forest_summary.json")
    news = find_json(week_dir, "weekly_news_context.json")
    market = find_json(week_dir, "weekly_market_series.json")
    diagram_path = find_diagram(week_dir)

    render_scene_01(diagram_path, slides_dir / "scene_01.png")

    scene_map = {str(s.get("scene_id")): s for s in narration.get("scenes", []) if isinstance(s, dict)}
    for scene_id in ["scene_02", "scene_03", "scene_04", "scene_05"]:
        render_focus_scene(scene_id, scene_map.get(scene_id, {"scene_id": scene_id}), diagram_path, news, market, slides_dir / f"{scene_id}.png")

    render_scene_06(narration, forest, news, slides_dir / "scene_06.png")

    manifest = {"generated": [str(slides_dir / f"scene_0{i}.png") for i in range(1, 7)]}
    (slides_dir / "slides_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Generated slide images under: {slides_dir}")


if __name__ == "__main__":
    main()
