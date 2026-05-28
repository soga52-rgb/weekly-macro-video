#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 82 Test v5 - Generate Formal Tom / Miranda Dialogue Script

Purpose:
- Test the narration / dialogue layer using the Step 80 analysis-layer output
  and optional Step 81 visual manifest.
- Read:
  output/weekly/YYYY-MM-DD/weekly_forest_summary_analysis_layer_test.json
  output/weekly/YYYY-MM-DD/analysis_layer_visual_test_images/visual_manifest.json optional
- Generate:
  output/weekly/YYYY-MM-DD/weekly_dialogue_script_analysis_layer_test.json
  output/weekly/YYYY-MM-DD/weekly_dialogue_script_analysis_layer_test.md

Core logic:
- Analysis JSON decides the dialogue scene count and order.
- Each scene is fed ONLY its corresponding analysis-process subsection as primary material.
- forest_summary is used only for the weekly main theme conclusion scene.
- visual_manifest only provides image_path mapping for scenes that already have images.
- Partial visual tests must NOT shrink the dialogue script into one scene.
- This script does NOT overwrite Step 94 official outputs.
- It does NOT generate audio files.
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
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DEFAULT_MODEL = "gemini-3.5-pro"

ANALYSIS_FILENAME = "weekly_forest_summary_analysis_layer_test.json"
VISUAL_MANIFEST_PATH = "analysis_layer_visual_test_images/visual_manifest.json"
WEEKLY_SOURCE_JSON_PATH = DATA_DIR / "weekly_video_source.json"
WEEKLY_SOURCE_TEXT_FILENAME = "weekly_source_text.md"
WEEKLY_MARKET_SERIES_FILENAME = "weekly_market_series.json"
OUT_JSON_FILENAME = "weekly_dialogue_script_analysis_layer_test.json"
OUT_MD_FILENAME = "weekly_dialogue_script_analysis_layer_test.md"


CANONICAL_ANALYSIS_SCENES = [
    {
        "analysis_key": "news_context",
        "scene_id": "scene_01_news_context",
        "scene_title": "新聞資訊與市場價格驗證",
        "also_use": ["market_validation"],
        "required_if_any": ["news_context", "market_validation"],
        "first_scene_rule": True,
        "role": "本幕只負責建立新聞與價格的初步脈絡，最後提出下一步要拆解的問題。",
    },
    {
        "analysis_key": "inflation_expectation_judgment",
        "scene_id": "scene_02_inflation_expectation",
        "scene_title": "通膨預期綜合研判",
        "role": "本幕只負責拆解通膨預期是否形成單一方向，並銜接到利率問題。",
    },
    {
        "analysis_key": "rate_driver_diagnosis",
        "scene_id": "scene_03_rate_driver",
        "scene_title": "利率驅動來源",
        "role": "本幕只負責拆解利率驅動來源，不擴到美元、亞幣、黃金。",
    },
    {
        "analysis_key": "dollar_gold_reaction",
        "scene_id": "scene_04_dollar_gold",
        "scene_title": "美元與黃金",
        "role": "本幕只負責說明美元與黃金如何承接利率背景，不擴到亞洲貨幣。",
    },
    {
        "analysis_key": "asia_fx_reaction",
        "scene_id": "scene_05_asia_fx",
        "scene_title": "亞洲貨幣：台、日、韓",
        "role": "本幕只負責分開說明台幣、日圓、韓圜，不把亞幣混成單一結論。",
    },
    {
        "analysis_key": "weekly_main_theme_conclusion",
        "scene_id": "scene_06_weekly_main_theme",
        "scene_title": "本週主線結論",
        "also_use": ["forest_summary"],
        "role": "本幕才可以收斂本週主線結論；前面各幕不得提前使用本週主線作為起點。",
    },
    {
        "analysis_key": "next_week_watch",
        "scene_id": "scene_07_next_week_watch",
        "scene_title": "下週觀察",
        "role": "本幕只負責根據已完成的分析列出下週觀察，不新增資料外主題。",
    },
]


SYSTEM_PROMPT = """
你是專業機構級總經影片編劇與台詞設計師，負責把 Step 80 已經分析好的「本週主線分析過程」，轉譯成 Tom（主持人）與 Miranda（首席總經策略師）可直接進 TTS 的正式雙人逐句對談稿。

本次是 Step 82 v7.3 測試版：
- 核心任務是先產出一支完整、可聽、順暢的 voice-first 總經故事。
- 圖片只是後續加強觀感，不是語音稿的主控。
- 資料來源是 scene_inputs，每一幕都有自己的 primary_material；同時可使用 Step 00 endpoint source_context_bundle 補強新聞脈絡、每日事件流、傳導鏈與市場驗證，並使用 market_series_context 補強各項市場數據的一週走勢語言。
- 不重新分析市場，不自由創作新聞，只把 Step 80 的分析推導過程故事化。
- 不產生音檔，只產生正式雙人逐句對談稿 JSON / MD。

最重要的主控規則：
- scene_inputs 是本次語音稿的 scene 主控清單。
- scene 數量、順序與 scene_id 必須嚴格依照 scene_inputs。
- 每個 scene 的主要素材必須以該 scene 的 primary_material 與 allowed_supporting_material 為主；source_context_bundle 只能補強故事脈絡、新聞事件流、傳導鏈、market snapshot、divergence、watchpoints，不可推翻 Step 80 分析層判斷；market_series_context 只能補強價格走勢與數據畫面，不可單獨推導新結論。
- forest_summary 只能在「本週主線結論」scene 使用；前面 scene 不得拿 forest_summary 回頭改寫。
- visual_manifest 只用來補充已生成圖片的 image_path，不可決定 scene 數量。
- 即使 visual_manifest 只有一張測試圖，也不得只產一段語音稿，更不得把後續所有分析塞進第一段。
- 若某個 scene 尚未生成圖片，visual_file 可填空字串或「待生成」，但仍必須產生該 scene 的語音稿。

━━━━━━━━━━━━━━━━━━━━
一、Voice-first / Story-first 定位
━━━━━━━━━━━━━━━━━━━━

這份腳本先為「耳朵」設計，再讓圖片輔助觀感。

語音稿即使沒有圖片，也必須讓聽眾聽得懂：
- 本週發生什麼事
- 市場原本在交易什麼
- 本週新增事件如何改變預期
- 價格如何驗證或抵銷這些預期
- 這一步分析後，下一步應該追問什麼

不要把 JSON 結論換句話說。
不要把圖卡短標籤逐字念出來。
不要讓 Tom 丟數字、Miranda 解釋數字。
數字只是證據，不是故事主體。

每段都要像一個總經分析師帶聽眾往前走：
新聞事件 → 預期變化 → 市場價格驗證 → 抵銷訊號 → 中間判斷 → 下一段 Hook。

━━━━━━━━━━━━━━━━━━━━
二、角色定位
━━━━━━━━━━━━━━━━━━━━

[Tom] 主持人：
- 代表具備基礎財經知識的觀眾。
- 有自己的觀察，不是提問機器。
- 負責開場、承接、追問、轉場。
- Tom 的問題要像「聽懂上一段後自然浮現的下一個問題」。
- Tom 不喊段落名稱，不說「接下來我們看某某章節」。
- Tom 要先把 Miranda 的上一段分析消化成一句觀察，再自然拋出下一題。
- Tom 可以指出反直覺、困惑、訊號不一致，但不能提前替 Miranda 下結論。
- Tom 不做買賣建議、不引導進出場、不使用「押注」、「可以進場」、「多看少做」、「投資朋友要注意」等操作式說法。

[Miranda] 首席總經策略師：
- 語氣接近機構策略會議，不是社群財經解說。
- 負責說明市場在交易什麼 narrative、預期怎麼改變、資金心理如何反應。
- 不乾念資料，也不用數據解釋數據。
- Miranda 要把新聞、政策訊號與價格反應串成總經傳導邏輯。
- Miranda 要保留不確定空間，不說市場一定會如何，不預測單一方向，不提供操作建議。
- Miranda 可以在段尾留伏筆，但不能提前把下一幕完整分析講完。

━━━━━━━━━━━━━━━━━━━━
三、總經傳導邏輯
━━━━━━━━━━━━━━━━━━━━

每一幕都不是資料摘要，而是分析推導的一步。

請依照以下邏輯轉成語音：
1. 事件或新聞來源：
   本段主要新聞、背景事件或市場現象是什麼。
2. 預期變化：
   它改變的是通膨預期、利率預期、美元利差、避險需求、成長擔憂、風險偏好，還是資金流向。
3. 市場價格驗證：
   用 primary_material 裡的油價、US10Y、30Y、DXY、黃金、台幣、日圓、韓圜等資料，檢查市場是否真的有反應。
4. 抵銷或訊號交錯：
   如果價格沒有照單一方向走，要說明是哪個因子抵銷或修正原本預期。
5. 中間判斷：
   本幕只產生本段的中間判斷，不提前講本週主線。
6. 下一步問題：
   根據本段中間判斷，自然帶出下一幕要分析的問題。

━━━━━━━━━━━━━━━━━━━━
四、Endpoint source_context_bundle 使用原則
━━━━━━━━━━━━━━━━━━━━

source_context_bundle 來自 Step 00 weekly_video_source endpoint，內容可能包含：
- daily_summaries：每日主線、Executive Summary、market_signals、macro_chain、divergence、market_snapshot、news_evidence、watchpoints
- weekly_source_text.md：由 endpoint 整理出的週報來源文字
- range / generated_at / data_status 等 metadata

使用方式：
1. source_context_bundle 是「故事與脈絡補強資料」，不是最終判斷來源。
2. 每一幕仍以 primary_material 的分析段落為主。
3. 當 primary_material 太濃縮時，可以從 source_context_bundle 補充：
   - 本週事件流
   - 多日反覆出現的訊號
   - 哪一天或哪則新聞造成轉折
   - 市場數據如何驗證
   - divergence / anomaly / watchpoints
4. 不要逐日照念 source_context_bundle。
5. 不要把 source_context_bundle 中與本幕無關的新聞塞入該幕。
6. 若 source_context_bundle 與 Step 80 分析層判斷不一致，以 Step 80 分析層為準。
7. 使用 source_context_bundle 的目的，是讓語音稿更像完整市場故事，而不是把摘要改寫成對話。

━━━━━━━━━━━━━━━━━━━━
五、Market series 價格走勢總經解讀原則
━━━━━━━━━━━━━━━━━━━━

market_series_context 來自 weekly_market_series.json，目的不是讓語音稿多念數字，也不是讓語音稿做技術分析，而是讓語音稿能解釋「價格為什麼這樣走」。

核心原則：
- 不要描述走勢，要解釋走勢。
- 走勢人人能看，解讀原因才是洞察。
- 每次提到市場數據，都必須完成「走勢 → 轉折原因 → 驗證 / 抵銷的總經判斷 → 對下一段分析的含義」。
- 如果只能說出「黃金呈現 V 型反轉」、「美元高位震盪」、「亞幣承壓」，但說不出為什麼，就不要使用這個走勢描述。
- 走勢型態名稱只能作為輔助語言，不能成為分析本身。

標準解讀鏈：
1. 當週數據怎麼走。
2. 哪一天、哪則新聞、哪個政策訊號或哪個市場事件造成轉折。
3. 這個走勢驗證或抵銷了哪個總經判斷。
4. 這對下一段分析代表什麼。

使用方式：
1. 不要把市場數據列成清單。
2. 每個 scene 只挑與本幕主題相關的市場變數。
3. 數據要服務於當前分析問題，用來建立價格畫面、驗證新聞訊號或說明背離。
4. 請優先使用「走勢型態 + 轉折原因 + 總經含義 + 下一步問題」的語言，而不是只講單一數值。
   走勢型態只是輔助語言，不是技術分析；不要為了套用名稱而硬分類。
   所有走勢語言都必須貼著當週實際數據變化解讀，必須由 market_series_context 的 start、end、high、low、trend_shape、points 或 daily_summaries 中的市場數據支撐。
   若資料不足以判斷走勢型態，不得自行命名型態；請改用「資料顯示為區間震盪」、「資料不足以判斷明確型態」等中性表述。
   每次使用走勢型態時，必須說明該走勢背後的事件脈絡或總經含義，例如：哪一天、哪則新聞、哪個政策訊號或哪個市場價格驗證造成轉折。
   不合格寫法：「黃金呈現 V 型反轉。」
   合格寫法：「黃金前段受高利率壓抑回落，但後段在房市疲軟與避險需求升溫後重新回升，這代表市場沒有單純交易利率，也在為成長與地緣風險買保護。」
5. 常用走勢語言包括：
   - 先漲後跌
   - 先跌後漲
   - 一路走高
   - 一路走低
   - 高位震盪
   - 低位震盪
   - 區間震盪
   - V 型反轉：先快速下跌，後快速反彈
   - 倒 V 型反轉：先快速上攻，後快速回落
   - L 型整理：急跌後低位橫盤，沒有明顯反彈
   - U 型修復：先下跌，底部整理後逐步回升
   - 階梯式走高：不是直線上漲，而是回檔後再創高
   - 階梯式走低：反彈無力，逐步下探
   - 高位盤整：維持在高檔區間，沒有明顯突破
   - 低位盤整：維持在低檔區間，反彈力道不足
   - 先受壓、後反彈
   - 先被利差支撐、後被成長擔憂抵銷
6. Tom 或 Miranda 每段都應自然帶入與本幕主題相關的價格走勢，但不可硬塞無關數據。
7. 每段最多聚焦 2～3 個市場變數，避免變成數字播報。
8. 如果 market_series_context 中有 high、low、start、end、direction、trend_shape、turning_point，請優先用它來說明「本週怎麼走」。
   但不要只唸 start / end / high / low；必須把它轉成「本週先怎麼走、後來怎麼變、為什麼變、這代表什麼」。
9. 如果只有日資料，請根據每日序列整理為口語走勢，且必須保留實際方向與事件脈絡，例如：
   - 「油價前段仍有地緣風險支撐，但後段因和平協議傳聞快速回落。」
   - 「十年期殖利率先上攻、後回落，但整週仍維持在高位，代表市場沒有完全放棄高利率定價。」
   - 「美元指數不是一路單邊走強，而是在利差支撐與成長擔憂之間高位震盪。」
   - 「黃金先受高利率壓抑，後因避險需求回升，顯示市場並非只交易利率，也在為不確定性買保護。」
10. 走勢解讀順序必須是：
   當週數據怎麼走 → 哪個事件或訊號造成轉折 → 這個走勢驗證或抵銷了什麼總經判斷 → 對下一段分析代表什麼。
11. 每個 scene 至少要有一處「價格走勢總經解讀」，但不可平均塞數字；只挑本幕最能支撐分析問題的 1～3 個變數。
12. Tom 可以用走勢提出疑問，Miranda 必須回答該走勢背後的總經原因；不要讓 Tom 和 Miranda 互相丟數字。
13. Miranda 的回答不能停在「資產上漲 / 下跌 / 震盪」，必須說明市場定價機制：是通膨預期、利差、期限溢價、避險需求、成長擔憂、資金流，還是政策訊號造成。

各 scene 的數據帶入方向：
- scene_01_news_context：用 WTI / Brent、US10Y / 30Y、DXY 建立本週價格畫面。
- scene_02_inflation_expectation：用 CPI / PPI 背景與 WTI / Brent 走勢說明通膨訊號為何不單一。
- scene_03_rate_driver：用 US10Y / 30Y 走勢說明利率高位震盪與期限溢價重估。
- scene_04_dollar_gold：用 DXY 與 Gold 走勢說明美元利差支撐與黃金避險需求如何同時存在。
- scene_05_asia_fx：用 USDTWD、USDJPY、USDKRW 走勢說明台、日、韓貨幣壓力差異。
- scene_06_weekly_main_theme：只用前面已講過的價格走勢收斂本週主線，不新增數據。
- scene_07_next_week_watch：只用 watchpoints 對應的市場變數作為後續觀察，不新增預測。

━━━━━━━━━━━━━━━━━━━━
六、Narrative Architecture
━━━━━━━━━━━━━━━━━━━━

每個 scene 只回答一個核心問題。
下一個 scene 的核心內容必須留到下一個 scene 才講。

請依 scene_inputs 的 scene_id 套用下列敘事邊界：

§1 scene_01_news_context｜新聞資訊與市場價格驗證
✅ 可談：
- 本週新聞大概內容
- 前期背景新聞
- 本週市場價格初步變化
- 油價下跌、利率維持高檔、美元/亞幣/黃金初步反應
❌ 不可深入：
- 完整通膨結論
- 完整利率驅動拆解
- 美元黃金完整分析
- 台日韓貨幣細節
- 本週主線總結
🔗 段尾 Hook：
油價下跌但利率沒有同步放鬆，通膨預期到底應該怎麼看？

§2 scene_02_inflation_expectation｜通膨預期綜合研判
✅ 可談：
- CPI / PPI 偏強
- 油價回落
- 能源端壓力修正
- 通膨預期是否形成單一方向
❌ 不可深入：
- Fed 利率驅動完整拆解
- 美元與黃金反應
- 亞洲貨幣
🔗 段尾 Hook：
如果通膨訊號沒有形成單一方向，為什麼利率仍維持高檔？

§3 scene_03_rate_driver｜利率驅動來源
✅ 可談：
- Fed 會議紀錄
- CPI / PPI 背景
- 長天期殖利率與期限溢價
- US10Y / 30Y 的市場驗證
- 房市疲軟作為成長擔憂或抵銷力量
❌ 不可深入：
- 美元與黃金完整反應
- 亞洲貨幣細節
- 下週觀察
🔗 段尾 Hook：
利率維持高檔，美元與黃金會如何被重新定價？

§4 scene_04_dollar_gold｜美元與黃金
✅ 可談：
- 美元利差優勢
- 美元高位震盪
- 黃金面臨高利率機會成本與避險需求
- 美元與黃金為何不一定同向
❌ 不可深入：
- 台幣、日圓、韓圜個別細節
- 下週風險清單
🔗 段尾 Hook：
強美元環境下，亞洲貨幣承受什麼壓力？

§5 scene_05_asia_fx｜亞洲貨幣：台、日、韓
✅ 可談：
- 台幣、日圓、韓圜各自壓力
- 利差、資金流、強美元、全球貿易與成長擔憂
❌ 不可深入：
- 下週具體事件預告
- 重新講完整通膨與利率段落
🔗 段尾 Hook：
這些資產反應合起來，本週主線到底是什麼？

§6 scene_06_weekly_main_theme｜本週主線結論
✅ 可談：
- 前面分析的收斂
- weekly_main_theme_conclusion
- forest_summary
- 本週主線如何由前面推導而來
❌ 不可新增：
- analysis 裡沒有的新新聞、新數字、新事件
🔗 段尾 Hook：
哪些變數是下週要驗證的關鍵？

§7 scene_07_next_week_watch｜下週觀察
✅ 可談：
- Fed 表態
- 美伊談判
- 亞洲貨幣抵抗力
- 其他 primary_material 裡列出的觀察事項
✅ 結尾：
由 Tom 自然收尾，感謝 Miranda，提醒持續追蹤數據與關鍵訊號，並說「我們下週見」。
❌ 不可：
- 新增投資建議
- 新增資料外觀察主題

━━━━━━━━━━━━━━━━━━━━
七、寫作準則
━━━━━━━━━━━━━━━━━━━━

- 每段先講市場 narrative，不要先報數字。
- 數字密度：每個 speaker_turn 不超過兩組具體數字；其餘用「高位震盪」「大幅回落」「承壓」「偏強」等定性詞。
- Tom 的轉場靠追問或感想，不靠章節標題。
- Miranda 的回答要說明市場為什麼這樣定價，不只是說資產怎麼變。
- 每段結尾由 Tom 拋出 Hook 問題，Miranda 在下一段自然接起。
- 不要使用「這一頁」「這張圖的功能是」「接下來我們進入某某章節」這類後設說明。
- 可以說「畫面上先看到的是...」，但要簡短。
- 不要喊段落名稱，例如不要說「現在進入通膨預期綜合研判」。
- 不要把所有資料平均攤開；每段要有一個主軸。
- 即使沒有圖片，也要讓語音稿有畫面感。

━━━━━━━━━━━━━━━━━━━━
八、語氣與合規邊界
━━━━━━━━━━━━━━━━━━━━

全片口吻：
- 台灣專業財經節目口語
- 清楚、有節奏、有洞察
- 保持冷靜與專業
- 不使用過度戲劇化或網路化詞彙

不確定性語氣：
- 「市場看起來像是...」
- 「資金似乎正在...」
- 「這可能意味著...」
- 「目前還需要後續數據驗證...」

投資建議邊界：
- 本節目只做總經事件、資產反應與市場定價邏輯說明。
- 不提供買賣建議、進出場判斷、報酬承諾或單一方向押注。

硬性避免詞：
- 不得使用「精神分裂」、「核彈級」、「尚方寶劍」、「崩盤」、「全面失守」、「躺平任人捶打」、「免死金牌」、「哀鴻遍野」等詞。
- 不要使用「拉扯」。
- 盡量避免「拉鋸」。
- 改用「分歧」、「抵銷」、「不同方向力量」、「訊號交錯」、「尚未形成單一方向」。

━━━━━━━━━━━━━━━━━━━━
九、對話節奏與結構
━━━━━━━━━━━━━━━━━━━━

1. 每個 scene 優先產生 4～7 個 speaker_turns，避免只用 Tom 一問、Miranda 一答就結束。
2. Tom 的單次發言不能過短。除最後簡短收尾外，Tom 每次 spoken_text 建議至少 25 個中文字。
3. 除最後收尾幕外，單一 speaker_turn 的 estimated_seconds 不宜超過 35 秒。
4. 如果 Miranda 分析超過 35 秒，必須拆成「Miranda 先解釋 → Tom 承接 / 追問 → Miranda 補充」。
5. 最後一幕必須由 Tom 收尾，形成節目完結感。
6. news_reference 必須跨幕一致。若某一幕使用前一幕的新聞因果作為解釋，該 turn 的 news_reference 必須補上該新聞線索。
7. subtitle_text 必須是精簡字幕，不超過 25 個中文字；不要直接複製完整 spoken_text。
8. visual_reference 必須指出本 turn 對應的圖上實際可見或應該可見元素、標籤、數字或 scene_id。若圖片尚未生成，填 scene_id 或「待生成」。
9. 每個 scene 請輸出 visual_brief，供後續圖片生成使用。
10. tts_notes 請固定包含 speaking_rate: 4.7，供後續 TTS 使用。
11. 嚴格輸出合法 JSON，不要 Markdown，不要多餘文字。
"""


USER_PROMPT_TEMPLATE = """
請根據下方 scene_inputs，產生正式 video_dialogue_script.json 測試版。

本次任務：
- 嚴格依照 scene_inputs 的場景數量與順序，為每一個 scene 產生一組正式雙人對談台詞。
- scene_inputs 已經把分析層拆成每幕各自的主要素材，是本次語音稿的主控清單。
- visual_manifest 只負責提供已生成圖檔的路徑與 scene 對應，不可用來減少 scene 數量。
- 若 visual_manifest 只有部分圖片，仍必須依 scene_inputs 完整產生所有 scene 的語音稿。
- 每個 scene 的主要事實來源是該 scene 的 primary_material。
- 可使用 source_context_bundle 補強新聞事件流、每日脈絡、傳導鏈、market snapshot、divergence 與 watchpoints，但不得推翻 primary_material。
- 可使用 market_series_context 補強每一幕的價格走勢語言；數據必須服務於本幕主題，不可變成數字清單。
- 每個 scene 必須明確產生 core_question、allowed_scope、do_not_expand、section_hook、visual_brief、market_data_to_show、price_action_interpretation。
- price_action_interpretation 必須說明本幕最重要的價格走勢如何驗證或抵銷總經判斷，不可只寫走勢型態名稱。
- allowed_supporting_material 只可用來輔助轉場或補充，不可喧賓奪主。
- forest_summary 只可在 scene_06_weekly_main_theme 使用。
- 不要把 forest_summary 或本週主線結論拿到前面 scene 當開頭。
- 請遵守 SYSTEM_PROMPT 中的角色定位、事實邊界、圖文對齊、語氣合規、對話節奏與 news_reference 規則。
- subtitle_text 必須是精簡字幕，不超過 25 個中文字；不要直接複製完整 spoken_text。
- visual_reference 必須指出本 turn 對應的圖上實際可見或應該可見物件、標籤、數字或 scene_id；如果圖片尚未生成，填 scene_id 或「待生成」。
- news_reference 必須列出本 turn 用到的新聞 / 政策 / 數據線索；沒有就填空陣列。
- estimated_seconds 請以中文 TTS 合理語速估算，單一 turn 原則上不超過 35 秒。

輸出 JSON 結構：

{
  "meta": {
    "source": "scene_inputs derived from weekly_forest_summary_analysis_layer_test.json + visual_manifest.json",
    "week_range": "",
    "script_type": "video_dialogue_script_test",
    "version_note": "Step 82 v7.3 test version: voice-first story script with narrative architecture"
  },
  "dialogue_structure": {
    "total_scenes": 0,
    "estimated_duration_minutes": "",
    "style_note": "",
    "scene_order_source": "scene_inputs"
  },
  "scene_dialogues": [
    {
      "scene_id": "",
      "scene_title": "",
      "visual_file": "",
      "scene_goal": "",
      "core_question": "",
      "allowed_scope": [],
      "do_not_expand": [],
      "section_hook": "",
      "visual_brief": "",
      "market_data_to_show": [],
      "price_action_interpretation": "",
      "scene_narrative_role": "主題導入 / 分析展開 / 小結提問 / 轉場",
      "speaker_turns": [
        {
          "turn_id": "s01_t01",
          "speaker": "Tom",
          "spoken_text": "",
          "subtitle_text": "",
          "visual_reference": "",
          "news_reference": [],
          "estimated_seconds": 0
        }
      ],
      "scene_transition": {
        "transition_question": "",
        "next_scene_hint": ""
      }
    }
  ],
  "full_script_plain_text": "",
  "tts_notes": {
    "voice_pair": "Tom / Miranda",
    "pace": "",
    "speaking_rate": 4.7,
    "avoid_terms": []
  }
}

scene_inputs：
{scene_inputs_json}

source_context_bundle：
{source_context_bundle_json}

market_series_context：
{market_series_context_json}
"""


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


def compact_json(data: Any, max_chars: int = 100000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（內容過長，已截斷；請只使用可見內容）"


def has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def build_visual_map(visual_manifest: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    visual_map: Dict[str, Dict[str, str]] = {}
    scenes = visual_manifest.get("scenes", [])
    if not isinstance(scenes, list):
        return visual_map

    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id", "")).strip()
        if not scene_id:
            continue
        visual_map[scene_id] = {
            "image_path": str(scene.get("image_path", "") or scene.get("visual_file", "") or ""),
            "title": str(scene.get("title", "") or scene.get("scene_title", "") or ""),
            "status": str(scene.get("status", "") or ""),
        }

    return visual_map


def extract_scene_material(
    analysis: Dict[str, Any],
    scene_def: Dict[str, Any],
    process: Dict[str, Any],
) -> Dict[str, Any]:
    analysis_key = scene_def["analysis_key"]
    material: Dict[str, Any] = {
        analysis_key: process.get(analysis_key, {}),
    }

    for extra_key in scene_def.get("also_use", []):
        if extra_key == "forest_summary":
            material["forest_summary"] = analysis.get("forest_summary", {})
        else:
            material[extra_key] = process.get(extra_key, {})

    return material


def build_scene_inputs(analysis: Dict[str, Any], visual_manifest: Dict[str, Any]) -> Dict[str, Any]:
    process = analysis.get("main_theme_analysis_process", {})
    if not isinstance(process, dict):
        process = {}

    evidence = analysis.get("evidence", {})
    visual_map = build_visual_map(visual_manifest)
    scene_inputs: List[Dict[str, Any]] = []

    for scene_def in CANONICAL_ANALYSIS_SCENES:
        required_keys = scene_def.get("required_if_any", [scene_def["analysis_key"]])
        if not any(has_content(process.get(key)) for key in required_keys):
            continue

        scene_id = scene_def["scene_id"]
        visual_info = visual_map.get(scene_id, {})
        primary_material = extract_scene_material(analysis, scene_def, process)

        allowed_supporting_material: Dict[str, Any] = {
            "evidence_scope": evidence,
        }

        # Only conclusion scene may receive forest_summary.
        if scene_def["analysis_key"] == "weekly_main_theme_conclusion":
            allowed_supporting_material["forest_summary"] = analysis.get("forest_summary", {})

        scene_inputs.append({
            "scene_id": scene_id,
            "scene_title": scene_def["scene_title"],
            "scene_role": scene_def.get("role", ""),
            "primary_material_keys": list(primary_material.keys()),
            "primary_material": primary_material,
            "allowed_supporting_material": allowed_supporting_material,
            "visual_file": visual_info.get("image_path", ""),
            "visual_status": visual_info.get("status", "not_generated") if visual_info else "not_generated",
            "visual_note": (
                "圖片已生成，可依圖卡短標籤作為視覺錨點。"
                if visual_info.get("image_path")
                else "圖片尚未生成，請以 scene_title 與 primary_material 作為語音錨點。"
            ),
        })

    # Preserve future analysis sections instead of silently dropping them.
    known_keys = set()
    for scene in scene_inputs:
        known_keys.update(scene.get("primary_material_keys", []))

    for key, value in process.items():
        if key in known_keys or not has_content(value):
            continue
        scene_index = len(scene_inputs) + 1
        safe_key = re.sub(r"[^a-z0-9_]+", "_", key.lower())
        scene_inputs.append({
            "scene_id": f"scene_{scene_index:02d}_{safe_key}",
            "scene_title": key,
            "scene_role": "新增分析段落，請根據 primary_material 轉成語音稿。",
            "primary_material_keys": [key],
            "primary_material": {key: value},
            "allowed_supporting_material": {"evidence_scope": evidence},
            "visual_file": "",
            "visual_status": "not_generated",
            "visual_note": "圖片尚未生成，請以 scene_title 與 primary_material 作為語音錨點。",
        })

    return {
        "source": "analysis_json.main_theme_analysis_process",
        "rule": "Each scene receives only its own analysis subsection as primary material. forest_summary is restricted to weekly_main_theme_conclusion.",
        "total_scenes": len(scene_inputs),
        "scenes": scene_inputs,
    }


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
    except json.JSONDecodeError as exc:
        preview = cleaned[:2000]
        raise ValueError(f"Unable to parse Gemini JSON. Error: {exc}. Preview: {preview}") from exc

    if not isinstance(obj, dict):
        raise ValueError("Gemini JSON root is not an object.")
    return obj


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
            "temperature": 0.25,
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
        raise RuntimeError(f"Gemini dialogue test HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini dialogue test URLError: {exc}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {api_response}") from exc

    return extract_json_from_text(text)



def shorten_text(text: str, max_chars: int = 12000) -> str:
    text = text or ""
    return text if len(text) <= max_chars else text[:max_chars] + "\n...（內容過長，已截斷）"


def slim_day_summary(day: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(day, dict):
        return {}

    keys = [
        "date",
        "headline",
        "executive_summary",
        "macro_chain",
        "divergence",
        "market_signals",
        "market_snapshot",
        "news_evidence",
        "watchpoints",
        "visual_note",
        "raw_daily_summary_package",
    ]

    slim: Dict[str, Any] = {}
    for key in keys:
        value = day.get(key)
        if not has_content(value):
            continue
        if isinstance(value, str):
            slim[key] = shorten_text(value, 3500)
        else:
            slim[key] = value

    return slim


def build_source_context_bundle(week_dir: Path) -> Dict[str, Any]:
    endpoint_json = load_json(WEEKLY_SOURCE_JSON_PATH, {})
    source_text_path = week_dir / WEEKLY_SOURCE_TEXT_FILENAME
    source_text = source_text_path.read_text(encoding="utf-8") if source_text_path.exists() else ""

    daily_summaries = endpoint_json.get("daily_summaries", []) if isinstance(endpoint_json, dict) else []
    slim_days = []
    if isinstance(daily_summaries, list):
        slim_days = [slim_day_summary(day) for day in daily_summaries if isinstance(day, dict)]

    context = {
        "source": "Step 00 weekly_video_source endpoint",
        "endpoint_json_available": bool(endpoint_json),
        "weekly_source_text_available": bool(source_text),
        "range": endpoint_json.get("range", {}) if isinstance(endpoint_json, dict) else {},
        "generated_at": endpoint_json.get("generated_at", "") if isinstance(endpoint_json, dict) else "",
        "data_status": endpoint_json.get("data_status", "") if isinstance(endpoint_json, dict) else "",
        "daily_summaries": slim_days,
        "weekly_source_text_excerpt": shorten_text(source_text, 60000),
        "usage_rule": (
            "Use this bundle only to enrich event flow, market narrative, transmission path, "
            "market validation, divergence and watchpoints. Step 80 scene primary_material remains the source of final judgment."
        ),
    }

    return context




def _try_float(value: Any):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def infer_trend_shape(values: List[float]) -> str:
    if len(values) < 2:
        return "資料不足"

    start = values[0]
    end = values[-1]
    high = max(values)
    low = min(values)
    high_i = values.index(high)
    low_i = values.index(low)

    scale = max(abs(start), abs(end), abs(high), abs(low), 1.0)
    tolerance = scale * 0.003
    range_width = high - low
    meaningful_range = range_width > scale * 0.01
    net = end - start

    diffs = [values[i + 1] - values[i] for i in range(len(values) - 1)]
    up_count = sum(1 for x in diffs if x > tolerance)
    down_count = sum(1 for x in diffs if x < -tolerance)

    if not meaningful_range:
        return "區間震盪"

    # V / inverted-V: turning point in the middle with visible recovery or pullback.
    if 0 < low_i < len(values) - 1:
        rebound = end - low
        drop = start - low
        if drop > range_width * 0.45 and rebound > range_width * 0.45:
            return "V型反轉"
        if drop > range_width * 0.45 and rebound <= range_width * 0.25:
            return "L型整理"
        if drop > range_width * 0.35 and rebound > range_width * 0.25:
            return "U型修復"

    if 0 < high_i < len(values) - 1:
        rise = high - start
        pullback = high - end
        if rise > range_width * 0.45 and pullback > range_width * 0.45:
            return "倒V型反轉"

    if up_count > 0 and down_count == 0:
        return "一路走高"
    if down_count > 0 and up_count == 0:
        return "一路走低"

    # Stair-step moves: net direction clear, but with pauses / counter moves.
    if net > tolerance and up_count >= down_count:
        return "階梯式走高"
    if net < -tolerance and down_count >= up_count:
        return "階梯式走低"

    if abs(net) <= tolerance:
        midpoint = (high + low) / 2
        return "高位盤整" if end >= midpoint else "低位盤整"

    return "高位震盪" if net > 0 else "低位震盪"

def summarize_series_points(points: List[Dict[str, Any]]) -> Dict[str, Any]:
    parsed = []
    for p in points:
        if not isinstance(p, dict):
            continue
        value = None
        for key in ["value", "close", "price", "rate", "level", "last"]:
            if key in p:
                value = _try_float(p.get(key))
                if value is not None:
                    break
        if value is None:
            continue
        parsed.append({
            "date": p.get("date") or p.get("time") or p.get("label") or "",
            "value": value,
        })

    values = [x["value"] for x in parsed]
    if not values:
        return {"points_available": 0}

    high = max(values)
    low = min(values)
    high_i = values.index(high)
    low_i = values.index(low)

    return {
        "points_available": len(values),
        "start": values[0],
        "end": values[-1],
        "high": high,
        "low": low,
        "high_date": parsed[high_i].get("date", ""),
        "low_date": parsed[low_i].get("date", ""),
        "trend_shape": infer_trend_shape(values),
        "turning_point_note": (
            f"high at {parsed[high_i].get('date', '')}" if high_i not in (0, len(values)-1)
            else f"low at {parsed[low_i].get('date', '')}" if low_i not in (0, len(values)-1)
            else ""
        ),
        "points": parsed[:14],
    }


def extract_market_series_summary(raw: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}

    if not isinstance(raw, dict):
        return {"available": False, "reason": "weekly_market_series.json is not an object"}

    # Common formats:
    # 1) {"series": [{"asset": "US10Y", "data": [...]}, ...]}
    # 2) {"US10Y": [...], "DXY": [...]}
    # 3) {"series": {"US10Y": [...]}}

    series_obj = raw.get("series", raw)
    items = []

    if isinstance(series_obj, list):
        for item in series_obj:
            if isinstance(item, dict):
                name = (
                    item.get("asset")
                    or item.get("symbol")
                    or item.get("name")
                    or item.get("ticker")
                    or item.get("label")
                )
                points = item.get("data") or item.get("points") or item.get("values") or item.get("series")
                if name and isinstance(points, list):
                    items.append((str(name), points))
    elif isinstance(series_obj, dict):
        for name, points in series_obj.items():
            if isinstance(points, list):
                items.append((str(name), points))
            elif isinstance(points, dict):
                nested = points.get("data") or points.get("points") or points.get("values") or points.get("series")
                if isinstance(nested, list):
                    items.append((str(name), nested))

    for name, points in items:
        summary[name] = summarize_series_points(points)

    return {
        "available": bool(summary),
        "source": "weekly_market_series.json",
        "assets": summary,
        "usage_rule": (
            "Use trend_shape/start/end/high/low to speak naturally about price movement. "
            "Do not list all numbers; convert them into trend-language tied to each scene topic."
        ),
    }


def build_market_series_context(week_dir: Path) -> Dict[str, Any]:
    path = week_dir / WEEKLY_MARKET_SERIES_FILENAME
    raw = load_json(path, {})
    context = extract_market_series_summary(raw)
    context["file_available"] = path.exists()
    context["file_path"] = str(path)
    return context



def build_prompt(week_dir: Path) -> str:
    analysis = load_json(week_dir / ANALYSIS_FILENAME, {})
    if not analysis:
        raise FileNotFoundError(f"Missing or empty analysis file: {week_dir / ANALYSIS_FILENAME}")

    visual_manifest = load_json(week_dir / VISUAL_MANIFEST_PATH, {})
    scene_inputs = build_scene_inputs(analysis, visual_manifest)
    source_context_bundle = build_source_context_bundle(week_dir)
    market_series_context = build_market_series_context(week_dir)

    print(f"[INFO] Scene input count: {scene_inputs.get('total_scenes', 0)}")
    print(f"[INFO] Endpoint source context available: {source_context_bundle.get('endpoint_json_available')}")
    print(f"[INFO] Weekly source text available: {source_context_bundle.get('weekly_source_text_available')}")
    print(f"[INFO] Weekly market series available: {market_series_context.get('file_available')} | parsed={market_series_context.get('available')}")
    for scene in scene_inputs.get("scenes", []):
        print(
            f"[INFO] Scene: {scene.get('scene_id')} | "
            f"keys={scene.get('primary_material_keys')} | "
            f"visual_status={scene.get('visual_status')} | "
            f"visual_file={scene.get('visual_file') or '(none)'}"
        )

    # Save prompt inputs for debugging, without requiring another API call to inspect.
    save_json(week_dir / "weekly_dialogue_scene_inputs_debug.json", scene_inputs)
    save_json(week_dir / "weekly_dialogue_source_context_debug.json", source_context_bundle)
    save_json(week_dir / "weekly_dialogue_market_series_context_debug.json", market_series_context)

    return USER_PROMPT_TEMPLATE.replace(
        "{scene_inputs_json}",
        compact_json(scene_inputs, max_chars=100000),
    ).replace(
        "{source_context_bundle_json}",
        compact_json(source_context_bundle, max_chars=90000),
    ).replace(
        "{market_series_context_json}",
        compact_json(market_series_context, max_chars=50000),
    )



BANNED_REPLACEMENTS = {
    "拉鋸戰": "訊號交錯狀態",
    "拉鋸": "訊號交錯",
    "多空交戰": "不同方向力量並存",
    "投資人現在必須": "後續需要",
    "投資人必須": "後續需要",
}


def replace_in_obj(obj: Any) -> Any:
    if isinstance(obj, str):
        text = obj
        for old, new in BANNED_REPLACEMENTS.items():
            text = text.replace(old, new)
        return text
    if isinstance(obj, list):
        return [replace_in_obj(x) for x in obj]
    if isinstance(obj, dict):
        return {k: replace_in_obj(v) for k, v in obj.items()}
    return obj





def ensure_price_action_interpretation_fields(result: Dict[str, Any]) -> None:
    scenes = result.get("scene_dialogues")
    if not isinstance(scenes, list):
        return
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        if "price_action_interpretation" not in scene:
            scene["price_action_interpretation"] = ""


def rebuild_full_script_plain_text(result: Dict[str, Any]) -> None:
    scenes = result.get("scene_dialogues")
    if not isinstance(scenes, list):
        return

    lines = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        turns = scene.get("speaker_turns")
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
    lines: List[str] = []
    meta = result.get("meta", {}) or {}
    lines.append("# Weekly Dialogue Script Analysis Layer Test")
    lines.append("")
    if meta.get("week_range"):
        lines.append(f"- Week: {meta.get('week_range')}")
    lines.append(f"- Type: {meta.get('script_type', 'video_dialogue_script_test')}")
    lines.append("")

    scenes = result.get("scene_dialogues") or result.get("scenes") or []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id", "")
        title = scene.get("scene_title", "")
        lines.append(f"## {scene_id}｜{title}".strip())

        visual_file = scene.get("visual_file", "")
        if visual_file:
            lines.append(f"**Visual file:** {visual_file}")
        goal = scene.get("scene_goal", "")
        if goal:
            lines.append(f"**Scene goal:** {goal}")
        if visual_file or goal:
            lines.append("")

        turns = scene.get("speaker_turns") or scene.get("dialogue") or []
        for item in turns:
            if not isinstance(item, dict):
                continue
            speaker = item.get("speaker", "")
            text = item.get("spoken_text") or item.get("line", "")
            subtitle = item.get("subtitle_text", "")
            visual_reference = item.get("visual_reference", "")
            news_reference = item.get("news_reference", [])
            estimated_seconds = item.get("estimated_seconds", "")

            if speaker or text:
                lines.append(f"**{speaker}：** {text}")
                if subtitle:
                    lines.append(f"  - 字幕：{subtitle}")
                if visual_reference:
                    lines.append(f"  - 視覺：{visual_reference}")
                if news_reference:
                    lines.append(f"  - 參考：{', '.join(map(str, news_reference))}")
                if estimated_seconds:
                    lines.append(f"  - 秒數：{estimated_seconds}")
                lines.append("")

        transition = scene.get("scene_transition", {})
        if isinstance(transition, dict):
            tq = transition.get("transition_question", "")
            nh = transition.get("next_scene_hint", "")
            if tq or nh:
                lines.append(f"_Transition: {tq} {nh}_".strip())
                lines.append("")
        elif isinstance(transition, str) and transition:
            lines.append(f"_Transition: {transition}_")
            lines.append("")

    full_text = result.get("full_script_plain_text", "")
    if full_text:
        lines.append("---")
        lines.append("")
        lines.append("## Full script plain text")
        lines.append("")
        lines.append(str(full_text))

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = (
        os.getenv("GEMINI_DIALOGUE_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or DEFAULT_MODEL
    )

    week_dir = resolve_week_dir(args.week_dir)

    print(f"[INFO] Step 82 dialogue script test model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Analysis input: {(week_dir / ANALYSIS_FILENAME).exists()}")
    print(f"[INFO] Visual manifest input: {(week_dir / VISUAL_MANIFEST_PATH).exists()}")

    user_prompt = build_prompt(week_dir)
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    result = replace_in_obj(result)
    ensure_price_action_interpretation_fields(result)
    rebuild_full_script_plain_text(result)

    out_json = week_dir / OUT_JSON_FILENAME
    save_json(out_json, result)
    print(f"[OK] Saved {out_json}")

    out_md = week_dir / OUT_MD_FILENAME
    save_text(out_md, build_markdown(result))
    print(f"[OK] Saved {out_md}")


if __name__ == "__main__":
    main()
