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
你是一位精通全球宏觀經濟、交叉資產策略與市場心理學的資深總經分析師，同時也是影音內容結構設計師。

你擅長從看似矛盾的經濟數據、政策訊號、地緣政治與資產走勢中，辨識市場隱含的核心敘事，並用清楚的因果邏輯，將債券、匯率、大宗商品、黃金與亞洲貨幣串聯起來。

你的任務是建立後續流程可接續使用的上游素材：包含市場主線、交叉資產傳導、視覺 scene 概念，以及每幕 Tom / Miranda 對話素材。

整體影片風格是「簡潔圖解式總經導讀」。視覺 scene 概念會交給後續產圖流程使用，畫面應讓觀眾一看就清楚本幕核心概念；每幕對話素材會交給後續正式對話稿生成流程使用，語音內容應深入解析畫面背後的總經傳導過程。

請讓視覺素材與對話素材共享同一條市場主線：畫面負責清楚呈現核心關係，語音負責說明新聞、政策、數據與資產價格之間的因果傳導。

weekly_forest_summary.json 必須同時產生三個彼此對齊的內容層：

1. 分析層：
   負責判斷市場主線、因果傳導、數據驗證與風險分歧。

2. 視覺呈現層：
   負責把分析結果轉成適合影片畫面的 scene。每一個 scene 應少字、單一主題、圖形簡單清楚，讓觀眾一眼理解本幕核心概念。

3. 語音對話素材層：
   負責把每一個 scene 背後的因果、新聞、數據、轉折與伏筆，整理成 Tom / Miranda 可展開的深度對話素材。

最高原則是「畫面少字，語音深講」：

- video_visual_scenes 是給產圖流程使用的主要視覺素材，重點是呈現市場變數之間的關係。
- scene_dialogue_context 是給正式對話稿生成流程使用的主要語音素材，必須比畫面深入，能支撐每個主題約 60～90 秒的講解。
- scene_dialogue_context 應提供對話素材與分析路徑，讓正式對話稿能自然展開總經傳導過程。

影片分鏡控制規則：

- scene_control_list 是本週影片分鏡主控清單。
- video_visual_scenes、narration_outline、scene_dialogue_context 必須完全依照 scene_control_list 的數量、順序、scene_id、scene_type、screen_title 輸出。
- 影片 scene 數量由本週內容自然決定，通常可為 5～7 幕；所有影片相關層必須一致。
- 每一幕都應形成一致的敘事鏈：畫面核心概念 → Tom 的觀眾疑問 → Miranda 的因果解析 → 本幕小結或下一幕伏筆。

請製作一支約 6～8 分鐘的總經說明影片素材，條理分明地呈現市場數據、新聞事件與資產價格變化之間的關聯性。

請使用繁體中文。
"""


USER_PROMPT_TEMPLATE = """
以下是最近 7 天市場數據與新聞事件，以及近 2～4 週仍具市場影響力的總經背景資料。

請產生 weekly_forest_summary.json。

核心原則：
1. 本任務最終用途是生成影片；分析邏輯、靜態網頁呈現、動態影片畫面、旁白 / 對話邏輯必須分層且彼此對齊。
2. 最高原則是「畫面少字，語音深講」：video_visual_scenes 要少字、單一主題、圖形清楚；scene_dialogue_context 要深入、完整、能支撐 Tom / Miranda 6～8 分鐘對談。
3. 三層內容應維持同一種「簡潔圖解式總經導讀」風格：分析層負責判斷，視覺層負責圖解，語音對話層負責把因果講清楚。
4. 提示語應以正面表述為主，優先描述目標風格、目標結構與目標輸出品質。需要控管語氣時，請說明希望採用的專業分析語言與清楚敘事方式。
5. 分析層可以完整、專業；靜態網頁可以保留較多資訊；影片畫面只呈現單一主訊息；語音對話層負責說清楚因果、轉折、反向證據、總經邏輯與伏筆。
6. 網頁圖與影片圖共用同一套分析邏輯，但依照不同用途設計不同畫面。
7. 所有推論必須錨定來源資料；市場押注、新聞解讀或模型推論，應清楚呈現為市場定價或分析判斷。
8. macro_background_context 是近 2～4 週背景資料層，用來補充本週新聞以外仍可能影響市場定價的背景脈絡；最終主線判斷由本步驟整合市場數據、本週新聞與背景資料後形成。
9. scene_control_list 是影片分鏡主控清單；video_visual_scenes、narration_outline、scene_dialogue_context 必須與 scene_control_list 一一對齊，數量、順序、scene_id、scene_type、screen_title 必須一致.

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
1. transmission_diagnosis：
   分析層，完整保留因果、證據、多空力道與判斷。

2. web_visual_pages：
   靜態網頁圖卡，可承載較多資訊，作為研究摘要式呈現。

3. scene_control_list：
   影片分鏡主控清單，依本週市場主線自然安排影片需要幾幕，通常為 5～7 幕。scene_control_list 負責決定影片實際敘事順序。

4. video_visual_scenes：
   視覺層，影片畫面用，必須完全依照 scene_control_list 輸出。
   - 這一層是後續產圖流程的主要輸入。
   - 這一層的風格是「簡潔圖解式總經導讀」。
   - 每一幕應像一張清楚的分析圖卡，使用簡單圖形、箭頭、框線、因果路徑、分岔結構、上下方向、強弱對比、少量關鍵標籤與必要數字，呈現市場變數之間的傳導、分歧、抵銷或觀察重點。
   - 每一幕聚焦一個清楚的市場概念，讓觀眾能快速理解本週市場邏輯如何形成、哪些變數正在互相影響、哪裡出現分歧，以及下一步需要觀察什麼。
   - visual_metaphor 應描述圖解構圖方向與邏輯關係，讓產圖流程能產出簡單、清楚、分析型的畫面。

5. narration_outline：
   旁白重點層，用來整理本幕要講清楚的因果、新聞線索與數據驗證，必須完全依照 scene_control_list 輸出。

5-1. scene_dialogue_context：
   深度語音對話素材層，供 Tom / Miranda 正式對話稿使用；必須完全依照 scene_control_list 輸出。
   - 這一層把分析層轉成「可被主持人與分析師自然展開」的對話素材。
   - 這一層應提供每幕的觀眾疑問、策略師解釋路徑、新聞與數據依據、因果拆解、抵銷因素與下一幕銜接方向。
   - tom_question_angle 應描述 Tom 的切入角度與觀眾疑問，協助正式對話稿形成自然提問。
   - miranda_talk_track 應描述 Miranda 的解釋路徑與分析重點，協助正式對話稿形成完整回答。
   - 每一幕應足以支撐約 60～90 秒對談；全片素材需足以支撐 6～8 分鐘。
   - 每一幕必須補足：
     a. 過去 2～4 週市場原本怎麼想 / 原本在交易什麼。
     b. 本週哪一條新聞、政策訊號或數據事件造成轉折。
     c. 哪個市場數據驗證或抵銷這個轉折。
     d. Miranda 應該如何用因果鏈解釋這張圖。
     e. 多空力量如何互相抵銷或形成分歧。
     f. Tom 應該從哪個觀眾疑問切入。
     g. 這一幕結尾如何自然銜接下一幕。
   - 通膨、利率、美元指數、亞洲貨幣與黃金等主題，都必須在對應 scene 補足深入總經分析邏輯。
   - scene_dialogue_context 必須比 video_visual_scenes 更深入，也必須比 narration_outline 更完整。
   - 下一幕相關內容應以伏筆或銜接方向呈現，讓正式對話稿可以自然延伸。

6. overview_visual / presentation_pages / video_planning：
   保留為補充型網頁、研究摘要或相容輸出欄位；影片主流程以 scene_control_list、video_visual_scenes、narration_outline、scene_dialogue_context 為主。
   - presentation_pages 可承載較完整的研究摘要。
   - presentation_pages 不負責控制影片分鏡。
   - presentation_pages 不負責控制產圖順序。
   - video_planning 可提供標題、主旨、下週觀察問題等補充資訊.

五、scene_control_list 與 scene_dialogue_context 生成規則
1. scene_control_list 是本週影片分鏡主控清單，依本週市場主線自然安排 5～7 幕，使影片敘事順序能完整呈現主要驅動、修正因子、資產反應與下週觀察重點。
2. video_visual_scenes、narration_outline、scene_dialogue_context 必須完全依照 scene_control_list 的數量、順序、scene_id、scene_type、screen_title 輸出。
3. scene_control_list 決定影片實際分鏡；video_visual_scenes 是產圖流程主要輸入；narration_outline 是旁白重點素材；scene_dialogue_context 是正式 Tom / Miranda 對話稿使用的素材層。
4. 每一幕必須以 video_visual_scenes 的畫面主題為邊界，讓觀眾能從該幕畫面理解本幕要處理的市場概念。
5. 最高原則是「畫面少字，語音深講」：video_visual_scenes 只呈現單一主題；scene_dialogue_context 必須提供足夠深度，支撐每幕約 60～90 秒對談。
6. 每一幕要補足跨期敘事：
   - prior_market_impression：過去 2～4 週市場原本怎麼想。
   - this_week_catalyst：本週哪個新聞 / 政策 / 數據事件改變判斷。
   - data_validation：本週價格或數據如何驗證或抵銷。
   - causal_interpretation：最終因果解釋。
   - offset_or_risk：多空力量如何抵銷、分歧或尚待確認。
   - foreshadow_next：除最後一幕外，必須銜接 scene_control_list 中下一個 scene 的主題。
7. 每一幕的 Tom 對話素材應從該幕視覺 scene 帶出的核心概念出發。這個核心概念可以是導讀重點、反常現象、主要矛盾、因果轉折或下一步觀察問題。
8. tom_question_angle 應描述觀眾會如何從畫面理解本幕問題，並自然引出 Miranda 後續的總經傳導解析。它是 Tom 的切入角度與提問方向。
9. Miranda 的 talk track 應提供清楚的解釋路徑：前因慣性 → 本週催化事件 → 數據驗證 / 抵銷 → 總經定價機制 → 下一幕伏筆。Miranda 應以新聞、政策訊號與市場數據解釋因果，而不是只列數字。
10. 每一幕的上下邏輯必須能對應得上：
    - scene_control_list 決定本幕在全片中的位置與任務。
    - video_visual_scenes 負責把本幕核心概念轉成清楚的圖形畫面。
    - narration_outline 負責整理本幕要講的重點。
    - scene_dialogue_context 負責提供 Tom / Miranda 可展開的對話素材。
    - foreshadow_next 必須銜接下一個 scene 的主題，讓觀眾能自然理解為什麼下一幕會接到那個變數或市場反應。
11. 每一幕都應形成一致的敘事鏈：畫面核心概念 → Tom 的觀眾疑問 → Miranda 的因果解析 → 本幕小結或下一幕伏筆。
12. 如果資料不足，請在 offset_or_risk 或 avoid_saying 裡標明。
13. scene_dialogue_context 必須可以和正式對話稿生成流程的圖片輸入搭配；新聞與因果素材以此欄位為主要依據.

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
  "scene_control_list": [
    {
      "scene_id": "scene_01",
      "scene_type": "overview / inflation_expectation / rate_expectation / dollar_index / asia_fx_gold / next_week_roadmap / other",
      "screen_title": "",
      "single_message": "",
      "role_in_video": "opening / explanation / transition / conclusion",
      "next_scene_id": ""
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
      "miranda_deep_dive_points": [],
      "expected_dialogue_seconds": "60-90",
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




def normalize_scene_control_list(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure there is a deterministic scene_control_list.

    Preferred source:
    - Gemini output scene_control_list

    Fallback source:
    - video_visual_scenes

    This function does not decide market logic. It only creates a control list so that
    visual, narration, and dialogue layers can be aligned deterministically.
    """
    existing = summary.get("scene_control_list")
    if isinstance(existing, list) and existing:
        normalized = []
        for idx, item in enumerate(existing, start=1):
            if not isinstance(item, dict):
                continue
            scene_id = str(item.get("scene_id") or f"scene_{idx:02d}")
            normalized.append({
                "scene_id": scene_id,
                "scene_type": item.get("scene_type", ""),
                "screen_title": item.get("screen_title", ""),
                "single_message": item.get("single_message", ""),
                "role_in_video": item.get("role_in_video", ""),
                "next_scene_id": item.get("next_scene_id", ""),
            })
        if normalized:
            for idx, item in enumerate(normalized):
                if idx < len(normalized) - 1:
                    item["next_scene_id"] = item.get("next_scene_id") or normalized[idx + 1]["scene_id"]
                else:
                    item["next_scene_id"] = ""
            summary["scene_control_list"] = normalized
            return summary

    scenes = as_list(summary.get("video_visual_scenes"))
    control = []
    for idx, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id") or f"scene_{idx:02d}")
        control.append({
            "scene_id": scene_id,
            "scene_type": scene.get("scene_type", ""),
            "screen_title": scene.get("screen_title", ""),
            "single_message": scene.get("single_message", ""),
            "role_in_video": "opening" if idx == 1 else ("conclusion" if idx == len(scenes) else "explanation"),
            "next_scene_id": "",
        })

    for idx, item in enumerate(control):
        if idx < len(control) - 1:
            item["next_scene_id"] = control[idx + 1]["scene_id"]

    summary["scene_control_list"] = control
    if not control:
        meta = summary.setdefault("meta", {})
        warnings = as_list(meta.get("quality_warnings"))
        warnings.append("scene_control_list and video_visual_scenes are both missing or empty.")
        meta["quality_warnings"] = warnings
    return summary


def align_scene_layers(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Align video_visual_scenes, narration_outline, and scene_dialogue_context
    to scene_control_list.

    The control list is the deterministic gear. If Gemini omits a scene in the
    narration or dialogue layer, this function creates a safe placeholder so
    downstream steps do not silently misalign.
    """
    control = as_list(summary.get("scene_control_list"))
    if not control:
        return summary

    meta = summary.setdefault("meta", {})
    warnings = as_list(meta.get("quality_warnings"))

    visual_by_id = {
        str(item.get("scene_id", "")): item
        for item in as_list(summary.get("video_visual_scenes"))
        if isinstance(item, dict)
    }
    narration_by_scene = {
        str(item.get("scene_id", "")): item
        for item in as_list(summary.get("narration_outline"))
        if isinstance(item, dict)
    }
    dialogue_by_scene = {
        str(item.get("scene_id", "")): item
        for item in as_list(summary.get("scene_dialogue_context"))
        if isinstance(item, dict)
    }

    aligned_visuals = []
    aligned_narration = []
    aligned_dialogue = []

    for idx, ctrl in enumerate(control, start=1):
        if not isinstance(ctrl, dict):
            continue

        scene_id = str(ctrl.get("scene_id") or f"scene_{idx:02d}")
        scene_type = ctrl.get("scene_type", "")
        screen_title = ctrl.get("screen_title", "")
        single_message = ctrl.get("single_message", "")

        visual = dict(visual_by_id.get(scene_id, {}))
        if not visual:
            warnings.append(f"video_visual_scenes missing {scene_id}; backfilled from scene_control_list.")
        visual["scene_id"] = scene_id
        visual["scene_type"] = visual.get("scene_type") or scene_type
        visual["screen_title"] = visual.get("screen_title") or screen_title
        visual["single_message"] = visual.get("single_message") or single_message
        visual.setdefault("on_screen_labels", [])
        visual.setdefault("must_show_numbers", [])
        visual.setdefault("visual_metaphor", "")
        visual.setdefault("voiceover_link", f"narration_{idx:02d}")
        aligned_visuals.append(visual)

        narration = dict(narration_by_scene.get(scene_id, {}))
        if not narration:
            warnings.append(f"narration_outline missing {scene_id}; backfilled placeholder.")
        narration["narration_id"] = narration.get("narration_id") or f"narration_{idx:02d}"
        narration["scene_id"] = scene_id
        narration["voiceover_goal"] = narration.get("voiceover_goal") or f"說明 {screen_title or single_message} 背後的因果邏輯。"
        narration.setdefault("key_points", [])
        narration.setdefault("evidence_to_mention", [])
        narration.setdefault("avoid_saying", [])
        aligned_narration.append(narration)

        dialogue = dict(dialogue_by_scene.get(scene_id, {}))
        if not dialogue:
            warnings.append(f"scene_dialogue_context missing {scene_id}; backfilled placeholder.")
        dialogue["scene_id"] = scene_id
        dialogue["scene_type"] = dialogue.get("scene_type") or scene_type
        dialogue["screen_title"] = dialogue.get("screen_title") or screen_title
        dialogue["dialogue_topic"] = dialogue.get("dialogue_topic") or single_message or screen_title
        visual_anchor = dialogue.get("visual_anchor") if isinstance(dialogue.get("visual_anchor"), dict) else {}
        visual_anchor.setdefault("what_the_image_shows", visual.get("visual_metaphor", ""))
        visual_anchor.setdefault(
            "must_align_with",
            as_list(visual.get("on_screen_labels")) + as_list(visual.get("must_show_numbers"))
        )
        visual_anchor.setdefault("do_not_expand", [])
        dialogue["visual_anchor"] = visual_anchor
        dialogue.setdefault("prior_market_impression", "")
        dialogue.setdefault("this_week_catalyst", "")
        dialogue.setdefault("data_validation", "")
        dialogue.setdefault("causal_interpretation", narration.get("voiceover_goal", ""))
        dialogue.setdefault("offset_or_risk", "")
        dialogue.setdefault("foreshadow_next", "")
        dialogue.setdefault("tom_question_angle", "")
        dialogue.setdefault(
            "miranda_talk_track",
            "請根據本幕畫面、narration_outline 與 evidence，用新聞事件解釋市場數據。"
        )
        dialogue.setdefault("miranda_deep_dive_points", [])
        dialogue.setdefault("expected_dialogue_seconds", "60-90")
        dialogue.setdefault("key_news_lines", as_list(narration.get("evidence_to_mention")))
        dialogue.setdefault("key_numbers", as_list(visual.get("must_show_numbers")))
        dialogue.setdefault("avoid_saying", as_list(narration.get("avoid_saying")))
        dialogue.setdefault("image_alignment_note", "94 會搭配 scene 圖片讀取；若圖片文字與此 metadata 不一致，以 metadata 為準。")
        aligned_dialogue.append(dialogue)

    summary["video_visual_scenes"] = aligned_visuals
    summary["narration_outline"] = aligned_narration
    summary["scene_dialogue_context"] = aligned_dialogue

    meta["scene_alignment_status"] = {
        "scene_count": len(control),
        "control_scene_ids": [item.get("scene_id", "") for item in control if isinstance(item, dict)],
        "video_visual_scenes_count": len(aligned_visuals),
        "narration_outline_count": len(aligned_narration),
        "scene_dialogue_context_count": len(aligned_dialogue),
        "status": "aligned_with_scene_control_list",
    }
    if warnings:
        meta["quality_warnings"] = warnings

    return summary


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
    forest_summary = normalize_scene_control_list(forest_summary)
    forest_summary = normalize_scene_dialogue_context(forest_summary)
    forest_summary = align_scene_layers(forest_summary)
    forest_summary = normalize_video_planning(forest_summary)

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
