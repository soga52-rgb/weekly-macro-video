#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 82 v8.11.2.2 - Story-only Dialogue Generator (V35 authority focused)

Purpose:
- Generate a complete Tom / Miranda macro dialogue story first.
- Do NOT use visual manifest or scene image mapping.
- Use the V35 diagnosis as the main-theme authority.
- Use the Step 80 analysis layer as the filtered event-evidence layer.
- Use only analysis-window market data for price direction and numbers.
- Do not feed raw weekly-news narrative, background-news text, source text, or endpoint excerpts into Gemini.
- Focus on event-led macro storytelling:
  event context -> price reaction -> macro interpretation -> transmission bridge -> closing callback.

Outputs:
- weekly_dialogue_story_only_v8.json
- weekly_dialogue_story_only_v8.md
- weekly_dialogue_story_only_v8_prompt_debug.txt
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

ANALYSIS_FILENAME = "weekly_forest_summary_analysis_layer_test.json"
WEEKLY_V35_DIAGNOSIS_FILENAME = "weekly_v35_diagnosis.json"
MARKET_SERIES_FILENAME = "weekly_market_series.json"
# Raw weekly-news narrative, background text, source text, and endpoint excerpts are
# intentionally excluded from the Step 82 Gemini input. Step 80 has already distilled
# the current-period event evidence, while V35 remains the main-theme authority.
# The source-text filename remains only as a last-resort analysis-window fallback;
# its body is never inserted into the Gemini input bundle.
SOURCE_TEXT_FILENAME = "weekly_source_text.md"

OUT_JSON_FILENAME = "weekly_dialogue_story_only_v8.json"
OUT_MD_FILENAME = "weekly_dialogue_story_only_v8.md"
OUT_PROMPT_DEBUG_FILENAME = "weekly_dialogue_story_only_v8_prompt_debug.txt"


SYSTEM_PROMPT = """
你是機構級總經影片的 showrunner、主筆與敘事導演。

你的任務不是把資料摘要改寫成對話，也不是替圖片寫旁白。
你的任務是使用已由 Step 80 篩選、並與 V35 對齊的事件證據，以及正式分析區間內的市場價格變化，寫出一支 Tom 與 Miranda 的完整總經訪談故事。
你不會收到完整 weekly_news_context.md、舊背景新聞、weekly_source_text 或 endpoint 原文；不得自行補回未提供的新聞敘事。

這一版是 Story-only：
- 不處理圖片。
- 不需要 visual_reference。
- 不需要 visual_brief。
- 不要依照圖卡數量切段。
- 先讓語音故事本身成立。

角色：
Tom 是成熟的國際財經訪談主持人。他不是新聞播報員，也不是單純的問答機器。
Tom 的工作是替聽眾打開問題：他擅長用敏銳的直覺指出市場矛盾，例如「價格明明往一個方向走，為什麼市場的結論沒有跟著改變？」也擅長在聽完分析後，用生活化比喻或頓悟式短句幫聽眾提煉重點。Tom 的語氣要自然、好奇、克制，但要能代表聽眾把反直覺的地方問清楚。

Miranda 是機構級總經策略師。她不是念資料的人。
Miranda 的工作是解釋市場價格背後的市場走勢背後的判斷：事件為什麼重要、價格怎麼反應、這個反應驗證或抵銷了什麼判斷、下一步會傳導到哪個變數。她非常擅長把冷冰冰的宏觀數字落地，在解釋高利率、強美元、流動性壓力或避險需求時，會自然帶出實體經濟的微觀痛點，例如房貸凍結、企業融資成本上升、原物料進口壓力、外資撤離或央行外匯存底消耗。她也擅長指出央行、投資人或市場當下面臨的兩難困境，例如保匯率 vs 保外匯存底、打通膨 vs 救經濟、維持高利率 vs 實體經濟受傷。

核心寫作原則：
0. 【分析區間硬規則】input_bundle.meta.analysis_window 是本集唯一正式分析區間。storyline、main_event_threads、sections、price_reaction、spoken_text、subtitle_text、full_script_plain_text 的「本週」價格變化，只能使用 analysis window 內的數字與事件。
0-1. lookback、macro_background、endpoint_context、weekly_source_text 中屬於 analysis window 以前的內容，只能作為「前期背景」或「延續性脈絡」用一兩句交代，不得成為第一段主軸，不得列為 main_event_threads 的主要價格反應。
0-2. 嚴禁把 lookback window 的起點價格寫成本週起點。本週任何資產的起點、終點與淨方向，只能使用 input_bundle.market_series_analysis_window.assets.*.summary 的 start_value、end_value 與 net_direction。
0-3. 若需提到 analysis window 以前的長債壓力、政策人事、地緣政治或其他背景，必須明確稱為「前期背景」或「延續性脈絡」，並在同一段內快速轉回 analysis window 的本週主線，不可讓背景事件成為整支影片的開場主軸。
0-4. 本集主線的資料優先序為：
    第一順位：weekly_v35_diagnosis.weekly_v35_diagnosis；
    第二順位：analysis_layer.main_theme_analysis_process.main_theme_next_validation；
    第三順位：analysis_layer.main_theme_analysis_process.market_contradictions_and_modifiers；
    第四順位：analysis_layer.forest_summary。
    不得引用不存在的 analysis-layer 欄位，也不得繞過 V35 另建一套主線。
0-4-1. analysis_layer 已是 Step 80 篩選後的事件證據與分析層。不得把其中的修正因子、背離訊號或單一新聞重新升格為另一條主線。
0-4-2. meta.story_thesis、storyline.main_event_threads、各 section 的 story_purpose 與 macro_interpretation 必須共同服務 V35 dominant_driver；可以延後揭示主線，但不可在中後段改成另一套結論。
0-5. weekly_v35_diagnosis 是 Python rule-based V35 診斷層，不是旁白文案；你可以重新組織故事語言，但不可推翻其主導因子、修正因子、背離訊號、資產驗證、油價 / 通膨方向規則與資產方向。
0-6. 若 analysis_layer 與 weekly_v35_diagnosis 出現張力，請寫成分歧、修正因子或待觀察，不要自行改成另一套主線。
0-6-1. 對 analysis_layer.evidence.insufficient_evidence 已標示不足的原因，只能說「待確認、資料不足、可能但無法確認」，不得自行補成資金流、央行干預、政策立場或其他確定因果。
0-7. 油價方向必須以 weekly_v35_diagnosis.observed_market 或 market_series_analysis_window 的 WTI / Brent 實際方向為準。油價上行代表能源成本與短期通膨預期上行壓力；油價下行可能緩和能源通膨，若源自需求疲弱也可能代表成長降溫。若油價不是本期主線，應描述為修正因子或並行訊號。不得把油價變動直接歸因於財政赤字、高利率或公債供需。
0-8. 就業指標名稱不等於方向。初領失業金、非農、失業率與薪資必須有明確方向或相對預期才能判斷。失業率下降先視為韌性訊號，不可單獨改寫成全面就業強勁；非農偏弱但失業率下降時應呈現為就業訊號分歧。勞動市場韌性本身不得直接推升通膨預期，只有薪資壓力或需求偏強等訊號才可進入通膨上行敘事。
0-9. 不得為了配合 US10Y、DXY、Gold、WTI 或亞洲貨幣方向，而把低於預期、轉弱或混合的新聞改寫成強勁，也不得創造 input_bundle 未提供的事件、數字或政策結論。
1. 這是一個故事，不是資料摘要。
2. 前後邏輯必須接得上：上一段留下的問題，下一段要接著回答。
3. 頭尾要呼應：開頭鋪陳過、尚未結束的事件線，必須自然變成下週觀察。
4. 不要裸講數字。每個價格走勢都要由事件、新聞或市場疑問帶出。
5. 每個重要變數都要判斷：它是上游影響、本身驅動，還是兩者混合。
6. 每一段都是傳導節點，不是封閉主題。可以自然觸碰下一個變數，作為下一段伏筆。
7. 不要一開始就總結本週主線。先讓聽眾跟著事件與價格一步一步形成理解。
8. 本週主線應在後段自然收斂，不要在開頭提前講完。
9. 下週觀察不能突然出現，必須回扣前面已經鋪陳過的未解事件或價格線。
10. 全片最後必須有正式收尾，但正式收尾不能取代下週觀察段。最後一段必須分成兩步：
    - Miranda 先完整說明下週觀察，必須回扣本週輸入資料與前文已鋪陳的事件線，最後用一句自然語把話交還給 Tom；不得因範例文字自行加入未出現在 input_bundle 的 Fed 表態、地緣談判、央行干預或其他事件。
    - Tom 最後只做簡短正式收尾：回扣本集主線、感謝 Miranda、提醒觀眾下週持續追蹤，並自然說「我們下週見」。Tom 收尾不得再展開新的分析。
11. 不要為了進入下週觀察或正式收尾，而壓縮中間故事。每一條主要事件線都必須先完整展開「事件脈絡 → 價格反應 → 市場解讀 → Tom 追問 → Miranda 補充」之後，才能進入下一段或下週觀察。
12. 下週觀察與正式收尾只是故事的收束，不是替代主體分析的段落。不得因為要完成結尾格式，就縮短前面各 section 的推論、追問與價格解讀。
13. 主要事件線至少挑一個代表性價格走勢做「口語化走勢解讀」：不要只說價格到哪裡，要說它是快速回落、先上攻後回落、先受壓後反彈、高位震盪，或區間反覆，並解釋這代表市場在重新評估什麼。
14. 【防壓縮規則】除結尾段外，每個 section 目標包含 5 到 6 個 speaker_turns。Tom 在 Miranda 第一次回答後，至少要有兩次獨立追問，避免固定成「Tom 問 → Miranda 答 → Tom 追問 → Miranda 收斂」的 4 回合公式。
15. 【厚度防護指令】節目目標時長為 10 到 12 分鐘。你必須給中間劇情充分推論空間，禁止為了趕著進入下週觀察或正式收尾而壓縮中間 sections。不要急著過渡到下一個變數，要把當下的矛盾點挖深。
16. 【具體情境要求】Miranda 解釋總經傳導時，必須帶入至少一個具體的實體經濟情境或資產範例，例如企業融資成本、房貸凍結、原物料進口壓力、新興市場資金外流、出口敏感型貨幣壓力等，讓宏觀邏輯落地。
17. 【內容深度與質感要求】增加微觀痛點：Miranda 在解釋高利率、強美元、流動性壓力、匯率貶值或避險需求時，要舉出具體痛點，例如房地產產業鏈資金被凍結、企業融資成本上升、進口原物料變貴、外資撤離、央行外匯存底消耗等。
18. 【兩難困境要求】在提到央行政策或市場抉擇時，必須強調局面中的兩難，例如保匯率 vs 保外匯存底、打通膨 vs 救經濟、維持高利率 vs 實體經濟受傷、追逐利差 vs 防範硬著陸。
19. 【主持人頓悟金句】Tom 的追問不能只是平鋪直敘的過場；在聽完 Miranda 的分析後，Tom 應嘗試用一句生動但克制的「頓悟式總結」幫聽眾消化，例如「所以現在市場買黃金，不只是為了賺錢，而是為了買一份保險？」或「換句話說，這不是單純比誰經濟強，而是比誰比較沒那麼差？」
11. Tom 的開場白不要先報新聞清單，也不要先下本週結論；Tom 要用主持人的方式打開問題，請 Miranda 先從本週市場價格走勢切入分析。
    Tom 開場請使用自然節目開場，再請 Miranda 從本週市場價格走勢切入。
    建議句型：
    「歡迎來到本週總經報導。Miranda，在進入今天的主線分析之前，我想先從市場價格本身看起。這週有哪些重要財經數據的走勢，最值得我們注意？」
    Miranda 第一段必須接著用事件脈絡帶出 2～3 個代表性價格走勢，並解釋這些走勢為什麼重要。

追問、白話翻譯與呼吸感原則：
- 保留 Tom 開場方式，不必再改開場。
- 每條主要事件線至少安排一輪 Tom 追問，讓 Miranda 有機會把原因、傳導與市場含義講深一層。
- Tom 的追問要有「解謎感」，不要只是換段落；要代表聽眾指出反直覺或未解矛盾，例如：
  「這只是短期修正，還是真的改變了市場主線？」
  「這個價格反應，究竟是在驗證主線，還是只反映短期雜訊？」
  「如果主要資產大致同向，為什麼仍有局部市場出現背離？」
  「等一下，這聽起來有點反直覺。價格明明往一個方向走，為什麼市場結論卻沒有跟著轉向？」
- Miranda 的回答要像在解謎：先承認表面矛盾，再揭示背後的市場市場走勢背後的判斷。
- Miranda 使用專業術語後，必須立刻補一句白話翻譯。尤其是：期限溢價、結構性通膨、利差優勢、避險需求、上游影響、流動性壓力。
  例如：「這就是期限溢價。白話說，就是投資人覺得長期不確定性變高，所以要求更高的補償。」
- 增加對話呼吸感：Miranda 不要連續講太久。如果單一 Miranda spoken_text 可能超過 35 秒，請拆成「Miranda 先解釋 → Tom 短句確認或追問 → Miranda 補充」。
- Tom 可以用短句幫聽眾消化，例如：「所以這個訊號不是失效，而是被更強的力量暫時壓過？」、「換句話說，市場不是忽略這項資料，而是在重新比較不同因素的權重？」
- 價格走勢要用口語描述，不要用技術分類詞當台詞主體。
- 可以使用「先被壓下去、後來又被買盤拉回」、「前段快速回落、後段低位整理」、「先上攻、後來被成長擔憂壓回」這類說法。
- 避免在 spoken_text 裡直接把「V 型反轉」、「倒 V 型」、「L 型整理」當成主要表述；如果需要使用，必須立刻用一句口語原因解釋。

價格走勢解讀範例：
不要寫成：「某資產呈現 V 型反轉，價格在某個區間震盪。」
應該寫成：「這項資產前段先受主要因子影響，後段又因另一股力量出現局部修正。這代表市場沒有只看單一訊號，而是在重新比較不同因素的權重。」

建議故事推進方式：
- 先從本週最重要的市場矛盾或淨方向切入；範例只能示範敘事方法，不可預設任何資產本週一定上漲或下跌。
- 用整週淨方向建立主線，再用週內事件解釋中間的反覆。
- 用價格反應解釋市場目前更關注什麼，不要把單日波動寫成整週結論。
- 如果價格走勢和直覺不同，要把它當作故事問題。
- 讓 Tom 問出這個問題，讓 Miranda 解釋。
- 每段結尾自然帶出下一個變數。

請產生 10 到 12 分鐘左右的中文雙人對談稿。
語氣：台灣專業財經節目口語，清楚、有節奏、有洞察，但不要浮誇。
語言邊界：
- 避免戲劇化或絕對化詞彙，例如：拉鋸、雙重夾擊、海嘯、毀滅性打擊、兩杯毒藥、終極考驗、狂飆、完全正確、屏息等待。請改用：訊號分歧、抵銷力量、修正因子、壓力升高、仍需驗證、局部反彈、區間震盪。
- 匯率表述必須清楚：USD/TWD 上升代表台幣貶值，USD/KRW 上升代表韓元貶值，USD/JPY 上升代表日圓貶值。不要寫成「美元/台幣貶值」。
- 請用「本週 / 本期 / 正式分析區間」描述週報，不要用「今天」代表整週。
不要投資建議，不要買賣指令。
請輸出合法 JSON，不要 Markdown，不要多餘文字。
"""


USER_PROMPT_TEMPLATE = """
請根據下方資料，產生 Step 82 v8.11.2 Story-only Tom / Miranda 總經訪談稿。

資料：
{input_bundle_json}

輸入範圍說明：
- input_bundle 只包含 Step 80 分析層、V35 診斷層、正式分析區間市場資料與 lookback 使用說明。
- 完整 weekly_news_context.json / md、背景新聞、weekly_source_text 與 endpoint 原文均未提供。
- 事件細節以 analysis_layer 已保留的材料為限；不得自行補回未提供的舊新聞主線或背景敘事。

weekly_v35_diagnosis 使用規則：
- input_bundle.weekly_v35_diagnosis 是 Python rule-based V35 診斷層，請優先用來對齊本集主線與網頁主線。
- 請優先使用 weekly_v35_diagnosis.weekly_v35_diagnosis 裡的 dominant_driver、correction_factors、divergence_signal、asset_validation、next_period_watch。
- Tom / Miranda 可以用更自然的訪談語言重組故事，但不可推翻 V35 的油價 / 通膨方向規則、資產方向與背離判斷。
- 若 V35 診斷層與 analysis_layer 看似衝突，請在對話中表述為「分歧、修正因子、仍待觀察」，不要自行創造另一條主線。
- meta.story_thesis 必須直接使用或語意等同 V35 dominant_driver；不得把 correction_factors 或單一事件改寫成新的主題。
- analysis_layer.evidence.insufficient_evidence 中列出的未知原因不得被補成確定因果。
- 對外台詞請避免「交易、定價、體制、風險溢價、傳導源」等生硬名詞；優先使用「市場更關注、主導因子、修正因子、背離訊號、資產驗證、下期觀察、市場重新評估」。

硬性生成規則：
- 你必須先讀取 input_bundle.meta.analysis_window，並將其作為本集唯一正式週期。
- meta.week_range 必須等於 input_bundle.meta.analysis_window.label。
- 所有「本週」價格反應必須優先使用 input_bundle.market_series_analysis_window.assets.*.summary。
- 任何資產的整週方向必須以 summary.start_value → summary.end_value / summary.net_direction 為準。
- 若要描述 summary.high_value / summary.low_value 或中間某一天走勢，必須明確寫成「週內一度」或「週中波動」，不得寫成本週主線方向。
- input_bundle.market_series_lookback_note、weekly_source_text、endpoint_context_excerpt 若包含更早日期，只能用於前期背景，不可作為本週起點。
- storyline.main_event_threads 不得把 lookback 起點價格當成本週主要事件線。
- 第一段可簡短交代前期高利率背景，但必須快速轉入 analysis window 內的本週變化，不可整段都圍繞前期長債恐慌。
- 嚴禁使用 analysis window 外的價格區間描述本週變化。正式區間的起點、終點與淨方向，只能使用 input_bundle.market_series_analysis_window.assets.*.summary；lookback 或 endpoint context 中的更早價格不得寫成本週走勢。

請輸出 JSON，結構如下：

{{
  "meta": {{
    "script_type": "story_only_dialogue_v8",
    "week_range": "",
    "estimated_duration_minutes": "10-12",
    "story_thesis": "用一句話描述本集故事核心，但不要像投資建議"
  }},
  "storyline": {{
    "opening_question": "本集一開始要打開的市場問題",
    "main_event_threads": [
      {{
        "thread_name": "事件線名稱",
        "why_it_matters": "為什麼重要",
        "price_reaction": "價格如何反應",
        "unresolved_question": "為什麼延伸到後面或下週"
      }}
    ],
    "closing_callback": "結尾如何回扣開頭"
  }},
  "sections": [
    {{
      "section_id": "s1",
      "section_title": "自然語意標題，不要像簡報標題",
      "story_purpose": "這段在整支故事中的任務",
      "event_setup": "這段先鋪陳的事件或背景",
      "price_reaction": "這段要使用的價格反應",
      "driver_judgment": "上游影響 / 本身驅動 / 混合",
      "macro_interpretation": "這段真正要讓聽眾理解的洞察",
      "micro_pain_point": "這段可落地的實體經濟痛點或資產範例，例如房貸、企業融資、原物料進口、外資流出",
      "dilemma": "這段涉及的兩難困境，例如保匯率 vs 保外匯存底、打通膨 vs 救經濟；若無則簡短說明",
      "tom_insight_line": "Tom 可用來幫聽眾頓悟的金句式總結",
      "bridge_question": "自然帶到下一段的問題",
      "speaker_turns": [
        {{
          "speaker": "Tom",
          "spoken_text": "正式可進 TTS 的台詞",
          "subtitle_text": "25字以內字幕",
          "estimated_seconds": 20
        }}
      ]
    }}
  ],
  "next_week_watch": [
    {{
      "watch_item": "下週觀察項目",
      "callback_to_story": "它回扣前面哪條事件線",
      "why_it_matters": "為什麼要追蹤"
    }}
  ],
  "closing_handoff_turn": {
    "speaker": "Miranda",
    "spoken_text": "下週觀察摘要分析後，把話自然交還 Tom，例如：Tom，以上就是下週最需要追蹤的幾個關鍵訊號。",
    "subtitle_text": "25字以內字幕",
    "estimated_seconds": 10
  },
  "closing_turn": {
    "speaker": "Tom",
    "spoken_text": "簡短正式收尾，回扣主線、感謝 Miranda、提醒下週追蹤，並自然說我們下週見；不得再展開新分析",
    "subtitle_text": "25字以內字幕",
    "estimated_seconds": 12
  },
  "full_script_plain_text": "[Tom]: ...\\n[Miranda]: ..."
}}

生成要求：
- sections 數量由故事需要決定，建議 5 到 7 段，不要為了固定張數硬切。
- 除結尾段外，每個 section 目標 5 到 6 個 speaker_turns；重要段落可以更多。
- 主要事件線至少要有兩輪 Tom 追問與 Miranda 補充，不要只用一問一答或固定 4 回合公式就結束。
- 若 Miranda 單次 spoken_text 預估超過 35 秒，優先拆成多個 turn，中間插入 Tom 的確認、頓悟式總結或追問。
- Tom 負責打開問題與承接，不要替 Miranda 下完整結論；但 Tom 必須用頓悟式金句幫聽眾消化至少 2 個關鍵段落。
- Miranda 負責解釋事件、價格與總經傳導；使用專業術語後，必須補一句白話翻譯。
- Miranda 在解釋宏觀邏輯時，必須加入具體實體經濟痛點或資產範例，避免只停留在抽象概念。
- 涉及央行或市場選擇時，必須把兩難困境講出來，讓故事有張力。
- 價格走勢必須服務故事，不要變成數字清單。
- 如果某個事件最後列為 next_week_watch，前面故事中必須已經鋪陳過。
- 不得為了趕進下週觀察或正式收尾而壓縮前面 sections；每個主要事件線都要有足夠的推論、追問與補充。
- 最後一個 section 的 speaker_turns 必須先由 Miranda 完整說明下週觀察，並自然把話交還給 Tom。
- Miranda 的下週觀察說明不得只列清單，必須回扣前面故事已鋪陳的事件線。
- closing_handoff_turn 必須與最後一段中 Miranda 交還主持人的 speaker_turn 內容一致。
- closing_turn 必須與最後一個 Tom speaker_turn 內容一致。
- full_script_plain_text 必須由 speaker_turns 重新組成，保留 [Tom] / [Miranda] 標籤，且最後一行必須是 Tom 的簡短正式收尾。
- sections 未來會交給圖片層使用，所以每個 section 的 story_purpose、event_setup、price_reaction、macro_interpretation 要保持清楚，但不要在這版生成圖片提示詞。
"""


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Failed to read JSON: {path} | {exc}")
        return default


def read_text(path: Path, max_chars: int = 80000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        return text[:max_chars] + "\n...（內容過長，已截斷）"
    return text


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def compact_json(data: Any, max_chars: int = 140000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) > max_chars:
        return text[:max_chars] + "\n...（內容過長，已截斷）"
    return text


def latest_week_dir() -> Path:
    if not OUTPUT_WEEKLY_DIR.exists():
        raise FileNotFoundError(f"Missing output weekly directory: {OUTPUT_WEEKLY_DIR}")
    candidates = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No weekly output directories under: {OUTPUT_WEEKLY_DIR}")
    return sorted(candidates, key=lambda p: p.name)[-1]


def build_market_series_summary(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"available": False}

    summary: Dict[str, Any] = {"available": True, "assets": {}}
    series = raw.get("series", raw)

    if isinstance(series, dict):
        for name, values in series.items():
            if not isinstance(values, list) or not values:
                continue
            summary["assets"][name] = {
                "points_count": len(values),
                "sample_points": [x for x in values[:20] if isinstance(x, dict)],
            }
    elif isinstance(series, list):
        for item in series:
            if not isinstance(item, dict):
                continue
            name = item.get("asset") or item.get("symbol") or item.get("name") or item.get("ticker")
            values = item.get("data") or item.get("points") or item.get("values")
            if name and isinstance(values, list):
                summary["assets"][str(name)] = {
                    "points_count": len(values),
                    "sample_points": values[:20],
                }
    return summary


def infer_analysis_window(analysis: Any, week_dir: Path) -> Dict[str, str]:
    env_start = os.environ.get("ANALYSIS_START_DATE", "").strip()
    env_end = os.environ.get("ANALYSIS_END_DATE", "").strip()
    if env_start and env_end:
        return {
            "start_date": env_start,
            "end_date": env_end,
            "label": f"{env_start} ～ {env_end}",
            "source": "workflow_env",
        }

    if isinstance(analysis, dict):
        meta = analysis.get("meta") if isinstance(analysis.get("meta"), dict) else {}
        window = meta.get("analysis_window") if isinstance(meta.get("analysis_window"), dict) else {}
        start = str(window.get("start_date") or "").strip()
        end = str(window.get("end_date") or "").strip()
        if start and end:
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "analysis_layer.meta.analysis_window",
            }

        week_range = str(meta.get("week_range") or "").strip()
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:～|~|to|-)\s*(\d{4}-\d{2}-\d{2})", week_range)
        if match:
            start, end = match.group(1), match.group(2)
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "analysis_layer.meta.week_range",
            }

    source_text = read_text(week_dir / SOURCE_TEXT_FILENAME, 20000)
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


def infer_point_direction(start_value: float, end_value: float, tolerance: float = 1e-9) -> str:
    if end_value > start_value + tolerance:
        return "up"
    if end_value < start_value - tolerance:
        return "down"
    return "flat"


def summarize_analysis_points(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    clean_points: List[Dict[str, Any]] = []
    for point in points:
        if not isinstance(point, dict):
            continue
        try:
            value = float(point.get("value"))
        except (TypeError, ValueError):
            continue
        clean_points.append({"date": str(point.get("date") or ""), "value": value})

    if not clean_points:
        return {
            "available": False,
            "net_direction": "unclear",
            "instruction": "No usable analysis-window points. Treat direction as unclear / 待確認.",
        }

    start_point = clean_points[0]
    end_point = clean_points[-1]
    start_value = float(start_point["value"])
    end_value = float(end_point["value"])
    net_change = end_value - start_value
    net_change_pct = (net_change / start_value * 100) if start_value else None
    high_point = max(clean_points, key=lambda x: x["value"])
    low_point = min(clean_points, key=lambda x: x["value"])

    return {
        "available": True,
        "start_date": start_point["date"],
        "start_value": start_value,
        "end_date": end_point["date"],
        "end_value": end_value,
        "net_change": net_change,
        "net_change_pct": net_change_pct,
        "net_direction": infer_point_direction(start_value, end_value),
        "high_date": high_point["date"],
        "high_value": high_point["value"],
        "low_date": low_point["date"],
        "low_value": low_point["value"],
        "instruction": (
            "Use net_direction as the formal this-week direction. "
            "High/low and intermediate moves may be described only as intra-week episodes."
        ),
    }



def build_market_series_analysis_window(raw: Any, analysis_window: Dict[str, str]) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"available": False}

    start = analysis_window.get("start_date", "")
    end = analysis_window.get("end_date", "")
    result: Dict[str, Any] = {
        "available": True,
        "analysis_window": analysis_window,
        "assets": {},
        "direction_rule": (
            "For every asset, the formal this-week direction is start_value -> end_value "
            "inside analysis_window. The model may discuss high/low or mid-week reversals, "
            "but must label them as intra-week episodes and must not describe them as the whole-week direction."
        ),
        "instruction": (
            "Use these filtered points and the computed summary for all this-week price reactions in the dialogue. "
            "Do not use lookback-window start prices as this-week starting points."
        ),
    }

    series = raw.get("series", raw)

    if isinstance(series, dict):
        for name, values in series.items():
            if not isinstance(values, list):
                continue
            points = filter_points_by_window(values, start, end)
            result["assets"][str(name)] = {
                "asset_key": str(name),
                "asset_name": str(name),
                "points_count": len(points),
                "points": points,
                "summary": summarize_analysis_points(points),
            }
    elif isinstance(series, list):
        for item in series:
            if not isinstance(item, dict):
                continue
            asset_key = item.get("asset_key") or item.get("symbol") or item.get("ticker") or item.get("asset") or item.get("name")
            asset_name = item.get("asset") or item.get("name") or asset_key
            unit = item.get("unit", "")
            values = item.get("data") or item.get("points") or item.get("values")
            if asset_key and isinstance(values, list):
                points = filter_points_by_window(values, start, end)
                result["assets"][str(asset_key)] = {
                    "asset_key": str(asset_key),
                    "asset_name": str(asset_name),
                    "unit": unit,
                    "points_count": len(points),
                    "points": points,
                    "summary": summarize_analysis_points(points),
                }

    return result


def build_market_series_lookback_note(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        return {"available": False}

    meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    return {
        "available": True,
        "meta": meta,
        "note": (
            "Lookback data is intentionally not provided as raw dialogue material. "
            "It may be used only as prior context already distilled in the analysis_layer."
        ),
    }


def build_input_bundle(week_dir: Path) -> Dict[str, Any]:
    analysis = load_json(week_dir / ANALYSIS_FILENAME, {})
    weekly_v35_diagnosis = load_json(week_dir / WEEKLY_V35_DIAGNOSIS_FILENAME, {})
    market_series_raw = load_json(week_dir / MARKET_SERIES_FILENAME, {})

    if not analysis:
        raise FileNotFoundError(
            f"Missing or empty analysis layer: {week_dir / ANALYSIS_FILENAME}. "
            "Run Step 80 before Step 82."
        )

    compact_v35 = (
        weekly_v35_diagnosis.get("weekly_v35_diagnosis", {})
        if isinstance(weekly_v35_diagnosis, dict)
        else {}
    )
    if not isinstance(compact_v35, dict) or not compact_v35:
        raise FileNotFoundError(
            f"Missing or empty V35 diagnosis: {week_dir / WEEKLY_V35_DIAGNOSIS_FILENAME}. "
            "Run scripts/macro_v35_diagnosis.py before Step 82."
        )

    if not market_series_raw:
        raise FileNotFoundError(
            f"Missing or empty market series: {week_dir / MARKET_SERIES_FILENAME}."
        )

    analysis_window = infer_analysis_window(analysis, week_dir)

    return {
        "meta": {
            "week_dir": str(week_dir),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "analysis_window": analysis_window,
            "input_files": {
                "analysis": str(week_dir / ANALYSIS_FILENAME),
                "weekly_v35_diagnosis": str(week_dir / WEEKLY_V35_DIAGNOSIS_FILENAME),
                "weekly_market_series": str(week_dir / MARKET_SERIES_FILENAME),
            },
            "excluded_from_gemini": [
                "weekly_news_context.json",
                "weekly_news_context.md",
                "macro_background_context.json",
                "macro_background_context.md",
                "weekly_source_text.md",
                "data/weekly_video_source.json",
            ],
            "hard_rule": (
                "The dialogue must use analysis_window as the only formal week range. "
                "V35 is the main-theme authority. Step 80 is the filtered event-evidence layer. "
                "Pre-analysis-window and raw-news narrative are not provided to Gemini."
            ),
        },
        "analysis_layer": analysis,
        "weekly_v35_diagnosis": weekly_v35_diagnosis,
        "weekly_v35_diagnosis_note": (
            "Rule-based V35 diagnosis. Use it as the authority for dominant driver, correction factors, "
            "divergence signal, asset validation, next-period watch, oil/inflation direction rules, "
            "and asset directions."
        ),
        "market_series_analysis_window": build_market_series_analysis_window(market_series_raw, analysis_window),
        "market_series_lookback_note": build_market_series_lookback_note(market_series_raw),
        "source_scope_note": (
            "Event evidence has already been filtered and distilled in analysis_layer. "
            "Do not reconstruct a separate theme from raw weekly-news narrative, because it is intentionally excluded."
        ),
        "instruction_hint": (
            "Build the story around the V35 dominant driver. Use analysis_layer only to explain, qualify, and humanize it. "
            "Use market_series_analysis_window for every price number and direction. "
            "Keep correction factors and divergences in their proper supporting roles."
        ),
    }


def extract_json(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if not match:
            raise ValueError("No JSON object found in model response")
        return json.loads(match.group(0))


def call_gemini_json(system_prompt: str, user_prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": system_prompt.strip() + "\n\n" + user_prompt.strip()}]}],
        "generationConfig": {
            "temperature": 0.55,
            "topP": 0.90,
            "maxOutputTokens": 24576,
            "responseMimeType": "application/json",
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")

    last_error = None
    for attempt in range(1, 4):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                raw = response.read().decode("utf-8")
            data = json.loads(raw)
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return extract_json(text)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = f"HTTP {exc.code}: {detail}"
            if exc.code in (429, 500, 503):
                wait = 10 * attempt
                print(f"[WARN] Gemini temporary error. Retry in {wait}s. attempt={attempt}/3")
                time.sleep(wait)
                continue
            raise RuntimeError(last_error) from exc
        except Exception as exc:
            last_error = str(exc)
            if attempt < 3:
                wait = 5 * attempt
                print(f"[WARN] Gemini call failed. Retry in {wait}s. attempt={attempt}/3 | {exc}")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError(f"Gemini call failed after retries: {last_error}")



def clean_text_value(text: str) -> str:
    replacements = {
        "聯聯準會": "聯準會",
        "定價邏輯": "市場走勢背後的判斷",
        "市場定價": "市場看法",
        "重新定價": "重新評估",
        "交易利率": "只看利率",
        "交易通膨": "關注通膨",
        "交易美元": "關注美元",
        "避險溢價": "避險需求",
        "風險溢價": "風險補償",
        "傳導源": "主導因子",
        "上游傳導": "上游影響",
        "拉鋸戰": "訊號分歧",
        "拉鋸": "訊號分歧",
        "雙重夾擊": "多重壓力",
        "海嘯": "壓力升高",
        "毀滅性的打擊": "明顯壓力",
        "毀滅性打擊": "明顯壓力",
        "兩杯毒藥": "兩難選擇",
        "終極考驗": "關鍵驗證",
        "狂飆": "快速上行",
        "完全正確": "可以這樣理解",
        "屏息等待": "等待",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def clean_result_texts(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {key: clean_result_texts(value) for key, value in obj.items()}
    if isinstance(obj, list):
        return [clean_result_texts(value) for value in obj]
    if isinstance(obj, str):
        return clean_text_value(obj)
    return obj




def collect_text_fragments(obj: Any) -> List[str]:
    fragments: List[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "full_script_plain_text":
                continue
            fragments.extend(collect_text_fragments(value))
    elif isinstance(obj, list):
        for value in obj:
            fragments.extend(collect_text_fragments(value))
    elif isinstance(obj, str):
        fragments.append(obj)
    return fragments


def apply_v35_authority_metadata(result: Dict[str, Any], bundle: Dict[str, Any]) -> None:
    full_v35 = bundle.get("weekly_v35_diagnosis", {})
    compact_v35 = (
        full_v35.get("weekly_v35_diagnosis", {})
        if isinstance(full_v35, dict)
        else {}
    )
    dominant_driver = str(compact_v35.get("dominant_driver") or "").strip()

    result.setdefault("meta", {})
    result["meta"]["v35_authority_applied"] = bool(dominant_driver)
    result["meta"]["v35_dominant_driver"] = dominant_driver
    if dominant_driver:
        # story_thesis is internal story metadata, so keep it deterministically aligned
        # with the web/V35 main theme. The spoken opening still follows the rule of
        # revealing the conclusion gradually rather than announcing it immediately.
        result["meta"]["story_thesis"] = dominant_driver


def sentence_has_qualifier(sentence: str) -> bool:
    qualifiers = (
        "週內一度", "週中一度", "盤中一度", "短暫", "一度",
        "先", "後來", "但整週", "不代表整週",
    )
    return any(q in sentence for q in qualifiers)


def sentence_is_hypothetical(sentence: str) -> bool:
    markers = ("如果", "若", "假設", "一旦", "會不會", "是否", "可能", "預期", "能否", "假如")
    return any(marker in sentence for marker in markers)


def sentence_is_negated(sentence: str, phrase: str) -> bool:
    for neg in ("沒有", "並未", "未", "不是", "不再", "不能說"):
        if f"{neg}{phrase}" in sentence or f"{neg} {phrase}" in sentence:
            return True
    return False


def find_direction_conflict(
    clause: str,
    subjects: tuple[str, ...],
    bad_phrases: tuple[str, ...],
    allow_reverse_order: bool = True,
    max_gap: int = 18,
) -> str:
    """Match only an explicit asset-direction statement, not nearby words."""
    for subject in subjects:
        subject_re = re.escape(subject)
        for bad in bad_phrases:
            bad_re = re.escape(bad)
            patterns = [rf"{subject_re}.{{0,{max_gap}}}{bad_re}"]
            if allow_reverse_order:
                patterns.append(rf"{bad_re}.{{0,{max_gap}}}{subject_re}")
            for pattern in patterns:
                if re.search(pattern, clause, flags=re.I):
                    if sentence_is_negated(clause, bad):
                        continue
                    return bad
    return ""


def validate_directional_consistency(result: Dict[str, Any], bundle: Dict[str, Any]) -> None:
    full_v35 = bundle.get("weekly_v35_diagnosis", {})
    observed = full_v35.get("observed_market", {}) if isinstance(full_v35, dict) else {}
    if not isinstance(observed, dict):
        return

    text = "\n".join(collect_text_fragments(result))
    sentences = [s.strip() for s in re.split(r"[。！？!?\n]+", text) if s.strip()]
    issues: List[str] = []
    rules: List[Dict[str, Any]] = []

    if observed.get("WTI", {}).get("direction") == "up" or observed.get("Brent", {}).get("direction") == "up":
        rules.append({
            "subjects": ("油價", "WTI", "Brent", "西德州原油", "布蘭特原油"),
            "bad": ("下跌", "走低", "轉跌", "回落"),
            "reason": "WTI / Brent 本週淨方向為上行",
            "reverse": True,
        })

    if observed.get("DXY", {}).get("direction") == "up":
        rules.append({
            "subjects": ("DXY", "美元指數"),
            "bad": ("走弱", "下跌", "走貶", "轉弱", "回落"),
            "reason": "DXY 本週淨方向為上行",
            "reverse": True,
        })

    if observed.get("Gold", {}).get("direction") == "down":
        rules.append({
            "subjects": ("黃金", "金價"),
            "bad": ("上漲", "走高", "上行", "轉強"),
            "reason": "Gold 本週淨方向為下行",
            "reverse": True,
        })

    if observed.get("USDJPY", {}).get("direction") == "up":
        rules.extend([
            {
                "subjects": ("USD/JPY", "USDJPY", "美元兌日圓"),
                "bad": ("下跌", "走低", "轉跌", "回落"),
                "reason": "USD/JPY 本週淨方向為上行",
                "reverse": False,
            },
            {
                "subjects": ("日圓",),
                "bad": ("升值", "走強", "轉強"),
                "reason": "USD/JPY 上行代表日圓本週走弱",
                "reverse": True,
            },
        ])

    if observed.get("USDTWD", {}).get("direction") == "up":
        rules.extend([
            {
                "subjects": ("USD/TWD", "USDTWD", "美元兌台幣"),
                "bad": ("下跌", "走低", "轉跌", "回落"),
                "reason": "USD/TWD 本週淨方向為上行",
                "reverse": False,
            },
            {
                "subjects": ("台幣",),
                "bad": ("升值", "走強", "轉強"),
                "reason": "USD/TWD 上行代表台幣本週走弱",
                "reverse": True,
            },
        ])

    if observed.get("USDKRW", {}).get("direction") == "down":
        rules.extend([
            {
                "subjects": ("USD/KRW", "USDKRW", "美元兌韓元"),
                "bad": ("上漲", "走高", "上行", "轉強"),
                "reason": "USD/KRW 本週淨方向為下行",
                "reverse": False,
            },
            {
                "subjects": ("韓元",),
                "bad": ("貶值", "走弱", "承壓", "轉弱"),
                "reason": "USD/KRW 下行代表韓元本週相對走強",
                "reverse": True,
            },
        ])

    for sentence in sentences:
        clauses = [c.strip() for c in re.split(r"[，,；;：:]", sentence) if c.strip()]
        for clause in clauses:
            if sentence_has_qualifier(clause) or sentence_is_hypothetical(clause):
                continue
            for rule in rules:
                bad = find_direction_conflict(
                    clause=clause,
                    subjects=rule["subjects"],
                    bad_phrases=rule["bad"],
                    allow_reverse_order=bool(rule.get("reverse", True)),
                )
                if bad:
                    issues.append(f"{rule['reason']}，但輸出出現：{clause[:180]}")

    if issues:
        unique_issues: List[str] = []
        for issue in issues:
            if issue not in unique_issues:
                unique_issues.append(issue)
        raise RuntimeError(
            "Step 82 directional consistency check failed. Review the generated story before Step 83:\n- "
            + "\n- ".join(unique_issues[:12])
        )


def ensure_closing_turn(result: Dict[str, Any]) -> None:
    sections = result.get("sections")
    handoff = result.get("closing_handoff_turn")
    closing = result.get("closing_turn")

    if not isinstance(sections, list) or not sections:
        return

    last_section = None
    for section in reversed(sections):
        if isinstance(section, dict):
            last_section = section
            break
    if not isinstance(last_section, dict):
        return

    turns = last_section.get("speaker_turns")
    if not isinstance(turns, list):
        turns = []
        last_section["speaker_turns"] = turns

    def append_if_missing(turn_data: Dict[str, Any]) -> None:
        speaker = str(turn_data.get("speaker", "")).strip()
        text = str(turn_data.get("spoken_text", "")).strip()
        if not speaker or not text:
            return

        for existing in turns:
            if not isinstance(existing, dict):
                continue
            if (
                str(existing.get("speaker", "")).strip() == speaker
                and str(existing.get("spoken_text", "")).strip() == text
            ):
                return

        turns.append({
            "speaker": speaker,
            "spoken_text": text,
            "subtitle_text": turn_data.get("subtitle_text", ""),
            "estimated_seconds": turn_data.get("estimated_seconds", 12),
        })

    # First ensure Miranda has a handoff after the watch explanation.
    if isinstance(handoff, dict):
        append_if_missing(handoff)

    # Then ensure Tom closes the show. The last line should be Tom.
    if isinstance(closing, dict):
        append_if_missing(closing)



def rebuild_full_script(result: Dict[str, Any]) -> None:
    lines: List[str] = []
    sections = result.get("sections")
    if not isinstance(sections, list):
        return
    for section in sections:
        if not isinstance(section, dict):
            continue
        turns = section.get("speaker_turns")
        if not isinstance(turns, list):
            continue
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            speaker = str(turn.get("speaker", "")).strip()
            text = str(turn.get("spoken_text", "")).strip()
            if speaker and text:
                lines.append(f"[{speaker}]: {text}")
    if lines:
        result["full_script_plain_text"] = "\n".join(lines)


def build_markdown(result: Dict[str, Any]) -> str:
    lines: List[str] = ["# Weekly Dialogue Story-only v8", ""]
    meta = result.get("meta", {})
    storyline = result.get("storyline", {})

    if isinstance(meta, dict):
        lines.append(f"- Type: {meta.get('script_type', 'story_only_dialogue_v8')}")
        lines.append(f"- Week: {meta.get('week_range', '')}")
        lines.append(f"- Estimated duration: {meta.get('estimated_duration_minutes', '')} minutes")
        lines.append(f"- Story thesis: {meta.get('story_thesis', '')}")
        lines.append("")

    if isinstance(storyline, dict):
        lines.append("## Storyline")
        lines.append("")
        lines.append(f"- Opening question: {storyline.get('opening_question', '')}")
        lines.append(f"- Closing callback: {storyline.get('closing_callback', '')}")
        lines.append("")

    sections = result.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            lines.append(f"## {section.get('section_id', '')}｜{section.get('section_title', '')}")
            lines.append("")
            if section.get("story_purpose"):
                lines.append(f"**Purpose:** {section.get('story_purpose')}")
                lines.append("")
            for turn in section.get("speaker_turns", []) or []:
                if not isinstance(turn, dict):
                    continue
                lines.append(f"**{turn.get('speaker', '')}：** {turn.get('spoken_text', '')}")
                if turn.get("subtitle_text"):
                    lines.append(f"  - 字幕：{turn.get('subtitle_text')}")
                if turn.get("estimated_seconds") != "":
                    lines.append(f"  - 秒數：{turn.get('estimated_seconds', '')}")
                lines.append("")
            if section.get("bridge_question"):
                lines.append(f"_Bridge: {section.get('bridge_question')}_")
                lines.append("")

    next_watch = result.get("next_week_watch", [])
    if isinstance(next_watch, list) and next_watch:
        lines.append("## Next week watch")
        lines.append("")
        for item in next_watch:
            if not isinstance(item, dict):
                continue
            lines.append(f"- **{item.get('watch_item', '')}**：{item.get('why_it_matters', '')}")
            if item.get("callback_to_story"):
                lines.append(f"  - 回扣：{item.get('callback_to_story')}")
        lines.append("")

    if result.get("full_script_plain_text"):
        lines.append("---")
        lines.append("")
        lines.append("## Full script plain text")
        lines.append("")
        lines.append(result["full_script_plain_text"])
    return "\n".join(lines).strip() + "\n"


def main() -> None:
    week_dir_arg = os.environ.get("WEEK_DIR", "").strip()

    if not week_dir_arg:
        week_dir = latest_week_dir()
    else:
        raw_week_dir = Path(week_dir_arg)
        if raw_week_dir.is_absolute():
            week_dir = raw_week_dir
        else:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", week_dir_arg):
                week_dir = OUTPUT_WEEKLY_DIR / week_dir_arg
            else:
                week_dir = ROOT_DIR / raw_week_dir

    if not week_dir.exists():
        raise FileNotFoundError(
            "Week directory not found: "
            f"{week_dir}\n"
            "Please use WEEK_DIR as either YYYY-MM-DD, "
            "output/weekly/YYYY-MM-DD, or leave it blank to use the latest folder."
        )

    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY")
    model = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash").strip()

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Gemini model: {model}")

    bundle = build_input_bundle(week_dir)
    analysis_window = bundle.get("meta", {}).get("analysis_window", {})
    print(f"[INFO] Analysis window: {analysis_window.get('label')} ({analysis_window.get('source')})")
    print(f"[INFO] weekly_v35_diagnosis.json included: {(week_dir / WEEKLY_V35_DIAGNOSIS_FILENAME).exists()}")
    print("[INFO] Raw weekly news/background/source/endpoint text excluded from Gemini input: True")

    user_prompt = USER_PROMPT_TEMPLATE.replace("{input_bundle_json}", compact_json(bundle, 120000))
    (week_dir / OUT_PROMPT_DEBUG_FILENAME).write_text(SYSTEM_PROMPT.strip() + "\n\n" + user_prompt.strip(), encoding="utf-8")

    print("[INFO] Generating story-only dialogue...")
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    result = clean_result_texts(result)
    apply_v35_authority_metadata(result, bundle)

    result.setdefault("meta", {})
    if isinstance(analysis_window, dict):
        result["meta"]["week_range"] = analysis_window.get("label", result["meta"].get("week_range", ""))
        result["meta"]["analysis_window"] = analysis_window

    ensure_closing_turn(result)
    rebuild_full_script(result)
    try:
        validate_directional_consistency(result, bundle)
    except RuntimeError:
        # Keep the generated candidate for diagnosis instead of discarding it.
        failed_path = week_dir / "weekly_dialogue_story_only_v8_validation_failed.json"
        save_json(failed_path, result)
        print(f"[WARN] Saved validation-failed candidate: {failed_path}")
        raise

    save_json(week_dir / OUT_JSON_FILENAME, result)
    (week_dir / OUT_MD_FILENAME).write_text(build_markdown(result), encoding="utf-8")

    print(f"[OK] Wrote: {week_dir / OUT_JSON_FILENAME}")
    print(f"[OK] Wrote: {week_dir / OUT_MD_FILENAME}")
    print(f"[OK] Wrote: {week_dir / OUT_PROMPT_DEBUG_FILENAME}")


if __name__ == "__main__":
    main()
