#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V2 - Step 01
Build weekly_facts.json from input data.

Purpose:
- Create a NotebookLM-like source package for AI.
- Keep only facts, calculated market paths, and structured event inputs.
- Do not generate final narration or video story here.

Input files:
- data/history_data.json
- data/news_narrative.json
- data/visual_note.json
- data/market_snapshot.json

Output:
- output/weekly/YYYY-MM-DD/weekly_facts.json
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
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def to_float(value: Any) -> Optional[float]:
    try:
        if value is None or value == "":
            return None
        return float(str(value).replace(",", "").replace("%", ""))
    except ValueError:
        return None


def classify_path(values: List[float]) -> str:
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

    if full_range == 0:
        return "窄幅盤整"

    total_change_pct = 0 if start == 0 else (end - start) / abs(start)
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
        return "先高後盤整" if end_near_high else "先高後低"
    if low_idx <= 2 and end > low:
        return "先低後盤整" if end_near_low else "先低後高"
    if abs(end - start) <= full_range * 0.3:
        return "高低震盪"
    return "震盪偏升" if end > start else "震盪偏弱"


def format_change(start: Optional[float], end: Optional[float], unit: str = "") -> str:
    if start is None or end is None:
        return ""
    change = end - start
    if unit == "bp":
        return f"{change * 100:.1f} bp"
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.2f}"


def build_path_comment(asset_name: str, path_type: str) -> str:
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


def build_asset_summary(asset_name: str, values: List[Optional[float]], unit: str = "") -> Dict[str, Any]:
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


def extract_market_paths(history_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    market_paths = []
    raw_assets = history_data.get("assets")
    if isinstance(raw_assets, list):
        for item in raw_assets:
            asset_name = item.get("asset_name") or item.get("name") or item.get("asset")
            values = [to_float(v) for v in item.get("values", [])]
            unit = item.get("unit", "")
            if asset_name:
                market_paths.append(build_asset_summary(asset_name, values, unit))
        return market_paths

    for asset_name in ASSET_ORDER:
        raw_values = history_data.get(asset_name)
        if isinstance(raw_values, list):
            values = [to_float(v) for v in raw_values]
            unit = "bp" if asset_name == "美國10年期公債殖利率" else ""
            market_paths.append(build_asset_summary(asset_name, values, unit))
    return market_paths


def extract_events(news_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw_events = news_data.get("events") or news_data.get("key_events") or []
    if not isinstance(raw_events, list):
        return []
    events = []
    for item in raw_events:
        events.append({
            "event_title": item.get("event_title") or item.get("title") or "",
            "event_category": item.get("event_category") or item.get("category") or "",
            "event_summary": item.get("event_summary") or item.get("summary") or "",
            "macro_relevance": item.get("macro_relevance") or "",
            "impact_direction": item.get("impact_direction") or "",
        })
    return events


def get_week_meta(market_snapshot: Dict[str, Any]) -> Dict[str, str]:
    week_start = market_snapshot.get("week_start", "")
    week_end = market_snapshot.get("week_end", "") or date.today().isoformat()
    if not week_start:
        week_start = "上週五"
    return {
        "week_start": week_start,
        "week_end": week_end,
        "week_label": f"{week_start} - {week_end}",
        "period_definition": "上週五收盤至本週四收盤",
    }


def build_weekly_facts(history_data, news_data, visual_note, market_snapshot) -> Dict[str, Any]:
    return {
        "week_meta": get_week_meta(market_snapshot),
        "source_notes": {
            "history_data": "data/history_data.json",
            "news_narrative": "data/news_narrative.json",
            "visual_note": "data/visual_note.json",
            "market_snapshot": "data/market_snapshot.json",
            "created_at": datetime.now().isoformat(timespec="seconds"),
        },
        "market_paths": extract_market_paths(history_data),
        "weekly_events": extract_events(news_data),
        "inflation_factors": {
            "upside_factors": news_data.get("inflation_up_factors", []),
            "downside_factors": news_data.get("inflation_down_factors", []),
            "mixed_factors": news_data.get("mixed_or_uncertain_factors", []),
            "initial_direction_from_source": news_data.get("inflation_expectation_direction", ""),
            "source_reasoning": news_data.get("inflation_reasoning", ""),
        },
        "rate_factors": {
            "inflation_driven": news_data.get("inflation_driven_rate_factors", []),
            "non_inflation_driven": news_data.get("non_inflation_rate_factors", []),
            "initial_main_driver_from_source": news_data.get("main_rate_driver", ""),
            "rate_vs_inflation_consistency_from_source": news_data.get("rate_vs_inflation_consistency", ""),
        },
        "asset_reaction_facts": {
            "rate_direction": market_snapshot.get("rate_direction", ""),
            "dollar_reaction": market_snapshot.get("dollar_direction", ""),
            "asia_fx_reaction": market_snapshot.get("asia_fx_direction", ""),
            "gold_reaction": market_snapshot.get("gold_direction", ""),
            "dollar_vs_rate_consistency_from_source": market_snapshot.get("dollar_vs_rate_consistency", ""),
            "asia_fx_vs_dollar_consistency_from_source": market_snapshot.get("asia_fx_vs_dollar_consistency", ""),
            "gold_logic_from_source": market_snapshot.get("gold_logic", ""),
            "oil_to_inflation_feedback": market_snapshot.get("oil_to_inflation_feedback", ""),
        },
        "existing_human_or_system_notes": {
            "main_theme": visual_note.get("main_theme") or news_data.get("main_theme") or market_snapshot.get("main_theme") or "",
            "main_market_path": market_snapshot.get("main_market_path", ""),
            "most_important_asset_move": market_snapshot.get("most_important_asset_move", ""),
            "event_highlight": visual_note.get("event_highlight", ""),
            "event_groups": visual_note.get("event_groups", []),
            "main_conclusion": news_data.get("main_conclusion", ""),
            "next_week_watchpoints": news_data.get("next_week_watchpoints", []),
            "transmission_verdict_from_source": news_data.get("transmission_verdict") or visual_note.get("transmission_verdict") or "",
            "macro_chain_from_source": news_data.get("macro_chain", []),
            "key_supporting_points_from_source": news_data.get("key_supporting_points", []),
            "divergence_points_from_source": news_data.get("divergence_points", []),
        },
        "required_video_logic": {
            "scene_order": [
                "Scene 01：本週主要資產走勢路徑",
                "Scene 02：本週經濟數據與事件",
                "Scene 03：通膨預期方向",
                "Scene 04：利率走勢與原因拆解",
                "Scene 05：美元、亞洲貨幣與黃金反應",
                "Scene 06：本週總經傳導判斷",
            ],
            "transition_style": "每段先提出問題，回答後在結尾拋出下一段問題。",
            "core_chain": "本週主要資產走勢 → 經濟數據與事件 → 通膨預期 → 利率 → 美元 → 亞洲貨幣 / 黃金 / 原油 → 總經傳導判斷",
        },
    }


def main() -> None:
    history_data = load_json(INPUT_FILES["history"], default={})
    news_data = load_json(INPUT_FILES["news"], default={})
    visual_note = load_json(INPUT_FILES["visual_note"], default={})
    market_snapshot = load_json(INPUT_FILES["market_snapshot"], default={})

    weekly_facts = build_weekly_facts(history_data, news_data, visual_note, market_snapshot)
    week_end = weekly_facts["week_meta"]["week_end"]
    if week_end == "本週四":
        week_end = date.today().isoformat()

    output_path = OUTPUT_DIR / week_end / "weekly_facts.json"
    save_json(output_path, weekly_facts)
    print(f"[OK] Weekly facts JSON created: {output_path}")


if __name__ == "__main__":
    main()
