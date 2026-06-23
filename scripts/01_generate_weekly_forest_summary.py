#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Explainer Brief - Step 01

Purpose:
- Generate weekly_forest_summary.json from:
  1) weekly_market_series.json
  2) weekly_news_context.md / weekly_news_context.json if available

Design:
- Use market data and news context as the primary inputs.
- Do not use weekly_source_text.md as the main analysis input.
- Produce a 6-8 minute World Economic Forum-style macro explainer brief.
- Emphasize transmission checks among market data, news events, expectations, and asset price moves.
- Add a V3.5 structured diagnosis for downstream weekly diagrams:
  dominant driver, correction factors, divergence signal, asset validation, and next-period watch.
- Keep the existing weekly_forest_summary.json schema for downstream compatibility.
- Although the product name may be "weekly", the analysis period is controlled by the formal analysis window and is not assumed to be exactly 7 days.

Input:
- output/weekly/YYYY-MM-DD/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_news_context.md optional
- output/weekly/YYYY-MM-DD/weekly_news_context.json optional

Output:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json

Required env:
- GEMINI_API_KEY

Optional env / CLI:
- ANALYSIS_START_DATE / --start = YYYY-MM-DD
- ANALYSIS_END_DATE   / --end   = YYYY-MM-DD
- WEEK_DIR / --week-dir = output/weekly/YYYY-MM-DD or YYYY-MM-DD
- GEMINI_ANALYSIS_MODEL, preferred for this analysis step
- GEMINI_MODEL, fallback if GEMINI_ANALYSIS_MODEL is not set
- default fallback: gemini-3.5-pro
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_ANALYSIS_MODEL = "gemini-3.5-pro"


SYSTEM_PROMPT = """
你是一位冷靜、專業、具權威感的總經學者，也是一位熟悉全球宏觀經濟、交叉資產策略與市場心理的總經解說者。

你的任務是根據正式 analysis window 內的市場數據、新聞事件、V35 rule-based 診斷結果與資產價格變化，製作一支約 6～8 分鐘的總經說明影片，並產生可供本週總經摘要網頁與後續影片流程共用的結構化分析結果。

請使用繁體中文。語氣要像機構級總經導讀：清楚、克制、有邏輯，不誇大，不硬湊因果，也不要使用過度生硬的金融術語。

請條理分明地說明：
1. 本期市場最關注什麼；
2. 哪些新聞、數據或資產走勢形成主導因子；
3. 哪些訊號只是修正因子；
4. 哪些地方出現背離或仍待觀察；
5. 哪些資產走勢支持或挑戰這條主線；
6. 接下來需要觀察什麼。

請把重點放在市場數據、新聞事件、V35 診斷層與資產價格變化之間如何互相印證、互相修正，或形成值得解釋的分歧。
"""


USER_PROMPT_TEMPLATE = """
以下資料包含正式 analysis window 與較長的 lookback/context window。

請根據來源資料產生 weekly_forest_summary.json。

重要區間原則：
- 本次正式分析區間是：{analysis_window_label}
- 本期主線、漲跌、傳導檢查、影片段落與視覺描述，必須以 analysis window 為準。
- market series 可能包含較長 lookback/context window，這是為了提供前期位置與延續性背景。
- analysis window 之前的資料只能作為前期背景，不可當成本期變動起點。
- 若提到前期資料，請明確寫成「前期背景」或「延續性脈絡」，不要把它寫成本期走勢。

任務目標：
請產生一份可供本週總經摘要網頁與後續影片流程共用的 weekly_forest_summary.json。
內容要條理分明地呈現市場數據、新聞事件、V35 診斷層與資產價格變化之間如何互相印證、互相修正，或形成值得解釋的分歧。

weekly_v35_diagnosis 使用規則：
- weekly_v35_diagnosis 是前一階段由 Python rule-based V35 診斷層產生的結構化結果。
- 請優先使用其中的 dominant_driver、correction_factors、divergence_signal、asset_validation、next_period_watch。
- weekly_v35_diagnosis 是診斷框架，不是最終文案；你可以改寫成自然主管摘要語氣，但不要推翻其資產方向、油價 / 通膨方向規則與背離判斷。
- 若 weekly_v35_diagnosis 與新聞文字看似衝突，請呈現為分歧、修正因子或待觀察，不要自行創造新的因果鏈。
- 若 weekly_v35_diagnosis 缺漏或空白，才回到 weekly_market_series 與 weekly_news_context 自行判斷，並在 insufficient_evidence 說明。

分析要求：
- 先說明本期主導因子。
- 再說明修正因子。
- 再說明最重要的背離訊號。
- 再用 US10Y、DXY、WTI / Brent、Gold、USDJPY、USDTWD、USDKRW 做資產驗證。
- 最後提出下期觀察重點。
- 若證據不足，請明確寫待觀察，不要硬湊因果。
- 請使用自然主管摘要語氣，避免「交易、定價、體制、風險溢價、傳導源」等生硬名詞。
- 請使用繁體中文。

請注意：
- video_segments 請依內容自行產生；每一項請包含 segment_id、segment_title、segment_question、narration_focus、main_point、estimated_duration、visual_needed、visual_role、visual_concept。
- visual_sequence 請依內容自行產生；每一項請包含 visual_id、source_segment_id、visual_title、visual_purpose、visual_concept、key_labels、is_web_hero_candidate。
- web_hero_visual 請指出最適合作為網頁主視覺或影片總結圖的視覺。
- six_scene_outline 與 image_card_brief 為舊流程相容欄位，可留空；程式會自動由新版欄位補齊。

請只輸出合法 JSON，不要加 Markdown，不要加解釋文字。

JSON 結構請維持如下；可以新增 weekly_v35_diagnosis，但不要移除既有欄位：

{
  "meta": {
    "source": "weekly_market_series.json + weekly_news_context.md/json + weekly_v35_diagnosis.json",
    "data_status_note": "",
    "week_range": "",
    "days_observed": ""
  },
  "forest_summary": {
    "weekly_main_theme": "",
    "main_question": "",
    "one_sentence_verdict": "",
    "overall_verdict": "成立 / 部分成立 / 分歧待觀察 / 待觀察",
    "narrative_arc": "",
    "why_it_matters": ""
  },
  "macro_storyline": {
    "story_start": "",
    "main_drivers": [],
    "market_transmission": "",
    "revision_or_noise": "",
    "story_end": ""
  },
  "macro_variables": {
    "inflation_view": "",
    "rate_view": "",
    "dollar_fx_view": "",
    "asia_fx_view": "",
    "gold_view": "",
    "energy_view": ""
  },
  "evidence": {
    "most_important_evidence": [],
    "insufficient_evidence": [],
    "watch_items_from_daily_summaries": [],
    "watch_items_from_news_context": []
  },
  "weekly_v35_diagnosis": {
    "dominant_driver": "",
    "correction_factors": [],
    "divergence_signal": "",
    "asset_validation": [],
    "next_period_watch": []
  },
  "video_planning": {
    "suggested_video_title": "",
    "target_duration": "6-8 minutes",
    "video_thesis": "",
    "opening_hook": "",
    "video_segments": [],
    "visual_sequence": [],
    "web_hero_visual": {
      "source_visual_id": "",
      "purpose": "",
      "reason": ""
    },
    "six_scene_outline": [],
    "image_card_brief": [],
    "next_week_questions": []
  }
}

weekly_market_series.json：
{weekly_market_series_json}

weekly_news_context.md：
{weekly_news_context_md}

weekly_news_context.json：
{weekly_news_context_json}
"""


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


def infer_analysis_window_from_source(
    week_dir: Path,
    start_override: str = "",
    end_override: str = "",
    weekly_market_series: Dict[str, Any] | None = None,
    weekly_news_context_json: Dict[str, Any] | None = None,
) -> Dict[str, str]:
    """
    Determine the formal weekly analysis window.

    Priority:
    1) CLI overrides / workflow env ANALYSIS_START_DATE / ANALYSIS_END_DATE.
    2) weekly_market_series.json meta.requested_analysis_window from Step 00 market fetch.
    3) weekly_news_context.json meta.analysis_window from Step 00 news context.
    4) weekly_source_text.md, because it is the formal source for this weekly issue.
    5) data/weekly_video_source.json requested_analysis_window / range.
    6) week_dir name as end date only.
    """
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

    source_json = load_json(ROOT_DIR / "data" / "weekly_video_source.json", {}) or {}
    if isinstance(source_json, dict):
        requested = source_json.get("requested_analysis_window", {})
        if isinstance(requested, dict):
            start = str(requested.get("start_date") or "").strip()
            end = str(requested.get("end_date") or "").strip()
            if start and end:
                return {
                    "start_date": start,
                    "end_date": end,
                    "label": f"{start} ～ {end}",
                    "source": "data/weekly_video_source.requested_analysis_window",
                }

        range_data = source_json.get("range", {})
        if isinstance(range_data, dict):
            start = str(range_data.get("start_date") or "")
            end = str(range_data.get("end_date") or week_dir.name)
            if start and end:
                return {
                    "start_date": start,
                    "end_date": end,
                    "label": f"{start} ～ {end}",
                    "source": "data/weekly_video_source.range",
                }

    return {
        "start_date": "",
        "end_date": week_dir.name,
        "label": week_dir.name,
        "source": "week_dir",
    }


def filter_points_by_window(points: Any, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    if not isinstance(points, list):
        return []

    filtered: List[Dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        date_text = str(point.get("date") or "")
        if start_date and date_text < start_date:
            continue
        if end_date and date_text > end_date:
            continue
        filtered.append(point)

    return filtered


def build_market_payload_for_analysis(
    weekly_market_series: Dict[str, Any],
    analysis_window: Dict[str, str],
) -> Dict[str, Any]:
    """
    Give Gemini both the formal analysis window and the longer lookback context.

    The original market series is preserved as lookback_series for background.
    analysis_series contains the same assets filtered to the formal weekly window.
    """
    series = weekly_market_series.get("series", [])
    start = analysis_window.get("start_date", "")
    end = analysis_window.get("end_date", "")

    analysis_series: List[Dict[str, Any]] = []
    lookback_series: List[Dict[str, Any]] = []

    if isinstance(series, list):
        for item in series:
            if not isinstance(item, dict):
                continue

            original_item = dict(item)
            original_points = item.get("points") or []
            filtered_points = filter_points_by_window(original_points, start, end)

            filtered_item = dict(item)
            filtered_item["points"] = filtered_points
            filtered_item["analysis_points_count"] = len(filtered_points)
            filtered_item["lookback_points_count"] = len(original_points) if isinstance(original_points, list) else 0

            analysis_series.append(filtered_item)
            lookback_series.append(original_item)

    original_meta = weekly_market_series.get("meta", {}) if isinstance(weekly_market_series.get("meta"), dict) else {}

    return {
        "meta": {
            "source": "weekly_market_series.json",
            "analysis_window": analysis_window,
            "lookback_window": original_meta.get("range", {}),
            "instruction": (
                "Use analysis_series for this week's main move and transmission checks. "
                "Use lookback_series only as background/context."
            ),
        },
        "analysis_series": analysis_series,
        "lookback_series": lookback_series,
    }


def validate_analysis_series_points(market_payload: Dict[str, Any]) -> None:
    analysis_series = market_payload.get("analysis_series", [])
    if not isinstance(analysis_series, list):
        return

    empty_assets = []
    for item in analysis_series:
        if not isinstance(item, dict):
            continue
        points = item.get("points")
        if isinstance(points, list) and len(points) == 0:
            label = item.get("label") or item.get("name") or item.get("symbol") or item.get("asset") or "unknown"
            empty_assets.append(str(label))

    if empty_assets and len(empty_assets) == len(analysis_series):
        print("[WARN] All market series have zero points inside the analysis window.")
        print("[WARN] Check whether Step 00 market series fetched the requested custom date range.")
    elif empty_assets:
        print(f"[WARN] Some market series have zero analysis-window points: {', '.join(empty_assets[:8])}")


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def extract_json_from_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    if start == -1:
        preview = cleaned[:1000]
        raise ValueError(f"Gemini response does not contain a JSON object. Preview: {preview}")

    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(cleaned[start:])
        if not isinstance(obj, dict):
            raise ValueError("Gemini JSON root is not an object.")
        return obj
    except json.JSONDecodeError as exc:
        preview = cleaned[:2000]
        raise ValueError(f"Unable to parse Gemini JSON. Error: {exc}. Preview: {preview}") from exc


def normalize_weekly_v35_diagnosis(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure the V3.5 diagnosis block exists for downstream weekly diagram prompts.
    This keeps older Gemini outputs compatible if the model omits the new field.
    """
    diag = summary.setdefault("weekly_v35_diagnosis", {})

    if not isinstance(diag, dict):
        diag = {}
        summary["weekly_v35_diagnosis"] = diag

    diag.setdefault("dominant_driver", "")
    diag.setdefault("correction_factors", [])
    diag.setdefault("divergence_signal", "")
    diag.setdefault("asset_validation", [])
    diag.setdefault("next_period_watch", [])

    if not isinstance(diag.get("correction_factors"), list):
        diag["correction_factors"] = as_list(diag.get("correction_factors"))

    if not isinstance(diag.get("asset_validation"), list):
        diag["asset_validation"] = as_list(diag.get("asset_validation"))

    if not isinstance(diag.get("next_period_watch"), list):
        diag["next_period_watch"] = as_list(diag.get("next_period_watch"))

    return summary


def normalize_video_planning(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill legacy fields from the flexible video fields so older workflows can continue to run.
    The legacy field names are kept only for compatibility and do not imply a fixed scene count.
    """
    summary = normalize_weekly_v35_diagnosis(summary)
    video = summary.setdefault("video_planning", {})

    segments = as_list(video.get("video_segments"))
    visuals = as_list(video.get("visual_sequence"))

    if not video.get("six_scene_outline") and segments:
        legacy_scenes = []
        for idx, segment in enumerate(segments, start=1):
            if not isinstance(segment, dict):
                continue
            legacy_scenes.append({
                "scene_id": f"scene_{idx:02d}",
                "scene_title": segment.get("segment_title", ""),
                "scene_question": segment.get("segment_question", ""),
                "main_point": segment.get("main_point") or segment.get("narration_focus", ""),
                "visual_hint": segment.get("visual_concept", ""),
            })
        video["six_scene_outline"] = legacy_scenes

    if not video.get("image_card_brief") and visuals:
        image_cards = []
        for idx, visual in enumerate(visuals, start=1):
            if not isinstance(visual, dict):
                continue
            image_cards.append({
                "card_id": f"card_{idx:02d}",
                "headline": visual.get("visual_title", ""),
                "short_labels": as_list(visual.get("key_labels")),
                "visual_concept": visual.get("visual_concept", ""),
            })
        video["image_card_brief"] = image_cards

    video.setdefault("target_duration", "6-8 minutes")

    return summary


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
            "temperature": 0.9,
            "topP": 0.9,
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
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini forest summary HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini forest summary URLError: {exc}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {api_response}") from exc

    return extract_json_from_text(text)


def build_user_prompt(
    weekly_market_series: Dict[str, Any],
    weekly_news_context_md: str,
    weekly_news_context_json: Dict[str, Any],
    analysis_window: Dict[str, str],
    weekly_v35_diagnosis: Dict[str, Any] | None = None,
) -> str:
    return USER_PROMPT_TEMPLATE.replace(
        "{analysis_window_label}",
        analysis_window.get("label", "資料週期待確認"),
    ).replace(
        "{weekly_v35_diagnosis_json}",
        json.dumps(weekly_v35_diagnosis or {}, ensure_ascii=False, indent=2),
    ).replace(
        "{weekly_market_series_json}",
        json.dumps(weekly_market_series, ensure_ascii=False, indent=2),
    ).replace(
        "{weekly_news_context_md}",
        weekly_news_context_md,
    ).replace(
        "{weekly_news_context_json}",
        json.dumps(weekly_news_context_json, ensure_ascii=False, indent=2),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default=os.getenv("WEEK_DIR", "").strip())
    parser.add_argument("--start", type=str, default=os.getenv("ANALYSIS_START_DATE", "").strip())
    parser.add_argument("--end", type=str, default=os.getenv("ANALYSIS_END_DATE", "").strip())
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = (
        os.getenv("GEMINI_ANALYSIS_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or DEFAULT_ANALYSIS_MODEL
    )

    week_dir = resolve_week_dir(args.week_dir)

    weekly_market_series = load_json(week_dir / "weekly_market_series.json", {})
    weekly_news_context_md = load_text(week_dir / "weekly_news_context.md")
    weekly_news_context_json = load_json(week_dir / "weekly_news_context.json", {})
    weekly_v35_diagnosis = load_json(week_dir / "weekly_v35_diagnosis.json", {}) or {}
    analysis_window = infer_analysis_window_from_source(
        week_dir,
        start_override=args.start,
        end_override=args.end,
        weekly_market_series=weekly_market_series,
        weekly_news_context_json=weekly_news_context_json,
    )

    if not weekly_market_series:
        raise FileNotFoundError(f"Missing or empty weekly_market_series.json in {week_dir}")

    market_payload = build_market_payload_for_analysis(
        weekly_market_series=weekly_market_series,
        analysis_window=analysis_window,
    )
    validate_analysis_series_points(market_payload)

    if not weekly_news_context_md and not weekly_news_context_json:
        weekly_news_context_md = (
            "本週新聞補充尚未產生。請僅根據 weekly_market_series.json 判斷市場變化，"
            "並在 insufficient_evidence 註明新聞事件層不足。"
        )

    user_prompt = build_user_prompt(
        weekly_market_series=market_payload,
        weekly_news_context_md=weekly_news_context_md,
        weekly_news_context_json=weekly_news_context_json,
        analysis_window=analysis_window,
        weekly_v35_diagnosis=weekly_v35_diagnosis,
    )

    print(f"[INFO] Generating weekly forest summary with analysis model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Analysis window: {analysis_window.get('label')} ({analysis_window.get('source')})")
    print(f"[INFO] Market series included: {bool(weekly_market_series)}")
    print(f"[INFO] News context md included: {bool((week_dir / 'weekly_news_context.md').exists())}")
    print(f"[INFO] News context json included: {bool((week_dir / 'weekly_news_context.json').exists())}")

    forest_summary = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    forest_summary = normalize_video_planning(forest_summary)

    if weekly_v35_diagnosis and not forest_summary.get("weekly_v35_diagnosis"):
        forest_summary["weekly_v35_diagnosis"] = weekly_v35_diagnosis.get("weekly_v35_diagnosis", {})

    forest_summary.setdefault("meta", {})
    forest_summary["meta"]["source"] = "weekly_market_series.json + weekly_news_context.json + weekly_v35_diagnosis"
    forest_summary["meta"]["week_range"] = analysis_window.get("label", "")
    forest_summary["meta"]["analysis_window"] = {
        "start_date": analysis_window.get("start_date", ""),
        "end_date": analysis_window.get("end_date", ""),
        "source": analysis_window.get("source", ""),
    }
    forest_summary["meta"]["lookback_window"] = market_payload.get("meta", {}).get("lookback_window", {})
    forest_summary["meta"]["weekly_v35_diagnosis_included"] = bool(weekly_v35_diagnosis)

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
