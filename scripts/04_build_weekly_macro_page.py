#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Step 04
Build weekly macro summary web page.

Page order:
1. Macro transmission diagram image
2. 重點摘要
3. 本週市場訊號與走勢
4. 修正因子 / 待觀察
5. 本週新聞佐證
6. 下週觀察
7. 週報影片 / 圖卡草稿

Design:
- Unified Apple/iOS widget-inspired glassmorphism style.
- Warm neutral palette: off-white, white, deep gray, amber accent.
- News evidence grouped into: 通膨預期 / 利率 / 貨幣 / 其他.
- Market signals and trend charts merged into one card section.
"""

import json
import html
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""

def infer_week_label_from_source_text(week_dir: Path) -> str:
    """
    Prefer the source-text weekly range for the page header.

    weekly_market_series may intentionally include a longer lookback window for charts.
    The page headline period should follow weekly_source_text.md / weekly_video_source,
    e.g. 2026-05-22 ～ 2026-05-28.
    """
    source_text_path = week_dir / "weekly_source_text.md"
    if not source_text_path.exists():
        return ""

    try:
        text = source_text_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""

    match = re.search(r"週期：\s*(\d{4}-\d{2}-\d{2})\s*[～~\-to]+\s*(\d{4}-\d{2}-\d{2})", text)
    if not match:
        return ""

    return f"{match.group(1)} ～ {match.group(2)}"

def parse_week_range_label(week_label: str) -> tuple[str, str]:
    """Return YYYY-MM-DD start/end from a label like 2026-05-22 ～ 2026-05-28."""
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:～|~|to|-)\s*(\d{4}-\d{2}-\d{2})", week_label or "")
    if not match:
        return "", ""
    return match.group(1), match.group(2)


def filter_points_by_week(points: Any, week_start: str, week_end: str) -> List[Dict[str, Any]]:
    """Filter market series points to the weekly source range used by the page."""
    if not isinstance(points, list):
        return []

    filtered = []
    for point in points:
        if not isinstance(point, dict):
            continue
        date_text = str(point.get("date") or "")
        if week_start and date_text < week_start:
            continue
        if week_end and date_text > week_end:
            continue
        filtered.append(point)

    return filtered


def get_nested(data: Dict[str, Any], *keys: str) -> Any:
    obj: Any = data
    for key in keys:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(key)
    return obj


def render_list(items: Any, empty: str = "資料不足，待觀察") -> str:
    values = as_list(items)
    if not values:
        return f"<li>{esc(empty)}</li>"

    rows = []
    for item in values:
        if isinstance(item, dict):
            text = "｜".join(
                x for x in [
                    first_non_empty(item.get("driver"), item.get("title"), item.get("theme"), item.get("label")),
                    first_non_empty(item.get("impact"), item.get("summary"), item.get("why_it_matters"), item.get("main_point")),
                ] if x
            )
            rows.append(f"<li>{esc(text or json.dumps(item, ensure_ascii=False))}</li>")
        else:
            rows.append(f"<li>{esc(item)}</li>")
    return "\n".join(rows)


def render_video_section(week_dir: Path) -> str:
    """Render the weekly macro video player near the top of the page."""
    candidates = [
        week_dir / "final" / "weekly_macro_video.mp4",
        week_dir / "video" / "weekly_macro_video.mp4",
        week_dir / "weekly_macro_video.mp4",
    ]

    video_path = next((p for p in candidates if p.exists()), None)
    if not video_path:
        return """
  <section class="section section-video">
    <h2>本週總經影片</h2>
    <div class="muted-box">本週影片尚未產生，完成 07 合成後會自動顯示於此。</div>
  </section>
"""

    src = video_path.relative_to(week_dir).as_posix()
    poster_path = week_dir / "slides" / "scene_01.png"
    poster_attr = f' poster="{esc(poster_path.relative_to(week_dir).as_posix())}"' if poster_path.exists() else ""

    return f"""
  <section class="section section-video">
    <h2>本週總經影片</h2>
    <div class="video-shell">
      <video class="weekly-video" controls playsinline preload="metadata"{poster_attr}>
        <source src="{esc(src)}" type="video/mp4">
        您的瀏覽器不支援影片播放。
      </video>
    </div>
    <div class="video-note">影片依本週總經傳導圖、旁白與圖卡自動合成。</div>
  </section>
"""


def build_asset_signal_map(forest: Dict[str, Any]) -> Dict[str, str]:
    variables = forest.get("macro_variables") or {}
    return {
        "US10Y": str(variables.get("rate_view", "") or "").strip(),
        "DXY": str(variables.get("dollar_fx_view", "") or "").strip(),
        "Gold": str(variables.get("gold_view", "") or "").strip(),
        "WTI": str(variables.get("energy_view", "") or "").strip(),
        "Brent": str(variables.get("energy_view", "") or "").strip(),
        "USDJPY": str(variables.get("asia_fx_view", "") or "").strip(),
        "USDTWD": str(variables.get("asia_fx_view", "") or "").strip(),
        "USDKRW": str(variables.get("asia_fx_view", "") or "").strip(),
    }


def source_label_from_market(_: Dict[str, Any]) -> str:
    return "YAHOO財經"


def classify_news_item(item: Dict[str, Any]) -> str:
    title = str(item.get("title") or "").lower()
    theme = str(item.get("theme") or "").lower()
    why = str(item.get("why_it_matters") or "").lower()
    source = str(item.get("source") or "").lower()

    # Title/theme should dominate classification. Otherwise a currency article that
    # mentions yields in why_it_matters may be incorrectly moved into the rate bucket.
    currency_keywords = [
        "美元", "美元指數", "匯率", "亞幣", "新台幣", "台幣", "日圓", "韓元", "人民幣",
        "dxy", "currency", "dollar", "yen", "twd", "krw", "cny", "fx"
    ]
    rate_keywords = [
        "利率", "殖利率", "美債", "公債", "fed", "聯準會", "升息", "降息",
        "債市", "長債", "yield", "treasury", "rate", "bond"
    ]
    inflation_keywords = [
        "通膨", "再通膨", "物價", "cpi", "ppi", "油價", "原油", "能源",
        "inflation", "reflation", "oil", "energy", "wti", "brent"
    ]

    def hit(text: str, keywords: List[str]) -> bool:
        return any(keyword.lower() in text for keyword in keywords)

    title_theme = f"{title} {theme}"
    all_text = f"{title} {theme} {why} {source}"

    # Priority 1: title/theme direct signal.
    # Example:「美元指數衝破99 新台幣連4貶」must stay in 貨幣,
    # even if the explanation mentions 美債殖利率.
    if hit(title_theme, currency_keywords):
        return "貨幣"
    if hit(title_theme, rate_keywords):
        return "利率"
    if hit(title_theme, inflation_keywords):
        return "通膨預期"

    # Priority 2: fallback to full text.
    scores = {
        "通膨預期": sum(1 for keyword in inflation_keywords if keyword.lower() in all_text),
        "利率": sum(1 for keyword in rate_keywords if keyword.lower() in all_text),
        "貨幣": sum(1 for keyword in currency_keywords if keyword.lower() in all_text),
    }
    best_category = max(scores, key=scores.get)
    return best_category if scores[best_category] > 0 else "其他"



def normalize_news_title(title: Any) -> str:
    text = str(title or "").strip().lower()
    return re.sub(r"\W+", "", text)[:90]


def build_news_url_lookup(news_context: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Build URL lookup from top_news and data/weekly_news_raw.json.

    Gemini may put good categorized cards into news_categories but omit URL.
    The original RSS package usually still has URLs, so the web layer can restore
    clickable links without re-running AI.
    """
    lookup: Dict[str, Dict[str, Any]] = {}

    def add_item(item: Any) -> None:
        if not isinstance(item, dict):
            return
        key = normalize_news_title(item.get("title"))
        url = first_non_empty(item.get("url"), "")
        if not key or not url:
            return
        current = lookup.get(key, {})
        merged = dict(current)
        for field in ["title", "url", "source", "published_at", "why_it_matters", "theme", "score"]:
            if item.get(field) and not merged.get(field):
                merged[field] = item.get(field)
        lookup[key] = merged

    for item in as_list(news_context.get("top_news")):
        add_item(item)

    raw_package = load_json(ROOT_DIR / "data" / "weekly_news_raw.json", {})
    for item in as_list(raw_package.get("items") if isinstance(raw_package, dict) else []):
        add_item(item)

    return lookup


def enrich_news_items_with_urls(items: List[Dict[str, Any]], lookup: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched = []
    for item in items:
        if not isinstance(item, dict):
            continue

        merged = dict(item)
        if not first_non_empty(merged.get("url"), ""):
            matched = lookup.get(normalize_news_title(merged.get("title")), {})
            for field in ["url", "source", "published_at", "theme"]:
                if matched.get(field) and not merged.get(field):
                    merged[field] = matched.get(field)

        enriched.append(merged)
    return enriched


def render_news_card(item: Dict[str, Any]) -> str:
    title = first_non_empty(item.get("title"), "未命名新聞")
    source = first_non_empty(item.get("source"), "News")
    why = first_non_empty(item.get("why_it_matters"), item.get("theme"), "")
    url = first_non_empty(item.get("url"), "#")
    target_attr = ' target="_blank" rel="noopener noreferrer"' if url != "#" else ""

    return f"""
    <a class="news-mini-card" href="{esc(url)}"{target_attr}>
      <div class="news-mini-top">
        <span class="news-source">{esc(source)}</span>
        <span class="open-mark">↗</span>
      </div>
      <div class="news-title">{esc(title)}</div>
      <div class="news-why">{esc(why)}</div>
    </a>
    """


def dedupe_news_items(items: List[Dict[str, Any]], limit: int = 8) -> List[Dict[str, Any]]:
    output = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        key = (item.get("title") or "", item.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
        if len(output) >= limit:
            break
    return output


def get_categorized_news(news_context: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    categories = {
        "通膨預期": [],
        "利率": [],
        "貨幣": [],
        "其他": [],
    }

    direct_categories = news_context.get("news_categories")
    if isinstance(direct_categories, dict):
        for key in categories.keys():
            categories[key] = dedupe_news_items(direct_categories.get(key) or [], 8)

    # Fallback for older weekly_news_context.json:
    # classify top_news only if the AI did not provide category buckets.
    if not any(categories.values()):
        top_news = news_context.get("top_news") or []
        for item in top_news:
            if not isinstance(item, dict):
                continue
            category = classify_news_item(item)
            categories.setdefault(category, []).append(item)

        for key in categories.keys():
            categories[key] = dedupe_news_items(categories[key], 8)

    url_lookup = build_news_url_lookup(news_context)
    for key in categories.keys():
        categories[key] = enrich_news_items_with_urls(categories[key], url_lookup)

    return categories


def render_news(news_context: Dict[str, Any]) -> str:
    categories = get_categorized_news(news_context)
    if not any(categories.values()):
        return '<div class="muted-box">本週新聞補充資料不足，待觀察。</div>'

    category_descriptions = {
        "通膨預期": "油價、能源、物價與再通膨訊號",
        "利率": "美債殖利率、Fed 與高利率定價",
        "貨幣": "美元、亞洲貨幣與資金流向壓力",
        "其他": "補充其他可能影響主線的事件",
    }

    # Natural weighting:
    # Categories with more evidence occupy larger visual space.
    # Keep the macro reading order as a tie breaker.
    category_order = ["通膨預期", "利率", "貨幣", "其他"]
    non_empty = [
        (category, categories.get(category, []))
        for category in category_order
        if categories.get(category, [])
    ]

    if not non_empty:
        return '<div class="muted-box">本週新聞補充資料不足，待觀察。</div>'

    max_count = max(len(items) for _, items in non_empty)

    def span_for(count: int) -> int:
        if len(non_empty) == 1:
            return 12
        if count >= 5 or count == max_count and max_count >= 4:
            return 8
        if count >= 3:
            return 6
        return 4

    sections = []
    for category, items in non_empty:
        count = len(items)
        span = span_for(count)
        cards = "\n".join(render_news_card(item) for item in items[:8])
        density_label = f"{count} 則"

        sections.append(f"""
        <div class="news-category news-weight-{min(count, 8)}" style="grid-column: span {span};">
          <div class="news-category-head">
            <div>
              <div class="category-pill">{esc(category)}</div>
              <div class="news-category-desc">{esc(category_descriptions[category])}</div>
            </div>
            <div class="news-count">{esc(density_label)}</div>
          </div>
          <div class="news-category-cards">
            {cards}
          </div>
        </div>
        """)

    return "\n".join(sections)


def fmt_number(value: float, unit: str = "") -> str:
    if abs(value) >= 1000:
        text = f"{value:,.1f}"
    elif abs(value) >= 100:
        text = f"{value:.2f}"
    else:
        text = f"{value:.3f}"
    return f"{text} {unit}".strip()

def fmt_number_only(value: float) -> str:
    if abs(value) >= 1000:
        return f"{value:,.1f}"
    if abs(value) >= 100:
        return f"{value:.2f}"
    return f"{value:.3f}"


def sparkline_svg(points_data: List[Dict[str, Any]], unit: str = "") -> str:
    if len(points_data) < 2:
        return '<div class="chart-empty">資料不足</div>'

    values = [float(p["value"]) for p in points_data]

    width = 280
    height = 92
    pad_x = 14
    pad_y = 14
    chart_w = width - pad_x * 2
    chart_h = height - pad_y * 2

    min_v = min(values)
    max_v = max(values)
    span = max(max_v - min_v, 1e-9)

    coords = []
    dots = []
    for i, point in enumerate(points_data):
        value = float(point["value"])
        date = str(point.get("date") or "")

        x = pad_x + (i / (len(points_data) - 1)) * chart_w
        y = pad_y + (1 - ((value - min_v) / span)) * chart_h

        coords.append(f"{x:.1f},{y:.1f}")
        dots.append(
            f'<g class="spark-node">'
            f'<circle class="spark-dot" cx="{x:.1f}" cy="{y:.1f}" r="4.2"></circle>'
            f'<title>{esc(date)}｜{esc(fmt_number(value, unit))}</title>'
            f'</g>'
        )

    return f"""
    <div class="gf-chart-wrap">
      <svg class="sparkline" viewBox="0 0 {width} {height}" preserveAspectRatio="none">
        <polyline points="{' '.join(coords)}" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" />
        {''.join(dots)}
      </svg>
    </div>
    """


def render_market_charts(market: Dict[str, Any], forest: Dict[str, Any], week_label: str = "") -> str:
    series = market.get("series") or []
    signal_map = build_asset_signal_map(forest)
    week_start, week_end = parse_week_range_label(week_label)
    if not isinstance(series, list) or not series:
        return '<div class="muted-box">目前尚未匯入本週市場走勢資料。</div>'

    preferred_order = ["US10Y", "DXY", "Gold", "WTI", "Brent", "USDJPY", "USDTWD", "USDKRW"]
    series_sorted = sorted(
        [s for s in series if isinstance(s, dict)],
        key=lambda s: preferred_order.index(s.get("asset_key")) if s.get("asset_key") in preferred_order else 999
    )

    cards = []
    for item in series_sorted[:8]:
        asset = first_non_empty(item.get("asset"), item.get("asset_key"), "未命名資產")
        unit = first_non_empty(item.get("unit"), "")
        points = filter_points_by_week(item.get("points") or [], week_start, week_end)
        if len(points) < 2:
            points = item.get("points") or []

        clean_points = []
        for point in points:
            if not isinstance(point, dict):
                continue
            try:
                value = float(point.get("value"))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                clean_points.append({"date": str(point.get("date") or ""), "value": value})

        if not clean_points:
            continue

        values = [p["value"] for p in clean_points]
        first_value = values[0]
        latest_value = values[-1]
        change = latest_value - first_value
        pct = (change / first_value * 100) if first_value else 0.0

        direction = "up" if change > 0 else "down" if change < 0 else "flat"
        direction_text = "上行" if direction == "up" else "下行" if direction == "down" else "持平"
        change_sign = "+" if change > 0 else ""

        asset_key = str(item.get("asset_key") or "")
        signal_text = signal_map.get(asset_key, "")
        asset_theme = {
            "US10Y": "rate",
            "DXY": "dollar",
            "Gold": "gold",
            "WTI": "energy",
            "Brent": "energy",
            "USDJPY": "fx",
            "USDTWD": "fx",
            "USDKRW": "fx",
        }.get(asset_key, "neutral")

        cards.append(f"""
        <div class="chart-card chart-theme-{asset_theme}">
          <div class="chart-head">
            <div class="asset-pill">{esc(asset)}</div>
            <div class="chart-direction {direction}">{esc(direction_text)}</div>
          </div>
          <div class="chart-value-row">
            <div class="chart-latest">
              <span class="chart-latest-value">{esc(fmt_number_only(latest_value))}</span>
              <span class="chart-latest-unit">{esc(unit)}</span>
            </div>
            <div class="chart-change">{esc(change_sign)}{change:.3f}｜{change_sign}{pct:.2f}%</div>
          </div>
          {sparkline_svg(clean_points, unit)}
          <div class="chart-signal">{esc(signal_text or "本週方向待觀察。")}</div>
        </div>
        """)

    return "\n".join(cards) if cards else '<div class="muted-box">市場走勢資料格式無法繪圖。</div>'


def render_scene_cards(forest: Dict[str, Any]) -> str:
    scenes = get_nested(forest, "video_planning", "six_scene_outline") or []
    if not scenes:
        return '<div class="muted-box">六張投影片規劃尚未產生。</div>'

    cards = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        cards.append(f"""
        <div class="slide-card">
          <div class="slide-id">{esc(scene.get("scene_id", ""))}</div>
          <div class="slide-title">{esc(scene.get("scene_title", ""))}</div>
          <div class="slide-question">{esc(scene.get("scene_question", ""))}</div>
          <div class="slide-point">{esc(scene.get("main_point", ""))}</div>
        </div>
        """)
    return "\n".join(cards)


def build_html(week_dir: Path, forest: Dict[str, Any], news_context: Dict[str, Any], market: Dict[str, Any]) -> str:
    summary = forest.get("forest_summary") or {}
    storyline = forest.get("macro_storyline") or {}
    evidence = forest.get("evidence") or {}
    video = forest.get("video_planning") or {}

    week_label = first_non_empty(
        infer_week_label_from_source_text(week_dir),
        get_nested(forest, "meta", "week_range"),
        f"{get_nested(market, 'meta', 'range', 'start') or ''} ～ {get_nested(market, 'meta', 'range', 'end') or ''}".strip(" ～"),
        "資料週期待確認",
    )
    generated_at = datetime.utcnow().strftime("%Y-%m-%d")

    page_title = "本週總經摘要"
    title = page_title
    headline = first_non_empty(summary.get("weekly_main_theme"), video.get("suggested_video_title"), page_title)
    verdict = first_non_empty(summary.get("one_sentence_verdict"), summary.get("narrative_arc"), "資料不足，待觀察")
    main_question = first_non_empty(summary.get("main_question"), "下週市場將驗證哪些總經訊號？")

    diagram_exists = (week_dir / "weekly_macro_diagram.png").exists()
    diagram_html = (
        '<img class="diagram-img" src="weekly_macro_diagram.png" alt="總經傳導圖解">'
        if diagram_exists
        else '<div class="muted-box">總經傳導圖解尚未產生。</div>'
    )

    news_html = render_news(news_context)
    charts_html = render_market_charts(market, forest, week_label)
    video_html = render_video_section(week_dir)

    revision_items = render_list([
        first_non_empty(storyline.get("revision_or_noise"), ""),
        *as_list(evidence.get("insufficient_evidence")),
    ])
    next_week = render_list(video.get("next_week_questions") or evidence.get("watch_items_from_news_context"))
    evidence_items = render_list(evidence.get("most_important_evidence"))

    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
:root {{
  --bg:#f7f7f4;
  --paper:#fffdf7;
  --glass:rgba(255,255,255,.62);
  --glass-strong:rgba(255,255,255,.78);
  --ink:#111827;
  --navy:#0f2a44;
  --navy-soft:#eaf0f7;
  --muted:#64748b;
  --line:rgba(209,213,219,.72);
  --accent:#f59e0b;
  --accent-dark:#8a4b08;
  --accent-soft:#fff3d1;
  --shadow:0 18px 45px rgba(31,41,55,.075);
  --soft-shadow:0 10px 26px rgba(31,41,55,.055);
  --radius:24px;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  background:
    radial-gradient(circle at 50% 0%, rgba(255,216,130,.22) 0, rgba(255,216,130,0) 26%),
    radial-gradient(circle at 90% 12%, rgba(234,240,247,.72) 0, rgba(234,240,247,0) 34%),
    linear-gradient(180deg,#fbfaf7 0%,#eef1f5 100%);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;
  line-height:1.65;
}}
.wrap {{ max-width:1180px; margin:0 auto; padding:38px 18px 72px; }}
.header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-end; margin-bottom:24px; }}
.kicker {{ color:#9a6200; font-weight:850; letter-spacing:.08em; font-size:13px; text-transform:uppercase; }}
.title {{ color:var(--navy); font-size:42px; line-height:1.2; font-weight:900; margin:6px 0 10px; }}
.subtitle {{ color:#4b5563; font-size:20px; max-width:840px; }}
.meta {{ text-align:right; color:var(--muted); font-size:14px; white-space:nowrap; }}
.section {{
  background:var(--glass);
  border:1px solid rgba(255,255,255,.68);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  padding:26px;
  margin:20px 0;
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
}}
.section h2 {{
  color:var(--navy);
  margin:0 0 18px;
  font-size:28px;
  display:flex;
  align-items:center;
  gap:10px;
}}
.section h2::before {{
  content:"";
  width:10px;
  height:28px;
  border-radius:999px;
  background:var(--accent);
  display:inline-block;
}}
.hero {{
  background:linear-gradient(135deg,rgba(255,247,220,.82) 0%,rgba(255,255,255,.72) 58%,rgba(248,250,252,.72) 100%);
  border:1px solid rgba(234,214,162,.72);
}}
.diagram-img {{
  width:100%;
  display:block;
  border-radius:22px;
  border:1px solid rgba(234,223,191,.8);
  background:#fffdf7;
  box-shadow:var(--soft-shadow);
}}
.summary-grid {{ display:grid; grid-template-columns:1.1fr .9fr; gap:16px; }}
.big-text {{ font-size:24px; font-weight:800; }}
.question {{
  font-size:18px;
  background:linear-gradient(135deg,rgba(255,243,209,.88) 0%,rgba(255,250,240,.86) 100%);
  border:1px solid rgba(243,210,139,.72);
  border-radius:20px;
  padding:18px;
  color:#7c2d12;
  font-weight:900;
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.5);
}}
.charts {{ display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:16px; }}
.chart-card,.slide-card,.news-category,.news-mini-card {{
  background:var(--glass-strong);
  border:1px solid rgba(255,255,255,.72);
  border-radius:24px;
  box-shadow:var(--soft-shadow);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
}}
.chart-card {{
  position:relative;
  padding:18px;
  overflow:hidden;
  min-width:0;
  border-top:4px solid rgba(245,158,11,.78);
  background:linear-gradient(180deg,rgba(250,252,255,.90) 0%,rgba(255,255,255,.78) 38%);
}}
.chart-head {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; margin-bottom:8px; }}
.asset-pill {{
  color:var(--navy);
  display:inline-flex;
  align-items:center;
  min-height:34px;
  padding:5px 12px;
  border-radius:999px;
  font-weight:900;
  font-size:17px;
  border:1px solid rgba(234,223,191,.9);
  background:rgba(255,247,237,.86);
  color:var(--accent-dark);
  gap:8px;
}}
.asset-pill::before {{
  content:"";
  width:8px;
  height:8px;
  border-radius:999px;
  background:var(--accent);
  display:inline-block;
}}
.chart-value-row {{ display:flex; align-items:baseline; gap:12px; flex-wrap:wrap; margin-top:8px; }}
.chart-latest {{ color:var(--navy); line-height:1.15; letter-spacing:.01em; display:flex; align-items:baseline; gap:7px; flex-wrap:wrap; }}
.chart-latest-value {{ font-size:34px; font-weight:850; }}
.chart-latest-unit {{ font-size:17px; font-weight:800; color:#52637a; letter-spacing:0; }}
.chart-change {{ color:var(--muted); font-size:15px; white-space:nowrap; }}
.chart-direction {{ font-size:14px; font-weight:900; border-radius:999px; padding:4px 12px; background:#f3f4f6; white-space:nowrap; border:1px solid transparent; }}
.chart-direction.up {{ color:#7c2d12; background:#fff3d1; border-color:#f3d28b; }}
.chart-direction.down {{ color:#374151; background:#f3f4f6; border-color:#e5e7eb; }}
.chart-direction.flat {{ color:#4b5563; background:#f3f4f6; border-color:#e5e7eb; }}
.gf-chart-wrap {{ width:100%; margin:16px 0 10px; overflow:hidden; border-radius:16px; }}
.sparkline {{ width:100%; height:96px; display:block; color:#334155; }}
.spark-node {{ pointer-events:auto; }}
.spark-dot {{ fill:#fff; stroke:currentColor; stroke-width:2.6; cursor:pointer; opacity:.95; }}
.spark-dot:hover {{ fill:var(--accent); stroke:var(--accent); }}
.chart-signal {{ color:#374151; font-size:16px; margin-top:10px; min-height:48px; }}
.market-section {{
  position:relative;
  padding-bottom:54px;
}}
.section-source {{
  position:absolute;
  right:26px;
  bottom:18px;
  color:var(--muted);
  font-size:14px;
  white-space:nowrap;
  background:rgba(255,255,255,.72);
  border:1px solid rgba(209,213,219,.55);
  border-radius:999px;
  padding:5px 11px;
}}
.two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
ul {{ margin:0; padding-left:22px; }}
.section li {{
  margin:8px 0;
  padding:9px 11px;
  background:rgba(255,250,240,.62);
  border:1px solid rgba(231,196,106,.35);
  border-radius:13px;
}}
.video-shell {{
  width:100%;
  border-radius:24px;
  overflow:hidden;
  background:#0f172a;
  box-shadow:var(--shadow);
  border:1px solid rgba(255,255,255,.72);
}}
.weekly-video {{
  width:100%;
  display:block;
  aspect-ratio:16/9;
  background:#0f172a;
}}
.video-note {{
  color:var(--muted);
  font-size:14px;
  margin-top:12px;
}}
.news-masonry {{
  display:grid;
  grid-template-columns:repeat(12,minmax(0,1fr));
  gap:16px;
  align-items:stretch;
}}
.news-category {{ padding:16px; background:rgba(255,255,255,.56); min-width:0; }}
.news-category-head {{
  margin-bottom:12px;
  display:flex;
  justify-content:space-between;
  align-items:flex-start;
  gap:12px;
}}
.news-count {{
  flex:0 0 auto;
  color:var(--accent-dark);
  background:rgba(255,243,209,.88);
  border:1px solid rgba(243,210,139,.72);
  border-radius:999px;
  padding:5px 10px;
  font-size:13px;
  font-weight:900;
}}
.category-pill {{
  color:var(--navy);
  display:inline-flex;
  align-items:center;
  padding:6px 13px;
  border-radius:999px;
  background:rgba(255,243,209,.9);
  border:1px solid rgba(243,210,139,.75);
  color:var(--accent-dark);
  font-size:18px;
  font-weight:900;
}}
.news-category-desc {{ color:var(--muted); font-size:14px; margin-top:8px; }}
.news-category-cards {{
  display:grid;
  grid-template-columns:repeat(auto-fit,minmax(210px,1fr));
  gap:12px;
}}
.news-mini-card {{
  display:block;
  position:relative;
  min-height:148px;
  padding:14px;
  text-decoration:none;
  color:inherit;
  transition:.16s ease;
}}
.news-mini-card:hover {{
  transform:translateY(-2px);
  box-shadow:0 14px 30px rgba(31,41,55,.10);
}}
.news-mini-top {{ display:flex; justify-content:space-between; gap:8px; align-items:center; margin-bottom:8px; }}
.news-source {{ color:#9a6200; font-size:13px; font-weight:850; }}
.open-mark {{ color:#9a6200; font-size:15px; font-weight:900; opacity:.75; }}
.news-title {{
  color:var(--navy);
  font-size:16px;
  font-weight:900;
  line-height:1.38;
  display:-webkit-box;
  -webkit-line-clamp:3;
  -webkit-box-orient:vertical;
  overflow:hidden;
}}
.news-why {{
  color:#4b5563;
  font-size:13.5px;
  line-height:1.45;
  margin-top:8px;
  display:-webkit-box;
  -webkit-line-clamp:2;
  -webkit-box-orient:vertical;
  overflow:hidden;
}}
.muted-box {{ background:rgba(249,250,251,.72); border:1px dashed #d1d5db; color:#6b7280; border-radius:16px; padding:16px; }}
.muted-box.compact {{ padding:12px; font-size:14px; }}
.slides {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.slide-card {{ padding:16px; text-decoration:none; color:inherit; }}
.slide-id {{ color:#9a6200; font-size:12px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
.slide-title {{ font-size:18px; font-weight:900; margin:4px 0; }}
.slide-question {{ color:#7c2d12; font-weight:800; font-size:14px; margin-bottom:8px; }}
.slide-point {{ color:#4b5563; font-size:14px; }}
.footer {{ color:var(--muted); font-size:13px; padding:20px 2px; }}
@media(max-width:1000px) {{
  .charts,.slides {{ grid-template-columns:repeat(2,minmax(0,1fr)); }}
  .news-category {{ grid-column:span 6 !important; }}
  .news-category-cards {{ grid-template-columns:1fr; }}
}}
@media(max-width:760px) {{
  .header,.summary-grid,.two-col {{ display:block; }}
  .meta {{
    position:static !important;
    text-align:center !important;
    white-space:normal;
    margin-top:10px;
  }}
  .charts,.slides {{ grid-template-columns:1fr; }}
  .news-masonry {{ grid-template-columns:1fr; }}
  .news-category {{ grid-column:span 1 !important; }}
  .title {{ font-size:34px; }}
  .subtitle {{ font-size:18px; }}
}}

/* V12 header/source placement overrides */
.header {{
  display:block !important;
  position:relative !important;
  width:100% !important;
  text-align:center !important;
  margin-left:auto !important;
  margin-right:auto !important;
}}
.header-main {{
  margin-left:auto !important;
  margin-right:auto !important;
  text-align:center !important;
}}
.header .meta {{
  position:absolute !important;
  right:0 !important;
  bottom:10px !important;
  text-align:right !important;
}}
.section-source {{
  text-align:right;
}}

</style>
</head>
<body>
<div class="wrap">
  <header class="header">
    <div class="header-main">
      <div class="kicker">Weekly Macro Summary</div>
      <div class="title">{esc(title)}</div>
    </div>
    <div class="meta">
      週期：{esc(week_label)}　｜　產生日期：{esc(generated_at)}
    </div>
  </header>

  {video_html}

  <section class="section hero">
    <h2>總經傳導圖解</h2>
    {diagram_html}
  </section>

  <section class="section section-highlight">
    <h2>重點摘要</h2>
    <div class="summary-grid">
      <div class="big-text">{esc(headline)}</div>
      <div class="question">{esc(main_question)}</div>
    </div>
    <p>{esc(summary.get("narrative_arc", ""))}</p>
  </section>

  <section class="section section-market market-section">
    <h2>本週市場訊號與走勢</h2>
    <div class="charts">{charts_html}</div>
    <div class="section-source">來源：YAHOO財經</div>
  </section>

  <section class="section section-watch">
    <h2>修正因子 / 待觀察</h2>
    <ul>{revision_items}</ul>
  </section>

  <section class="section section-news">
    <h2>本週新聞佐證</h2>
    <div class="news-masonry">{news_html}</div>
  </section>

  <section class="section section-next">
    <h2>下週觀察</h2>
    <div class="two-col">
      <div>
        <h3>關鍵問題</h3>
        <ul>{next_week}</ul>
      </div>
      <div>
        <h3>主要佐證</h3>
        <ul>{evidence_items}</ul>
      </div>
    </div>
  </section>

  <div class="footer">
    本頁由 weekly_forest_summary.json、weekly_news_context.json、weekly_market_series.json 與 weekly_macro_diagram.png 自動產生。內容為總經資訊整理，不構成投資建議。
  </div>
</div>
</body>
</html>"""


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    forest = load_json(week_dir / "weekly_forest_summary.json", {})
    news_context = load_json(week_dir / "weekly_news_context.json", {})
    market = load_json(week_dir / "weekly_market_series.json", {})

    if not forest:
        raise FileNotFoundError(f"Missing or empty weekly_forest_summary.json in {week_dir}")

    html_text = build_html(week_dir, forest, news_context, market)
    out_path = week_dir / "index.html"
    save_text(out_path, html_text)

    print(f"[OK] Weekly macro page created: {out_path}")


if __name__ == "__main__":
    main()
