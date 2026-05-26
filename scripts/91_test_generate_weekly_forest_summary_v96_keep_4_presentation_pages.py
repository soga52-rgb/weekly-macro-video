#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Explainer Brief - Step 91

Purpose:
- Generate weekly_forest_summary.json from:
  1) weekly_market_series.json
  2) weekly_news_context.md / weekly_news_context.json if available
  3) macro_background_context.md / macro_background_context.json if available

Design:
- Use market data and news context as the primary inputs.
- Do not use weekly_source_text.md as the main analysis input.
- Produce a 6-8 minute macro explainer brief based on separated layers:
  1) analysis layer
  2) visual layer
  3) dialogue layer
- The analysis layer diagnoses signals, expectations, transmission, divergence, and evidence.
- The visual layer converts the diagnosis into viewer-facing website/video pages.
- The dialogue layer converts the diagnosis into scene-level Tom / Miranda talking material.
- Keep the existing weekly_forest_summary.json schema for downstream compatibility.

Input:
- output/weekly/YYYY-MM-DD/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_news_context.md optional
- output/weekly/YYYY-MM-DD/weekly_news_context.json optional
- output/weekly/YYYY-MM-DD/macro_background_context.md optional
- output/weekly/YYYY-MM-DD/macro_background_context.json optional

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
以下是最近 7 天市場數據與新聞事件，以及近 2～4 週仍具市場影響力的總經背景資料。

請產生 weekly_forest_summary.json。

核心原則：
1. 分析邏輯、靜態網頁呈現、動態影片畫面、旁白 / 對話邏輯必須分層。
2. 分析層可以完整、專業；靜態網頁可以保留較多資訊；影片畫面必須少字、單一主訊息；旁白 / 對話層負責說清楚因果、轉折與證據。
3. 網頁圖與影片圖共用同一套分析邏輯，但不應共用同一張圖。
4. 所有推論必須錨定來源資料；若只是市場押注、新聞解讀或模型推論，不可寫成官方已宣布或已發生事實。

一、共通研判漏斗 common_judgment_funnel
請對通膨、利率、美元、亞洲貨幣與黃金，使用同一套研判漏斗：
1. 新聞自然比重：觀察當週新聞與 2～4 週背景新聞中，哪些主題被高密度討論。此為市場關注度訊號，不是結論。
2. 方向一致性：判斷新聞方向是偏多、偏空、混合或不明。例如同一類新聞中是否多數指向升溫、降溫、風險上升或風險下降。
3. 市場價格驗證：檢查對應資產價格是否同步反映，例如 WTI / Brent、US10Y / 30Y、DXY、USDJPY、USDTWD、USDKRW、Gold。
4. 高權重事件修正：CPI、PPI、PCE、Fed 會議紀錄、主要政策變化、長債拍賣、重大地緣事件等，可以覆蓋一般新聞篇數的判斷。
5. 結論分類：若兩類以上資訊同向且價格驗證成立，可判斷方向較明確；若多空力道交錯或高權重事件互相抵銷，應判斷 mixed / unclear / 待確認。

二、各變數分析框架
1. 通膨預期：
   - 參考物價硬數據：CPI、PPI、PCE、核心 PCE、PMI / ISM 價格分項。
   - 參考能源與供給：WTI、Brent、天然氣、BDI、OPEC、EIA、戰略儲備、荷姆茲海峽、戰爭與地緣供應風險。
   - 參考需求與景氣：零售銷售、PMI / ISM、GDP、消費信心。
   - 參考勞動市場：非農、ADP、初領失業金、失業率、薪資、裁員報導。
   - 參考市場與政策預期：Fed 談話、會議紀錄、升降息機率、美債殖利率、通膨連動債。
   - 不得只因油價單週下跌就判斷通膨預期降溫；也不得只因 CPI / PPI 偏強就忽略能源端修正。

2. 利率預期：
   - 區分基本面通膨、Fed 政策引導、長債供需、期限溢價、財政赤字、全球長債同步拋售、避險需求。
   - 若長端利率上升但油價或通膨預期未同步上升，應檢查是否為 term_premium / bond_supply_demand / policy_guidance。

3. 美元指數：
   - 區分利差支撐、避險需求、美元流動性、非美貨幣弱勢、貿易與政策風險。
   - 若利率偏強但美元未突破，應檢查成長擔憂或風險偏好是否限制美元上行。

4. 亞洲貨幣：
   - 日圓、台幣、韓圜必須分開判斷，不可只寫「亞幣」。
   - 檢查利差、央行干預、出口 / 股市資金流、外資流動、地緣與美元壓力。
   - 若 asset 是 USD/JPY，direction 應描述匯率走高或走低；若要描述日圓承壓，asset 應寫「日圓」。

5. 黃金：
   - 檢查實質利率、美元、避險需求、地緣政治、央行買金、中印需求。
   - 若高利率壓抑與避險需求同時存在，應判斷為拉鋸 / mixed，不可硬下單邊結論。

三、官方訊號、媒體解讀、市場定價、模型推論要分清楚
- Fed 已正式宣布、Fed 會議紀錄、媒體報導、市場押注、模型推論，必須明確區分。
- 若資料只顯示「市場押注未來 Fed 轉鷹」，不可改寫成「Fed 已正式重啟升息」。
- 若沒有 MMF、T-Bill 或資金流數據，不可把「現金為王」寫成已發生事實；可寫成「防禦性配置可能上升 / 待觀察」。

四、輸出分層要求
1. transmission_diagnosis：分析層，完整保留因果、證據、多空力道與判斷。
2. web_visual_pages：靜態網頁圖卡，可承載較多資訊，作為研究摘要式呈現。
3. video_visual_scenes：影片畫面用，少字、單一重點、適合 92 產圖。
4. narration_outline：旁白邏輯，用來講清楚畫面背後的因果，不要把旁白全部塞進圖。
4-1. scene_dialogue_context：對話層，供 94 Tom / Miranda 雙人講稿使用。
   - 這一層不是重新分析，也不是畫圖素材，而是把分析層轉成「可被主持人與分析師說出口」的素材。
   - 每一個 scene 必須對齊 video_visual_scenes 的 scene_id、scene_type、screen_title 與 single_message。
   - 每一幕必須補足：
     a. 過去 2～4 週市場原本怎麼想 / 原本在交易什麼。
     b. 本週哪一條新聞、政策訊號或數據事件造成轉折。
     c. 哪個市場數據驗證或抵銷這個轉折。
     d. Miranda 應該如何用因果鏈解釋這張圖。
     e. Tom 應該從哪個觀眾疑問切入，但不能提前說破答案。
     f. 這一幕結尾如何自然銜接下一幕。
   - scene_dialogue_context 必須比 video_visual_scenes 更有敘事血肉，但比 web_visual_pages 更適合口語。
   - 不可把下一幕的完整分析提前寫進本幕，只能保留伏筆。
5. overview_visual / presentation_pages / video_planning：保留舊流程相容欄位，但內容應由 web_visual_pages / video_visual_scenes 自然轉寫。
6. presentation_pages 必須完整保留 4 張說明頁，供現有 92 流程讀取，不可只輸出 1 張：
   - page_01：inflation_expectation，先回答「通膨預期訊號是否明確」。
   - page_02：rate_expectation，再回答「利率預期為何偏強」。
   - page_03：dollar_index，說明美元指數與利差 / 避險 / 成長疑慮。
   - page_04：asia_fx_gold，說明日圓、台幣、韓圜與黃金的分化。
7. video_visual_scenes 可較精簡，但 presentation_pages 必須維持上述 4 頁，以確保 92 舊流程相容。

五、scene_dialogue_context 生成規則
1. scene_dialogue_context 是給 94 生成 Tom / Miranda 對談稿使用，不是給 92 畫圖使用。
2. 每一幕必須以 video_visual_scenes 的畫面主題為邊界，不得為了敘事順暢而超出該幕畫面。
3. 每一幕要補足跨期敘事：
   - prior_market_impression：過去 2～4 週市場原本怎麼想。
   - this_week_catalyst：本週哪個新聞 / 政策 / 數據事件改變判斷。
   - data_validation：本週價格或數據如何驗證或抵銷。
   - causal_interpretation：最終因果解釋。
4. Tom 的提示語必須是「觀眾會問的問題」，不得提前講出 Miranda 的答案。
5. Miranda 的 talk track 必須以新聞或政策訊號解釋數據，不得只用數據解釋數據。
6. 如果資料不足，請在 offset_or_risk 或 avoid_saying 裡標明，不可自行編造。
7. scene_dialogue_context 必須可以和 94 的圖片輸入版搭配；94 會看圖，但新聞與因果素材以此欄位為準。

六、請只輸出合法 JSON，不要加 Markdown，不要加解釋文字。

JSON 結構請維持並擴充如下：

{
  "meta": {
    "source": "weekly_market_series.json + weekly_news_context.md/json + macro_background_context.md/json",
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
  "common_judgment_funnel": {
    "attention_signal": {
      "dominant_topics": [],
      "natural_news_weight_note": ""
    },
    "direction_consistency": {
      "inflation": "bullish / bearish / mixed / unclear",
      "rates": "bullish / bearish / mixed / unclear",
      "dollar": "bullish / bearish / mixed / unclear",
      "asia_fx": "pressure / resilient / mixed / unclear",
      "gold": "supportive / restrictive / mixed / unclear"
    },
    "price_validation": [],
    "high_weight_event_adjustments": [],
    "final_rule_note": ""
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
        "pair": "",
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
        "type": "market_data / news / macro_data / inference",
        "title": "",
        "supports": "",
        "related_checks": []
      }
    ],
    "watch_points": []
  },
  "web_visual_pages": [
    {
      "page_id": "web_01",
      "page_type": "overview / inflation_expectation / rate_expectation / dollar_index / asia_fx_gold / next_week_roadmap",
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
      "visual_density": "medium / high"
    }
  ],
  "video_visual_scenes": [
    {
      "scene_id": "scene_01",
      "scene_type": "overview / inflation_expectation / rate_expectation / dollar_index / asia_fx_gold / next_week_roadmap",
      "screen_title": "",
      "single_message": "",
      "on_screen_labels": [],
      "must_show_numbers": [],
      "visual_metaphor": "",
      "voiceover_link": "narration_01"
    }
  ],
  "narration_outline": [
    {
      "narration_id": "narration_01",
      "scene_id": "scene_01",
      "voiceover_goal": "",
      "key_points": [],
      "evidence_to_mention": [],
      "avoid_saying": []
    }
  ],
  "scene_dialogue_context": [
    {
      "scene_id": "scene_01",
      "scene_type": "overview / inflation_expectation / rate_expectation / dollar_index / asia_fx_gold / next_week_roadmap",
      "screen_title": "",
      "dialogue_topic": "",
      "visual_anchor": {
        "what_the_image_shows": "",
        "must_align_with": [],
        "do_not_expand": []
      },
      "prior_market_impression": "",
      "this_week_catalyst": "",
      "data_validation": "",
      "causal_interpretation": "",
      "offset_or_risk": "",
      "foreshadow_next": "",
      "tom_question_angle": "",
      "miranda_talk_track": "",
      "key_news_lines": [],
      "key_numbers": [],
      "avoid_saying": [],
      "image_alignment_note": ""
    }
  ],
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
    "validation_cards": [],
    "watch_items": []
  },
  "presentation_pages": [
    {
      "page_id": "page_01",
      "page_type": "inflation_expectation",
      "page_title": "通膨預期訊號明不明確？",
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
        "layout": "two_signals_plus_conclusion",
        "style_note": "日報總經傳遞圖解風格，簡潔、少字、手繪感",
        "key_labels": []
      }
    },
    {
      "page_id": "page_02",
      "page_type": "rate_expectation",
      "page_title": "利率預期為何偏強？",
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
        "layout": "two_signals_plus_conclusion",
        "style_note": "日報總經傳遞圖解風格，簡潔、少字、手繪感",
        "key_labels": []
      }
    },
    {
      "page_id": "page_03",
      "page_type": "dollar_index",
      "page_title": "美元指數為何維持偏強？",
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
        "layout": "two_signals_plus_conclusion",
        "style_note": "日報總經傳遞圖解風格，簡潔、少字、手繪感",
        "key_labels": []
      }
    },
    {
      "page_id": "page_04",
      "page_type": "asia_fx_gold",
      "page_title": "亞洲貨幣與黃金為何分化？",
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
        "layout": "two_signals_plus_conclusion",
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

macro_background_context.md：
{macro_background_context_md}

macro_background_context.json：
{macro_background_context_json}
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


def normalize_scene_dialogue_context(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure weekly_forest_summary.json has a dialogue layer for Step 94.

    scene_dialogue_context is the bridge between:
    - analysis layer: transmission_diagnosis / common_judgment_funnel / macro_storyline
    - visual layer: video_visual_scenes
    - dialogue layer: Tom / Miranda script generation

    It should not create new analysis. It only backfills safe placeholders if Gemini omits the field.
    """
    scenes = as_list(summary.get("video_visual_scenes"))
    existing = summary.get("scene_dialogue_context")

    if isinstance(existing, list) and existing:
        return summary

    narration_items = as_list(summary.get("narration_outline"))
    narration_by_scene = {
        str(item.get("scene_id", "")): item
        for item in narration_items
        if isinstance(item, dict)
    }

    scene_dialogue_context = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue

        scene_id = str(scene.get("scene_id", ""))
        narration = narration_by_scene.get(scene_id, {})

        scene_dialogue_context.append({
            "scene_id": scene_id,
            "scene_type": scene.get("scene_type", ""),
            "screen_title": scene.get("screen_title", ""),
            "dialogue_topic": scene.get("single_message", "") or scene.get("screen_title", ""),
            "visual_anchor": {
                "what_the_image_shows": scene.get("visual_metaphor", ""),
                "must_align_with": as_list(scene.get("on_screen_labels")) + as_list(scene.get("must_show_numbers")),
                "do_not_expand": []
            },
            "prior_market_impression": "",
            "this_week_catalyst": "",
            "data_validation": "",
            "causal_interpretation": narration.get("voiceover_goal", ""),
            "offset_or_risk": "",
            "foreshadow_next": "",
            "tom_question_angle": "",
            "miranda_talk_track": "請根據本幕畫面、narration_outline 與 evidence，用新聞事件解釋市場數據。",
            "key_news_lines": as_list(narration.get("evidence_to_mention")),
            "key_numbers": as_list(scene.get("must_show_numbers")),
            "avoid_saying": as_list(narration.get("avoid_saying")),
            "image_alignment_note": "94 會搭配 scene 圖片讀取；若圖片文字與此 metadata 不一致，以 metadata 為準。"
        })

    summary["scene_dialogue_context"] = scene_dialogue_context
    return summary


def normalize_video_planning(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Fill legacy fields from presentation_pages so older workflows can continue to run.
    The new contract is:
    - transmission_diagnosis: internal analysis layer
    - overview_visual / presentation_pages / video_visual_scenes: visual layer
    - scene_dialogue_context / narration_outline: dialogue layer
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
    macro_background_context_md: str,
    macro_background_context_json: Dict[str, Any],
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
    ).replace(
        "{macro_background_context_md}",
        macro_background_context_md,
    ).replace(
        "{macro_background_context_json}",
        json.dumps(macro_background_context_json, ensure_ascii=False, indent=2),
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
    macro_background_context_md = load_text(week_dir / "macro_background_context.md")
    macro_background_context_json = load_json(week_dir / "macro_background_context.json", {})

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
        macro_background_context_md=macro_background_context_md,
        macro_background_context_json=macro_background_context_json,
    )

    print(f"[INFO] Generating weekly forest summary with analysis model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Market series included: {bool(weekly_market_series)}")
    print(f"[INFO] News context md included: {bool((week_dir / 'weekly_news_context.md').exists())}")
    print(f"[INFO] News context json included: {bool((week_dir / 'weekly_news_context.json').exists())}")
    print(f"[INFO] Macro background context md included: {bool((week_dir / 'macro_background_context.md').exists())}")
    print(f"[INFO] Macro background context json included: {bool((week_dir / 'macro_background_context.json').exists())}")

    forest_summary = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    forest_summary = normalize_scene_dialogue_context(forest_summary)
    forest_summary = normalize_video_planning(forest_summary)

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
