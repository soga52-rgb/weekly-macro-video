#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Macro Background Context Test

Purpose:
- Build a 2-4 week macro background context for weekly video generation.
- This is a TEST script and intentionally starts with 93.
- It complements weekly_news_context.json with still-relevant macro background:
  inflation, labor, Fed policy, global long bonds, fiscal / term premium.
- Output is used by Step 91 as a background layer, not as a replacement for weekly news.

Input:
- data/weekly_video_source.json optional
- output/weekly/YYYY-MM-DD/weekly_source_text.md optional
- output/weekly/YYYY-MM-DD/weekly_news_context.json optional

Output:
- data/macro_background_raw.json
- output/weekly/YYYY-MM-DD/macro_background_context.json
- output/weekly/YYYY-MM-DD/macro_background_context.md

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_MODEL, default: gemini-3.5-flash
- MACRO_BACKGROUND_MAX_ITEMS, default: 40
- MACRO_BACKGROUND_LOOKBACK_DAYS, default: 30
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_MAX_ITEMS = 40
DEFAULT_LOOKBACK_DAYS = 30

SOURCE_FILTERS = [
    "site:udn.com",
    "site:cnyes.com",
    "site:marketwatch.com",
    "site:investing.com",
]

BACKGROUND_QUERY_GROUPS = [
    {
        "theme": "inflation_background",
        "queries": [
            "美國 CPI PPI 通膨 黏性 市場預期",
            "美國 PCE CPI PPI 通膨 預期 Fed",
            "US CPI PPI PCE inflation expectations sticky inflation",
        ],
    },
    {
        "theme": "labor_background",
        "queries": [
            "美國 就業 薪資 通膨 聯準會 利率",
            "非農 就業 薪資 通膨 預期 Fed",
            "US jobs wage growth inflation expectations Federal Reserve",
        ],
    },
    {
        "theme": "fed_policy_background",
        "queries": [
            "Fed 官員 升息 降息 高利率 更久",
            "聯準會 會議紀錄 升息可能 高利率",
            "Federal Reserve officials rate hikes higher for longer",
        ],
    },
    {
        "theme": "global_bond_background",
        "queries": [
            "全球 長債 殖利率 美國 英國 日本 德國",
            "長天期 公債 殖利率 全球 上升 通膨",
            "global long bond yields US UK Japan Germany inflation",
        ],
    },
    {
        "theme": "fiscal_term_premium_background",
        "queries": [
            "美債 期限溢價 財政赤字 長債 供需",
            "美國 財政赤字 美債 拍賣 期限溢價",
            "Treasury term premium fiscal deficit bond supply demand auction",
        ],
    },
]

SYSTEM_PROMPT = """
你是一位專業總經資料編輯。

你的任務是把近 2～4 週仍可能影響本週市場定價的背景資料整理成 macro_background_context。
這不是一般新聞摘要，而是要補足週報分析中「預期形成的背景」。

請特別整理五大背景類別：
1. 通膨背景：CPI / PPI / PCE / PMI價格分項 / 通膨黏性 / 消費者通膨預期 / 油價。
2. 就業與薪資背景：非農、失業率、薪資、勞動市場是否仍支撐通膨或高利率。
3. Fed政策背景：官員談話、會議紀錄、降息或升息可能、高利率維持更久。
4. 全球長債背景：美、英、日、德等長天期殖利率是否同步上升。
5. 財政與期限溢價背景：赤字、長債供需、拍賣需求、期限溢價。

signal 欄位請使用下列固定值之一：
- support_inflation：直接支撐通膨壓力或通膨黏性的資料，例如 CPI / PPI / PCE / PMI價格 / 薪資偏強。
- cool_inflation：直接壓低通膨壓力的資料，例如油價下跌、供應風險降溫。
- support_labor_strength：就業或薪資顯示勞動市場仍具韌性。
- support_policy_guidance：Fed 官員談話、會議紀錄或政策路徑使利率預期偏鷹。
- support_rate_expectation：直接支持利率預期走高或高利率維持更久。
- support_term_premium：期限溢價、長債風險補償或長端殖利率重估。
- support_bond_supply_pressure：長債供給、拍賣需求疲弱、財政赤字或債務供給壓力。
- support_growth_slowdown：成長、房市、消費或企業活動放緩。
- support_dollar_strength：利差、避險或政策預期支撐美元。
- support_fx_pressure：非美貨幣、亞幣、日圓、韓圜、台幣面臨壓力。
- support_gold_safe_haven：避險需求、地緣政治或成長風險支撐黃金。
- mixed：同一類資料多空交錯。
- unclear：資料不足或訊號不明確。

分類規則：
- Fed 鷹派、會議紀錄、升息選項，不要自動歸類為 support_inflation；通常應歸類為 support_policy_guidance 或 support_rate_expectation。
- 長天期殖利率上升、全球長債拋售、30年期美債突破，不要自動歸類為 support_inflation；通常應歸類為 support_term_premium 或 support_rate_expectation。
- 長債拍賣需求疲弱、財政赤字、債務供給壓力，應歸類為 support_bond_supply_pressure。
- 油價下跌只能代表能源端通膨壓力降溫，不可直接推論整體通膨預期明確轉弱。
- 若 CPI / PPI / PCE / 就業 / 薪資偏強與油價下跌同時存在，請在 background_assessment_for_91 中提醒：通膨預期應偏 mixed / 待確認，而不是明確 weak 或 strong。

規則：
- 請使用繁體中文。
- 只輸出合法 JSON，不要 Markdown。
- 若資料不足，請標示「資料不足」或「待觀察」，不要硬下結論。
- 請區分「本週事件」與「仍具影響力的背景資料」。
- 不要把單一新聞直接等同於整體總經預期，除非有跨資料佐證。
"""

USER_PROMPT_TEMPLATE = """
以下資料包含：
A. weekly_source_text：本週已整理的市場敘事。
B. weekly_news_context：近 7 天新聞脈絡。
C. macro_background_candidates：近 {lookback_days} 天由 Google News RSS 搜尋出的背景資料候選。

請產生 macro_background_context.json。

輸出結構如下：

{{
  "meta": {{
    "source": "Google News RSS",
    "lookback_days": {lookback_days},
    "week_range": "",
    "candidate_count": 0,
    "data_quality_note": ""
  }},
  "background_theme": "",
  "inflation_background": [
    {{
      "title": "",
      "source": "",
      "published_at": "",
      "why_it_matters": "",
      "signal": "support_inflation / cool_inflation / support_labor_strength / support_policy_guidance / support_rate_expectation / support_term_premium / support_bond_supply_pressure / support_growth_slowdown / support_dollar_strength / support_fx_pressure / support_gold_safe_haven / mixed / unclear",
      "url": ""
    }}
  ],
  "labor_background": [],
  "fed_policy_background": [],
  "global_bond_background": [],
  "fiscal_term_premium_background": [],
  "background_assessment_for_91": {{
    "inflation_expectation_note": "",
    "rate_expectation_note": "",
    "dollar_note": "",
    "asia_fx_gold_note": "",
    "key_cautions": []
  }},
  "top_background_items": [],
  "editor_note_for_forest_summary": ""
}}

判斷重點：
- inflation_background 只放直接影響通膨或通膨預期的資料。
- Fed 政策、長債殖利率、期限溢價、長債供需，應分別放入 fed_policy_background、global_bond_background、fiscal_term_premium_background，不要硬塞進 inflation_background。
- background_assessment_for_91 請協助 91 判斷：
  1. 通膨預期是 strong / mixed / weak / unclear。
  2. 利率預期主要來自 inflation / policy_guidance / term_premium / bond_supply_demand / mixed / unclear。
  3. 美元是否受利差、避險或政策預期支撐。
  4. 亞幣與黃金是否出現同頻、分化或避險支撐。
- 若通膨資料多空交錯，請明確提醒 91：不要只因油價下跌就判斷通膨預期 weak。

weekly_source_text:
{weekly_source_text}

weekly_news_context:
{weekly_news_context}

macro_background_candidates:
{macro_background_candidates}
"""


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
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


def resolve_week_dir(value: str) -> Path:
    if value:
        week_dir = Path(value)
        if not week_dir.exists() and not week_dir.is_absolute():
            candidate = OUTPUT_WEEKLY_DIR / value
            if candidate.exists():
                return candidate
        return week_dir
    return find_latest_week_dir()


def infer_week_range(week_dir: Path) -> Tuple[str, str, str]:
    source_json = load_json(DATA_DIR / "weekly_video_source.json", {})
    range_data = source_json.get("range", {}) or {}
    start = str(range_data.get("start_date") or "")
    end = str(range_data.get("end_date") or week_dir.name)
    label = f"{start} ～ {end}" if start else end
    return start, end, label


def build_queries(lookback_days: int) -> List[Tuple[str, str]]:
    source_clause = "(" + " OR ".join(SOURCE_FILTERS) + ")"
    output = []
    for group in BACKGROUND_QUERY_GROUPS:
        theme = group["theme"]
        for q in group["queries"]:
            output.append((theme, f"{q} {source_clause} when:{lookback_days}d"))
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
            "User-Agent": "weekly-macro-video-background-context/1.0",
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
        "cpi", "ppi", "pce", "pmi", "通膨", "物價", "薪資", "就業", "非農",
        "fed", "聯準會", "升息", "降息", "高利率",
        "美債", "殖利率", "長債", "期限溢價", "赤字", "拍賣",
        "treasury", "yield", "term premium", "inflation", "wage", "jobs",
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
        raise RuntimeError(f"Gemini macro background HTTPError {exc.code}: {detail}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {api_response}") from exc

    return extract_json_from_text(text)


def normalize_background_context(context: Dict[str, Any]) -> Dict[str, Any]:
    allowed_signals = {
        "support_inflation",
        "cool_inflation",
        "support_labor_strength",
        "support_policy_guidance",
        "support_rate_expectation",
        "support_term_premium",
        "support_bond_supply_pressure",
        "support_growth_slowdown",
        "support_dollar_strength",
        "support_fx_pressure",
        "support_gold_safe_haven",
        "mixed",
        "unclear",
    }

    for key in [
        "inflation_background",
        "labor_background",
        "fed_policy_background",
        "global_bond_background",
        "fiscal_term_premium_background",
        "top_background_items",
    ]:
        if not isinstance(context.get(key), list):
            context[key] = []

        normalized_items = []
        for item in context[key]:
            if not isinstance(item, dict):
                normalized_items.append(item)
                continue

            signal = str(item.get("signal", "")).strip()
            if signal and signal not in allowed_signals:
                item["signal"] = "unclear"
            elif not signal:
                item["signal"] = "unclear"
            normalized_items.append(item)

        context[key] = normalized_items

    if not isinstance(context.get("background_assessment_for_91"), dict):
        context["background_assessment_for_91"] = {
            "inflation_expectation_note": "",
            "rate_expectation_note": "",
            "dollar_note": "",
            "asia_fx_gold_note": "",
            "key_cautions": [],
        }

    assessment = context["background_assessment_for_91"]
    if not isinstance(assessment.get("key_cautions"), list):
        assessment["key_cautions"] = []

    return context

def build_markdown(context: Dict[str, Any]) -> str:
    lines = [
        "## 近 2～4 週總經背景資料",
        "",
        "### 背景主線",
        str(context.get("background_theme", "資料不足，待觀察")),
        "",
        "### 給 91 的背景判斷",
    ]

    assessment = context.get("background_assessment_for_91", {}) or {}
    for key, label in [
        ("inflation_expectation_note", "通膨預期"),
        ("rate_expectation_note", "利率預期"),
        ("dollar_note", "美元"),
        ("asia_fx_gold_note", "亞幣與黃金"),
    ]:
        value = assessment.get(key, "")
        if value:
            lines.append(f"- {label}：{value}")

    def add_items(title: str, key: str) -> None:
        lines.extend(["", f"### {title}"])
        items = context.get(key, [])
        if isinstance(items, list) and items:
            for item in items:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('source','')}｜{item.get('title','')}｜{item.get('why_it_matters','')}｜{item.get('url','')}")
                else:
                    lines.append(f"- {item}")
        else:
            lines.append("- 資料不足，待觀察")

    add_items("通膨背景", "inflation_background")
    add_items("就業背景", "labor_background")
    add_items("Fed 政策背景", "fed_policy_background")
    add_items("全球長債背景", "global_bond_background")
    add_items("財政與期限溢價背景", "fiscal_term_premium_background")

    note = context.get("editor_note_for_forest_summary", "")
    if note:
        lines.extend(["", "### 給 Forest Summary 的編輯提示", str(note)])

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--max-items", type=int, default=int(os.getenv("MACRO_BACKGROUND_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))))
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("MACRO_BACKGROUND_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))))
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    week_dir = resolve_week_dir(args.week_dir)

    weekly_source_text = load_text(week_dir / "weekly_source_text.md")
    weekly_news_context = load_json(week_dir / "weekly_news_context.json", {})
    _, _, week_label = infer_week_range(week_dir)

    all_items: List[Dict[str, Any]] = []
    queries = build_queries(args.lookback_days)

    for theme, query in queries:
        print(f"[INFO] Fetching macro background: {theme} | {query}")
        all_items.extend(fetch_rss_items(query, theme=theme, max_items=6))
        time.sleep(0.5)

    ranked = dedupe_and_rank(all_items, max_items=args.max_items)

    raw_package = {
        "meta": {
            "source": "Google News RSS",
            "week_range": week_label,
            "lookback_days": args.lookback_days,
            "query_count": len(queries),
            "raw_count": len(all_items),
            "ranked_count": len(ranked),
            "sources_preferred": SOURCE_FILTERS,
        },
        "items": ranked,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(DATA_DIR / "macro_background_raw.json", raw_package)
    print(f"[OK] Saved {DATA_DIR / 'macro_background_raw.json'}")

    user_prompt = USER_PROMPT_TEMPLATE.replace(
        "{lookback_days}", str(args.lookback_days)
    ).replace(
        "{weekly_source_text}", weekly_source_text
    ).replace(
        "{weekly_news_context}", json.dumps(weekly_news_context, ensure_ascii=False, indent=2)
    ).replace(
        "{macro_background_candidates}", json.dumps(ranked, ensure_ascii=False, indent=2)
    )

    print(f"[INFO] Generating macro background context with model: {model}")
    context = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    context = normalize_background_context(context)

    context.setdefault("meta", {})
    context["meta"]["source"] = "Google News RSS"
    context["meta"]["week_range"] = context["meta"].get("week_range") or week_label
    context["meta"]["lookback_days"] = context["meta"].get("lookback_days") or args.lookback_days
    context["meta"]["candidate_count"] = context["meta"].get("candidate_count") or len(ranked)

    out_json = week_dir / "macro_background_context.json"
    save_json(out_json, context)
    print(f"[OK] Saved {out_json}")

    out_md = week_dir / "macro_background_context.md"
    save_text(out_md, build_markdown(context))
    print(f"[OK] Saved {out_md}")


if __name__ == "__main__":
    main()
