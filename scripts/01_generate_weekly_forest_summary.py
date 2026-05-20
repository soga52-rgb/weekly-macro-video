#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Forest Summary
Generate weekly_forest_summary.json from weekly_source_text.md.

Input:
- output/weekly/YYYY-MM-DD/weekly_source_text.md

Output:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_MODEL, default: gemini-3.5-flash
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

你要讀取最近 3～5 天的「今日總經摘要」，不是逐日摘要，而是拉高視角，歸納成一份「本週森林視角」。
每日摘要是樹木，週報摘要是森林。

你的任務：
1. 找出本週真正主線。
2. 找出反覆出現的市場訊號。
3. 找出本週轉折點。
4. 判斷通膨預期 → 利率 → 美元 → 亞洲貨幣 / 黃金 的傳導鏈是否成立。
5. 找出哪些地方背離、哪些地方只是待觀察。
6. 給出下週最重要的驗證問題。

你不是要把每天內容重複整理，而是要做週報主編的判斷。
請使用繁體中文。
"""


USER_PROMPT_TEMPLATE = """
以下是 weekly_source_text.md，內容來自最近 3～5 天的 Daily Summary Package。

請根據這份來源文件產生 weekly_forest_summary.json。

重要規則：
1. 不要逐日照抄。
2. 不要把單日摘要直接串起來。
3. 要用「森林視角」歸納本週主線。
4. 要說清楚「延續」、「轉折」、「背離」、「待觀察」。
5. 若資料只有 3 天，也可以產生週報初版，但要在 data_status_note 說明資料仍為 partial。
6. 不要捏造來源中沒有的數字或新聞。
7. 若是推論，請明確寫「可能」、「顯示」、「待觀察」。
8. 只輸出合法 JSON，不要加 Markdown，不要加解釋文字。

請輸出以下 JSON 結構：

{
  "meta": {
    "source": "weekly_source_text.md",
    "data_status_note": "",
    "week_range": "",
    "days_observed": ""
  },
  "forest_summary": {
    "weekly_main_theme": "",
    "main_question": "",
    "one_sentence_verdict": "",
    "overall_verdict": "成立 / 部分成立 / 背離 / 待觀察",
    "narrative_arc": "",
    "why_it_matters": ""
  },
  "signal_evolution": {
    "repeated_signals": [],
    "strengthening_signals": [],
    "weakening_signals": [],
    "turning_points": [],
    "noise_or_one_day_signals": []
  },
  "macro_transmission": {
    "expected_chain": "通膨預期 → 利率 → 美元 → 亞洲貨幣 / 黃金",
    "confirmed_links": [],
    "broken_or_weakened_links": [],
    "key_divergences": [],
    "inflation_view": "",
    "rate_view": "",
    "dollar_fx_view": "",
    "gold_view": ""
  },
  "evidence": {
    "most_important_evidence": [],
    "insufficient_evidence": [],
    "watch_items_from_daily_summaries": []
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
      }
    ],
    "image_card_brief": [
      {
        "card_id": "card_01",
        "headline": "",
        "short_labels": [],
        "visual_concept": ""
      }
    ],
    "next_week_questions": []
  }
}

weekly_source_text.md：
{weekly_source_text}
"""


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
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
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response does not contain a valid JSON object.")

    return json.loads(cleaned[start:end + 1])


def call_gemini_json(system_prompt: str, user_prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "topP": 0.9,
            "responseMimeType": "application/json"
        }
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
    parser.add_argument("--source-name", type=str, default="weekly_source_text.md")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    source_path = week_dir / args.source_name
    weekly_source_text = load_text(source_path)

    user_prompt = USER_PROMPT_TEMPLATE.replace("{weekly_source_text}", weekly_source_text)

    print(f"[INFO] Generating weekly forest summary with model: {model}")
    print(f"[INFO] Source: {source_path}")

    forest_summary = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
