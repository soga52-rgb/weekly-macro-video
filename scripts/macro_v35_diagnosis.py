#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Macro V35 Diagnosis｜GitHub weekly shared analysis layer

Purpose:
- Port the Apps Script V35 rule-based design into GitHub / Python.
- Build a shared V35 diagnosis file for both:
  1) Weekly static webpage line: 01 -> 02 -> 04
  2) Weekly video line: 80 -> 82 -> 83 -> 85 -> 86

Input files under output/weekly/YYYY-MM-DD:
- weekly_market_series.json
- weekly_news_context.json optional
- weekly_news_context.md optional
- macro_background_context.json optional
- macro_background_context.md optional

Output:
- weekly_v35_diagnosis.json

Design principles:
- This script is rule-based. It does not call Gemini.
- It creates factor groups, rate factor map, core contradiction, primary macro story,
  expected chain, asset validation, and a compact weekly_v35_diagnosis block.
- Downstream Gemini prompts should read this file instead of re-inventing the macro logic.
- Synced with current Apps Script labor direction guards, labor-mixed logic, wage-pressure rule, and directional dollar detection.
- Current-week market direction takes precedence for oil, DXY and Gold; news is used to explain or correct, not overwrite, observed prices.
- News regex runs on one-record-per-line factual segments and excludes watch/future/editor fields.
- The analysis period is controlled by the formal analysis window; do not assume 7 days.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


ASSET_ALIASES = {
    "US10Y": ["US10Y", "^TNX", "TNX", "10Y", "UST10Y", "美國10年期公債殖利率", "美10年期公債殖利率"],
    "DXY": ["DXY", "DX-Y.NYB", "美元指數"],
    "Gold": ["Gold", "GC=F", "XAU", "XAUUSD", "黃金", "金價"],
    "WTI": ["WTI", "CL=F", "Crude Oil", "西德州", "西德州原油"],
    "Brent": ["Brent", "BZ=F", "布蘭特", "布蘭特原油"],
    "USDJPY": ["USDJPY", "JPY=X", "美元兌日圓", "美元/日圓", "美元／日圓"],
    "USDTWD": ["USDTWD", "USDTWD=X", "TWD=X", "美元兌台幣", "美元/台幣", "美元／台幣"],
    "USDKRW": ["USDKRW", "KRW=X", "美元兌韓元", "美元/韓元", "美元／韓元", "美元兌韓圜"],
}


def load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def resolve_week_dir(value: str) -> Path:
    value = (value or "").strip()
    if not value:
        return find_latest_week_dir()

    raw = Path(value)
    if raw.is_absolute():
        return raw

    if len(value) == 10 and value[4] == "-" and value[7] == "-":
        return OUTPUT_WEEKLY_DIR / value

    candidate = ROOT_DIR / raw
    if candidate.exists():
        return candidate

    return OUTPUT_WEEKLY_DIR / value


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def regex_has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE) is not None


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def unique_list(values: List[str]) -> List[str]:
    seen = set()
    out = []
    for value in values:
        value = str(value or "").strip()
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def infer_analysis_window_from_source(
    week_dir: Path,
    start_override: str = "",
    end_override: str = "",
    weekly_market_series: Optional[Dict[str, Any]] = None,
    weekly_news_context_json: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    env_start = (start_override or os.getenv("ANALYSIS_START_DATE", "")).strip()
    env_end = (end_override or os.getenv("ANALYSIS_END_DATE", "")).strip()
    if env_start and env_end:
        return {
            "start_date": env_start,
            "end_date": env_end,
            "label": f"{env_start} ～ {env_end}",
            "source": "workflow_env_or_cli",
        }

    if isinstance(weekly_market_series, dict):
        meta = weekly_market_series.get("meta", {})
        requested = meta.get("requested_analysis_window", {}) if isinstance(meta, dict) else {}
        start = str(requested.get("start_date") or "").strip()
        end = str(requested.get("end_date") or "").strip()
        if start and end:
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "weekly_market_series.meta.requested_analysis_window",
            }

    if isinstance(weekly_news_context_json, dict):
        meta = weekly_news_context_json.get("meta", {})
        analysis_window = meta.get("analysis_window", {}) if isinstance(meta, dict) else {}
        start = str(analysis_window.get("start_date") or "").strip()
        end = str(analysis_window.get("end_date") or "").strip()
        if start and end:
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "weekly_news_context.meta.analysis_window",
            }

        week_range = str(meta.get("week_range") or "").strip() if isinstance(meta, dict) else ""
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:～|~|to|-)\s*(\d{4}-\d{2}-\d{2})", week_range)
        if match:
            start, end = match.group(1), match.group(2)
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "weekly_news_context.meta.week_range",
            }

    source_text = load_text(week_dir / "weekly_source_text.md")
    match = re.search(r"週期：\s*(\d{4}-\d{2}-\d{2})\s*[～~\-to]+\s*(\d{4}-\d{2}-\d{2})", source_text)
    if match:
        start, end = match.group(1), match.group(2)
        return {
            "start_date": start,
            "end_date": end,
            "label": f"{start} ～ {end}",
            "source": "weekly_source_text.md",
        }

    return {
        "start_date": "",
        "end_date": week_dir.name,
        "label": week_dir.name,
        "source": "week_dir",
    }


def value_from_point(point: Dict[str, Any]) -> Optional[float]:
    for key in ("value", "close", "price", "last", "adj_close", "adjClose", "y"):
        if key in point:
            try:
                return float(point[key])
            except (TypeError, ValueError):
                continue
    return None


def get_point_date(point: Dict[str, Any]) -> str:
    for key in ("date", "datetime", "time", "timestamp"):
        if key in point:
            return str(point.get(key) or "")[:10]
    return ""


def points_in_window(points: Any, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    if not isinstance(points, list):
        return []
    filtered = []
    for point in points:
        if not isinstance(point, dict):
            continue
        date_text = get_point_date(point)
        if start_date and date_text and date_text < start_date:
            continue
        if end_date and date_text and date_text > end_date:
            continue
        filtered.append(point)
    return filtered


def identify_asset(item: Dict[str, Any]) -> str:
    """Resolve a market-series item to the canonical asset key.

    Priority:
    1) ``asset_key`` from the market-history endpoint is authoritative.
    2) key / symbol / ticker use exact alias matching.
    3) Human-readable name fields use conservative fuzzy matching.

    This prevents ``布蘭特原油`` from being captured by a generic WTI alias and
    supports full-width slashes used by the Apps Script endpoint.
    """

    def normalize_asset_token(value: Any) -> str:
        return normalize_text(value).strip().lower().replace("／", "/").replace(" ", "")

    canonical_lookup = {normalize_asset_token(key): key for key in ASSET_ALIASES}

    # The endpoint already provides a stable canonical key. Use it first.
    asset_key = normalize_asset_token(item.get("asset_key"))
    if asset_key in canonical_lookup:
        return canonical_lookup[asset_key]

    # Machine-readable identifiers must match exactly; do not use substring logic.
    exact_alias_lookup: Dict[str, str] = {}
    for canonical, aliases in ASSET_ALIASES.items():
        exact_alias_lookup[normalize_asset_token(canonical)] = canonical
        for alias in aliases:
            exact_alias_lookup[normalize_asset_token(alias)] = canonical

    for field in ("key", "symbol", "ticker"):
        token = normalize_asset_token(item.get(field))
        if token and token in exact_alias_lookup:
            return exact_alias_lookup[token]

    # Human-readable fields may contain extra descriptions. Match longer aliases
    # first so specific names such as Brent are preferred over broad terms.
    name_text = " ".join([
        normalize_text(item.get("asset")),
        normalize_text(item.get("name")),
        normalize_text(item.get("label")),
        normalize_text(item.get("title")),
    ]).lower().replace("／", "/")

    fuzzy_aliases = sorted(
        (
            (normalize_text(alias).lower().replace("／", "/"), canonical)
            for canonical, aliases in ASSET_ALIASES.items()
            for alias in aliases
            if normalize_text(alias)
        ),
        key=lambda pair: len(pair[0]),
        reverse=True,
    )
    for alias, canonical in fuzzy_aliases:
        if alias in name_text:
            return canonical

    return normalize_text(
        item.get("asset_key")
        or item.get("key")
        or item.get("symbol")
        or item.get("label")
        or item.get("name")
        or "unknown"
    )


def direction_text(direction: str, asset: str) -> str:
    if direction == "up":
        if asset in {"USDJPY", "USDTWD", "USDKRW"}:
            return "美元上行，當地貨幣承壓"
        if asset == "US10Y":
            return "殖利率上行"
        if asset == "DXY":
            return "美元偏強"
        if asset == "Gold":
            return "黃金上行"
        if asset in {"WTI", "Brent"}:
            return "油價上行"
        return "上行"
    if direction == "down":
        if asset in {"USDJPY", "USDTWD", "USDKRW"}:
            return "美元回落，當地貨幣相對支撐"
        if asset == "US10Y":
            return "殖利率下行"
        if asset == "DXY":
            return "美元偏弱"
        if asset == "Gold":
            return "黃金下行"
        if asset in {"WTI", "Brent"}:
            return "油價下行"
        return "下行"
    if direction == "flat":
        return "變化有限"
    return "方向不足"


def build_observed_market(
    weekly_market_series: Dict[str, Any],
    analysis_window: Dict[str, str],
) -> Dict[str, Dict[str, Any]]:
    observed: Dict[str, Dict[str, Any]] = {
        key: {"direction": "", "text": "方向不足", "start_value": None, "end_value": None, "change": None, "start_date": "", "end_date": "", "points_count": 0}
        for key in ASSET_ALIASES.keys()
    }

    series = weekly_market_series.get("series", [])
    if not isinstance(series, list):
        return observed

    start = analysis_window.get("start_date", "")
    end = analysis_window.get("end_date", "")

    for item in series:
        if not isinstance(item, dict):
            continue

        asset = identify_asset(item)
        if asset not in observed:
            continue

        points = points_in_window(item.get("points") or item.get("data") or [], start, end)
        points = [p for p in points if value_from_point(p) is not None]
        if len(points) < 2:
            continue

        first = points[0]
        last = points[-1]
        start_value = value_from_point(first)
        end_value = value_from_point(last)
        if start_value is None or end_value is None:
            continue

        change = end_value - start_value
        if abs(change) < 1e-12:
            direction = "flat"
        else:
            direction = "up" if change > 0 else "down"

        observed[asset] = {
            "direction": direction,
            "text": direction_text(direction, asset),
            "start_value": start_value,
            "end_value": end_value,
            "change": change,
            "start_date": get_point_date(first),
            "end_date": get_point_date(last),
            "points_count": len(points),
        }

    return observed


def collect_news_text(
    weekly_news_context_json: Dict[str, Any],
    weekly_news_context_md: str,
    macro_background_context_json: Dict[str, Any],
    macro_background_context_md: str,
) -> str:
    """Collect factual news evidence as one-record-per-line segments.

    The old implementation flattened the entire JSON/Markdown tree into one long
    sentence. Regex patterns such as ``非農.*強美元`` could therefore cross from
    one article or section into another and create false opposite-direction flags.

    This version intentionally:
    - keeps each news record / signal on its own line;
    - reads factual and correction fields only;
    - excludes watch points, future scenarios, metadata, editor instructions, and
      duplicated Markdown summaries from directional detection;
    - preserves correction news as evidence, but does not let hypothetical text
      contaminate current-period facts.
    """
    segments: List[str] = []
    seen = set()

    def add_segment(*values: Any) -> None:
        parts: List[str] = []
        for value in values:
            if value is None:
                continue
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            cleaned = re.sub(r"\s+", " ", str(value)).strip()
            if cleaned:
                parts.append(cleaned)
        segment = "｜".join(parts).strip("｜ ")
        key = segment.lower()
        if not segment or key in seen:
            return
        seen.add(key)
        segments.append(segment)

    def add_news_item(item: Any) -> None:
        if not isinstance(item, dict):
            add_segment(item)
            return
        add_segment(
            item.get("title") or item.get("headline"),
            item.get("theme"),
            item.get("why_it_matters") or item.get("summary") or item.get("impact"),
        )

    def add_context(context: Any) -> None:
        if not isinstance(context, dict):
            return

        # Current-period editorial theme is allowed, but watch/future fields are not.
        add_segment(context.get("weekly_news_theme"))

        for driver in as_list(context.get("macro_drivers")):
            if isinstance(driver, dict):
                add_segment(
                    driver.get("driver") or driver.get("title") or driver.get("theme"),
                    driver.get("impact") or driver.get("summary") or driver.get("why_it_matters"),
                )
            else:
                add_segment(driver)

        # These are current-period evidence or explicit corrections, not future watch points.
        for field in ("confirming_signals", "contradicting_signals", "news_based_corrections"):
            for item in as_list(context.get(field)):
                if isinstance(item, dict):
                    add_segment(
                        item.get("title") or item.get("driver") or item.get("theme"),
                        item.get("impact") or item.get("summary") or item.get("why_it_matters"),
                    )
                else:
                    add_segment(item)

        categories = context.get("news_categories")
        if isinstance(categories, dict):
            for category_items in categories.values():
                for item in as_list(category_items):
                    add_news_item(item)

        # top_news may duplicate category cards; add_segment() de-duplicates exact records.
        for item in as_list(context.get("top_news")):
            add_news_item(item)

    add_context(weekly_news_context_json)
    add_context(macro_background_context_json)

    # Compatibility fallback only when structured JSON contains no usable evidence.
    # Keep one source line per segment and drop headings that explicitly denote watch/future text.
    if not segments:
        for raw_text in (weekly_news_context_md, macro_background_context_md):
            skip_section = False
            for line in str(raw_text or "").splitlines():
                cleaned = line.strip()
                if not cleaned:
                    continue
                if re.match(r"^#{1,6}\s*", cleaned):
                    skip_section = bool(re.search(r"下週|待觀察|watch|future|展望", cleaned, flags=re.IGNORECASE))
                    continue
                if skip_section:
                    continue
                add_segment(re.sub(r"^[-*]\s*", "", cleaned))

    return "\n".join(segments).lower()

def extract_macro_event_flags_v35(
    news_text: str,
    observed: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Extract directional macro event flags using the current Apps Script V35/V36 rules.

    Important safeguards:
    - An indicator name alone is not a direction.
    - Labor data is split into weak, strong, resilient, mixed, wage-cooling, and wage-pressure signals.
    - Labor strength alone affects the Fed path, but does not directly raise inflation expectations.
    - Oil news describes the cause; actual WTI / Brent direction is validated later from market data.
    """
    text = news_text or ""
    observed = observed or {}

    inflation_hot = regex_has(
        r"\b(cpi|ppi|pce|core cpi|core pce|consumer prices|producer prices|personal consumption expenditures|import prices|prices paid|inflation)\b.*(hot|higher|above|accelerat|sticky|surpris|rise|rose|jump|increase|beat)|通膨.*(高於預期|升溫|黏性|加速|反彈)|物價.*(高於預期|上升|加速)|ppi.*高於|cpi.*高於|pce.*高於|價格分項.*上升",
        text,
    )
    inflation_cooling = regex_has(
        r"\b(cpi|ppi|pce|core cpi|core pce|inflation|prices|consumer prices|producer prices)\b.*(cool|lower|below|miss|ease|eased|slowed|moderate|decelerate)|通膨.*(降溫|低於預期|放緩)|物價.*(降溫|低於預期|放緩)|價格壓力.*緩和",
        text,
    )

    # Labor market direction reading. Indicator names alone are not directional.
    payroll_weak_signal = regex_has(
        r"\b(payrolls|nonfarm payrolls|job growth|jobs growth|jobs report|hiring)\b.*(miss|misses|below|weaker|weak|slowed|slow|disappoint|undershoot|revis(ed|ion).*down|downward revision)|非農.*(爆冷|遜於預期|低於預期|不如預期|放緩|下修)|就業.*(遜於預期|低於預期|不如預期|放緩|轉弱)",
        text,
    )
    payroll_strong_signal = regex_has(
        r"\b(payrolls|nonfarm payrolls|job growth|jobs growth|jobs report|hiring)\b.*(beat|beats|above|strong|stronger|surpris(e|ed).*up|accelerat)|非農.*(強|強勁|優於預期|高於預期)|就業.*強勁",
        text,
    )
    claims_weak_signal = regex_has(
        r"\b(initial claims|weekly claims|jobless claims|continuing claims|unemployment benefits|claims)\b.*(rise|rose|rising|jump|increase|higher|above|elevated)|初領失業金.*(上升|增加|高於預期)|續領失業金.*(上升|增加|高於預期)|申請失業救濟.*(上升|增加)",
        text,
    )
    claims_strong_signal = regex_has(
        r"\b(initial claims|weekly claims|jobless claims|continuing claims|unemployment benefits|claims)\b.*(fall|fell|drop|decline|decrease|lower|below)|初領失業金.*(下降|減少|低於預期)|續領失業金.*(下降|減少|低於預期)|申請失業救濟.*(下降|減少)",
        text,
    )
    unemployment_weak_signal = regex_has(
        r"unemployment rate.*(rise|rose|rising|increase|higher|above)|失業率.*(上升|高於預期)",
        text,
    )
    unemployment_resilience_signal = regex_has(
        r"unemployment rate.*(fall|fell|drop|decline|decrease|lower|below)|失業率.*(下降|低於預期)",
        text,
    )
    wage_cooling_signal = regex_has(
        r"wage growth.*(slow|slowed|cool|cooling|moderate|decelerate|weaker)|average hourly earnings.*(slow|slowed|below|weaker)|薪資.*(放緩|降溫|低於預期)",
        text,
    )
    wage_pressure_signal = regex_has(
        r"wage growth.*(accelerat|strong|hot|higher|above)|average hourly earnings.*(accelerat|strong|higher|above)|薪資.*(加速|強勁|高於預期)",
        text,
    )
    layoff_weak_signal = regex_has(
        r"layoffs|job cuts|ai.*layoff|ai.*job cuts|裁員|企業裁員|ai.*裁員|ai替代",
        text,
    )

    labor_weak_signal = (
        payroll_weak_signal
        or claims_weak_signal
        or unemployment_weak_signal
        or wage_cooling_signal
        or layoff_weak_signal
        or regex_has(r"labor market.*(cool|soft|weaken)|labour market.*(cool|soft|weaken)|就業.*降溫|就業.*轉弱|勞動市場.*(降溫|轉弱)", text)
    )
    labor_strong_signal = (
        payroll_strong_signal
        or claims_strong_signal
        or wage_pressure_signal
        or regex_has(r"labor market.*tight|labour market.*tight|adp.*strong|勞動市場.*緊俏", text)
    )
    labor_resilience_signal = unemployment_resilience_signal or claims_strong_signal
    labor_mixed = labor_weak_signal and (labor_strong_signal or labor_resilience_signal)
    labor_cooling = labor_weak_signal
    labor_strength = labor_strong_signal and not labor_weak_signal

    growth_cooling = regex_has(
        r"retail sales.*weak|consumer spending.*weak|housing starts.*fall|building permits.*fall|home sales.*fall|industrial production.*weak|gdp.*slow|pmi.*slow|ism.*slow|growth slowdown|growth warning|recession risk|零售銷售.*弱|消費.*放緩|房市.*降溫|房屋開工.*下滑|營建許可.*下滑|工業生產.*弱|gdp.*放緩|pmi.*放緩|ism.*放緩|成長放緩|景氣降溫|衰退風險",
        text,
    )
    growth_strength = regex_has(
        r"retail sales.*strong|consumer spending.*strong|gdp.*strong|pmi.*expand|ism.*expand|new orders.*strong|growth rebound|soft landing|零售銷售.*強|消費.*強|gdp.*強|pmi.*擴張|ism.*擴張|新訂單.*強|軟著陸",
        text,
    )
    risk_off = regex_has(
        r"risk-off|risk aversion|safe haven|flight to quality|geopolitical risk|war|sanction|tariff|middle east|iran|israel|hormuz|避險|風險趨避|地緣政治|戰爭|制裁|關稅|中東|伊朗|以色列|荷姆茲",
        text,
    )
    market_expectation_shift = regex_has(
        r"ceasefire|talks|negotiation|probability|uncertainty|risk premium|market expectations|policy signal|停火|談判|協商|機率|不確定性|風險擔憂|市場預期|政策訊號|重新評估",
        text,
    )
    geopolitical_cooling = regex_has(
        r"ceasefire|peace deal|peace talks|talks resume|de-escalation|risk premium.*fade|risk premium.*ease|risk.*fade|risk.*ease|停火|和平協議|和談|談判重啟|地緣.*降溫|風險擔憂.*消退|風險擔憂.*下降",
        text,
    )

    # Oil news is a cause signal. Actual WTI / Brent direction is checked later.
    oil_supply_shock = regex_has(
        r"oil supply|crude supply|oil disruption|crude disruption|supply disruption|supply outage|supply shock|oil sanctions|crude sanctions|opec.*cut|production cut|output cut|hormuz|middle east.*oil|war.*oil|oil.*war|sanction.*oil|oil.*sanction|原油.*供給|油價.*供給|能源供給|供給中斷|供給衝擊|原油.*減產|油價.*減產|opec.*減產|庫存下降|荷姆茲|戰爭.*油價|油價.*戰爭|制裁.*原油|原油.*制裁",
        text,
    )
    oil_demand_weakness = regex_has(
        r"oil.*demand|crude.*demand|inventory build|stockpile rise|demand weak|growth concern.*oil|原油需求|油品需求|庫存增加|需求疲弱|需求放緩|油價.*需求",
        text,
    )

    fed_hawkish = regex_has(
        r"fed.*hawk|fomc.*hawk|powell.*hawk|rate hike|higher for longer|hold rates high|not ready to cut|not prepared to cut|rate cuts.*delay|rate cut.*delay|fewer cuts|less easing|cut rates.*later|rates.*higher.*longer|dot plot.*higher|聯準會.*偏鷹|fed.*偏鷹|鮑爾.*偏鷹|升息|高利率維持更久|降息.*延後|降息.*推遲|不急於降息|尚未準備降息|降息次數.*減少|點陣圖.*上修",
        text,
    )
    fed_dovish = regex_has(
        r"fed.*dovish|fomc.*dovish|powell.*dovish|open to cut|cuts expected|rate cuts likely|rate cut expectations rise|rate cut bets increase|policy easing|easing bias|聯準會.*偏鴿|fed.*偏鴿|鮑爾.*偏鴿|準備降息|可能降息|降息預期.*升溫|降息預期.*增加|降息機率.*上升|政策寬鬆|寬鬆傾向",
        text,
    )
    treasury_supply_pressure = regex_has(
        r"treasury supply|bond supply|debt issuance|heavy issuance|fiscal deficit|deficit worries|auction.*weak|weak demand.*auction|tailing auction|美債供給|公債供給|發債規模|財政赤字|標售.*疲弱|標售.*需求弱|拍賣.*需求弱",
        text,
    )
    treasury_demand_strong = regex_has(
        r"auction.*strong|strong demand.*auction|solid demand.*auction|safe-haven demand.*treasury|treasury buying|標售.*強勁|標售.*需求強|買盤.*美債|避險買盤.*美債",
        text,
    )
    refunding_pressure = regex_has(
        r"treasury refunding|quarterly refunding|debt rollover|rollover risk|maturity wall|refinancing pressure|refunding|再融資|季度再融資|再續發|到期再發|債務到期|發債壓力",
        text,
    )
    term_premium_pressure = regex_has(
        r"term premium|long-end premium|duration risk|long bond yield|期限溢價|長端利率|長債|長債溢價|存續期間風險",
        text,
    )
    fed_balance_sheet_tightening = regex_has(
        r"\bqt\b|quantitative tightening|balance sheet runoff|fed balance sheet.*shrink|reserve drain|縮表|量化緊縮|資產負債表.*縮|準備金.*下降|流動性.*收緊",
        text,
    )
    fed_balance_sheet_easing = regex_has(
        r"\bqe\b|quantitative easing|balance sheet expansion|fed balance sheet.*expand|liquidity facility|liquidity support|擴表|量化寬鬆|資產負債表.*擴|流動性工具|流動性支持",
        text,
    )
    fed_leadership_shift = regex_has(
        r"kevin warsh|warsh|new fed chair|fed chair nominee|fed chair candidate|next fed chair|successor to powell|powell successor|fed leadership|fed independence|central bank independence|policy reaction function|fed reaction function|monetary policy framework|fed chair|聯準會主席|新任主席|新任fed主席|新任聯準會主席|聯準會主席.*人選|fed主席.*人選|鮑爾接班|鮑威爾接班|鮑爾接班人|主席風格|政策反應函數|貨幣政策框架|央行獨立性|聯準會獨立性|政策首秀",
        text,
    )
    financial_stress = regex_has(
        r"bank crisis|bank stress|credit stress|credit spreads.*widen|high yield.*stress|commercial real estate.*risk|liquidity crisis|financial conditions.*tighten|stock market.*selloff|equities.*plunge|financial stress|liquidity stress|銀行危機|銀行壓力|信用風險|信用壓力|信用利差.*擴大|高收益債.*壓力|商業不動產.*風險|流動性危機|流動性壓力|金融條件.*收緊|金融壓力|股市.*大跌|證券市場.*下跌",
        text,
    )

    # Directional guards: merely mentioning dollar / DXY is not enough.
    dollar_weakness = regex_has(
        r"dollar.*(weak|weaken|weakened|weaker)|dxy.*(fall|falls|fell|drop|drops|dropped|decline|declines|declined)|greenback.*(fall|falls|fell|slip|slips|slipped|weaken)|美元.*走弱|美元指數.*(下跌|回落)|美元.*回落",
        text,
    )
    dollar_strength = regex_has(
        r"dollar.*(strong|stronger|strengthen|strengthened)|dxy.*(rise|rises|rose|rising|gain|gains|gained)|greenback.*(rise|rises|rose|gain|gains|gained|strengthen)|usd strength|美元.*走強|美元指數.*(上漲|走高)|美元.*偏強|強美元",
        text,
    )
    gold_pressure = regex_has(r"gold drops|gold falls|gold.*down|gold pressured|金價大跌|黃金.*跌|金價.*跌|黃金承壓", text)
    gold_safe_haven = regex_has(r"gold.*safe haven|gold.*risk|gold.*geopolitical|gold rises|gold gains|黃金.*避險|金價.*避險|黃金.*地緣|黃金上漲|金價上漲", text)

    # Market-direction precedence for traded assets.
    # News explains possible causes; observed prices decide whether the channel was
    # actually inflationary / disinflationary during the formal analysis window.
    wti_direction = str(observed.get("WTI", {}).get("direction") or "")
    brent_direction = str(observed.get("Brent", {}).get("direction") or "")
    oil_market_up = wti_direction == "up" or brent_direction == "up"
    oil_market_down = wti_direction == "down" or brent_direction == "down"
    oil_direction_known = bool(wti_direction or brent_direction)

    dxy_direction = str(observed.get("DXY", {}).get("direction") or "")
    gold_direction = str(observed.get("Gold", {}).get("direction") or "")

    oil_inflation_pressure = oil_market_up or (
        not oil_direction_known
        and (oil_supply_shock or regex_has(r"oil prices.*inflation|油價.*通膨|能源.*通膨", text))
    )
    oil_inflation_relief = oil_market_down or (
        not oil_direction_known and (oil_demand_weakness or geopolitical_cooling)
    )

    # Current rule: labor strength alone affects the Fed path, not inflation expectations.
    inflation_expectation_up = inflation_hot or oil_inflation_pressure or wage_pressure_signal or growth_strength
    inflation_expectation_down = inflation_cooling or oil_inflation_relief or labor_cooling or growth_cooling
    inflation_expectation_mixed = inflation_expectation_up and inflation_expectation_down
    inflation_expectation_shift = market_expectation_shift or inflation_expectation_mixed or (
        risk_off and (inflation_expectation_up or inflation_expectation_down)
    )

    # DXY and Gold are validation assets. Once an observed direction exists, it is
    # authoritative for the current week; opposite news wording remains contextual
    # evidence but must not create two simultaneous market-direction flags.
    if dxy_direction == "up":
        dollar_strength = True
        dollar_weakness = False
    elif dxy_direction == "down":
        dollar_strength = False
        dollar_weakness = True

    if gold_direction == "down":
        gold_pressure = True
        gold_safe_haven = False
    elif gold_direction == "up":
        gold_pressure = False
        gold_safe_haven = True

    return {
        "inflationPressure": inflation_hot or inflation_expectation_up,
        "inflationRelief": inflation_expectation_down,
        "inflationCoolingSignal": inflation_cooling,
        "inflationMixed": inflation_expectation_mixed,
        "inflationExpectationShift": inflation_expectation_shift,
        "highRateExpectation": fed_hawkish or regex_has(r"higher for longer|高利率維持更久|降息.*延後|not ready to cut", text),
        "fedHawkish": fed_hawkish,
        "fedDovish": fed_dovish,
        "laborCooling": labor_cooling,
        "laborStrength": labor_strength,
        "laborMixed": labor_mixed,
        "laborResilience": labor_resilience_signal,
        "laborWagePressure": wage_pressure_signal,
        "growthCooling": growth_cooling,
        "growthStrength": growth_strength,
        "oilInflationPressure": oil_inflation_pressure,
        "oilInflationRelief": oil_inflation_relief,
        "dollarStrength": dollar_strength,
        "dollarWeakness": dollar_weakness,
        "goldPressure": gold_pressure,
        "goldSafeHaven": gold_safe_haven,
        "riskOff": risk_off,
        "inflationHot": inflation_hot,
        "inflationCooling": inflation_cooling,
        "inflationExpectationUp": inflation_expectation_up,
        "inflationExpectationDown": inflation_expectation_down,
        "inflationExpectationMixed": inflation_expectation_mixed,
        "inflationExpectationMixedSignal": inflation_expectation_mixed,
        "inflationExpectationShiftSignal": inflation_expectation_shift,
        "treasurySupplyPressure": treasury_supply_pressure,
        "treasuryDemandStrong": treasury_demand_strong,
        "refundingPressure": refunding_pressure,
        "termPremiumPressure": term_premium_pressure,
        "fedBalanceSheetTightening": fed_balance_sheet_tightening,
        "fedBalanceSheetEasing": fed_balance_sheet_easing,
        "fedLeadershipShift": fed_leadership_shift,
        "financialStress": financial_stress,
        "marketExpectationShift": market_expectation_shift,
        "geopoliticalCooling": geopolitical_cooling,
        "oilSupplyShock": oil_supply_shock,
        "oilDemandWeakness": oil_demand_weakness,
        "factor_groups": {
            "inflation": {
                "detected": inflation_hot or inflation_cooling,
                "hot": inflation_hot,
                "cooling": inflation_cooling,
            },
            "labor_market": {
                "detected": labor_cooling or labor_strength or labor_mixed or labor_resilience_signal,
                "cooling": labor_cooling,
                "strength": labor_strength,
                "mixed": labor_mixed,
                "resilience": labor_resilience_signal,
                "wage_pressure": wage_pressure_signal,
                "weak_signals": {
                    "payroll_weak": payroll_weak_signal,
                    "claims_weak": claims_weak_signal,
                    "unemployment_rise": unemployment_weak_signal,
                    "wage_cooling": wage_cooling_signal,
                    "layoffs": layoff_weak_signal,
                },
                "strong_or_resilient_signals": {
                    "payroll_strong": payroll_strong_signal,
                    "claims_down": claims_strong_signal,
                    "unemployment_fall": unemployment_resilience_signal,
                    "wage_pressure": wage_pressure_signal,
                },
            },
            "growth_demand": {
                "detected": growth_cooling or growth_strength,
                "cooling": growth_cooling,
                "strength": growth_strength,
            },
            "oil_energy": {
                "detected": oil_supply_shock or oil_demand_weakness or geopolitical_cooling,
                "supply_shock": oil_supply_shock,
                "demand_weakness": oil_demand_weakness,
                "geopolitical_cooling": geopolitical_cooling,
                "market_direction": "up" if oil_market_up else "down" if oil_market_down else "unknown",
                "inflation_pressure": oil_inflation_pressure,
                "inflation_relief": oil_inflation_relief,
            },
            "inflation_expectation": {
                "detected": inflation_expectation_up or inflation_expectation_down or inflation_expectation_shift,
                "upward": inflation_expectation_up,
                "downward": inflation_expectation_down,
                "mixed": inflation_expectation_mixed,
                "shift": inflation_expectation_shift,
                "components": {
                    "inflation_hot": inflation_hot,
                    "inflation_cooling": inflation_cooling,
                    "oil_supply_shock": oil_supply_shock,
                    "oil_demand_weakness": oil_demand_weakness,
                    "geopolitical_cooling": geopolitical_cooling,
                    "oil_market_up": oil_market_up,
                    "oil_market_down": oil_market_down,
                    "labor_strength": labor_strength,
                    "labor_cooling": labor_cooling,
                    "labor_mixed": labor_mixed,
                    "wage_pressure": wage_pressure_signal,
                    "growth_strength": growth_strength,
                    "growth_cooling": growth_cooling,
                    "risk_off": risk_off,
                    "market_expectation_shift": market_expectation_shift,
                },
            },
            "fed_policy_path": {
                "detected": fed_hawkish or fed_dovish or fed_leadership_shift or labor_strength or labor_cooling or labor_mixed,
                "hawkish": fed_hawkish,
                "dovish": fed_dovish,
                "leadership_shift": fed_leadership_shift,
                "labor_strength_effect": labor_strength,
                "labor_cooling_effect": labor_cooling,
                "labor_mixed_effect": labor_mixed,
            },
            "treasury_market": {
                "detected": treasury_supply_pressure or treasury_demand_strong or refunding_pressure or term_premium_pressure,
                "supply_pressure": treasury_supply_pressure,
                "demand_strong": treasury_demand_strong,
                "refunding_pressure": refunding_pressure,
                "term_premium_pressure": term_premium_pressure,
            },
            # Keep the legacy group for downstream compatibility.
            "liquidity_balance_sheet": {
                "detected": fed_balance_sheet_tightening or fed_balance_sheet_easing,
                "tightening": fed_balance_sheet_tightening,
                "easing": fed_balance_sheet_easing,
            },
            "financial_conditions": {
                "detected": fed_balance_sheet_tightening or fed_balance_sheet_easing or financial_stress,
                "tightening": fed_balance_sheet_tightening,
                "easing": fed_balance_sheet_easing,
                "stress": financial_stress,
            },
            "market_psychology": {
                "detected": risk_off or market_expectation_shift or gold_safe_haven or dollar_weakness or dollar_strength,
                "risk_off": risk_off,
                "expectation_shift": market_expectation_shift,
                "gold_safe_haven": gold_safe_haven,
                "dollar_weakness": dollar_weakness,
                "dollar_strength": dollar_strength,
            },
            # Keep these legacy groups for downstream compatibility.
            "dollar_external": {
                "detected": dollar_strength or dollar_weakness,
                "dollar_strength": dollar_strength,
                "dollar_weakness": dollar_weakness,
            },
            "gold_risk": {
                "detected": gold_pressure or gold_safe_haven,
                "pressure": gold_pressure,
                "safe_haven": gold_safe_haven,
            },
        },
    }

def add_factor(target: List[Dict[str, str]], label: str, reason: str) -> None:
    target.append({"label": label, "reason": reason})


def build_rate_factor_map_v35(flags: Dict[str, Any], observed: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    up: List[Dict[str, str]] = []
    down: List[Dict[str, str]] = []
    offsetting: List[Dict[str, str]] = []
    psychology: List[Dict[str, str]] = []
    policy: List[Dict[str, str]] = []

    if flags.get("inflationHot"):
        add_factor(up, "通膨硬數據偏熱", "CPI、PPI、PCE 或價格分項偏強，代表前期物價壓力仍有黏性。")
    if flags.get("inflationCooling"):
        add_factor(down, "通膨硬數據降溫", "CPI、PPI、PCE 或價格分項放緩，代表前期物價壓力有所緩和。")
    if flags.get("inflationExpectationUp"):
        add_factor(up, "綜合通膨預期上行", "通膨硬數據、能源供給、勞動市場或成長需求訊號合計後，對通膨預期形成上行壓力。")
        add_factor(policy, "降息預期下降 / 高利率維持更久", "綜合通膨預期偏上行時，市場通常會降低對快速降息的期待。")
    if flags.get("inflationExpectationDown"):
        add_factor(down, "綜合通膨預期下行", "通膨降溫、油價需求疲弱、勞動市場降溫、成長放緩或地緣風險降溫，可能壓低通膨預期。")
        add_factor(policy, "降息預期上升", "綜合通膨預期偏下行時，市場通常會提高對利率下行的期待。")
    if flags.get("inflationExpectationMixed"):
        add_factor(offsetting, "通膨預期多空拉鋸", "通膨上行與下行訊號同時存在，應區分主線與修正因子，避免寫成市場無視通膨。")
    if flags.get("inflationExpectationShift") or flags.get("inflationExpectationShiftSignal"):
        add_factor(psychology, "通膨預期重新評估", "市場可能正在重新評估通膨、油價、成長與政策路徑之間的相對重要性。")

    wti_direction = str(observed.get("WTI", {}).get("direction") or "")
    brent_direction = str(observed.get("Brent", {}).get("direction") or "")
    oil_market_up = wti_direction == "up" or brent_direction == "up"
    oil_market_down = wti_direction == "down" or brent_direction == "down"
    oil_direction_known = bool(wti_direction or brent_direction)

    if oil_market_up:
        add_factor(up, "WTI / Brent 實際上行", "本期 WTI 或 Brent 週線上漲，能源價格對短期通膨預期形成實際上行壓力。")
    elif oil_market_down:
        add_factor(down, "WTI / Brent 實際下行", "本期 WTI 或 Brent 週線下跌，能源價格對短期通膨預期形成實際下行修正。")

    if flags.get("oilSupplyShock"):
        if oil_market_down:
            add_factor(offsetting, "供給風險未獲油價驗證", "新聞出現能源供給風險，但 WTI / Brent 實際下行，需視為新聞與市場分歧。")
        else:
            add_factor(up, "能源供給風險", "能源供給中斷、減產、制裁或地緣風險，是綜合通膨預期上行的來源之一。")
        add_factor(psychology, "能源風險擔憂升溫", "能源相關新聞可能改變市場對未來供給中斷機率的主觀判斷。")
    if flags.get("oilDemandWeakness"):
        if oil_market_up:
            add_factor(offsetting, "需求降溫未獲油價驗證", "新聞出現油品需求疲弱，但 WTI / Brent 實際上行，需判斷是否由供給或風險溢價因素壓過。")
        else:
            add_factor(down, "油價需求面壓力", "油價下跌若來自需求疲弱或庫存增加，可能反映成長降溫與通膨壓力緩和。")
    if flags.get("geopoliticalCooling"):
        if oil_market_up:
            add_factor(offsetting, "地緣降溫未獲油價驗證", "新聞顯示地緣風險降溫，但 WTI / Brent 實際上行，不能直接視為能源通膨緩和。")
        else:
            add_factor(down, "地緣風險擔憂降溫", "停火、和談或地緣風險降溫，可能壓低能源風險擔憂與通膨預期。")
    labor_group = flags.get("factor_groups", {}).get("labor_market", {})
    if flags.get("laborMixed") or labor_group.get("mixed"):
        add_factor(
            offsetting,
            "就業訊號分歧",
            "就業資料內部同時出現轉弱與韌性訊號，例如非農或薪資轉弱但失業率或初領失業金仍顯示韌性；不應直接寫成勞動市場強勁。",
        )
        add_factor(
            policy,
            "Fed 路徑待確認",
            "就業訊號分歧時，市場通常需要下一筆非農、初領失業金、薪資或勞動參與率資料確認方向。",
        )
    if flags.get("laborCooling"):
        add_factor(down, "勞動市場降溫訊號", "非農、ADP、初領失業金、失業率、薪資或裁員消息若明確轉弱，可能提高降息或成長放緩預期。")
        add_factor(policy, "降息預期上升", "勞動市場轉弱會使市場更關注 Fed 雙重使命中的就業風險。")
    if flags.get("laborStrength"):
        add_factor(up, "勞動市場偏強", "非農、薪資、初領失業金或勞動市場緊俏訊號若明確偏強，可能支撐需求韌性與較高利率路徑。")
        add_factor(policy, "降息預期下降 / 升息風險上升", "就業仍強可能讓 Fed 較不急於降息。")
    if flags.get("growthCooling"):
        add_factor(down, "成長動能降溫", "GDP、PMI、零售、房市或消費數據轉弱，可能壓低利率預期。")
    if flags.get("growthStrength"):
        add_factor(up, "成長動能仍強", "GDP、PMI、零售或消費支出偏強，可能支撐高利率維持更久。")

    if flags.get("fedHawkish") or flags.get("highRateExpectation"):
        add_factor(up, "Fed 偏鷹或高利率維持更久", "FOMC、會議紀要、官員談話或點陣圖若偏鷹，會推升政策利率路徑預期。")
        add_factor(policy, "高利率維持更久 / 升息預期上升", "Fed 偏鷹會降低降息期待，甚至提高升息或維持高利率的機率。")
    if flags.get("fedDovish"):
        add_factor(down, "Fed 偏鴿或政策轉向寬鬆", "Fed 若更重視就業、金融穩定或成長風險，可能提高降息預期。")
        add_factor(policy, "降息預期上升", "偏鴿訊號通常使市場上修降息機率。")
    if flags.get("fedLeadershipShift"):
        add_factor(offsetting, "Fed 領導風格或反應函數變化", "新任主席或政策反應函數變化會提高政策路徑不確定性，方向需看偏鷹或偏鴿訊號。")
        add_factor(policy, "政策不確定性上升", "領導風格變化會影響市場對 Fed 容忍通膨、就業與金融風險的判斷。")

    if flags.get("treasurySupplyPressure") or flags.get("refundingPressure") or flags.get("termPremiumPressure"):
        add_factor(up, "公債供需 / 再融資 / 期限溢價壓力", "美債供給、再融資、財政赤字或期限溢價上升，可能不經通膨直接推高長端殖利率。")
    if flags.get("treasuryDemandStrong"):
        add_factor(down, "美債需求強或避險買盤", "標售需求強或避險買盤流入美債，可能壓低長端殖利率。")
    if flags.get("fedBalanceSheetTightening"):
        add_factor(up, "Fed 縮表 / 流動性收緊", "QT 或準備金下降可能推升期限溢價或收緊金融條件。")
    if flags.get("fedBalanceSheetEasing"):
        add_factor(down, "Fed 擴表 / 流動性支持", "QE、擴表或流動性工具可能壓低利率或緩和金融壓力。")
    if flags.get("financialStress"):
        add_factor(down, "金融壓力 / 信用風險", "股市大跌、信用利差擴大、銀行壓力或金融危機可能提高降息或流動性支持預期。")
        add_factor(psychology, "金融穩定風險上升", "金融壓力可能使市場更重視 Fed 的穩定金融體系角色。")
    if flags.get("riskOff") or flags.get("marketExpectationShift"):
        add_factor(offsetting, "市場心理與風險擔憂變化", "地緣政治、停火談判、制裁、關稅或政策表態會改變市場對未來事件的主觀機率。")
        add_factor(psychology, "風險擔憂重新評估", "這類新聞可能直接影響油價、美元、黃金與美債避險買盤。")

    observed_rate = str(observed.get("US10Y", {}).get("direction") or "")
    observed_dollar = str(observed.get("DXY", {}).get("direction") or "")
    observed_gold = str(observed.get("Gold", {}).get("direction") or "")

    up_score = len(up)
    down_score = len(down)
    dominant_bias = "mixed"
    if up_score > down_score:
        dominant_bias = "up"
    elif down_score > up_score:
        dominant_bias = "down"

    market_alignment = "待觀察"
    if observed_rate == "up" and dominant_bias == "up":
        market_alignment = "利率方向與推升因子大致一致"
    elif observed_rate == "down" and dominant_bias == "down":
        market_alignment = "利率方向與壓低因子大致一致"
    elif observed_rate == "up" and dominant_bias == "down":
        market_alignment = "利率上行與因子地圖存在張力，需檢查是否有公債供需、Fed或美元因素壓過成長/通膨降溫訊號"
    elif observed_rate == "down" and dominant_bias == "up":
        market_alignment = "利率下行與因子地圖存在張力，需檢查是否有避險買盤、金融壓力或成長風險壓過通膨/Fed因素"
    elif not observed_rate:
        market_alignment = "US10Y 方向不足，需降低結論強度"

    confidence = "medium"
    if abs(up_score - down_score) >= 3 and observed_rate:
        confidence = "high"
    if up_score == down_score or not observed_rate:
        confidence = "low"

    return {
        "upward_rate_factors": up,
        "downward_rate_factors": down,
        "offsetting_or_uncertain_factors": offsetting,
        "policy_rate_path_expectation": policy,
        "market_expectation_shift": psychology,
        "observed_rate_direction": observed_rate or "unknown",
        "observed_dollar_direction": observed_dollar or "unknown",
        "observed_gold_direction": observed_gold or "unknown",
        "dominant_bias": dominant_bias,
        "market_alignment": market_alignment,
        "confidence": confidence,
    }


def infer_core_contradiction_v35(flags: Dict[str, Any], observed: Dict[str, Dict[str, Any]]) -> str:
    inflation_up = flags.get("inflationExpectationUp") or flags.get("inflationPressure")
    inflation_down = flags.get("inflationExpectationDown") or flags.get("inflationRelief")
    inflation_mixed = flags.get("inflationExpectationMixed") or flags.get("inflationMixed")

    oil_down = observed.get("WTI", {}).get("direction") == "down" or observed.get("Brent", {}).get("direction") == "down"
    oil_up = observed.get("WTI", {}).get("direction") == "up" or observed.get("Brent", {}).get("direction") == "up"
    rate_dir = observed.get("US10Y", {}).get("direction")
    dollar_dir = observed.get("DXY", {}).get("direction")
    gold_dir = observed.get("Gold", {}).get("direction")

    asia_directions = [
        str(observed.get(key, {}).get("direction") or "")
        for key in ("USDJPY", "USDTWD", "USDKRW")
        if str(observed.get(key, {}).get("direction") or "") in {"up", "down"}
    ]
    asia_fx_mixed = "up" in asia_directions and "down" in asia_directions

    if oil_up and rate_dir == "up" and dollar_dir == "up" and gold_dir == "down":
        if asia_fx_mixed:
            return "WTI 與 Brent 上行、美國10年期公債殖利率與美元指數同步偏強、黃金下跌，顯示能源通膨與高利率定價仍在；但日圓、台幣與韓元反應分化，亞洲資金流並未全面同步。"
        return "WTI 與 Brent 上行、美國10年期公債殖利率與美元指數同步偏強、黃金下跌，呈現能源通膨壓力與高利率、強美元的連貫傳導。"
    if oil_down and rate_dir == "up":
        return "油價下跌有助於修正通膨預期，但美國10年期公債殖利率仍上行，顯示市場目前更重視 Fed 路徑、利率預期或公債供需壓力。"
    if inflation_mixed and rate_dir == "up":
        return "通膨上行與下行訊號並存，但美國10年期公債殖利率仍上行，顯示利率端暫時更重視通膨黏性或高利率維持更久。"
    if inflation_mixed and rate_dir == "down":
        return "通膨上行與下行訊號並存，但美國10年期公債殖利率下行，顯示市場開始重視通膨修正、成長降溫或降息預期。"
    if flags.get("laborCooling") and rate_dir == "up":
        return "就業降溫訊號出現，但美國10年期公債殖利率仍上行，顯示就業風險目前只是修正因子，尚未扭轉利率主線。"
    if flags.get("growthCooling") and rate_dir == "up":
        return "成長降溫訊號出現，但美國10年期公債殖利率仍上行，顯示市場暫時更重視利率路徑、通膨黏性或公債供需。"
    if inflation_up and rate_dir == "down":
        return "通膨預期仍有上行壓力，但美國10年期公債殖利率下行，顯示成長風險、避險買盤或金融壓力可能正在壓過通膨因素。"
    if inflation_down and rate_dir == "up":
        return "通膨預期有下行修正，但美國10年期公債殖利率仍上行，顯示 Fed 路徑、美元或公債供需因素可能更具主導性。"
    if dollar_dir == "up" and gold_dir == "up":
        return "美元指數與黃金同步上行，顯示利差支撐美元與避險需求可能同時存在。"
    if oil_up and rate_dir == "down":
        return "油價上行理論上可能推升通膨預期，但美國10年期公債殖利率下行，顯示市場可能更重視成長風險或避險買盤。"
    if rate_dir == "up" and dollar_dir == "up" and gold_dir == "down":
        return "美國10年期公債殖利率與美元指數同步上行，黃金下跌，呈現高利率與強美元壓抑不孳息資產的連貫傳導。"

    return "本期市場訊號未呈現單一明顯矛盾，重點在於確認油價、利率、美元、黃金與亞洲貨幣是否形成一致傳導。"


def infer_primary_macro_story_v35(flags: Dict[str, Any], observed: Dict[str, Dict[str, Any]]) -> str:
    """Choose the weekly main line with observed markets first and news as explanation.

    News can add causes or correction factors, but it cannot override the direction
    actually shown by WTI/Brent, US10Y, DXY, Gold, and Asian FX in the formal window.
    """
    inflation_up = flags.get("inflationExpectationUp") or flags.get("inflationPressure")
    inflation_down = flags.get("inflationExpectationDown") or flags.get("inflationRelief")
    inflation_mixed = flags.get("inflationExpectationMixed") or flags.get("inflationMixed")

    oil_down = observed.get("WTI", {}).get("direction") == "down" or observed.get("Brent", {}).get("direction") == "down"
    oil_up = observed.get("WTI", {}).get("direction") == "up" or observed.get("Brent", {}).get("direction") == "up"
    rate_up = observed.get("US10Y", {}).get("direction") == "up"
    rate_down = observed.get("US10Y", {}).get("direction") == "down"
    dollar_up = observed.get("DXY", {}).get("direction") == "up"
    gold_down = observed.get("Gold", {}).get("direction") == "down"

    asia_directions = [
        str(observed.get(key, {}).get("direction") or "")
        for key in ("USDJPY", "USDTWD", "USDKRW")
        if str(observed.get(key, {}).get("direction") or "") in {"up", "down"}
    ]
    asia_fx_mixed = "up" in asia_directions and "down" in asia_directions

    # Strongest current-week market pattern: energy, rates, dollar and gold broadly
    # point to inflation/high-rate pressure, while Asian FX may still diverge.
    if oil_up and rate_up and dollar_up:
        if asia_fx_mixed:
            return "油價上行與高利率定價並存，美元偏強但亞洲貨幣分化"
        if gold_down:
            return "油價上行強化通膨壓力，高利率支撐美元"
        return "油價上行與高利率定價並存"

    if rate_up and dollar_up and gold_down:
        if inflation_mixed:
            return "高利率與通膨拉鋸，美元偏強"
        return "高利率支撐強美元"
    if inflation_mixed and rate_up:
        return "通膨預期多空拉鋸，但利率維持偏上"
    if inflation_mixed:
        return "通膨預期多空拉鋸"
    if oil_down and inflation_up:
        return "油價修正通膨壓力"
    if oil_up:
        return "油價上行推升能源通膨壓力"
    if inflation_up and rate_up:
        return "通膨壓力推升利率"
    if inflation_down and rate_down:
        return "通膨降溫壓低利率"
    if flags.get("laborCooling") or flags.get("growthCooling"):
        return "就業或成長降溫"
    if flags.get("financialStress"):
        return "金融壓力升溫"
    if flags.get("riskOff") and dollar_up:
        return "避險需求支撐美元"
    if dollar_up:
        return "美元偏強主導市場"
    return "市場等待新觸發點"

def build_expected_chain_v35(primary_story: str, flags: Dict[str, Any]) -> List[str]:
    story = str(primary_story or "")

    if "油價上行與高利率" in story or "油價上行強化通膨壓力" in story:
        return ["WTI 與 Brent 上行，能源通膨壓力增加", "美國10年期公債殖利率偏上，高利率定價仍在", "美元指數偏強、黃金承受利率與美元壓力", "日圓、台幣與韓元需分別驗證，不預設全面同向", "觀察通膨數據、Fed 路徑與油價是否延續共振"]
    if "高利率" in story or "強美元" in story:
        return ["Fed 路徑或高利率預期受到關注", "美國10年期公債殖利率偏上", "美元指數受利差或避險需求支撐", "亞洲貨幣需逐一驗證，不預設全面同向", "黃金、油價與風險資產依各自修正因子反應"]
    if "通膨拉鋸" in story or "多空拉鋸" in story:
        return ["通膨上行與下行訊號並存", "市場重新評估油價、成長、勞動與 Fed 權重", "美國10年期公債殖利率方向取決於主導因子", "美元指數反映利差與避險需求", "亞洲貨幣、黃金與油價可能出現分歧"]
    if "油價修正" in story:
        return ["油價下跌修正能源通膨壓力", "通膨預期出現下行修正", "利率是否回落取決於 Fed 與公債供需", "美元方向取決於利差與避險需求", "亞洲貨幣與黃金需交叉驗證"]
    if "油價推升" in story:
        return ["油價上行提高能源通膨疑慮", "通膨預期可能重新升溫", "降息預期受到限制", "美國10年期公債殖利率偏上", "美元與亞洲貨幣壓力需同步觀察"]
    if "通膨壓力" in story:
        return ["通膨壓力或物價黏性升溫", "市場降低快速降息期待", "美國10年期公債殖利率偏上", "美元指數可能受利差支撐", "亞洲貨幣與黃金承受壓力"]
    if "通膨降溫" in story:
        return ["通膨數據或通膨預期降溫", "市場提高利率下行或降息期待", "美國10年期公債殖利率偏下", "美元支撐可能減弱", "黃金與亞洲貨幣反應需看避險與風險偏好"]
    if "就業" in story or "成長" in story:
        return ["就業或成長數據降溫", "市場重新評估景氣與降息預期", "美國10年期公債殖利率理論上偏下", "美元走勢取決於利差下降與避險需求的拉鋸", "黃金可能受避險或利率下行支撐"]
    if "金融壓力" in story:
        return ["金融壓力或信用風險升溫", "市場提高避險與政策支持預期", "美國10年期公債殖利率可能受避險買盤壓低", "美元與黃金可能同時受避險需求支撐", "風險資產承壓"]
    if "美元" in story:
        return ["美元需求或利差支撐升溫", "美元指數偏強", "亞洲貨幣承壓", "美元計價商品受到牽制", "市場流動性偏緊"]

    return ["新聞事件尚未形成單一主線", "觀察美國10年期公債殖利率是否確認方向", "觀察美元指數是否跟隨利率變化", "觀察油價與黃金是否提供修正訊號", "觀察亞洲貨幣是否同步反應"]


def infer_final_judgment(matched_links: List[str], divergent_links: List[str], modifiers: List[str]) -> str:
    if len(matched_links) >= 4 and not divergent_links:
        return "支持"
    if matched_links and divergent_links:
        return "部分支持，但存在分歧"
    if matched_links and modifiers:
        return "部分支持，但存在修正因子"
    if divergent_links and not matched_links:
        return "分歧待觀察"
    return "待觀察"


def build_transmission_diagnosis_v35(
    observed: Dict[str, Dict[str, Any]],
    flags: Dict[str, Any],
) -> Dict[str, Any]:
    rate_map = build_rate_factor_map_v35(flags, observed)
    core_contradiction = infer_core_contradiction_v35(flags, observed)
    primary_story = infer_primary_macro_story_v35(flags, observed)
    expected_chain = build_expected_chain_v35(primary_story, flags)

    matched_links: List[str] = []
    divergent_links: List[str] = []
    modifiers: List[str] = []

    observed_rate = rate_map.get("observed_rate_direction")
    dominant_bias = rate_map.get("dominant_bias")

    if observed_rate == "up":
        if dominant_bias == "up":
            matched_links.append("美國10年期公債殖利率上行，與推升利率因子大致一致。")
        elif dominant_bias == "down":
            divergent_links.append("美國10年期公債殖利率上行，但新聞因子中也存在壓低利率訊號，需判斷是否有更強反向因子。")
    elif observed_rate == "down":
        if dominant_bias == "down":
            matched_links.append("美國10年期公債殖利率下行，與壓低利率因子大致一致。")
        elif dominant_bias == "up":
            divergent_links.append("美國10年期公債殖利率下行，但新聞因子中也存在推升利率訊號，需判斷避險、金融壓力或成長風險是否占上風。")

    if flags.get("inflationExpectationMixed"):
        modifiers.append("通膨預期呈現多空拉鋸：能源價格或偏熱物價訊號形成上行壓力，但通膨降溫、勞動轉弱或其他修正因子仍存在。")
    elif flags.get("inflationExpectationUp"):
        matched_links.append("綜合通膨預期存在上行壓力，來源可能包括通膨硬數據、實際油價上行、能源供給、薪資或成長需求。")
    elif flags.get("inflationExpectationDown"):
        matched_links.append("綜合通膨預期存在下行壓力，來源可能包括通膨降溫、實際油價下行、勞動降溫或成長放緩。")
    if flags.get("inflationExpectationShift") or flags.get("inflationExpectationShiftSignal"):
        modifiers.append("市場可能正在重新評估通膨預期，需比較油價、成長、勞動與 Fed 路徑哪個權重較高。")

    wti_dir = observed.get("WTI", {}).get("direction")
    brent_dir = observed.get("Brent", {}).get("direction")
    oil_up = wti_dir == "up" or brent_dir == "up"
    oil_down = wti_dir == "down" or brent_dir == "down"

    if oil_up:
        matched_links.append("WTI 或 Brent 實際上行，短期能源通膨壓力增加。")
        if flags.get("oilDemandWeakness"):
            divergent_links.append("WTI 或 Brent 上行，但新聞同時出現需求疲弱訊號，需判斷是否由供給、庫存或風險溢價因素壓過需求降溫。")
        if flags.get("geopoliticalCooling"):
            divergent_links.append("新聞顯示地緣風險降溫，但 WTI 或 Brent 實際上行，地緣降溫尚未獲油價驗證。")

    if oil_down and (flags.get("oilDemandWeakness") or flags.get("geopoliticalCooling")):
        matched_links.append("WTI 或 Brent 下行，且新聞出現需求疲弱或地緣風險降溫，油價方向與通膨預期降溫修正大致一致。")
    elif oil_down and flags.get("oilSupplyShock"):
        divergent_links.append("WTI 或 Brent 下行，但新聞同時出現供給風險，需判斷市場是否更重視需求放緩或風險擔憂降溫。")
    elif oil_down:
        modifiers.append("WTI 或 Brent 下行，屬於能源通膨降溫或通膨下修因子；是否影響利率需看 Fed 路徑與公債供需是否壓過此修正。")

    if not wti_dir and not brent_dir and (flags.get("oilSupplyShock") or flags.get("oilDemandWeakness")):
        modifiers.append("油價新聞已出現，但 WTI / Brent 方向不足，能源通膨判斷需降低結論強度。")

    if observed.get("DXY", {}).get("direction") == "up":
        matched_links.append("美元指數偏強，需檢查是利差支撐、避險美元，還是非美貨幣弱勢所造成。")
        asia_up_labels: List[str] = []
        asia_down_labels: List[str] = []
        for key, label in [("USDJPY", "日圓"), ("USDTWD", "台幣"), ("USDKRW", "韓元")]:
            pair_direction = observed.get(key, {}).get("direction")
            if pair_direction == "up":
                asia_up_labels.append(label)
                matched_links.append(f"美元兌{label}上行，符合該貨幣承壓的外溢效果。")
            elif pair_direction == "down":
                asia_down_labels.append(label)
        if asia_up_labels and asia_down_labels:
            modifiers.append(
                f"亞洲貨幣反應分化：{'、'.join(asia_up_labels)}承壓，但{'、'.join(asia_down_labels)}相對走強，不宜概括為亞洲貨幣全面走弱。"
            )
    elif observed.get("DXY", {}).get("direction") == "down":
        matched_links.append("美元指數偏弱，可能反映利差支撐下降、風險偏好改善或非美貨幣反彈。")

    if observed.get("Gold", {}).get("direction") == "up":
        modifiers.append("黃金上行可能反映避險需求、實質利率下行或通膨避險，需與美元與利率方向交叉驗證。")
    elif observed.get("Gold", {}).get("direction") == "down":
        matched_links.append("黃金下行通常符合高利率或強美元壓力。")

    for factor in rate_map.get("offsetting_or_uncertain_factors", []):
        modifiers.append(f"{factor.get('label', '')}：{factor.get('reason', '')}")

    matched = unique_list(matched_links)[:9]
    divergent = unique_list(divergent_links)[:9]
    mods = unique_list(modifiers)[:9]

    final_judgment = infer_final_judgment(matched, divergent, mods)
    if final_judgment == "支持" and (
        rate_map.get("confidence") == "low" or rate_map.get("dominant_bias") == "mixed"
    ):
        final_judgment = "部分支持，但存在修正因子"

    return {
        "core_contradiction": core_contradiction,
        "primary_macro_story": primary_story,
        "expected_chain": expected_chain,
        "observed_market": observed,
        "detected_news_events": flags,
        "rate_factor_map": rate_map,
        "matched_links": matched,
        "divergent_links": divergent,
        "modifiers": mods,
        "final_judgment": final_judgment,
    }


def build_compact_weekly_v35_diagnosis(diagnosis: Dict[str, Any]) -> Dict[str, Any]:
    rate_map = diagnosis.get("rate_factor_map", {})
    up = rate_map.get("upward_rate_factors", [])
    down = rate_map.get("downward_rate_factors", [])
    offsetting = rate_map.get("offsetting_or_uncertain_factors", [])

    dominant_driver = diagnosis.get("primary_macro_story") or "待確認"

    correction_factors: List[str] = []
    for item in down[:3]:
        label = item.get("label", "")
        if label:
            correction_factors.append(label)
    for item in offsetting[:3]:
        label = item.get("label", "")
        if label:
            correction_factors.append(label)
    if not correction_factors:
        correction_factors = diagnosis.get("modifiers", [])[:3]

    asset_validation = []
    asset_validation.extend(diagnosis.get("matched_links", [])[:5])
    if diagnosis.get("divergent_links"):
        asset_validation.extend(diagnosis.get("divergent_links", [])[:3])

    next_period_watch = []
    flags = diagnosis.get("detected_news_events", {})
    observed = diagnosis.get("observed_market", {})

    if flags.get("inflationExpectationMixed") or flags.get("inflationExpectationShift"):
        next_period_watch.append("通膨上行與下行訊號誰會成為下一期主導因子")
    if observed.get("WTI", {}).get("direction") == "down" or observed.get("Brent", {}).get("direction") == "down":
        next_period_watch.append("油價下行是否開始壓低利率與通膨預期")
    if flags.get("laborMixed"):
        next_period_watch.append("就業分歧訊號將由非農、初領失業金、失業率或薪資中的哪一項確認方向")
    elif flags.get("laborCooling") or flags.get("growthCooling"):
        next_period_watch.append("勞動或成長降溫是否擴大")
    if flags.get("fedHawkish") or flags.get("highRateExpectation"):
        next_period_watch.append("Fed 是否延續高利率維持更久的訊號")
    if not next_period_watch:
        next_period_watch = ["美國10年期公債殖利率是否確認方向", "美元指數是否跟隨利率變化", "油價、黃金與亞洲貨幣是否提供修正訊號"]

    return {
        "dominant_driver": dominant_driver,
        "correction_factors": unique_list(correction_factors)[:5],
        "divergence_signal": diagnosis.get("core_contradiction", ""),
        "asset_validation": unique_list(asset_validation)[:8],
        "next_period_watch": unique_list(next_period_watch)[:5],
    }


def build_weekly_v35_diagnosis(
    week_dir: Path,
    start_override: str = "",
    end_override: str = "",
) -> Dict[str, Any]:
    weekly_market_series = load_json(week_dir / "weekly_market_series.json", {}) or {}
    weekly_news_context_json = load_json(week_dir / "weekly_news_context.json", {}) or {}
    weekly_news_context_md = load_text(week_dir / "weekly_news_context.md")
    macro_background_context_json = load_json(week_dir / "macro_background_context.json", {}) or {}
    macro_background_context_md = load_text(week_dir / "macro_background_context.md")

    if not weekly_market_series:
        raise FileNotFoundError(f"Missing or empty weekly_market_series.json in {week_dir}")

    analysis_window = infer_analysis_window_from_source(
        week_dir,
        start_override=start_override,
        end_override=end_override,
        weekly_market_series=weekly_market_series,
        weekly_news_context_json=weekly_news_context_json,
    )

    observed = build_observed_market(weekly_market_series, analysis_window)
    news_text = collect_news_text(
        weekly_news_context_json=weekly_news_context_json,
        weekly_news_context_md=weekly_news_context_md,
        macro_background_context_json=macro_background_context_json,
        macro_background_context_md=macro_background_context_md,
    )
    flags = extract_macro_event_flags_v35(news_text, observed=observed)
    transmission = build_transmission_diagnosis_v35(observed, flags)
    compact = build_compact_weekly_v35_diagnosis(transmission)

    return {
        "meta": {
            "source": "macro_v35_diagnosis.py",
            "week_dir": str(week_dir),
            "analysis_window": analysis_window,
            "input_files": {
                "weekly_market_series_json": (week_dir / "weekly_market_series.json").exists(),
                "weekly_news_context_json": (week_dir / "weekly_news_context.json").exists(),
                "weekly_news_context_md": (week_dir / "weekly_news_context.md").exists(),
                "macro_background_context_json": (week_dir / "macro_background_context.json").exists(),
                "macro_background_context_md": (week_dir / "macro_background_context.md").exists(),
            },
            "note": "Rule-based V35 diagnosis. News evidence is segmented by record, future/watch text is excluded from directional regex, and observed market direction has precedence for oil, DXY and Gold validation.",
        },
        **transmission,
        "weekly_v35_diagnosis": compact,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default=os.getenv("WEEK_DIR", "").strip())
    parser.add_argument("--start", type=str, default=os.getenv("ANALYSIS_START_DATE", "").strip())
    parser.add_argument("--end", type=str, default=os.getenv("ANALYSIS_END_DATE", "").strip())
    parser.add_argument("--output", type=str, default="")
    args = parser.parse_args()

    week_dir = resolve_week_dir(args.week_dir)
    diagnosis = build_weekly_v35_diagnosis(
        week_dir=week_dir,
        start_override=args.start,
        end_override=args.end,
    )

    out_path = Path(args.output) if args.output else week_dir / "weekly_v35_diagnosis.json"
    save_json(out_path, diagnosis)

    compact = diagnosis.get("weekly_v35_diagnosis", {})
    print(f"[OK] Created {out_path}")
    print(f"[INFO] Analysis window: {diagnosis.get('meta', {}).get('analysis_window', {}).get('label')}")
    print(f"[INFO] Dominant driver: {compact.get('dominant_driver')}")
    print(f"[INFO] Final judgment: {diagnosis.get('final_judgment')}")


if __name__ == "__main__":
    main()
