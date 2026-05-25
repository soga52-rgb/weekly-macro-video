#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Macro Background Context Test

Purpose:
- Build a 2-4 week macro background context for weekly video generation.
- This is a TEST script and intentionally starts with 93.
- It complements weekly_news_context.json with broad macro and event-shock background.
- It maximizes recall with broad atomic queries; deeper judgment is left to Step 91.
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
- MACRO_BACKGROUND_ITEMS_PER_QUERY, default: 8
- MACRO_BACKGROUND_USE_SOURCE_FILTERS, default: false
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
DEFAULT_ITEMS_PER_QUERY = 8

SOURCE_FILTERS = [
    "site:udn.com",
    "site:money.udn.com",
    "site:cnyes.com",
    "site:ctee.com.tw",
    "site:moneydj.com",
    "site:marketwatch.com",
    "site:investing.com",
    "site:bloomberg.com",
    "site:reuters.com",
]

BACKGROUND_QUERY_GROUPS = [
    {
        "theme": "inflation_background",
        "queries": [
            "通膨 CPI",
            "PPI PCE PMI 物價",
            "通膨 黏性 預期",
            "US inflation CPI PPI PCE",
        ],
    },
    {
        "theme": "inflation_energy_background",
        "queries": [
            "油價 原油 能源 通膨",
            "WTI Brent 原油 油價",
            "energy prices oil inflation",
            "crude oil prices inflation expectations",
        ],
    },
    {
        "theme": "labor_background",
        "queries": [
            "美國 就業 薪資",
            "非農 失業率 薪資",
            "US jobs wages unemployment",
            "labor market wage growth inflation",
        ],
    },
    {
        "theme": "fed_policy_background",
        "queries": [
            "Fed 聯準會 利率",
            "Fed 官員 鷹派 會議紀錄",
            "升息 降息 高利率",
            "Federal Reserve rate hike hawkish officials",
        ],
    },
    {
        "theme": "bond_market_stress",
        "queries": [
            "美債 殖利率 長債",
            "美債 拋售 殖利率 飆升",
            "Treasury yields bond selloff",
            "long bond yields surge",
        ],
    },
    {
        "theme": "fiscal_term_premium_background",
        "queries": [
            "期限溢價 財政赤字",
            "美債 拍賣 國債 供給",
            "term premium fiscal deficit Treasury auction",
            "bond supply demand Treasury market",
        ],
    },
    {
        "theme": "geopolitics_commodity_background",
        "queries": [
            "地緣政治 油價 能源",
            "中東 伊朗 原油",
            "美伊 談判 油價",
            "geopolitical risk oil prices Middle East",
            "Iran oil supply risk",
        ],
    },
    {
        "theme": "policy_shock_background",
        "queries": [
            "川普 關稅 市場",
            "制裁 貿易政策 美元",
            "tariff policy shock markets",
            "sanctions trade policy dollar",
        ],
    },
    {
        "theme": "dollar_fx_gold_background",
        "queries": [
            "美元指數 亞幣 黃金",
            "日圓 韓圜 台幣 美元",
            "gold dollar yields safe haven",
            "Asia currencies dollar yen won Taiwan dollar",
        ],
    },
]

SYSTEM_PROMPT = """
你是一位總經新聞資料前處理編輯。

你的任務不是做最終研判，而是把近 2～4 週仍可能影響本週市場定價的背景新聞，整理成乾淨、可供下一階段 Pro 模型推理的 macro_background_context。

核心任務：
1. 最大化召回率：不要漏掉可能影響市場預期的總經、政策、能源、地緣、債市、美元、匯率與黃金新聞。
2. 標準化分類：請依新聞的主要影響路徑分類，不要硬塞、不平均分配、不為湊數放入低相關新聞。
3. 保留自然比重：如果本週長債 / Fed 新聞多，就讓該類較多；如果通膨 / 地緣 / 匯率新聞少，就如實較少。
4. 輕量說明：why_it_matters 只需說明這則新聞可能影響哪個市場預期，不要做完整投資結論。
5. 不做最終判斷：不要在本階段判定通膨預期 strong / weak，也不要替市場下最終結論；這些留給 Step 91。

背景類別：
- inflation_background：物價、通膨、CPI / PPI / PCE / PMI、通膨預期。
- inflation_energy_background：油價、原油、能源、供應風險對通膨的影響。
- labor_background：就業、薪資、失業率、勞動市場。
- fed_policy_background：Fed 官員談話、會議紀錄、升息 / 降息 / 高利率路徑。
- bond_market_stress：美債殖利率、長債拋售、全球長債、債市壓力。
- fiscal_term_premium_background：期限溢價、財政赤字、拍賣需求、長債供需。
- geopolitics_commodity_background：地緣政治、中東、伊朗、美伊、供應風險、避險需求。
- policy_shock_background：關稅、制裁、貿易政策、政策突變。
- dollar_fx_gold_background：美元、亞幣、日圓、韓圜、台幣、黃金、避險。

signal 欄位請使用下列固定值之一：
- support_inflation
- cool_inflation
- support_labor_strength
- support_policy_guidance
- support_rate_expectation
- support_term_premium
- support_bond_supply_pressure
- support_growth_slowdown
- support_dollar_strength
- support_fx_pressure
- support_gold_safe_haven
- support_geopolitical_risk
- support_energy_supply_risk
- support_policy_shock
- mixed
- unclear

規則：
- 請使用繁體中文。
- 只輸出合法 JSON，不要 Markdown。
- 若資料不足，請標示「資料不足」或「待觀察」，不要硬下結論。
- 每則新聞只放入一個最主要類別；若同時影響多個面向，在 why_it_matters 裡補充。
- 不要把單一新聞直接等同於整體總經預期。
"""

USER_PROMPT_TEMPLATE = """
以下資料包含：
A. weekly_source_text：本週已整理的市場敘事。
B. weekly_news_context：近 7 天新聞脈絡。
C. macro_background_candidates：近 {lookback_days} 天由 Google News RSS 搜尋出的背景資料候選。

請產生 macro_background_context.json。

請注意：
- 本階段是資料前處理，不是最終分析。
- 請保留與市場預期可能相關的背景新聞，並依主要影響路徑分類。
- 不要平均分配，不要硬湊類別，也不要為特定標的保留名額。
- 若某類新聞自然較多，可以較多；若某類新聞自然較少，可以較少。
- why_it_matters 請說明這則新聞可能影響通膨、利率、美元、匯率、黃金、能源、政策或避險中的哪一個面向。
- 不要輸出 background_assessment_for_91；最後研判留給 Step 91。

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
      "signal": "support_inflation / cool_inflation / support_labor_strength / support_policy_guidance / support_rate_expectation / support_term_premium / support_bond_supply_pressure / support_growth_slowdown / support_dollar_strength / support_fx_pressure / support_gold_safe_haven / support_geopolitical_risk / support_energy_supply_risk / support_policy_shock / mixed / unclear",
      "url": ""
    }}
  ],
  "inflation_energy_background": [],
  "labor_background": [],
  "fed_policy_background": [],
  "bond_market_stress": [],
  "fiscal_term_premium_background": [],
  "geopolitics_commodity_background": [],
  "policy_shock_background": [],
  "dollar_fx_gold_background": [],
  "top_background_items": [],
  "editor_note_for_step_91": ""
}}

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


def should_use_source_filters() -> bool:
    return os.getenv("MACRO_BACKGROUND_USE_SOURCE_FILTERS", "false").strip().lower() in {"1", "true", "yes", "y"}


def build_queries(lookback_days: int) -> List[Tuple[str, str]]:
    output = []
    source_clause = ""
    if should_use_source_filters():
        source_clause = " (" + " OR ".join(SOURCE_FILTERS) + ")"

    for group in BACKGROUND_QUERY_GROUPS:
        theme = group["theme"]
        for q in group["queries"]:
            output.append((theme, f"{q}{source_clause} when:{lookback_days}d"))
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

    macro_kw = [
        "cpi", "ppi", "pce", "pmi", "通膨", "物價", "薪資", "就業", "非農",
        "fed", "聯準會", "升息", "降息", "高利率", "inflation", "wage", "jobs",
    ]
    bond_kw = [
        "美債", "殖利率", "長債", "期限溢價", "赤字", "拍賣", "債券",
        "treasury", "yield", "term premium", "bond auction", "bond selloff",
    ]
    shock_kw = [
        "油價", "原油", "能源", "地緣", "中東", "伊朗", "美伊", "衝突", "戰爭",
        "停火", "協議", "和談", "封鎖", "荷姆茲", "供應風險", "避險",
        "crude", "oil", "energy", "geopolitical", "middle east", "iran", "supply shock",
    ]
    policy_kw = [
        "川普", "關稅", "制裁", "貿易", "政策突變",
        "trump", "tariff", "sanctions", "trade policy", "policy shock",
    ]
    fx_gold_kw = [
        "美元", "美元指數", "亞幣", "日圓", "韓圜", "韓元", "台幣", "新台幣",
        "黃金", "gold", "dollar", "yen", "won", "taiwan dollar", "safe haven",
    ]

    for kw in macro_kw:
        if kw.lower() in text:
            score += 2
    for kw in bond_kw:
        if kw.lower() in text:
            score += 3
    for kw in shock_kw:
        if kw.lower() in text:
            score += 3
    for kw in policy_kw:
        if kw.lower() in text:
            score += 3
    for kw in fx_gold_kw:
        if kw.lower() in text:
            score += 2

    preferred_sources = [
        "聯合", "經濟日報", "鉅亨", "工商", "MoneyDJ",
        "MarketWatch", "Investing", "Bloomberg", "Reuters",
    ]
    for src in preferred_sources:
        if src.lower() in text:
            score += 2

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
        "support_geopolitical_risk",
        "support_energy_supply_risk",
        "support_policy_shock",
        "mixed",
        "unclear",
    }

    for key in [
        "inflation_background",
        "inflation_energy_background",
        "labor_background",
        "fed_policy_background",
        "bond_market_stress",
        "fiscal_term_premium_background",
        "geopolitics_commodity_background",
        "policy_shock_background",
        "dollar_fx_gold_background",
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

    return context

def build_markdown(context: Dict[str, Any]) -> str:
    lines = [
        "## 近 2～4 週總經與事件衝擊背景資料",
        "",
        "### 背景主線",
        str(context.get("background_theme", "資料不足，待觀察")),
    ]

    def add_items(title: str, key: str) -> None:
        lines.extend(["", f"### {title}"])
        items = context.get(key, [])
        if isinstance(items, list) and items:
            for item in items:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('source','')}｜{item.get('title','')}｜"
                        f"{item.get('signal','')}｜{item.get('why_it_matters','')}｜{item.get('url','')}"
                    )
                else:
                    lines.append(f"- {item}")
        else:
            lines.append("- 資料不足，待觀察")

    add_items("通膨背景", "inflation_background")
    add_items("能源與通膨背景", "inflation_energy_background")
    add_items("就業背景", "labor_background")
    add_items("Fed 政策背景", "fed_policy_background")
    add_items("債市壓力背景", "bond_market_stress")
    add_items("財政與期限溢價背景", "fiscal_term_premium_background")
    add_items("地緣與商品背景", "geopolitics_commodity_background")
    add_items("政策衝擊背景", "policy_shock_background")
    add_items("美元 / 匯率 / 黃金背景", "dollar_fx_gold_background")

    note = context.get("editor_note_for_step_91") or context.get("editor_note_for_forest_summary", "")
    if note:
        lines.extend(["", "### 給 Step 91 的資料提示", str(note)])

    return "\n".join(lines).strip() + "\n"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--max-items", type=int, default=int(os.getenv("MACRO_BACKGROUND_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))))
    parser.add_argument("--lookback-days", type=int, default=int(os.getenv("MACRO_BACKGROUND_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))))
    parser.add_argument("--items-per-query", type=int, default=int(os.getenv("MACRO_BACKGROUND_ITEMS_PER_QUERY", str(DEFAULT_ITEMS_PER_QUERY))))
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
        all_items.extend(fetch_rss_items(query, theme=theme, max_items=args.items_per_query))
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
            "use_source_filters": should_use_source_filters(),
            "items_per_query": args.items_per_query,
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
