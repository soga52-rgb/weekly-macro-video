#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Weekly News Context v3

Purpose:
- Build a dynamic one-week macro news context for weekly video generation.
- Search Google News RSS for the same weekly window used by weekly_video_source.
- Preferred sources: UDN / Cnyes / MarketWatch / Investing.
- Reuters and CNBC are excluded in this version.
- Output is used as a correction layer for weekly_forest_summary.

Input:
- data/weekly_video_source.json
- output/weekly/YYYY-MM-DD/weekly_source_text.md

Output:
- data/weekly_news_raw.json
- output/weekly/YYYY-MM-DD/weekly_news_context.json
- output/weekly/YYYY-MM-DD/weekly_news_context.md

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_MODEL, default: gemini-3.5-flash
- WEEKLY_NEWS_MAX_ITEMS, default: 30
"""

import argparse
import email.utils
import html
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_MAX_ITEMS = 30

SOURCE_FILTERS = [
    "site:udn.com",
    "site:cnyes.com",
    "site:marketwatch.com",
    "site:investing.com",
]

NEWS_QUERY_GROUPS = [
    {
        "theme": "long_bond_yields",
        "queries": [
            "美債 殖利率 20年期 30年期",
            "美債 長天期 殖利率 期限溢價",
            "Treasury yields 30-year 20-year inflation premium",
        ],
    },
    {
        "theme": "fed_policy",
        "queries": [
            "Fed 降息 縮表 美債 殖利率",
            "聯準會 高利率 維持更久 殖利率",
            "Federal Reserve rate cut balance sheet Treasury yields",
        ],
    },
    {
        "theme": "dollar_asia_fx",
        "queries": [
            "美元指數 亞洲貨幣 台幣 日圓",
            "美元 亞幣 承壓 台幣 日圓 韓元",
            "dollar index Asia currencies yen Taiwan dollar",
        ],
    },
    {
        "theme": "gold",
        "queries": [
            "黃金 美元 利率 避險 通膨",
            "金價 美債殖利率 美元 避險",
            "gold dollar yields safe haven inflation",
        ],
    },
    {
        "theme": "energy_inflation",
        "queries": [
            "油價 原油 通膨 預期 地緣政治",
            "WTI Brent 原油 通膨 Fed",
            "oil prices inflation expectations geopolitical risk",
        ],
    },
    {
        "theme": "geopolitics",
        "queries": [
            "美伊 伊朗 地緣政治 油價 通膨",
            "中東 地緣政治 原油 通膨",
            "Iran Middle East oil inflation geopolitical risk",
        ],
    },
    {
        "theme": "us_china_trade",
        "queries": [
            "美中 會談 關稅 貿易 市場",
            "美中 關稅 貿易談判 美元",
            "US China talks tariff trade markets",
        ],
    },
]

SYSTEM_PROMPT = """
你是一位專業總經週報新聞編輯。

你的任務是把一週內的新聞候選整理成「週報影片用新聞脈絡」。
你不是要逐篇摘要新聞，而是要判斷：
1. 哪些新聞支撐週報主線。
2. 哪些新聞是修正因子。
3. 哪些新聞只是單日雜訊或待觀察。
4. 新聞是否能修正 daily summaries 的單日背離判斷。

語氣要求：
- 專業、克制、分析師週報風格。
- 不要像媒體標題或自媒體旁白。
- 原始新聞標題可以保留，但你自己的判斷文字不要使用過度戲劇化字眼。
- 避免：崩潰、狂歡、恐慌、徹底、全面、飆升、暴衝、導火線、反撲。
- 若因果關係不是新聞明確支持，請用「可能」、「顯示」、「反映」、「待觀察」。

請使用繁體中文。
"""

USER_PROMPT_TEMPLATE = """
以下有兩份資料：

A. weekly_source_text.md：
這是最近 3～5 天每日總經摘要整合而成的週報來源。

B. weekly_news_candidates：
這是一週內由 Google News RSS 搜尋出的新聞候選。
來源優先包含聯合新聞網、鉅亨網，也可包含 MarketWatch / Investing 等白名單來源。
本版本不使用 Reuters 與 CNBC。

請根據兩者，輸出 weekly_news_context.json。

重要規則：
1. 不要逐篇摘要新聞。
2. 請判斷新聞是否支持 weekly_source_text 的市場主線。
3. 請特別檢查：通膨預期、Fed政策、長天期美債殖利率、美元、亞洲貨幣、黃金、能源、地緣政治、美中關係。
4. 若新聞支持「高利率 → 美元 → 亞幣 / 黃金」傳導，請列入 confirming_signals。
5. 若新聞顯示單日背離或修正因子，請列入 contradicting_signals 或 news_based_corrections。
6. 若只有單一新聞或佐證不足，請標示為「待觀察」，不要改寫整週主線。
7. 不要使用過度戲劇化字眼；新聞原始標題可保留，但你的說明要克制。
8. 只輸出合法 JSON，不要加 Markdown。

新聞分類規則：
- 請務必輸出 news_categories，分成「通膨預期」「利率」「貨幣」「其他」四類。
- 每類最多放 4 則新聞，優先挑對本週主線最有佐證價值者。
- 一則新聞只能放在一類，不要重複。
- 分類以標題與新聞主題優先，why_it_matters 只作輔助。
- 「油價、能源、CPI、PPI、物價、再通膨、通膨黏性」優先放「通膨預期」。
- 「美債殖利率、長債、Fed、聯準會、升息、降息、利率路徑」優先放「利率」。
- 「美元、DXY、新台幣、日圓、韓元、人民幣、亞幣、匯率」優先放「貨幣」。
- 地緣政治若主要影響油價或能源，放「通膨預期」；若無法明確歸類，放「其他」。

請輸出 JSON 結構：

{
  "meta": {
    "source": "Google News RSS",
    "week_range": "",
    "sources_used": [],
    "candidate_count": 0,
    "data_quality_note": ""
  },
  "weekly_news_theme": "",
  "news_fit_to_daily_summaries": "支持 / 部分支持 / 不支持 / 待觀察",
  "macro_drivers": [
    {
      "driver": "",
      "evidence": [],
      "impact": "",
      "confidence": "高 / 中 / 低"
    }
  ],
  "confirming_signals": [],
  "contradicting_signals": [],
  "news_based_corrections": [],
  "watch_points": [],
  "news_categories": {
    "通膨預期": [
      {
        "title": "",
        "source": "",
        "url": "",
        "published_at": "",
        "theme": "inflation_energy",
        "why_it_matters": ""
      }
    ],
    "利率": [
      {
        "title": "",
        "source": "",
        "url": "",
        "published_at": "",
        "theme": "rates_bonds_fed",
        "why_it_matters": ""
      }
    ],
    "貨幣": [
      {
        "title": "",
        "source": "",
        "url": "",
        "published_at": "",
        "theme": "dollar_asia_fx",
        "why_it_matters": ""
      }
    ],
    "其他": [
      {
        "title": "",
        "source": "",
        "url": "",
        "published_at": "",
        "theme": "other_macro",
        "why_it_matters": ""
      }
    ]
  },
  "top_news": [
    {
      "title": "",
      "source": "",
      "url": "",
      "published_at": "",
      "theme": "",
      "why_it_matters": ""
    }
  ],
  "editor_note_for_forest_summary": ""
}

weekly_source_text.md:
{weekly_source_text}

weekly_news_candidates:
{weekly_news_candidates}
"""


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def infer_week_range(week_dir: Path) -> Tuple[str, str, str]:
    source_json = load_json(DATA_DIR / "weekly_video_source.json")
    range_data = source_json.get("range", {}) or {}
    start = str(range_data.get("start_date") or "")
    end = str(range_data.get("end_date") or week_dir.name)
    label = f"{start} ～ {end}" if start else end
    return start, end, label


def build_queries() -> List[Tuple[str, str]]:
    source_clause = "(" + " OR ".join(SOURCE_FILTERS) + ")"
    output = []
    for group in NEWS_QUERY_GROUPS:
        theme = group["theme"]
        for q in group["queries"]:
            output.append((theme, f"{q} {source_clause} when:7d"))
    return output


def google_news_rss_url(query: str) -> str:
    encoded = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"


def parse_pubdate(pubdate: str) -> str:
    if not pubdate:
        return ""
    try:
        dt = email.utils.parsedate_to_datetime(pubdate)
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return pubdate


def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(title or "").strip())


def fetch_rss_items(query: str, theme: str, max_items: int = 8) -> List[Dict[str, Any]]:
    request = urllib.request.Request(
        google_news_rss_url(query),
        headers={
            "User-Agent": "weekly-macro-video-news-context/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            xml_text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[WARN] RSS fetch failed for query={query}: {exc}")
        return []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        print(f"[WARN] RSS parse failed for query={query}: {exc}")
        return []

    items = []
    channel = root.find("channel")
    if channel is None:
        return items

    for item in channel.findall("item")[:max_items]:
        source_el = item.find("source")
        items.append({
            "theme": theme,
            "query": query,
            "title": clean_title(item.findtext("title", "")),
            "source": source_el.text if source_el is not None and source_el.text else "",
            "url": item.findtext("link", "") or "",
            "published_at": parse_pubdate(item.findtext("pubDate", "") or ""),
        })

    return [x for x in items if x["title"] and x["url"]]


def score_item(item: Dict[str, Any]) -> int:
    text = f"{item.get('title','')} {item.get('source','')} {item.get('theme','')}".lower()
    score = 0

    keywords = [
        "美債", "殖利率", "利率", "美元", "通膨", "fed", "聯準會",
        "黃金", "原油", "油價", "台幣", "日圓", "亞洲貨幣",
        "treasury", "yield", "dollar", "inflation", "gold", "oil",
    ]

    for kw in keywords:
        if kw.lower() in text:
            score += 2

    preferred_sources = ["聯合", "經濟日報", "鉅亨", "MarketWatch", "Investing"]
    for src in preferred_sources:
        if src.lower() in text:
            score += 3

    return score


def dedupe_and_rank(items: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    seen = set()
    deduped = []

    for item in items:
        key = re.sub(r"\W+", "", item.get("title", "").lower())[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["score"] = score_item(item)
        deduped.append(item)

    deduped.sort(key=lambda x: x.get("score", 0), reverse=True)
    return deduped[:max_items]


def extract_json_from_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response does not contain a valid JSON object.")

    return json.loads(cleaned[start:end + 1])


def call_gemini_json(system_prompt: str, user_prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.2,
            "topP": 0.85,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini news context HTTPError {exc.code}: {detail}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {api_response}") from exc

    return extract_json_from_text(text)


def build_news_context_markdown(context: Dict[str, Any]) -> str:
    lines = [
        "## 本週新聞補充",
        "",
        "### 新聞主線",
        str(context.get("weekly_news_theme", "資料不足，待觀察")),
        "",
        "### 新聞與每日摘要的關係",
        str(context.get("news_fit_to_daily_summaries", "待觀察")),
        "",
        "### 主要總經驅動",
    ]

    for driver in context.get("macro_drivers", []) or []:
        if not isinstance(driver, dict):
            continue
        lines.append(f"- {driver.get('driver', '')}｜{driver.get('impact', '')}｜信心：{driver.get('confidence', '')}")
        for ev in driver.get("evidence", []) if isinstance(driver.get("evidence", []), list) else []:
            lines.append(f"  - {ev}")

    def add_list(title: str, items: Any) -> None:
        lines.extend(["", f"### {title}"])
        if isinstance(items, list) and items:
            for item in items:
                lines.append(f"- {item}")
        else:
            lines.append("- 資料不足，待觀察")

    add_list("支撐訊號", context.get("confirming_signals"))
    add_list("修正或背離訊號", context.get("contradicting_signals"))
    add_list("新聞校正", context.get("news_based_corrections"))
    add_list("下週觀察", context.get("watch_points"))

    lines.extend(["", "### 代表新聞"])
    top_news = context.get("top_news", []) or []
    if top_news:
        for news in top_news:
            if isinstance(news, dict):
                lines.append(f"- {news.get('source','')}｜{news.get('title','')}｜{news.get('why_it_matters','')}｜{news.get('url','')}")
    else:
        lines.append("- 資料不足，待觀察")

    note = context.get("editor_note_for_forest_summary", "")
    if note:
        lines.extend(["", "### 給 Forest Summary 的編輯提示", str(note)])

    return "\n".join(lines).strip() + "\n"



def normalize_news_categories(context: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure categorized news fields exist and top_news has enough items."""
    categories = context.get("news_categories")
    if not isinstance(categories, dict):
        context["news_categories"] = {
            "通膨預期": [],
            "利率": [],
            "貨幣": [],
            "其他": [],
        }
        categories = context["news_categories"]

    for key in ["通膨預期", "利率", "貨幣", "其他"]:
        if not isinstance(categories.get(key), list):
            categories[key] = []
        categories[key] = [item for item in categories[key] if isinstance(item, dict)][:4]

    # Preserve top_news if present, but supplement it from category buckets.
    top_news = context.get("top_news")
    if not isinstance(top_news, list):
        top_news = []

    seen = set()
    normalized_top = []
    for item in top_news:
        if not isinstance(item, dict):
            continue
        key = (item.get("title") or "", item.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        normalized_top.append(item)

    for bucket in ["通膨預期", "利率", "貨幣", "其他"]:
        for item in categories.get(bucket, []):
            key = (item.get("title") or "", item.get("url") or "")
            if key in seen:
                continue
            seen.add(key)
            normalized_top.append(item)

    context["top_news"] = normalized_top[:12]
    return context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--max-items", type=int, default=int(os.getenv("WEEKLY_NEWS_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))))
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    weekly_source_text = load_text(week_dir / "weekly_source_text.md")
    _, _, week_label = infer_week_range(week_dir)

    all_items: List[Dict[str, Any]] = []
    queries = build_queries()

    for theme, query in queries:
        print(f"[INFO] Fetching news: {theme} | {query}")
        all_items.extend(fetch_rss_items(query, theme=theme, max_items=6))
        time.sleep(0.5)

    ranked = dedupe_and_rank(all_items, max_items=args.max_items)

    raw_package = {
        "meta": {
            "source": "Google News RSS",
            "week_range": week_label,
            "query_count": len(queries),
            "raw_count": len(all_items),
            "ranked_count": len(ranked),
            "sources_preferred": SOURCE_FILTERS,
        },
        "items": ranked,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(DATA_DIR / "weekly_news_raw.json", raw_package)
    print(f"[OK] Saved {DATA_DIR / 'weekly_news_raw.json'}")

    user_prompt = USER_PROMPT_TEMPLATE.replace(
        "{weekly_source_text}", weekly_source_text
    ).replace(
        "{weekly_news_candidates}", json.dumps(ranked, ensure_ascii=False, indent=2)
    )

    print(f"[INFO] Generating weekly news context with model: {model}")
    context = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)

    context.setdefault("meta", {})
    context["meta"]["source"] = "Google News RSS"
    context["meta"]["week_range"] = context["meta"].get("week_range") or week_label
    context["meta"]["candidate_count"] = context["meta"].get("candidate_count") or len(ranked)

    out_json = week_dir / "weekly_news_context.json"
    save_json(out_json, context)
    print(f"[OK] Saved {out_json}")

    out_md = week_dir / "weekly_news_context.md"
    save_text(out_md, build_news_context_markdown(context))
    print(f"[OK] Saved {out_md}")


if __name__ == "__main__":
    main()
