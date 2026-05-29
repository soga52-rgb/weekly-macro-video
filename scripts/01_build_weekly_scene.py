#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Step 01
Build weekly_video_scene.json from input data.

MVP scope:
1. Read four JSON files from data/
2. Classify weekly asset path from Friday-to-Thursday data points
3. Build six-scene weekly video analysis skeleton
4. Save output to output/weekly/YYYY-MM-DD/weekly_video_scene.json

Input files:
- data/history_data.json
- data/news_narrative.json
- data/visual_note.json
- data/market_snapshot.json
"""

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output" / "weekly"


INPUT_FILES = {
    "history": DATA_DIR / "history_data.json",
    "news": DATA_DIR / "news_narrative.json",
    "visual_note": DATA_DIR / "visual_note.json",
    "market_snapshot": DATA_DIR / "market_snapshot.json",
    # Optional file created by Step 00.
    # Used only to append latest daily market values when history_data.json is one day short.
    "weekly_video_source": DATA_DIR / "weekly_video_source.json",
}


ASSET_ORDER = [
    "美國10年期公債殖利率",
    "美元指數",
    "美元/台幣",
    "美元/日圓",
    "美元/人民幣",
    "黃金",
    "原油",
]


def load_json(path: Path, default: Any) -> Any:
    """Load JSON file. Return default when file does not exist or is invalid."""
    if not path.exists():
        print(f"[WARN] Missing file: {path}")
        return default

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as exc:
        print(f"[WARN] Invalid JSON: {path} ({exc})")
        return default


def save_json(path: Path, data: Dict[str, Any]) -> None:
    """Save JSON file with UTF-8 encoding."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value: Any) -> Optional[float]:
    """Convert value to float when possible."""
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def classify_path(values: List[float]) -> str:
    """
    Classify weekly path using 5 trading points:
    previous Friday, Monday, Tuesday, Wednesday, Thursday.

    This is intentionally simple for V1.
    """
    clean_values = [v for v in values if v is not None]

    if len(clean_values) < 3:
        return "資料不足"

    start = clean_values[0]
    end = clean_values[-1]
    high = max(clean_values)
    low = min(clean_values)
    high_idx = clean_values.index(high)
    low_idx = clean_values.index(low)

    full_range = high - low
    if start == 0:
        total_change_pct = 0
    else:
        total_change_pct = (end - start) / abs(start)

    if full_range == 0:
        return "窄幅盤整"

    # Range threshold: if end-start is small compared with weekly range, treat as volatile or range-bound.
    end_near_high = (high - end) <= full_range * 0.25
    end_near_low = (end - low) <= full_range * 0.25

    rises = 0
    falls = 0
    for i in range(1, len(clean_values)):
        if clean_values[i] > clean_values[i - 1]:
            rises += 1
        elif clean_values[i] < clean_values[i - 1]:
            falls += 1

    if abs(total_change_pct) < 0.002 and full_range / max(abs(start), 1) < 0.006:
        return "窄幅盤整"

    if rises >= len(clean_values) - 2 and end > start:
        return "一路走升"

    if falls >= len(clean_values) - 2 and end < start:
        return "一路走低"

    if high_idx <= 2 and end < high:
        if end_near_high:
            return "先高後盤整"
        return "先高後低"

    if low_idx <= 2 and end > low:
        if end_near_low:
            return "先低後盤整"
        return "先低後高"

    if abs(end - start) <= full_range * 0.3:
        return "高低震盪"

    return "震盪偏升" if end > start else "震盪偏弱"


def format_change(start: Optional[float], end: Optional[float], unit: str = "") -> str:
    """Format weekly change."""
    if start is None or end is None:
        return ""

    change = end - start

    if unit == "bp":
        return f"{change * 100:.1f} bp"

    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.2f}"


def normalize_asset_name(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace(" ", "").replace("_", "").replace("-", "")
    text = text.replace("／", "/")
    return text


ASSET_ALIASES = {
    "美國10年期公債殖利率": [
        "美國10年期公債殖利率", "美國10年期公債", "美國10年債", "10年期美債",
        "us10y", "ust10y", "10y", "^tnx"
    ],
    "美元指數": [
        "美元指數", "dxy", "dollarindex", "dx-y.nyb"
    ],
    "美元/台幣": [
        "美元/台幣", "美元台幣", "台幣", "新台幣", "usdtwd", "usdtwd=x"
    ],
    "美元/日圓": [
        "美元/日圓", "美元日圓", "日圓", "日元", "usdjpy", "usdjpy=x"
    ],
    "美元/人民幣": [
        "美元/人民幣", "美元人民幣", "人民幣", "usdcny", "usdcny=x"
    ],
    "黃金": [
        "黃金", "gold", "xau", "xauusd", "gc=f"
    ],
    "原油": [
        "原油", "wti", "西德州原油", "輕原油", "oil", "cl=f"
    ],
}


def canonical_asset_name(value: Any) -> str:
    normalized = normalize_asset_name(value)
    if not normalized:
        return ""

    for canonical, aliases in ASSET_ALIASES.items():
        if normalized == normalize_asset_name(canonical):
            return canonical
        for alias in aliases:
            if normalized == normalize_asset_name(alias):
                return canonical

    for canonical, aliases in ASSET_ALIASES.items():
        keywords = [normalize_asset_name(canonical)] + [normalize_asset_name(x) for x in aliases]
        if any(k and k in normalized for k in keywords):
            return canonical

    return str(value or "").strip()


def extract_value_from_market_item(item: Dict[str, Any]) -> Optional[float]:
    for key in [
        "value",
        "latest_value",
        "close",
        "price",
        "last",
        "level",
        "yield",
        "rate",
        "current",
        "current_value",
        "end_value",
    ]:
        parsed = to_float(item.get(key))
        if parsed is not None:
            return parsed
    return None


def extract_latest_daily_summary(weekly_video_source: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    summaries = weekly_video_source.get("daily_summaries")
    if isinstance(summaries, list) and summaries:
        candidates = [x for x in summaries if isinstance(x, dict)]
        dated = [x for x in candidates if x.get("date")]
        if dated:
            return sorted(dated, key=lambda x: str(x.get("date")))[-1]
        return candidates[-1] if candidates else None

    daily_summary = weekly_video_source.get("daily_summary")
    if isinstance(daily_summary, dict):
        return daily_summary

    return None


def extract_today_market_values(weekly_video_source: Dict[str, Any]) -> Dict[str, float]:
    """
    Extract latest numeric asset values from Step 00 weekly_video_source / today_daily_source.

    If the source only contains directional text without numeric market values,
    this returns an empty dict and leaves history_data.json unchanged.
    """
    latest = extract_latest_daily_summary(weekly_video_source)
    if not isinstance(latest, dict):
        return {}

    raw_snapshot = (
        latest.get("market_snapshot")
        or latest.get("market_data")
        or latest.get("markets")
        or latest.get("asset_values")
        or latest.get("assets")
    )

    values: Dict[str, float] = {}

    if isinstance(raw_snapshot, dict):
        for raw_name, raw_value in raw_snapshot.items():
            asset_name = canonical_asset_name(raw_name)
            parsed = to_float(raw_value)
            if asset_name and parsed is not None:
                values[asset_name] = parsed
        return values

    if isinstance(raw_snapshot, list):
        for item in raw_snapshot:
            if not isinstance(item, dict):
                continue

            raw_name = (
                item.get("asset_name")
                or item.get("asset")
                or item.get("name")
                or item.get("label")
                or item.get("title")
                or item.get("symbol")
                or item.get("ticker")
            )
            asset_name = canonical_asset_name(raw_name)
            parsed = extract_value_from_market_item(item)
            if asset_name and parsed is not None:
                values[asset_name] = parsed

    return values


def infer_today_label(weekly_video_source: Dict[str, Any]) -> str:
    latest = extract_latest_daily_summary(weekly_video_source)
    if isinstance(latest, dict) and latest.get("date"):
        return str(latest.get("date"))

    range_data = weekly_video_source.get("range")
    if isinstance(range_data, dict) and range_data.get("end_date"):
        return str(range_data.get("end_date"))

    if weekly_video_source.get("end_date"):
        return str(weekly_video_source.get("end_date"))

    return date.today().isoformat()


def append_today_values_to_history(history_data: Dict[str, Any], weekly_video_source: Dict[str, Any]) -> Dict[str, Any]:
    """
    Append latest numeric market values to history_data.assets if:
    - weekly_video_source contains numeric value for the same asset
    - latest date/label is not already in that asset's dates list

    Conservative behavior:
    - If no numeric values exist, do nothing.
    - If a date already exists, do not duplicate.
    """
    if not isinstance(history_data, dict) or not isinstance(weekly_video_source, dict):
        return history_data

    today_values = extract_today_market_values(weekly_video_source)
    if not today_values:
        print("[INFO] No numeric today market values found in weekly_video_source; history_data unchanged.")
        return history_data

    today_label = infer_today_label(weekly_video_source)
    raw_assets = history_data.get("assets")

    if isinstance(raw_assets, list):
        appended_count = 0

        for item in raw_assets:
            if not isinstance(item, dict):
                continue

            asset_name = item.get("asset_name") or item.get("name") or item.get("asset")
            canonical = canonical_asset_name(asset_name)
            if canonical not in today_values:
                continue

            dates = item.setdefault("dates", [])
            values = item.setdefault("values", [])

            if not isinstance(dates, list) or not isinstance(values, list):
                continue

            if str(today_label) in [str(x) for x in dates]:
                continue

            dates.append(today_label)
            values.append(today_values[canonical])
            appended_count += 1

        print(f"[INFO] Appended today values to history_data.assets: {appended_count} asset(s).")
        return history_data

    # Legacy wide format: history_data["美元指數"] = [...]
    appended_count = 0
    for asset_name in ASSET_ORDER:
        values = history_data.get(asset_name)
        if not isinstance(values, list):
            continue

        canonical = canonical_asset_name(asset_name)
        if canonical not in today_values:
            continue

        if len(values) >= 6:
            continue

        values.append(today_values[canonical])
        appended_count += 1

    print(f"[INFO] Appended today values to legacy history_data format: {appended_count} asset(s).")
    return history_data


def extract_asset_series(history_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expected flexible input formats:
    1. {"assets": [{"asset_name": "...", "values": [..], "dates": [..], "unit": ""}]}
    2. {"美國10年期公債殖利率": [..], "美元指數": [..]}
    """
    assets = []

    raw_assets = history_data.get("assets")
    if isinstance(raw_assets, list):
        for item in raw_assets:
            asset_name = item.get("asset_name") or item.get("name") or item.get("asset")
            values = [to_float(v) for v in item.get("values", [])]
            unit = item.get("unit", "")
            assets.append(build_asset_summary(asset_name, values, unit))
        return [a for a in assets if a["asset_name"]]

    for asset_name in ASSET_ORDER:
        raw_values = history_data.get(asset_name)
        if isinstance(raw_values, list):
            values = [to_float(v) for v in raw_values]
            unit = "bp" if asset_name == "美國10年期公債殖利率" else ""
            assets.append(build_asset_summary(asset_name, values, unit))

    return assets


def build_asset_summary(asset_name: str, values: List[Optional[float]], unit: str = "") -> Dict[str, Any]:
    """Build asset weekly summary."""
    clean_values = [v for v in values if v is not None]
    start = clean_values[0] if clean_values else None
    end = clean_values[-1] if clean_values else None
    path_type = classify_path(clean_values)

    return {
        "asset_name": asset_name,
        "start_value": start,
        "end_value": end,
        "weekly_change": format_change(start, end, unit),
        "path_type": path_type,
        "path_comment": build_path_comment(asset_name, path_type),
        "raw_values": clean_values,
    }


def build_path_comment(asset_name: str, path_type: str) -> str:
    """Generate short path comment."""
    comments = {
        "一路走升": "整週方向偏強，代表市場定價持續累積。",
        "一路走低": "整週方向偏弱，代表市場預期持續降溫。",
        "先高後低": "週初反應較強，後半週出現修正。",
        "先低後高": "週初偏弱，後半週重新定價走強。",
        "先高後盤整": "前半週快速上修後，維持在相對高檔。",
        "先低後盤整": "前半週下修後，維持在相對低檔。",
        "高低震盪": "週內訊號分歧，缺乏單一方向。",
        "窄幅盤整": "波動有限，市場等待下一個催化。",
        "震盪偏升": "週內雖有震盪，但收斂後仍偏上行。",
        "震盪偏弱": "週內雖有震盪，但收斂後仍偏下行。",
        "資料不足": "目前資料點不足，暫不判斷週內路徑。",
    }
    return f"{asset_name}：{comments.get(path_type, '走勢仍需搭配事件判讀。')}"


def get_week_label(market_snapshot: Dict[str, Any]) -> Dict[str, str]:
    """Get week period label from market_snapshot or use today's date."""
    week_start = market_snapshot.get("week_start", "")
    week_end = market_snapshot.get("week_end", "") or date.today().isoformat()

    if not week_start:
        week_start = "上週五"

    return {
        "week_start": week_start,
        "week_end": week_end,
        "week_label": f"{week_start} - {week_end}",
    }


def extract_events(news_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract weekly events from News_Narrative."""
    raw_events = news_data.get("events") or news_data.get("key_events") or []
    events = []

    if not isinstance(raw_events, list):
        return events

    for item in raw_events[:6]:
        events.append({
            "event_title": item.get("event_title") or item.get("title") or "",
            "event_category": item.get("event_category") or item.get("category") or "",
            "event_summary": item.get("event_summary") or item.get("summary") or "",
            "macro_relevance": item.get("macro_relevance") or "",
            "impact_direction": item.get("impact_direction") or "",
        })

    return events


def build_weekly_scene(
    history_data: Dict[str, Any],
    news_data: Dict[str, Any],
    visual_note: Dict[str, Any],
    market_snapshot: Dict[str, Any],
) -> Dict[str, Any]:
    """Build weekly video scene JSON."""
    week = get_week_label(market_snapshot)
    asset_summaries = extract_asset_series(history_data)
    events = extract_events(news_data)

    main_theme = (
        visual_note.get("main_theme")
        or news_data.get("main_theme")
        or market_snapshot.get("main_theme")
        or "本週市場主線待資料補齊後判斷"
    )

    inflation_direction = (
        news_data.get("inflation_expectation_direction")
        or visual_note.get("inflation_expectation_direction")
        or "待判斷"
    )

    transmission_verdict = (
        news_data.get("transmission_verdict")
        or visual_note.get("transmission_verdict")
        or "待判斷"
    )

    return {
        "video_meta": {
            "week_start": week["week_start"],
            "week_end": week["week_end"],
            "week_label": week["week_label"],
            "video_title": "Weekly Macro Expectation Check",
            "language": "zh-TW",
            "target_duration_sec": 420,
            "version": "v1_mvp",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "macro_summary": {
            "main_theme": main_theme,
            "inflation_expectation_direction": inflation_direction,
            "rate_direction": market_snapshot.get("rate_direction", "待判斷"),
            "dollar_direction": market_snapshot.get("dollar_direction", "待判斷"),
            "asia_fx_direction": market_snapshot.get("asia_fx_direction", "待判斷"),
            "gold_direction": market_snapshot.get("gold_direction", "待判斷"),
            "transmission_verdict": transmission_verdict,
        },
        "scenes": [
            {
                "scene_id": "scene_01",
                "scene_order": 1,
                "card_title": "本週主要資產走勢路徑",
                "card_subtitle": "先看數據怎麼走，再判斷是否符合預期",
                "duration_target_sec": 65,
                "visual_type": "market_path_card",
                "data_sources": ["History_Data", "Market Snapshot"],
                "data_summary": {
                    "period": "上週五收盤至本週四收盤",
                    "assets": asset_summaries,
                },
                "analysis_logic": {
                    "main_market_path": market_snapshot.get("main_market_path", ""),
                    "most_important_asset_move": market_snapshot.get("most_important_asset_move", ""),
                    "initial_observation": "本段只描述本週主要資產走勢路徑，不急著下總經結論。",
                },
                "visual_content": {
                    "headline": "本週市場先看路徑，不只看漲跌",
                    "table_columns": ["資產", "週變化", "週內路徑", "解讀"],
                    "highlight_box": main_theme,
                },
                "narration": {
                    "script": "",
                    "tts_file": "scene_01.mp3",
                },
                "output_files": {
                    "card_png": "cards/card_01.png",
                    "scene_video": "video/scene_01.mp4",
                },
            },
            {
                "scene_id": "scene_02",
                "scene_order": 2,
                "card_title": "本週經濟數據與事件",
                "card_subtitle": "找出影響通膨、利率與美元的事件組合",
                "duration_target_sec": 75,
                "visual_type": "event_cluster_card",
                "data_sources": ["News_Narrative", "Visual Note"],
                "data_summary": {
                    "events": events,
                },
                "analysis_logic": {
                    "dominant_event_cluster": news_data.get("dominant_event_cluster", ""),
                    "event_balance": news_data.get("event_balance", "待判斷"),
                    "link_to_next_scene": "這些事件接下來要轉換成通膨預期判斷。",
                },
                "visual_content": {
                    "headline": "本週影響市場的不是單一事件，而是事件組合",
                    "event_groups": visual_note.get("event_groups", []),
                    "highlight_box": visual_note.get("event_highlight", ""),
                },
                "narration": {
                    "script": "",
                    "tts_file": "scene_02.mp3",
                },
                "output_files": {
                    "card_png": "cards/card_02.png",
                    "scene_video": "video/scene_02.mp4",
                },
            },
            {
                "scene_id": "scene_03",
                "scene_order": 3,
                "card_title": "通膨預期方向",
                "card_subtitle": "判斷事件對通膨預期的影響方向",
                "duration_target_sec": 75,
                "visual_type": "inflation_factor_card",
                "data_sources": ["News_Narrative", "Market Snapshot"],
                "data_summary": {
                    "inflation_up_factors": news_data.get("inflation_up_factors", []),
                    "inflation_down_factors": news_data.get("inflation_down_factors", []),
                    "mixed_or_uncertain_factors": news_data.get("mixed_or_uncertain_factors", []),
                },
                "analysis_logic": {
                    "inflation_expectation_direction": inflation_direction,
                    "reasoning": news_data.get("inflation_reasoning", ""),
                    "confidence": news_data.get("inflation_confidence", "中"),
                    "link_to_rates": "通膨預期變化會影響利率定價，但利率也可能受到非通膨因素干擾。",
                },
                "visual_content": {
                    "headline": f"本週通膨預期：{inflation_direction}",
                    "left_column_title": "推升通膨預期",
                    "right_column_title": "壓低通膨預期",
                    "center_verdict": inflation_direction,
                    "highlight_box": news_data.get("inflation_highlight", ""),
                },
                "narration": {
                    "script": "",
                    "tts_file": "scene_03.mp3",
                },
                "output_files": {
                    "card_png": "cards/card_03.png",
                    "scene_video": "video/scene_03.mp4",
                },
            },
            {
                "scene_id": "scene_04",
                "scene_order": 4,
                "card_title": "利率走勢與原因拆解",
                "card_subtitle": "區分通膨驅動與非通膨驅動",
                "duration_target_sec": 85,
                "visual_type": "rate_driver_card",
                "data_sources": ["History_Data", "News_Narrative", "Market Snapshot"],
                "data_summary": {
                    "us10y": next((a for a in asset_summaries if a["asset_name"] == "美國10年期公債殖利率"), {}),
                },
                "analysis_logic": {
                    "inflation_driven_factors": news_data.get("inflation_driven_rate_factors", []),
                    "non_inflation_rate_factors": news_data.get("non_inflation_rate_factors", []),
                    "main_rate_driver": news_data.get("main_rate_driver", "待判斷"),
                    "rate_vs_inflation_consistency": news_data.get("rate_vs_inflation_consistency", "待判斷"),
                },
                "visual_content": {
                    "headline": "利率變化要拆成通膨因素與非通膨因素",
                    "center_asset": "美國10年期公債殖利率",
                    "left_box_title": "通膨驅動",
                    "right_box_title": "非通膨驅動",
                    "verdict_box": news_data.get("rate_verdict", ""),
                },
                "narration": {
                    "script": "",
                    "tts_file": "scene_04.mp3",
                },
                "output_files": {
                    "card_png": "cards/card_04.png",
                    "scene_video": "video/scene_04.mp4",
                },
            },
            {
                "scene_id": "scene_05",
                "scene_order": 5,
                "card_title": "美元、亞洲貨幣與黃金反應",
                "card_subtitle": "檢查利率與美元邏輯是否傳導",
                "duration_target_sec": 75,
                "visual_type": "asset_reaction_card",
                "data_sources": ["History_Data", "Market Snapshot"],
                "data_summary": {
                    "assets": asset_summaries,
                },
                "analysis_logic": {
                    "dollar_vs_rate_consistency": market_snapshot.get("dollar_vs_rate_consistency", "待判斷"),
                    "asia_fx_vs_dollar_consistency": market_snapshot.get("asia_fx_vs_dollar_consistency", "待判斷"),
                    "gold_logic": market_snapshot.get("gold_logic", "待判斷"),
                    "oil_to_inflation_feedback": market_snapshot.get("oil_to_inflation_feedback", ""),
                },
                "visual_content": {
                    "headline": "美元、亞洲貨幣與黃金是否跟著利率邏輯走？",
                    "chain": ["利率", "美元", "亞洲貨幣", "黃金"],
                    "highlight_box": market_snapshot.get("asset_reaction_highlight", ""),
                },
                "narration": {
                    "script": "",
                    "tts_file": "scene_05.mp3",
                },
                "output_files": {
                    "card_png": "cards/card_05.png",
                    "scene_video": "video/scene_05.mp4",
                },
            },
            {
                "scene_id": "scene_06",
                "scene_order": 6,
                "card_title": "本週總經傳導判斷",
                "card_subtitle": "最後判斷成立、部分成立或背離",
                "duration_target_sec": 80,
                "visual_type": "macro_chain_verdict_card",
                "data_sources": ["News_Narrative", "Visual Note", "Market Snapshot"],
                "data_summary": {
                    "macro_chain": news_data.get("macro_chain", []),
                },
                "analysis_logic": {
                    "transmission_verdict": transmission_verdict,
                    "key_supporting_points": news_data.get("key_supporting_points", []),
                    "divergence_points": news_data.get("divergence_points", []),
                    "main_conclusion": news_data.get("main_conclusion", ""),
                    "next_week_watchpoints": news_data.get("next_week_watchpoints", []),
                },
                "visual_content": {
                    "headline": f"本週總經傳導：{transmission_verdict}",
                    "verdict_label": transmission_verdict,
                    "watchpoints_title": "下週三個驗證點",
                    "watchpoints": news_data.get("next_week_watchpoints", []),
                },
                "narration": {
                    "script": "",
                    "tts_file": "scene_06.mp3",
                },
                "output_files": {
                    "card_png": "cards/card_06.png",
                    "scene_video": "video/scene_06.mp4",
                },
            },
        ],
    }


def main() -> None:
    history_data = load_json(INPUT_FILES["history"], default={})
    news_data = load_json(INPUT_FILES["news"], default={})
    visual_note = load_json(INPUT_FILES["visual_note"], default={})
    market_snapshot = load_json(INPUT_FILES["market_snapshot"], default={})
    weekly_video_source = load_json(INPUT_FILES["weekly_video_source"], default={})

    history_data = append_today_values_to_history(history_data, weekly_video_source)

    weekly_scene = build_weekly_scene(
        history_data=history_data,
        news_data=news_data,
        visual_note=visual_note,
        market_snapshot=market_snapshot,
    )

    week_end = weekly_scene["video_meta"]["week_end"]
    if week_end == "本週四":
        week_end = date.today().isoformat()

    output_path = OUTPUT_DIR / week_end / "weekly_video_scene.json"
    save_json(output_path, weekly_scene)

    print(f"[OK] Weekly video scene JSON created: {output_path}")


if __name__ == "__main__":
    main()
