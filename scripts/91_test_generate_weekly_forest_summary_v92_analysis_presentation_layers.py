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
- Produce a 6-8 minute macro explainer brief based on a separated analysis layer and presentation layer.
- The analysis layer diagnoses signals, expectations, transmission, divergence, and evidence.
- The presentation layer converts the diagnosis into viewer-facing pages for the website/video.
- Keep the existing weekly_forest_summary.json schema for downstream compatibility.

Input:
- output/weekly/YYYY-MM-DD/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_news_context.md optional
- output/weekly/YYYY-MM-DD/weekly_news_context.json optional

Output:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json

Required env:
- GEMINI_API_KEY

Optional env:
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
你是一位冷靜、專業、具權威感的總經學者。

請製作一支約 6～8 分鐘的世界經濟論壇式總經說明影片，條理分明地呈現市場數據、新聞事件與資產價格變化之間的關聯性。

請使用繁體中文。
"""


USER_PROMPT_TEMPLATE = """
以下是最近 7 天市場數據與新聞事件。

請根據來源資料產生 weekly_forest_summary.json。

這支影片的格式是：說明影片。
核心原則是「分析層」與「呈現層」分開：

一、分析層 transmission_diagnosis
請根據市場數據與新聞，先做內部分析判斷：
- 本週市場資訊是否足夠形成明確通膨預期。
- 利率預期走強主要是通膨推動、Fed 政策引導、長天期債券供需 / 期限溢價，或多因素共同推動。
- 利率預期是否傳導至美元。
- 美元是否傳導至台幣、日圓、韓圜與黃金。
- 若資料多空交錯，請判斷為 mixed / unclear，不要硬下單邊結論。
- 若不同市場反應不一致，請判斷為 partial_sync / divergent，並找出可能的局部基本面、資金流、政策或避險因素。

二、呈現層 presentation_pages
請把上述分析轉成觀眾容易理解的網頁 / 影片說明頁。
畫面呈現不要直接使用「同頻、背離、新聞驗證」作為硬性三欄標題；這些是內部分析方法。
對外呈現應以結果導向的問題與結論為主，例如：
- 通膨預期訊號明不明確？
- 利率預期為何仍偏強？
- 美元指數為何維持偏強？
- 亞洲貨幣與黃金為何出現分化？

三、新聞與經濟數據的角色
新聞與經濟數據必須存在於分析中，但在畫面呈現中只需要自然嵌入重點區塊。
請避免把同一則新聞在不同區塊重複呈現。
例如：
- 若美伊協議傳聞已放在通膨 / 油價訊號中，就不要再另開「新聞驗證」區重複一次。
- Fed 鷹派談話應放在利率訊號或政策引導中，不要和新聞驗證區重複。
- 結論要單獨清楚呈現，字數要少，讓觀眾一眼看懂。

四、建議的對外頁面順序
presentation_pages 請優先產生以下 4 頁；若當週資料不支持某頁，請調整標題與內容，但保持 viewer-facing，不要暴露內部分析術語：
1. inflation_expectation：市場資訊足不足夠形成通膨預期？
2. rate_expectation：利率預期是通膨推動，還是政策 / 長債重估推動？
3. dollar_index：美元指數為何偏強或偏弱？
4. asia_fx_gold：台幣、日圓、韓圜與黃金如何反應美元壓力？

五、總覽圖 overview_visual
overview_visual 是整週的總覽母頁，不是單一說明頁。
它應該統整：
- 主傳導圖解
- 本週重點摘要
- 總經傳導鏈
- 走勢驗證卡片
- 下週觀察重點

請注意：
- 若某個結論無法由來源資料直接支持，請呈現為資料不足、訊號混雜、分歧或待觀察。
- presentation_pages 是 90 產圖主要資料來源。
- video_segments 與 video_planning.visual_sequence 保留為舊流程相容欄位，可由 presentation_pages 自然轉寫。
- 請只輸出合法 JSON，不要加 Markdown，不要加解釋文字。

JSON 結構請維持並擴充如下：

{
  "meta": {
    "source": "weekly_market_series.json + weekly_news_context.md/json",
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
  "transmission_diagnosis": {
    "inflation_expectation": {
      "signal_strength": "strong / mixed / weak / unclear",
      "supporting_signals": [],
      "offsetting_signals": [],
      "judgment": ""
    },
    "rate_expectation": {
      "main_driver": "inflation / policy_guidance / term_premium / bond_supply_demand / mixed / unclear",
      "signals": [],
      "judgment": ""
    },
    "sync_checks": [
      {
        "check_id": "check_01",
        "pair": "通膨預期 vs 利率預期",
        "status": "sync / partial_sync / divergent / mixed / unclear",
        "market_signal": "",
        "interpretation": "",
        "evidence": [],
        "watch_point": ""
      }
    ],
    "macro_evidence": [
      {
        "evidence_id": "evidence_01",
        "type": "market_data / news / macro_data",
        "title": "",
        "supports": "",
        "related_checks": []
      }
    ],
    "watch_points": []
  },
  "overview_visual": {
    "visual_id": "overview_01",
    "page_type": "overview_dashboard",
    "visual_title": "本週總經傳遞總覽",
    "viewer_message": "",
    "main_diagram": {
      "diagram_title": "",
      "drivers": [],
      "main_flow": [],
      "divergence_points": []
    },
    "summary_block": {
      "headline": "",
      "body": ""
    },
    "transmission_chain_block": {
      "headline": "",
      "steps": []
    },
    "validation_cards": [
      {
        "asset": "",
        "direction": "",
        "role": ""
      }
    ],
    "watch_items": []
  },
  "presentation_pages": [
    {
      "page_id": "page_01",
      "page_type": "inflation_expectation",
      "page_title": "",
      "viewer_question": "",
      "viewer_message": "",
      "blocks": [
        {
          "block_title": "",
          "block_body": "",
          "evidence_hint": ""
        }
      ],
      "conclusion": "",
      "visual_brief": {
        "layout": "three_blocks / two_signals_plus_conclusion / dashboard_note",
        "style_note": "日報總經傳遞圖解風格，簡潔、少字、手繪感",
        "key_labels": []
      }
    }
  ],
  "evidence": {
    "most_important_evidence": [],
    "insufficient_evidence": [],
    "watch_items_from_daily_summaries": [],
    "watch_items_from_news_context": []
  },
  "video_planning": {
    "suggested_video_title": "",
    "target_duration": "6-8 minutes",
    "video_thesis": "",
    "opening_hook": "",
    "video_segments": [],
    "visual_sequence": [],
    "web_hero_visual": {
      "source_visual_id": "overview_01",
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


def normalize_video_planning(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill legacy fields from presentation_pages so older workflows can continue to run.
    The new contract is:
    - transmission_diagnosis: internal analysis layer
    - overview_visual / presentation_pages: viewer-facing presentation layer
    - video_planning.visual_sequence: compatibility layer for existing image workflows
    """
    video = summary.setdefault("video_planning", {})
    presentation_pages = as_list(summary.get("presentation_pages"))
    overview = summary.get("overview_visual") if isinstance(summary.get("overview_visual"), dict) else {}

    if overview:
        overview.setdefault("visual_id", "overview_01")
        overview.setdefault("page_type", "overview_dashboard")
        video.setdefault("web_hero_visual", {
            "source_visual_id": overview.get("visual_id", "overview_01"),
            "purpose": "作為網頁主視覺與影片總覽母頁",
            "reason": "總結本週總經傳導、修正因子與走勢驗證"
        })

    if not video.get("video_segments") and presentation_pages:
        segments = []
        for idx, page in enumerate(presentation_pages, start=1):
            if not isinstance(page, dict):
                continue
            segments.append({
                "segment_id": f"seg_{idx:02d}",
                "page_type": page.get("page_type", ""),
                "segment_title": page.get("page_title", ""),
                "segment_question": page.get("viewer_question", ""),
                "narration_focus": page.get("viewer_message", ""),
                "main_point": page.get("conclusion", ""),
                "estimated_duration": "60-90 seconds",
                "visual_needed": True,
                "visual_role": "說明頁",
                "visual_concept": (page.get("visual_brief") or {}).get("style_note", ""),
            })
        video["video_segments"] = segments

    if not video.get("visual_sequence") and presentation_pages:
        visuals = []
        for idx, page in enumerate(presentation_pages, start=1):
            if not isinstance(page, dict):
                continue
            brief = page.get("visual_brief") if isinstance(page.get("visual_brief"), dict) else {}
            visuals.append({
                "visual_id": f"vis_{idx:02d}",
                "page_type": page.get("page_type", ""),
                "source_segment_id": f"seg_{idx:02d}",
                "visual_title": page.get("page_title", ""),
                "visual_purpose": page.get("viewer_message", ""),
                "visual_concept": page.get("conclusion", ""),
                "key_labels": brief.get("key_labels", []),
                "is_web_hero_candidate": False,
            })
        video["visual_sequence"] = visuals

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
) -> str:
    return USER_PROMPT_TEMPLATE.replace(
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
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = (
        os.getenv("GEMINI_ANALYSIS_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or DEFAULT_ANALYSIS_MODEL
    )

    if args.week_dir:
        week_dir = Path(args.week_dir)
        if not week_dir.exists() and not week_dir.is_absolute():
            candidate = OUTPUT_WEEKLY_DIR / args.week_dir
            if candidate.exists():
                week_dir = candidate
    else:
        week_dir = find_latest_week_dir()

    weekly_market_series = load_json(week_dir / "weekly_market_series.json", {})
    weekly_news_context_md = load_text(week_dir / "weekly_news_context.md")
    weekly_news_context_json = load_json(week_dir / "weekly_news_context.json", {})

    if not weekly_market_series:
        raise FileNotFoundError(f"Missing or empty weekly_market_series.json in {week_dir}")

    if not weekly_news_context_md and not weekly_news_context_json:
        weekly_news_context_md = (
            "本週新聞補充尚未產生。請僅根據 weekly_market_series.json 判斷市場變化，"
            "並在 insufficient_evidence 註明新聞事件層不足。"
        )

    user_prompt = build_user_prompt(
        weekly_market_series=weekly_market_series,
        weekly_news_context_md=weekly_news_context_md,
        weekly_news_context_json=weekly_news_context_json,
    )

    print(f"[INFO] Generating weekly forest summary with analysis model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Market series included: {bool(weekly_market_series)}")
    print(f"[INFO] News context md included: {bool((week_dir / 'weekly_news_context.md').exists())}")
    print(f"[INFO] News context json included: {bool((week_dir / 'weekly_news_context.json').exists())}")

    forest_summary = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    forest_summary = normalize_video_planning(forest_summary)

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
