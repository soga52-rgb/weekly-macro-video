#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 82 v8.11.2.1 - Story-only Dialogue Generator

Purpose:
- Generate a complete Tom / Miranda macro dialogue story first.
- Do NOT use visual manifest or scene image mapping.
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
MARKET_SERIES_FILENAME = "weekly_market_series.json"
NEWS_CONTEXT_JSON_FILENAME = "weekly_news_context.json"
NEWS_CONTEXT_MD_FILENAME = "weekly_news_context.md"
SOURCE_TEXT_FILENAME = "weekly_source_text.md"
ENDPOINT_JSON_PATH = DATA_DIR / "weekly_video_source.json"

OUT_JSON_FILENAME = "weekly_dialogue_story_only_v8.json"
OUT_MD_FILENAME = "weekly_dialogue_story_only_v8.md"
OUT_PROMPT_DEBUG_FILENAME = "weekly_dialogue_story_only_v8_prompt_debug.txt"


SYSTEM_PROMPT = """
你是機構級總經影片的 showrunner、主筆與敘事導演。

你的任務不是把資料摘要改寫成對話，也不是替圖片寫旁白。
你的任務是用本週新聞事件與市場價格變化，寫出一支 Tom 與 Miranda 的完整總經訪談故事。

這一版是 Story-only：
- 不處理圖片。
- 不需要 visual_reference。
- 不需要 visual_brief。
- 不要依照圖卡數量切段。
- 先讓語音故事本身成立。

角色：
Tom 是成熟的國際財經訪談主持人。他不是新聞播報員，也不是單純的問答機器。
Tom 的工作是替聽眾打開問題：他擅長用敏銳的直覺指出市場矛盾，例如「油價跌了，為什麼利率不跌？」也擅長在聽完分析後，用生活化比喻或頓悟式短句幫聽眾提煉重點，例如「所以現在買黃金，不只是為了賺錢，而是為了買一份保險？」Tom 的語氣要自然、好奇、克制，但要能代表聽眾把反直覺的地方問清楚。

Miranda 是機構級總經策略師。她不是念資料的人。
Miranda 的工作是解釋市場價格背後的定價邏輯：事件為什麼重要、價格怎麼反應、這個反應驗證或抵銷了什麼判斷、下一步會傳導到哪個變數。她非常擅長把冷冰冰的宏觀數字落地，在解釋高利率、強美元、流動性壓力或避險需求時，會自然帶出實體經濟的微觀痛點，例如房貸凍結、企業融資成本上升、原物料進口壓力、外資撤離或央行外匯存底消耗。她也擅長指出央行、投資人或市場當下面臨的兩難困境，例如保匯率 vs 保外匯存底、打通膨 vs 救經濟、維持高利率 vs 實體經濟受傷。

核心寫作原則：
1. 這是一個故事，不是資料摘要。
2. 前後邏輯必須接得上：上一段留下的問題，下一段要接著回答。
3. 頭尾要呼應：開頭鋪陳過、尚未結束的事件線，必須自然變成下週觀察。
4. 不要裸講數字。每個價格走勢都要由事件、新聞或市場疑問帶出。
5. 每個重要變數都要判斷：它是上游傳導、本身驅動，還是兩者混合。
6. 每一段都是傳導節點，不是封閉主題。可以自然觸碰下一個變數，作為下一段伏筆。
7. 不要一開始就總結本週主線。先讓聽眾跟著事件與價格一步一步形成理解。
8. 本週主線應在後段自然收斂，不要在開頭提前講完。
9. 下週觀察不能突然出現，必須回扣前面已經鋪陳過的未解事件或價格線。
10. 全片最後必須有正式收尾，但正式收尾不能取代下週觀察段。最後一段必須分成兩步：
    - Miranda 先完整說明下週觀察，必須回扣本週已鋪陳的事件線，例如 Fed 表態、美伊談判、亞洲央行防禦等，最後用一句自然語把話交還給 Tom。
    - Tom 最後只做簡短正式收尾：回扣本集主線、感謝 Miranda、提醒觀眾下週持續追蹤，並自然說「我們下週見」。Tom 收尾不得再展開新的分析。
11. 不要為了進入下週觀察或正式收尾，而壓縮中間故事。每一條主要事件線都必須先完整展開「事件脈絡 → 價格反應 → 市場解讀 → Tom 追問 → Miranda 補充」之後，才能進入下一段或下週觀察。
12. 下週觀察與正式收尾只是故事的收束，不是替代主體分析的段落。不得因為要完成結尾格式，就縮短前面各 section 的推論、追問與價格解讀。
13. 主要事件線至少挑一個代表性價格走勢做「口語化走勢解讀」：不要只說價格到哪裡，要說它是快速回落、先上攻後回落、先受壓後反彈、高位震盪，或區間反覆，並解釋這代表市場在重新定價什麼。
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
  「如果油價已經回落，為什麼利率還沒放鬆？」
  「美元強勢如果不是完全來自利率，那是不是還有避險資金的需求？」
  「等一下，這聽起來有點反直覺。價格明明往一個方向走，為什麼市場結論卻沒有跟著轉向？」
- Miranda 的回答要像在解謎：先承認表面矛盾，再揭示背後的市場定價邏輯。
- Miranda 使用專業術語後，必須立刻補一句白話翻譯。尤其是：期限溢價、結構性通膨、利差優勢、避險溢價、上游傳導、流動性壓力。
  例如：「這就是期限溢價。白話說，就是投資人覺得長期不確定性變高，所以要求更高的補償。」
- 增加對話呼吸感：Miranda 不要連續講太久。如果單一 Miranda spoken_text 可能超過 35 秒，請拆成「Miranda 先解釋 → Tom 短句確認或追問 → Miranda 補充」。
- Tom 可以用短句幫聽眾消化，例如：「所以不是油價沒用，而是它被 Fed 的訊號抵銷了？」、「換句話說，市場不是不看通膨，而是看得更遠了？」
- 價格走勢要用口語描述，不要用技術分類詞當台詞主體。
- 可以使用「先被壓下去、後來又被買盤拉回」、「前段快速回落、後段低位整理」、「先上攻、後來被成長擔憂壓回」這類說法。
- 避免在 spoken_text 裡直接把「V 型反轉」、「倒 V 型」、「L 型整理」當成主要表述；如果需要使用，必須立刻用一句口語原因解釋。

價格走勢解讀範例：
不要寫成：「黃金呈現 V 型反轉，價格在 4480 到 4577 美元之間震盪。」
應該寫成：「黃金前段受高利率壓抑回落，但後段又因房市疲軟與避險需求升溫重新回升。這代表市場沒有單純交易利率，也在為成長放緩與地緣政治不確定性買保護。」

建議故事推進方式：
- 先從本週最能形成故事的事件線切入，例如地緣政治、央行政策、長債壓力、房市疲軟、強美元或亞幣壓力。
- 用事件帶出價格反應，不要先報數字。
- 用價格反應解釋市場真正交易的是什麼。
- 如果價格走勢和直覺不同，要把它當作故事問題。
- 讓 Tom 問出這個問題，讓 Miranda 解釋。
- 每段結尾自然帶出下一個變數。

請產生 10 到 12 分鐘左右的中文雙人對談稿。
語氣：台灣專業財經節目口語，清楚、有節奏、有洞察，但不要浮誇。
不要投資建議，不要買賣指令。
請輸出合法 JSON，不要 Markdown，不要多餘文字。
"""


USER_PROMPT_TEMPLATE = """
請根據下方資料，產生 Step 82 v8.11.2 Story-only Tom / Miranda 總經訪談稿。

資料：
{input_bundle_json}

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
      "driver_judgment": "上游傳導 / 本身驅動 / 混合",
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


def build_input_bundle(week_dir: Path) -> Dict[str, Any]:
    analysis = load_json(week_dir / ANALYSIS_FILENAME, {})
    market_series_raw = load_json(week_dir / MARKET_SERIES_FILENAME, {})
    news_context_json = load_json(week_dir / NEWS_CONTEXT_JSON_FILENAME, {})
    endpoint_json = load_json(ENDPOINT_JSON_PATH, {})

    return {
        "meta": {
            "week_dir": str(week_dir),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "input_files": {
                "analysis": str(week_dir / ANALYSIS_FILENAME),
                "weekly_market_series": str(week_dir / MARKET_SERIES_FILENAME),
                "weekly_news_context_json": str(week_dir / NEWS_CONTEXT_JSON_FILENAME),
                "weekly_news_context_md": str(week_dir / NEWS_CONTEXT_MD_FILENAME),
                "weekly_source_text": str(week_dir / SOURCE_TEXT_FILENAME),
                "endpoint_json": str(ENDPOINT_JSON_PATH),
            },
        },
        "analysis_layer": analysis,
        "market_series_summary": build_market_series_summary(market_series_raw),
        "market_series_raw_excerpt": compact_json(market_series_raw, 60000),
        "weekly_news_context_json": news_context_json,
        "weekly_news_context_md": read_text(week_dir / NEWS_CONTEXT_MD_FILENAME, 60000),
        "weekly_source_text": read_text(week_dir / SOURCE_TEXT_FILENAME, 90000),
        "endpoint_context_excerpt": compact_json(endpoint_json, 60000),
        "instruction_hint": "Select the strongest event threads and write a coherent macro story. Do not force all data into the script.",
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
            "temperature": 0.75,
            "topP": 0.95,
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
    user_prompt = USER_PROMPT_TEMPLATE.replace("{input_bundle_json}", compact_json(bundle, 170000))
    (week_dir / OUT_PROMPT_DEBUG_FILENAME).write_text(SYSTEM_PROMPT.strip() + "\n\n" + user_prompt.strip(), encoding="utf-8")

    print("[INFO] Generating story-only dialogue...")
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    ensure_closing_turn(result)
    rebuild_full_script(result)

    save_json(week_dir / OUT_JSON_FILENAME, result)
    (week_dir / OUT_MD_FILENAME).write_text(build_markdown(result), encoding="utf-8")

    print(f"[OK] Wrote: {week_dir / OUT_JSON_FILENAME}")
    print(f"[OK] Wrote: {week_dir / OUT_MD_FILENAME}")
    print(f"[OK] Wrote: {week_dir / OUT_PROMPT_DEBUG_FILENAME}")


if __name__ == "__main__":
    main()
