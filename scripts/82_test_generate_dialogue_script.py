#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 82 v8.1.1 - Story-only Dialogue Generator

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
Tom 是成熟的國際財經訪談主持人。他不是新聞播報員，也不是問答機器。
Tom 的工作是替聽眾打開問題：他先讓觀眾知道「為什麼這件事值得聽」，再用自然追問把故事推進。

Miranda 是機構級總經策略師。她不是念資料的人。
Miranda 的工作是解釋市場價格背後的定價邏輯：事件為什麼重要、價格怎麼反應、這個反應驗證或抵銷了什麼判斷、下一步會傳導到哪個變數。

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

建議故事推進方式：
- 先從本週最能形成故事的事件線切入，例如地緣政治、央行政策、長債壓力、房市疲軟、強美元或亞幣壓力。
- 用事件帶出價格反應，不要先報數字。
- 用價格反應解釋市場真正交易的是什麼。
- 如果價格走勢和直覺不同，要把它當作故事問題。
- 讓 Tom 問出這個問題，讓 Miranda 解釋。
- 每段結尾自然帶出下一個變數。

請產生 8 到 10 分鐘左右的中文雙人對談稿。
語氣：台灣專業財經節目口語，清楚、有節奏、有洞察，但不要浮誇。
不要投資建議，不要買賣指令。
請輸出合法 JSON，不要 Markdown，不要多餘文字。
"""


USER_PROMPT_TEMPLATE = """
請根據下方資料，產生 Step 82 v8.1 Story-only Tom / Miranda 總經訪談稿。

資料：
{input_bundle_json}

請輸出 JSON，結構如下：

{{
  "meta": {{
    "script_type": "story_only_dialogue_v8",
    "week_range": "",
    "estimated_duration_minutes": "8-10",
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
  "full_script_plain_text": "[Tom]: ...\\n[Miranda]: ..."
}}

生成要求：
- sections 數量由故事需要決定，建議 5 到 7 段，不要為了固定張數硬切。
- 每段至少 3 個 speaker_turns，重要段落可以更多。
- Tom 負責打開問題與承接，不要替 Miranda 下完整結論。
- Miranda 負責解釋事件、價格與總經傳導。
- 價格走勢必須服務故事，不要變成數字清單。
- 如果某個事件最後列為 next_week_watch，前面故事中必須已經鋪陳過。
- full_script_plain_text 必須由 speaker_turns 重新組成，保留 [Tom] / [Miranda] 標籤。
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
    rebuild_full_script(result)

    save_json(week_dir / OUT_JSON_FILENAME, result)
    (week_dir / OUT_MD_FILENAME).write_text(build_markdown(result), encoding="utf-8")

    print(f"[OK] Wrote: {week_dir / OUT_JSON_FILENAME}")
    print(f"[OK] Wrote: {week_dir / OUT_MD_FILENAME}")
    print(f"[OK] Wrote: {week_dir / OUT_PROMPT_DEBUG_FILENAME}")


if __name__ == "__main__":
    main()
