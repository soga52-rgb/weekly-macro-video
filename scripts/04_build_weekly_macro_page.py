#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Step 04
Build weekly macro summary web page.

Page order:
1. Weekly macro transmission diagram image
2. Executive Summary
3. Weekly market signals
4. Revision factors / watch items
5. Weekly news evidence
6. Next week watch
7. Video / card draft

Trend charts are intentionally not included in this first page version.
They can be added later after confirming endpoint data format.
"""

import json
import html
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


def build_signal_cards(forest: Dict[str, Any]) -> List[Dict[str, str]]:
    variables = forest.get("macro_variables") or {}
    mapping = [
        ("通膨", "inflation_view", "🧭"),
        ("利率", "rate_view", "🏦"),
        ("美元", "dollar_fx_view", "💵"),
        ("亞幣", "asia_fx_view", "🌏"),
        ("黃金", "gold_view", "🟡"),
        ("能源", "energy_view", "🛢️"),
    ]

    cards = []
    for label, key, icon in mapping:
        cards.append({
            "label": label,
            "icon": icon,
            "text": str(variables.get(key, "") or "資料不足，待觀察").strip(),
        })
    return cards


def render_signal_cards(cards: List[Dict[str, str]]) -> str:
    return "\n".join(
        f"""
        <div class="signal-card">
          <div class="signal-icon">{esc(card['icon'])}</div>
          <div class="signal-label">{esc(card['label'])}</div>
          <div class="signal-text">{esc(card['text'])}</div>
        </div>
        """
        for card in cards
    )


def render_news(news_context: Dict[str, Any]) -> str:
    top_news = news_context.get("top_news") or []
    if not top_news:
        return '<div class="muted-box">本週新聞補充資料不足，待觀察。</div>'

    rows = []
    for item in top_news[:5]:
        if not isinstance(item, dict):
            continue
        title = first_non_empty(item.get("title"), "未命名新聞")
        source = first_non_empty(item.get("source"), "News")
        why = first_non_empty(item.get("why_it_matters"), item.get("theme"), "")
        url = first_non_empty(item.get("url"), "#")
        rows.append(f"""
        <a class="news-card" href="{esc(url)}" target="_blank" rel="noopener noreferrer">
          <div class="news-source">{esc(source)}</div>
          <div class="news-title">{esc(title)}</div>
          <div class="news-why">{esc(why)}</div>
        </a>
        """)
    return "\n".join(rows)


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


def build_html(week_dir: Path, forest: Dict[str, Any], news_context: Dict[str, Any]) -> str:
    summary = forest.get("forest_summary") or {}
    storyline = forest.get("macro_storyline") or {}
    evidence = forest.get("evidence") or {}
    video = forest.get("video_planning") or {}

    week_label = first_non_empty(get_nested(forest, "meta", "week_range"), "資料週期待確認")
    generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    title = first_non_empty(video.get("suggested_video_title"), summary.get("weekly_main_theme"), "本週總經摘要")
    headline = first_non_empty(summary.get("weekly_main_theme"), title)
    verdict = first_non_empty(summary.get("one_sentence_verdict"), summary.get("narrative_arc"), "資料不足，待觀察")
    main_question = first_non_empty(summary.get("main_question"), "下週市場將驗證哪些總經訊號？")

    diagram_exists = (week_dir / "weekly_macro_diagram.png").exists()
    diagram_html = (
        '<img class="diagram-img" src="weekly_macro_diagram.png" alt="本週總經傳導圖解">'
        if diagram_exists
        else '<div class="muted-box">本週總經傳導圖解尚未產生。</div>'
    )

    signal_cards_html = render_signal_cards(build_signal_cards(forest))
    news_html = render_news(news_context)
    scenes_html = render_scene_cards(forest)

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
  --card:#ffffff;
  --ink:#1f2937;
  --muted:#6b7280;
  --line:#e5e0d5;
  --accent:#f59e0b;
  --accent-soft:#fff3d1;
  --shadow:0 18px 45px rgba(31,41,55,.07);
  --radius:22px;
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0;
  background:radial-gradient(circle at top left,#fff7df 0,#f7f7f4 34%,#f4f5f7 100%);
  color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Noto Sans TC","PingFang TC","Microsoft JhengHei",sans-serif;
  line-height:1.65;
}}
.wrap {{ max-width:1180px; margin:0 auto; padding:34px 18px 64px; }}
.header {{ display:flex; justify-content:space-between; gap:18px; align-items:flex-end; margin-bottom:22px; }}
.kicker {{ color:#9a6200; font-weight:850; letter-spacing:.08em; font-size:13px; text-transform:uppercase; }}
.title {{ font-size:36px; line-height:1.2; font-weight:900; margin:6px 0 10px; }}
.subtitle {{ color:#4b5563; font-size:17px; max-width:820px; }}
.meta {{ text-align:right; color:var(--muted); font-size:14px; white-space:nowrap; }}
.section {{
  background:rgba(255,255,255,.78);
  border:1px solid var(--line);
  border-radius:var(--radius);
  box-shadow:var(--shadow);
  padding:24px;
  margin:18px 0;
  backdrop-filter: blur(10px);
}}
.section h2 {{ margin:0 0 16px; font-size:24px; }}
.hero {{
  background:linear-gradient(135deg,#fff7dc 0%,#fffdf7 54%,#f8fafc 100%);
  border:1px solid #ead6a2;
}}
.diagram-img {{
  width:100%;
  display:block;
  border-radius:20px;
  border:1px solid #eadfbf;
  background:#fffdf7;
}}
.summary-grid {{ display:grid; grid-template-columns:1.1fr .9fr; gap:16px; }}
.big-text {{ font-size:20px; font-weight:750; }}
.question {{ background:#fff7ed; border:1px solid #fed7aa; border-radius:16px; padding:16px; color:#7c2d12; font-weight:800; }}
.signals {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.signal-card,.slide-card,.news-card {{
  background:var(--card);
  border:1px solid var(--line);
  border-radius:18px;
  padding:16px;
  text-decoration:none;
  color:inherit;
}}
.signal-icon {{ font-size:26px; }}
.signal-label {{ font-weight:900; font-size:18px; margin:4px 0; }}
.signal-text {{ color:#4b5563; font-size:14px; }}
.two-col {{ display:grid; grid-template-columns:1fr 1fr; gap:16px; }}
ul {{ margin:0; padding-left:22px; }}
.news-grid {{ display:grid; grid-template-columns:repeat(2,1fr); gap:14px; }}
.news-card {{ display:block; transition:.15s ease; }}
.news-card:hover {{ transform:translateY(-2px); box-shadow:0 12px 30px rgba(31,41,55,.09); }}
.news-source {{ color:#9a6200; font-size:13px; font-weight:850; margin-bottom:6px; }}
.news-title {{ font-weight:900; margin-bottom:8px; }}
.news-why {{ color:#4b5563; font-size:14px; }}
.slides {{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; }}
.slide-id {{ color:#9a6200; font-size:12px; font-weight:900; letter-spacing:.08em; text-transform:uppercase; }}
.slide-title {{ font-size:18px; font-weight:900; margin:4px 0; }}
.slide-question {{ color:#7c2d12; font-weight:800; font-size:14px; margin-bottom:8px; }}
.slide-point {{ color:#4b5563; font-size:14px; }}
.muted-box {{ background:#f9fafb; border:1px dashed #d1d5db; color:#6b7280; border-radius:16px; padding:16px; }}
.footer {{ color:var(--muted); font-size:13px; padding:20px 2px; }}
@media(max-width:900px) {{
  .header,.summary-grid,.two-col {{ display:block; }}
  .meta {{ text-align:left; margin-top:10px; }}
  .signals,.slides,.news-grid {{ grid-template-columns:1fr; }}
  .title {{ font-size:30px; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <header class="header">
    <div>
      <div class="kicker">Weekly Macro Summary</div>
      <div class="title">{esc(title)}</div>
      <div class="subtitle">{esc(verdict)}</div>
    </div>
    <div class="meta">
      週期：{esc(week_label)}<br>
      產生時間：{esc(generated_at)}
    </div>
  </header>

  <section class="section hero">
    <h2>本週總經傳導圖解</h2>
    {diagram_html}
  </section>

  <section class="section">
    <h2>Executive Summary</h2>
    <div class="summary-grid">
      <div class="big-text">{esc(headline)}</div>
      <div class="question">{esc(main_question)}</div>
    </div>
    <p>{esc(summary.get("narrative_arc", ""))}</p>
  </section>

  <section class="section">
    <h2>本週市場訊號</h2>
    <div class="signals">{signal_cards_html}</div>
  </section>

  <section class="section">
    <h2>修正因子 / 待觀察</h2>
    <ul>{revision_items}</ul>
  </section>

  <section class="section">
    <h2>本週新聞佐證</h2>
    <div class="news-grid">{news_html}</div>
  </section>

  <section class="section">
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

  <section class="section">
    <h2>週報影片 / 圖卡草稿</h2>
    <div class="slides">{scenes_html}</div>
  </section>

  <div class="footer">
    本頁由 weekly_forest_summary.json、weekly_news_context.json 與 weekly_macro_diagram.png 自動產生。內容為總經資訊整理，不構成投資建議。
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

    if not forest:
        raise FileNotFoundError(f"Missing or empty weekly_forest_summary.json in {week_dir}")

    html_text = build_html(week_dir, forest, news_context)
    out_path = week_dir / "index.html"
    save_text(out_path, html_text)

    print(f"[OK] Weekly macro page created: {out_path}")


if __name__ == "__main__":
    main()
