#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Forest Summary Slide Mode v1

Purpose:
- Generate weekly_forest_summary.json from:
  1) weekly_source_text.md
  2) weekly_news_context.md if available

Design:
- Do not force the model to search for divergence.
- Ask for a six-slide macro theme analysis.
- Require coherent story flow, consistent logic, and no invented data.
- Let the model determine the main story from daily summaries + weekly news context.

Input:
- output/weekly/YYYY-MM-DD/weekly_source_text.md
- output/weekly/YYYY-MM-DD/weekly_news_context.md optional

Output:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_MODEL, default: gemini-3.5-flash
  To test Gemini 3.1 Flash Lite, set:
  GEMINI_MODEL=gemini-3.1-flash-lite
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_MODEL = "gemini-3.5-flash"


SYSTEM_PROMPT = """
你是一位專業總經週報主編。

你要讀取最近 3～5 天的「今日總經摘要」，並結合一週新聞補充，整理成一份「六張投影片式」的總經主軸分析。
每日摘要是樹木，週報投影片是森林；新聞補充是校正層。

你的任務不是找最戲劇化的背離，也不是逐日整理，而是建立一條前後連貫、一致的市場故事線。

請做到：
1. 找出本週最重要的總經主軸。
2. 說明這條主軸如何從每日摘要與新聞補充中形成。
3. 分析主要市場變數之間的關係：通膨預期、利率、美元、亞洲貨幣、黃金、能源。
4. 若出現短暫分歧、修正訊號或待觀察因素，請自然放入故事線，不要刻意放大。
5. 六張投影片之間要前後連貫，像一支完整週報影片，而不是六段分散摘要。
6. 不要自行創造來源中沒有的數據、新聞或事件。
7. 若資料不足，請明確寫「資料不足，待觀察」。

語氣要求：
- 專業、清楚、克制。
- 像分析師週報，不像財經自媒體。
- 可以有判斷，但不能把推論說成事實。
- 若因果關係不是來源直接明示，請使用「可能」、「顯示」、「反映」、「待觀察」。
- 避免過度戲劇化詞彙，例如：狂歡、恐慌、崩潰、暴衝、徹底、全面轉向、導火線、迎來反撲。
請使用繁體中文。
"""


USER_PROMPT_TEMPLATE = """
以下有兩份來源：

A. weekly_source_text.md：
最近 3～5 天 Daily Summary Package，代表每日觀察。

B. weekly_news_context.md：
一週 Google News RSS 搜尋後，由 Gemini 整理的新聞補充，代表週報校正層。

請根據 A + B 產生 weekly_forest_summary.json。

重要規則：
1. 不要逐日照抄。
2. 不要把單日摘要直接串起來。
3. 不要預設一定要找出背離或脫鉤。
4. 請以「六張投影片式總經主軸分析」建立完整故事線。
5. 六張投影片必須前後連貫、一致，不能各自分散。
6. 若有短暫分歧或修正訊號，只需自然說明其在主線中的位置，不要將其升級為整週主軸。
7. 不要捏造來源中沒有的數字或新聞。
8. 若是推論，請明確寫「可能」、「顯示」、「反映」、「待觀察」。
9. 不要使用過度戲劇化語氣。
10. 週報結論要像分析師週報，不要像媒體標題。
11. image_card_brief 必須非常短，適合放入影片圖卡。
12. 只輸出合法 JSON，不要加 Markdown，不要加解釋文字。

請輸出以下 JSON 結構：

{
  "meta": {
    "source": "weekly_source_text.md + weekly_news_context.md",
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
  "video_planning": {
    "suggested_video_title": "",
    "six_scene_outline": [
      {
        "scene_id": "scene_01",
        "scene_title": "",
        "scene_question": "",
        "main_point": "",
        "visual_hint": ""
      },
      {
        "scene_id": "scene_02",
        "scene_title": "",
        "scene_question": "",
        "main_point": "",
        "visual_hint": ""
      },
      {
        "scene_id": "scene_03",
        "scene_title": "",
        "scene_question": "",
        "main_point": "",
        "visual_hint": ""
      },
      {
        "scene_id": "scene_04",
        "scene_title": "",
        "scene_question": "",
        "main_point": "",
        "visual_hint": ""
      },
      {
        "scene_id": "scene_05",
        "scene_title": "",
        "scene_question": "",
        "main_point": "",
        "visual_hint": ""
      },
      {
        "scene_id": "scene_06",
        "scene_title": "",
        "scene_question": "",
        "main_point": "",
        "visual_hint": ""
      }
    ],
    "image_card_brief": [
      {
        "card_id": "card_01",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      },
      {
        "card_id": "card_02",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      },
      {
        "card_id": "card_03",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      },
      {
        "card_id": "card_04",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      },
      {
        "card_id": "card_05",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      },
      {
        "card_id": "card_06",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      }
    ],
    "next_week_questions": []
  }
}

品質控制：
- suggested_video_title：專業、克制，不要驚嘆號，不要聳動。
- scene_title：不超過 16 字。
- scene_question：像主持人提問，但不要誇張。
- 六張 scene 必須形成一條故事線：開場主題 → 主要驅動 → 市場傳導 → 修正因素 → 下週觀察。
- 不必固定每張投影片名稱，請依來源內容自行安排。
- image_card_brief.headline：8～16 字，適合圖卡。
- image_card_brief.short_labels：每個 2～8 字。
- visual_concept：可描述圖像，但不要放太多可見文字。
- 如果資料不足，請寫「資料不足，待觀察」，不要硬補。

weekly_source_text.md：
{weekly_source_text}

weekly_news_context.md：
{weekly_news_context}
"""


def load_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract the first valid JSON object from Gemini output.

    Gemini Lite may occasionally return a valid JSON object followed by
    extra text or another partial object. Using rfind("}") can include
    that extra content and cause: JSONDecodeError: Extra data.
    """
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
        with urllib.request.urlopen(request, timeout=180) as response:
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    weekly_source_text = load_text(week_dir / "weekly_source_text.md")
    weekly_news_context = load_text(week_dir / "weekly_news_context.md")

    if not weekly_source_text:
        raise FileNotFoundError(f"Missing weekly_source_text.md in {week_dir}")

    if not weekly_news_context:
        weekly_news_context = "本週新聞補充尚未產生。請僅根據 weekly_source_text.md 產生，並在 insufficient_evidence 註明新聞校正層不足。"

    user_prompt = USER_PROMPT_TEMPLATE.replace(
        "{weekly_source_text}", weekly_source_text
    ).replace(
        "{weekly_news_context}", weekly_news_context
    )

    print(f"[INFO] Generating weekly forest summary with model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] News context included: {bool((week_dir / 'weekly_news_context.md').exists())}")

    forest_summary = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
