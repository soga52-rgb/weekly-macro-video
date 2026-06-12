#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Weekly News Context v3

Purpose:
- Build a dynamic macro news context for weekly video generation.
- Search Google News RSS for the same analysis window used by weekly source.
- Keep a lookback window for macro hard-data releases with continuing effects.
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
- ANALYSIS_START_DATE / --start = YYYY-MM-DD
- ANALYSIS_END_DATE   / --end   = YYYY-MM-DD
- WEEK_DIR / --week-dir
- GEMINI_MODEL, default: gemini-3.5-flash
- WEEKLY_NEWS_MAX_ITEMS, default: 30
- WEEKLY_NEWS_LOOKBACK_DAYS, default: 14
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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DEFAULT_MODEL = "gemini-3.5-flash"
DEFAULT_MAX_ITEMS = 30
DEFAULT_LOOKBACK_DAYS = 14

SOURCE_FILTERS = [
    "site:udn.com",
    "site:cnyes.com",
    "site:marketwatch.com",
    "site:investing.com",
]

NEWS_QUERY_GROUPS = [
    {
        "theme": "us_macro_data",
        "queries": [
            "美國 CPI 4.2 通膨 Fed",
            "美國 CPI 通膨 超出預期 聯準會",
            "美國 PPI 生產者物價 通膨 Fed",
            "美國 非農 就業 大增 超出預期 Fed",
            "美國 就業報告 非農 薪資 通膨",
            "US CPI inflation 4.2 Federal Reserve",
            "US PPI producer prices inflation Fed",
            "nonfarm payrolls jobs report stronger than expected Fed",
            "initial jobless claims labor market Fed",
        ],
    },
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
這是由 Google News RSS 搜尋出的新聞候選。
來源優先包含聯合新聞網、鉅亨網，也可包含 MarketWatch / Investing 等白名單來源。
本版本不使用 Reuters 與 CNBC。

正式分析區間：
{analysis_window_label}

重要規則：
1. 不要逐篇摘要新聞。
2. 請判斷新聞是否支持 weekly_source_text 的市場主線。
3. 請特別檢查：CPI、PPI、非農就業、初領失業金、通膨預期、Fed政策、長天期美債殖利率、美元、亞洲貨幣、黃金、能源、地緣政治、美中關係。
4. 若新聞支持「高利率 → 美元 → 亞幣 / 黃金」傳導，請列入 confirming_signals。
5. 若新聞顯示單日背離或修正因子，請列入 contradicting_signals 或 news_based_corrections。
6. 若只有單一新聞或佐證不足，請標示為「待觀察」，不要改寫整週主線。
7. 不要使用過度戲劇化字眼；新聞原始標題可保留，但你的說明要克制。
8. 只輸出合法 JSON，不要加 Markdown。

新聞分類規則：
- 請務必輸出 news_categories，分成「通膨預期」「利率」「貨幣」「其他」四類。
- 不要平均分配新聞，也不要為了湊數把低相關新聞放進分類。
- 請依本週新聞密度與重要性自然分配：新聞較少的類別可以只放 0～2 則；新聞明顯較多的類別可以放 5～8 則。
- 每類最多 8 則，優先挑對本週主線最有佐證價值者。
- 請優先保留正式分析區間內或靠近週末最新交易日的新聞；較早新聞可作為前期脈絡，尤其是 PPI、CPI、非農、Fed 指引等會延續影響本週定價的總經參數，但不要讓舊新聞取代本週主線。
- 一則新聞只能放在一類，不要重複。
- news_categories 每則新聞都必須保留原始候選新聞的 title、source、url、published_at，並新增 why_it_matters。
- top_news 每則新聞也必須保留 title、source、url、published_at，並新增 why_it_matters。
- 不要改寫新聞標題；title 必須盡量沿用 weekly_news_candidates 的原始 title，以便後續網頁連結。
- 分類以標題與新聞主題優先，why_it_matters 只作輔助。
- 「油價、能源、CPI、PPI、物價、再通膨、通膨黏性」優先放「通膨預期」。
- 「非農、就業報告、初領失業金」若標題主軸是就業數據本身，優先放「利率」或作為 Fed 政策路徑佐證；若明確連到薪資通膨，可放「通膨預期」。
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
  "macro_drivers": [],
  "confirming_signals": [],
  "contradicting_signals": [],
  "news_based_corrections": [],
  "watch_points": [],
  "news_categories": {
    "通膨預期": [],
    "利率": [],
    "貨幣": [],
    "其他": []
  },
  "top_news": [],
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


def resolve_week_dir(week_dir_arg: str) -> Path:
    week_dir_arg = (week_dir_arg or "").strip()
    if not week_dir_arg:
        return find_latest_week_dir()

    raw = Path(week_dir_arg)
    if raw.is_absolute():
        return raw
    if len(week_dir_arg) == 10 and week_dir_arg[4] == "-" and week_dir_arg[7] == "-":
        return OUTPUT_WEEKLY_DIR / week_dir_arg
    return ROOT_DIR / raw


def infer_week_range(week_dir: Path, start_override: str = "", end_override: str = "") -> Tuple[str, str, str]:
    if start_override or end_override:
        start = start_override
        end = end_override or week_dir.name
        label = f"{start} ～ {end}" if start else end
        return start, end, label

    source_json = load_json(DATA_DIR / "weekly_video_source.json")
    requested = source_json.get("requested_analysis_window", {}) if isinstance(source_json, dict) else {}
    start = str(requested.get("start_date") or "")
    end = str(requested.get("end_date") or "")

    if not start or not end:
        range_data = source_json.get("range", {}) or {}
        start = str(range_data.get("start_date") or "")
        end = str(range_data.get("end_date") or week_dir.name)

    label = f"{start} ～ {end}" if start else end
    return start, end, label


def build_queries() -> List[Tuple[str, str]]:
    source_clause = "(" + " OR ".join(SOURCE_FILTERS) + ")"
    lookback_days = str(os.getenv("WEEKLY_NEWS_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))).strip() or str(DEFAULT_LOOKBACK_DAYS)
    output = []
    for group in NEWS_QUERY_GROUPS:
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


def pubdate_to_datetime(value: str) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S UTC", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        dt = email.utils.parsedate_to_datetime(value)
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


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


def score_item(item: Dict[str, Any], week_start: str = "", week_end: str = "") -> int:
    text = f"{item.get('title','')} {item.get('source','')} {item.get('theme','')} {item.get('query','')}".lower()
    score = 0

    keywords = [
        "美債", "殖利率", "利率", "美元", "通膨", "fed", "聯準會",
        "黃金", "原油", "油價", "台幣", "日圓", "亞洲貨幣",
        "treasury", "yield", "dollar", "inflation", "gold", "oil",
        "cpi", "ppi", "物價", "非農", "就業", "就業報告", "初領失業金",
        "payroll", "payrolls", "jobs report", "employment", "jobless claims",
    ]

    for kw in keywords:
        if kw.lower() in text:
            score += 2

    hard_data_keywords = [
        "cpi", "ppi", "consumer price", "producer price", "物價", "通膨率",
        "非農", "就業報告", "薪資", "失業率", "初領失業金",
        "payroll", "payrolls", "jobs report", "employment report", "jobless claims",
    ]
    if any(kw.lower() in text for kw in hard_data_keywords):
        score += 8

    preferred_sources = ["聯合", "經濟日報", "鉅亨", "MarketWatch", "Investing"]
    for src in preferred_sources:
        if src.lower() in text:
            score += 3

    published = pubdate_to_datetime(str(item.get("published_at") or ""))
    if published:
        published_date = published.date()
        start_dt = None
        end_dt = None
        try:
            if week_start:
                start_dt = datetime.strptime(week_start, "%Y-%m-%d").date()
            if week_end:
                end_dt = datetime.strptime(week_end, "%Y-%m-%d").date()
        except ValueError:
            start_dt = None
            end_dt = None

        if start_dt and end_dt:
            if start_dt <= published_date <= end_dt:
                score += 12
            elif start_dt - timedelta(days=7) <= published_date < start_dt:
                score += 5
            elif end_dt < published_date <= end_dt + timedelta(days=2):
                score += 4
        else:
            age_days = (datetime.now(timezone.utc) - published).days
            if age_days <= 2:
                score += 10
            elif age_days <= 5:
                score += 6
            elif age_days <= 10:
                score += 3

    return score


def dedupe_and_rank(items: List[Dict[str, Any]], max_items: int, week_start: str = "", week_end: str = "") -> List[Dict[str, Any]]:
    seen = set()
    deduped = []

    for item in items:
        key = re.sub(r"\W+", "", item.get("title", "").lower())[:80]
        if not key or key in seen:
            continue
        seen.add(key)
        item = dict(item)
        item["score"] = score_item(item, week_start=week_start, week_end=week_end)
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
        if isinstance(driver, dict):
            lines.append(f"- {driver.get('driver', '')}｜{driver.get('impact', '')}｜信心：{driver.get('confidence', '')}")
        else:
            lines.append(f"- {driver}")

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


def safe_news_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_news_title(title: Any) -> str:
    text = safe_news_text(title).lower()
    text = re.sub(r"\s*[-｜|]\s*(news\.cnyes\.com|經濟日報|聯合新聞網|udn|marketwatch|investing\.com)\s*$", "", text)
    text = re.sub(r"〈[^〉]{1,20}〉", "", text)
    return re.sub(r"\W+", "", text)[:90]


def news_title_similarity(a: Any, b: Any) -> float:
    aa = normalize_news_title(a)
    bb = normalize_news_title(b)
    if not aa or not bb:
        return 0.0
    if aa == bb:
        return 1.0
    if aa in bb or bb in aa:
        return min(len(aa), len(bb)) / max(len(aa), len(bb))

    grams_a = {aa[i:i + 2] for i in range(max(len(aa) - 1, 0))}
    grams_b = {bb[i:i + 2] for i in range(max(len(bb) - 1, 0))}
    if not grams_a or not grams_b:
        return 0.0
    return len(grams_a & grams_b) / len(grams_a | grams_b)


def classify_news_bucket(item: Dict[str, Any]) -> str:
    text = f"{item.get('title','')} {item.get('theme','')} {item.get('query','')}".lower()

    inflation_keywords = [
        "油價", "原油", "能源", "通膨", "物價", "pce", "cpi", "ppi",
        "inflation", "oil", "wti", "brent", "energy", "停滯性通膨",
        "美伊", "伊朗", "中東", "geopolitical",
    ]
    rate_keywords = [
        "美債", "殖利率", "長債", "fed", "聯準會", "利率", "降息", "升息",
        "treasury", "yield", "rate", "federal reserve", "期限溢價",
        "非農", "就業報告", "初領失業金", "payroll", "jobs report", "jobless claims",
    ]
    currency_keywords = [
        "美元", "dxy", "台幣", "新台幣", "日圓", "日元", "韓元", "人民幣",
        "亞幣", "匯率", "dollar", "yen", "taiwan dollar", "asia currencies",
        "fx",
    ]

    if any(k.lower() in text for k in inflation_keywords):
        return "通膨預期"
    if any(k.lower() in text for k in rate_keywords):
        return "利率"
    if any(k.lower() in text for k in currency_keywords):
        return "貨幣"
    return "其他"


def build_url_candidates(ranked_items: List[Dict[str, Any]], top_news: List[Any]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen = set()

    def add_item(item: Any) -> None:
        if not isinstance(item, dict):
            return
        title = safe_news_text(item.get("title"))
        url = safe_news_text(item.get("url"))
        key = (normalize_news_title(title), url)
        if not key[0] or not url or key in seen:
            return
        seen.add(key)
        candidates.append(item)

    for item in ranked_items or []:
        add_item(item)
    for item in top_news or []:
        add_item(item)

    return candidates


def enrich_news_item(item: Dict[str, Any], url_candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(item)

    if safe_news_text(merged.get("url")):
        return merged

    best_match: Dict[str, Any] = {}
    best_score = 0.0
    for candidate in url_candidates:
        score = news_title_similarity(merged.get("title"), candidate.get("title"))
        if score > best_score:
            best_score = score
            best_match = candidate

    if best_score >= 0.38:
        for field in ["url", "source", "published_at", "theme"]:
            if best_match.get(field) and not merged.get(field):
                merged[field] = best_match.get(field)

    return merged


def news_card_from_item(item: Dict[str, Any]) -> Dict[str, Any]:
    title = safe_news_text(item.get("title"))
    source = safe_news_text(item.get("source"))
    theme = safe_news_text(item.get("theme"))
    published_at = safe_news_text(item.get("published_at"))

    return {
        "title": title,
        "source": source,
        "url": safe_news_text(item.get("url")),
        "published_at": published_at,
        "theme": theme,
        "why_it_matters": safe_news_text(item.get("why_it_matters")) or "本週總經新聞候選。",
        "score": item.get("score", 0),
    }


def build_fallback_news_categories(ranked_items: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    categories: Dict[str, List[Dict[str, Any]]] = {
        "通膨預期": [],
        "利率": [],
        "貨幣": [],
        "其他": [],
    }

    seen = set()
    for item in ranked_items or []:
        if not isinstance(item, dict):
            continue
        card = news_card_from_item(item)
        key = (card.get("title") or "", card.get("url") or "")
        if not key[0] or key in seen:
            continue
        seen.add(key)

        bucket = classify_news_bucket(item)
        if len(categories[bucket]) < 8:
            categories[bucket].append(card)

    return categories


def normalize_news_categories(context: Dict[str, Any], ranked_items: List[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    categories = context.get("news_categories")
    if not isinstance(categories, dict):
        context["news_categories"] = {
            "通膨預期": [],
            "利率": [],
            "貨幣": [],
            "其他": [],
        }
        categories = context["news_categories"]

    top_news = context.get("top_news")
    if not isinstance(top_news, list):
        top_news = []

    url_candidates = build_url_candidates(ranked_items or [], top_news)

    for key in ["通膨預期", "利率", "貨幣", "其他"]:
        if not isinstance(categories.get(key), list):
            categories[key] = []
        cleaned_items = []
        for item in categories[key]:
            if isinstance(item, dict):
                cleaned_items.append(enrich_news_item(item, url_candidates))
        categories[key] = cleaned_items[:8]

    has_category_cards = any(categories.get(key) for key in ["通膨預期", "利率", "貨幣", "其他"])

    normalized_top = []
    seen = set()
    for item in top_news:
        if not isinstance(item, dict):
            continue
        enriched = enrich_news_item(item, url_candidates)
        key = (enriched.get("title") or "", enriched.get("url") or "")
        if key in seen:
            continue
        seen.add(key)
        normalized_top.append(enriched)

    if not has_category_cards and not normalized_top and ranked_items:
        fallback_categories = build_fallback_news_categories(ranked_items)
        for key in ["通膨預期", "利率", "貨幣", "其他"]:
            categories[key] = fallback_categories.get(key, [])[:8]

    for bucket in ["通膨預期", "利率", "貨幣", "其他"]:
        for item in categories.get(bucket, []):
            key = (item.get("title") or "", item.get("url") or "")
            if key in seen:
                continue
            seen.add(key)
            normalized_top.append(item)

    context["news_categories"] = categories
    context["top_news"] = normalized_top[:12]
    return context


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default=os.getenv("WEEK_DIR", "").strip())
    parser.add_argument("--start", type=str, default=os.getenv("ANALYSIS_START_DATE", "").strip())
    parser.add_argument("--end", type=str, default=os.getenv("ANALYSIS_END_DATE", "").strip())
    parser.add_argument("--max-items", type=int, default=int(os.getenv("WEEKLY_NEWS_MAX_ITEMS", str(DEFAULT_MAX_ITEMS))))
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    week_dir = resolve_week_dir(args.week_dir)

    weekly_source_text = load_text(week_dir / "weekly_source_text.md")
    week_start, week_end, week_label = infer_week_range(week_dir, start_override=args.start, end_override=args.end)

    all_items: List[Dict[str, Any]] = []
    queries = build_queries()

    for theme, query in queries:
        print(f"[INFO] Fetching news: {theme} | {query}")
        all_items.extend(fetch_rss_items(query, theme=theme, max_items=6))
        time.sleep(0.5)

    ranked = dedupe_and_rank(all_items, max_items=args.max_items, week_start=week_start, week_end=week_end)

    raw_package = {
        "meta": {
            "source": "Google News RSS",
            "week_range": week_label,
            "analysis_window": {
                "start_date": week_start,
                "end_date": week_end,
                "source": "workflow_env_or_weekly_video_source",
            },
            "query_count": len(queries),
            "raw_count": len(all_items),
            "ranked_count": len(ranked),
            "sources_preferred": SOURCE_FILTERS,
            "lookback_days": int(os.getenv("WEEKLY_NEWS_LOOKBACK_DAYS", str(DEFAULT_LOOKBACK_DAYS))),
        },
        "items": ranked,
    }

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(DATA_DIR / "weekly_news_raw.json", raw_package)
    print(f"[OK] Saved {DATA_DIR / 'weekly_news_raw.json'}")

    user_prompt = USER_PROMPT_TEMPLATE.replace(
        "{analysis_window_label}", week_label
    ).replace(
        "{weekly_source_text}", weekly_source_text
    ).replace(
        "{weekly_news_candidates}", json.dumps(ranked, ensure_ascii=False, indent=2)
    )

    print(f"[INFO] Generating weekly news context with model: {model}")
    context = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    context = normalize_news_categories(context, ranked_items=ranked)

    category_counts = {
        key: len(context.get("news_categories", {}).get(key, []) or [])
        for key in ["通膨預期", "利率", "貨幣", "其他"]
    }
    print(f"[INFO] News category counts: {category_counts}")
    print(f"[INFO] Top news count: {len(context.get('top_news', []) or [])}")

    context.setdefault("meta", {})
    context["meta"]["source"] = "Google News RSS"
    context["meta"]["week_range"] = context["meta"].get("week_range") or week_label
    context["meta"]["analysis_window"] = {
        "start_date": week_start,
        "end_date": week_end,
        "source": "workflow_env_or_weekly_video_source",
    }
    context["meta"]["candidate_count"] = context["meta"].get("candidate_count") or len(ranked)

    out_json = week_dir / "weekly_news_context.json"
    save_json(out_json, context)
    print(f"[OK] Saved {out_json}")

    out_md = week_dir / "weekly_news_context.md"
    save_text(out_md, build_news_context_markdown(context))
    print(f"[OK] Saved {out_md}")


if __name__ == "__main__":
    main()
