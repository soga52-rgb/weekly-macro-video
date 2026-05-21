#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 08
Build 6 NotebookLM-style slide images for the weekly macro video.

Flow:
- Scene 01: full-page weekly_macro_diagram.png
- Scene 02~05: single focused visual only (NO minimap / NO left-top thumbnail)
- Scene 06: full-page next-week watch list

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
GRID = (237, 233, 226)
TEXT = (29, 36, 51)
SUBTEXT = (80, 96, 122)
ORANGE = (242, 140, 40)
NAVY = (36, 54, 77)
RED = (217, 71, 47)
MUTED = (121, 135, 156)

MARGIN_X = 72
MARGIN_Y = 58

# Scene 02~05 crop positions on weekly_macro_diagram.png
FOCUS_PRESETS: Dict[str, Tuple[float, float, float, float]] = {
    "scene_02": (0.02, 0.08, 0.40, 0.42),  # drivers / oil / reinflation
    "scene_03": (0.30, 0.08, 0.67, 0.45),  # inflation / rates
    "scene_04": (0.50, 0.10, 0.88, 0.48),  # dollar / asia FX
    "scene_05": (0.56, 0.30, 0.88, 0.68),  # gold / correction factor
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

SCENE_CONFIG = {
    "scene_02": {
        "title": "起點：能源價格推升通膨預期",
        "assets": ["WTI", "Brent"],
        "news_category": "通膨預期",
        "news_keywords": ["油價", "原油", "通膨", "能源", "再通膨", "物價"],
        "default_bullets": [
            "地緣政治風險推升油價",
            "市場重新擔憂通膨黏性",
            "聯準會降息空間受限",
        ],
    },
    "scene_03": {
        "title": "利率：長債殖利率重新定價",
        "assets": ["US10Y"],
        "news_category": "利率",
        "news_keywords": ["殖利率", "美債", "利率", "Fed", "升息", "降息"],
        "default_bullets": [
            "長端利率反映高利率維持更久",
            "債市重新定價聯準會政策路徑",
            "全球資產估值錨點上移",
        ],
    },
    "scene_04": {
        "title": "美元與亞洲貨幣：利差壓力外溢",
        "assets": ["DXY", "USDJPY", "USDTWD", "USDKRW"],
        "news_category": "貨幣",
        "news_keywords": ["美元", "亞幣", "日圓", "台幣", "韓元", "匯率"],
        "default_bullets": [
            "美債利率上行支撐美元利差優勢",
            "日圓、台幣與韓元同步承壓",
            "匯率貶值不等於出口絕對利多",
        ],
    },
    "scene_05": {
        "title": "黃金與修正因子：高利率下的避險拉鋸",
        "assets": ["Gold", "DXY"],
        "news_category": "其他",
        "news_keywords": ["黃金", "避險", "房市", "成長", "修正", "衰退", "美元"],
        "default_bullets": [
            "高利率提高持有黃金的機會成本",
            "強美元對美元計價黃金形成壓力",
            "成長疑慮仍可能帶來短線避險支撐",
        ],
    },
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


FONT_H1 = font(48, True)
FONT_H2 = font(34, True)
FONT_H3 = font(26, True)
FONT_BODY = font(23, False)
FONT_SMALL = font(18, False)
FONT_XS = font(14, False)
FONT_NUM = font(52, True)
FONT_NUM_SMALL = font(40, True)
FONT_UNIT = font(15, False)
FONT_LINK = font(18, False)


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
        return (0, 0)
    box = draw.textbbox((0, 0), text, font=fnt)
    return box[2] - box[0], box[3] - box[1]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, fnt, max_width: int) -> List[str]:
    text = str(text or "").strip()
    if not text:
        return []
    lines = []
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


def draw_wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, fnt, fill, max_width: int, line_gap: int = 8, max_lines: Optional[int] = None) -> int:
    lines = wrap_text(draw, text, fnt, max_width)
    if max_lines is not None:
        lines = lines[:max_lines]
    cur_y = y
    for line in lines:
        draw.text((x, cur_y), line, font=fnt, fill=fill)
        _, h = text_size(draw, line, fnt)
        cur_y += h + line_gap
    return cur_y


def fit_contain(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    tw, th = target_size
    iw, ih = image.size
    ratio = min(tw / iw, th / ih)
    nw, nh = max(1, int(iw * ratio)), max(1, int(ih * ratio))
    img = image.resize((nw, nh), Image.LANCZOS)
    bg = Image.new("RGBA", target_size, (0, 0, 0, 0))
    bg.alpha_composite(img.convert("RGBA"), ((tw - nw) // 2, (th - nh) // 2))
    return bg


def fit_crop(image: Image.Image, target_size: Tuple[int, int]) -> Image.Image:
    tw, th = target_size
    iw, ih = image.size
    ratio = max(tw / iw, th / ih)
    nw, nh = max(1, int(iw * ratio)), max(1, int(ih * ratio))
    img = image.resize((nw, nh), Image.LANCZOS)
    left = max(0, (nw - tw) // 2)
    top = max(0, (nh - th) // 2)
    return img.crop((left, top, left + tw, top + th))


def draw_soft_paper_bg(base: Image.Image, box: Tuple[int, int, int, int], alpha: int = 160, radius: int = 28):
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(box, radius=radius, fill=(255, 255, 255, alpha))
    overlay = overlay.filter(ImageFilter.GaussianBlur(0.35))
    base.alpha_composite(overlay)


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
    draw.line(coords, fill=NAVY, width=4)
    for x, y in coords:
        draw.ellipse((x - 4, y - 4, x + 4, y + 4), fill=ORANGE)


def draw_asset_numbers(base_rgba: Image.Image, series_map: Dict[str, Any], asset_keys: List[str], box: Tuple[int, int, int, int]) -> None:
    draw_soft_paper_bg(base_rgba, box, 132)
    draw = ImageDraw.Draw(base_rgba)
    x1, y1, x2, y2 = box
    gap = 18
    count = max(1, len(asset_keys))
    if count <= 2:
        cols, rows = count, 1
    else:
        cols, rows = 2, 2
    card_w = (x2 - x1 - 32 - (cols - 1) * gap) // cols
    card_h = (y2 - y1 - 28 - (rows - 1) * gap) // rows
    for idx, key in enumerate(asset_keys):
        col = idx % cols
        row = idx // cols
        cx = x1 + 16 + col * (card_w + gap)
        cy = y1 + 14 + row * (card_h + gap)
        draw.rounded_rectangle((cx, cy, cx + card_w, cy + card_h), radius=22, fill=(255, 255, 255, 218))
        item = series_map.get(key, {})
        latest, prev = latest_and_prev(item)
        value_str = format_value(latest, key)
        delta = format_delta(latest, prev)
        unit = str(item.get("unit") or ASSET_UNITS.get(key, "")).strip()
        draw.text((cx + 20, cy + 16), ASSET_LABELS.get(key, key), font=FONT_SMALL, fill=NAVY)
        num_font = FONT_NUM if len(asset_keys) <= 2 else FONT_NUM_SMALL
        draw.text((cx + 20, cy + 48), value_str, font=num_font, fill=TEXT)
        val_w, _ = text_size(draw, value_str, num_font)
        if unit:
            draw.text((cx + 24 + val_w, cy + 76), unit, font=FONT_UNIT, fill=MUTED)
        if delta:
            draw.text((cx + 20, cy + 104), delta, font=FONT_XS, fill=ORANGE if delta.startswith("+") else SUBTEXT)
        pts = get_points(item)
        if pts:
            draw_sparkline(draw, pts[-6:], (cx + 20, cy + card_h - 54, cx + card_w - 20, cy + card_h - 18))


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
            str(item.get("summary") or item.get("description") or ""),
            str(item.get("theme") or item.get("category") or item.get("macro_category") or ""),
            str(item.get("why_it_matters") or item.get("reason") or ""),
        ])
        cat_text = str(item.get("category") or item.get("macro_category") or item.get("theme") or "")
        score = (4 if category and category in cat_text else 0) + sum(1 for kw in keywords if kw.lower() in blob.lower())
        ranked.append((score, item))
    ranked.sort(key=lambda x: x[0], reverse=True)
    selected = [item for score, item in ranked if score > 0][:limit]
    return selected if selected else items[:limit]


def draw_three_bullets(base_rgba: Image.Image, title: str, bullets: List[str], box: Tuple[int, int, int, int]) -> None:
    draw_soft_paper_bg(base_rgba, box, 120)
    draw = ImageDraw.Draw(base_rgba)
    x1, y1, x2, y2 = box
    draw.text((x1 + 24, y1 + 18), title, font=FONT_H3, fill=TEXT)
    cur_y = y1 + 70
    max_w = x2 - x1 - 68
    for bullet in bullets[:3]:
        draw.ellipse((x1 + 24, cur_y + 8, x1 + 38, cur_y + 22), fill=ORANGE)
        cur_y = draw_wrapped(draw, bullet, x1 + 52, cur_y, FONT_BODY, TEXT, max_w, 8, max_lines=2) + 22


def draw_news_links(base_rgba: Image.Image, news_items: List[Dict[str, Any]], box: Tuple[int, int, int, int], heading: str = "新聞連結") -> None:
    draw_soft_paper_bg(base_rgba, box, 118)
    draw = ImageDraw.Draw(base_rgba)
    x1, y1, x2, y2 = box
    draw.text((x1 + 22, y1 + 16), heading, font=FONT_H3, fill=TEXT)
    cur_y = y1 + 60
    max_w = x2 - x1 - 44
    for item in news_items[:2]:
        source = str(item.get("source") or item.get("publisher") or item.get("site") or "").strip()
        title = str(item.get("title") or item.get("headline") or "").strip()
        summary = str(item.get("summary") or item.get("description") or item.get("why_it_matters") or item.get("reason") or "").strip()
        if source:
            draw.text((x1 + 22, cur_y), source[:32], font=FONT_XS, fill=ORANGE)
            cur_y += 22
        cur_y = draw_wrapped(draw, title, x1 + 22, cur_y, FONT_LINK, NAVY, max_w, 5, max_lines=2)
        if summary:
            cur_y = draw_wrapped(draw, summary, x1 + 22, cur_y + 4, FONT_XS, SUBTEXT, max_w, 4, max_lines=1)
        cur_y += 24


def draw_main_title(draw: ImageDraw.ImageDraw, title: str):
    draw.text((MARGIN_X, 40), title, font=FONT_H1, fill=TEXT)


def crop_focus(diagram: Image.Image, preset: Tuple[float, float, float, float]) -> Image.Image:
    w, h = diagram.size
    x1, y1, x2, y2 = preset
    box = (int(w * x1), int(h * y1), int(w * x2), int(h * y2))
    return diagram.crop(box)


def get_scene_bullets(scene: Dict[str, Any], cfg: Dict[str, Any]) -> List[str]:
    bullets = scene.get("on_screen_bullets")
    if isinstance(bullets, list):
        cleaned = [str(x).strip() for x in bullets if str(x).strip()]
        if cleaned:
            return cleaned[:3]
    return cfg["default_bullets"][:3]


def get_next_watch_points(narration: Dict[str, Any], news: Dict[str, Any], forest: Dict[str, Any]) -> List[str]:
    scenes = narration.get("scenes") if isinstance(narration, dict) else []
    if isinstance(scenes, list):
        for scene in scenes:
            if str(scene.get("scene_id")) == "scene_06":
                bullets = scene.get("on_screen_bullets")
                if isinstance(bullets, list) and bullets:
                    return [str(x).strip() for x in bullets if str(x).strip()][:5]
    vp = forest.get("video_planning", {}) if isinstance(forest, dict) else {}
    points = vp.get("next_week_questions", []) if isinstance(vp, dict) else []
    if points:
        return [str(x).strip() for x in points if str(x).strip()][:5]
    points = news.get("watch_points", []) if isinstance(news, dict) else []
    if points:
        return [str(x).strip() for x in points if str(x).strip()][:5]
    return [
        "30年期美債殖利率是否挑戰 5.5%",
        "勞動力數據是否放大成長放緩擔憂",
        "亞洲央行是否採取實質干預",
        "美元與黃金是否出現主線修正",
    ]


def find_diagram(week_dir: Path) -> Path:
    for p in [week_dir / "weekly_macro_diagram.png", week_dir / "final" / "weekly_macro_diagram.png", week_dir / "data" / "weekly_macro_diagram.png"]:
        if p.exists():
            return p
    raise FileNotFoundError("Cannot find weekly_macro_diagram.png")


def render_scene_01(diagram_path: Path, out_path: Path) -> None:
    base = make_canvas().convert("RGBA")
    diagram = Image.open(diagram_path).convert("RGBA")
    fitted = fit_contain(diagram, (CANVAS_W - 120, CANVAS_H - 120))
    base.alpha_composite(fitted, (60, 60))
    base.convert("RGB").save(out_path, "PNG")


def render_focus_scene(scene: Dict[str, Any], diagram_path: Path, news: Dict[str, Any], market: Dict[str, Any], out_path: Path) -> None:
    scene_id = str(scene.get("scene_id") or "").strip()
    cfg = SCENE_CONFIG[scene_id]
    base = make_canvas().convert("RGBA")
    draw = ImageDraw.Draw(base)
    title = str(scene.get("on_screen_title") or scene.get("scene_title") or cfg["title"]).strip()
    draw_main_title(draw, title[:28])

    diagram = Image.open(diagram_path).convert("RGBA")
    cropped = crop_focus(diagram, FOCUS_PRESETS[scene_id])
    focus_box = (MARGIN_X, 138, 1008, 728)
    focus_img = fit_crop(cropped, (focus_box[2] - focus_box[0], focus_box[3] - focus_box[1]))
    base.alpha_composite(focus_img, (focus_box[0], focus_box[1]))
    draw.rounded_rectangle(focus_box, radius=26, outline=RED, width=6)

    series_map = normalize_asset_series(market)
    draw_asset_numbers(base, series_map, cfg["assets"], (MARGIN_X, 775, 1008, 1018))
    draw_three_bullets(base, "三點重點", get_scene_bullets(scene, cfg), (1065, 138, 1848, 508))
    draw_news_links(base, search_news(news, cfg["news_category"], cfg["news_keywords"], 2), (1065, 565, 1848, 1018), heading=cfg["news_category"])
    base.convert("RGB").save(out_path, "PNG")


def render_scene_06(narration: Dict[str, Any], forest: Dict[str, Any], news: Dict[str, Any], out_path: Path) -> None:
    base = make_canvas().convert("RGBA")
    draw = ImageDraw.Draw(base)
    title = "下週觀察重點"
    tw, _ = text_size(draw, title, FONT_H1)
    draw.text(((CANVAS_W - tw) // 2, 95), title, font=FONT_H1, fill=TEXT)
    start_y = 225
    for point in get_next_watch_points(narration, news, forest)[:5]:
        box = (220, start_y, 1700, start_y + 118)
        draw_soft_paper_bg(base, box, 126)
        pin_x = 260
        pin_y = start_y + 42
        draw.ellipse((pin_x, pin_y, pin_x + 18, pin_y + 18), fill=ORANGE)
        draw_wrapped(draw, point, 310, start_y + 30, FONT_H2, TEXT, 1300, 8, max_lines=2)
        start_y += 136
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
        render_focus_scene(scene_map.get(scene_id, {"scene_id": scene_id}), diagram_path, news, market, slides_dir / f"{scene_id}.png")

    render_scene_06(narration, forest, news, slides_dir / "scene_06.png")

    manifest = {
        "generated": [str(slides_dir / f"scene_0{i}.png") for i in range(1, 7)]
    }
    (slides_dir / "slides_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Generated slide images under: {slides_dir}")


if __name__ == "__main__":
    main()
