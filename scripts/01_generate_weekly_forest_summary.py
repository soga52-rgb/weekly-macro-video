#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Forest Summary v8.6 A-Test

Purpose:
- Generate weekly_forest_summary.json from the freshest primary inputs:
  1) weekly_market_series.json
  2) weekly_news_context.md / weekly_news_context.json if available

Design:
- Do not use weekly_source_text.md as the main analysis input.
- Let the model first read market data, then use news events to explain possible causes.
- Position the output as a live-news interview style macro explanation.
- Keep the existing weekly_forest_summary.json schema so downstream steps remain compatible.

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
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_ANALYSIS_MODEL = "gemini-3.5-pro"


SYSTEM_PROMPT = """
你是一位正在接受現場新聞採訪的總經學者。

你的任務是根據市場數據與新聞事件，幫一般觀眾理解本週市場發生什麼事。

請遵守以下原則：
1. 先看市場數據，再用新聞事件解釋可能原因。
2. 請用一般大眾聽得懂的語言回答。
3. 語氣像冷靜的總經學者接受新聞現場採訪，不要像投資老師喊盤。

請使用繁體中文。
"""


USER_PROMPT_TEMPLATE = """
以下是最近 7 天市場數據與新聞事件。

請像現場新聞採訪一樣，先指出本週最值得注意的矛盾、反差或關鍵變化，再說明：

1. 市場數據真正透露了什麼？
2. 新聞事件能否解釋這些變化？
3. 如果有矛盾，矛盾在哪裡？
4. 本週最合理的市場主線是什麼？
5. 下週一般觀眾應該看什麼？

請將你的判斷整理成 weekly_forest_summary.json。
只輸出合法 JSON，不要加 Markdown，不要加解釋文字。

JSON 結構請維持如下，欄位內容可依本週資料自由判斷，不需要硬湊固定故事線。
如果資料顯示市場分歧，請讓 JSON 反映「分歧、斷點、部分成立或待觀察」，不要寫成完整順暢的傳導鏈。

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


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Extract the first valid JSON object from Gemini output.
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

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

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

    out_path = week_dir / "weekly_forest_summary.json"
    save_json(out_path, forest_summary)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
