#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V2 - Step 02
Generate AI-driven weekly_video_scene_ai.json from weekly_facts.json.

Input:
- output/weekly/YYYY-MM-DD/weekly_facts.json
- prompts/weekly_story_prompt_v1.txt

Output:
- output/weekly/YYYY-MM-DD/weekly_video_scene_ai.json

Required GitHub Secret:
- GEMINI_API_KEY
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
PROMPT_PATH = ROOT_DIR / "prompts" / "weekly_story_prompt_v1.txt"

DEFAULT_MODEL = "gemini-3.1-flash-lite"

DEFAULT_SYSTEM_PROMPT = """
你是一位總經分析編輯，負責將每週市場數據、新聞事件與資產走勢整理成一支 6～8 分鐘的繁體中文總經週報影片。

你的任務不是寫新聞摘要，而是建立一條有邏輯的總經傳導分析：

本週主要資產走勢
→ 本週經濟數據與事件
→ 通膨預期方向
→ 利率走勢與原因
→ 美元、亞洲貨幣與黃金反應
→ 本週總經傳導是否成立

影片必須使用「問題轉場」方式串聯。每一段都要先提出一個問題，回答該問題，並在結尾拋出下一段問題。
""".strip()

DEFAULT_USER_PROMPT_TEMPLATE = """
以下是本週資料包 weekly_facts.json。請根據資料產生一份 weekly_video_scene.json。

請嚴格遵守以下規則：

1. 不得捏造未提供的數字。
2. 不得改寫資產實際方向。
3. 若資料不足，請明確寫「資料不足，暫不判斷」。
4. 必須使用繁體中文。
5. 影片要有上下段串聯，不可寫成 6 段彼此獨立的摘要。
6. 每段都要包含：
   - opening_question
   - answer_summary
   - card_bullets
   - transition_question
   - narration.script
7. 旁白語氣要像專業但容易理解的總經分析影片。
8. 每段旁白約 60～90 秒。
9. 分析順序必須固定如下：
   Scene 01：本週主要資產走勢路徑
   Scene 02：本週經濟數據與事件
   Scene 03：通膨預期方向
   Scene 04：利率走勢與原因拆解
   Scene 05：美元、亞洲貨幣與黃金反應
   Scene 06：本週總經傳導判斷

固定問題轉場骨架如下：

Scene 01 opening_question：
本週主要市場價格到底怎麼走？

Scene 01 transition_question：
但價格只是結果，真正的問題是：本週有哪些數據與事件推動了這些走勢？

Scene 02 opening_question：
本週有哪些經濟數據與事件，值得放進總經邏輯裡？

Scene 02 transition_question：
這些事件不一定都指向同一方向，所以接下來要問的是：它們合起來，究竟是在推升通膨預期，還是在壓低通膨預期？

Scene 03 opening_question：
本週通膨預期是升溫、降溫，還是呈現分歧？

Scene 03 transition_question：
如果通膨預期已經出現變化，下一個問題就是：利率有沒有跟著反應？還是利率其實受到其他因素影響？

Scene 04 opening_question：
本週利率變化，是通膨驅動，還是其他因素驅動？

Scene 04 transition_question：
利率是美元的重要支撐，但市場真的有照這個邏輯走嗎？接下來要看美元、亞洲貨幣與黃金的反應。

Scene 05 opening_question：
美元、亞洲貨幣與黃金，有沒有符合利率與避險邏輯？

Scene 05 transition_question：
把這些變數串起來後，最後要回答的問題是：本週的總經傳導鏈，到底是成立、部分成立，還是出現背離？

Scene 06 opening_question：
本週總經傳導邏輯是否成立？

Scene 06 transition_question：
下週最重要的，不是單看某一個數字，而是驗證這條傳導鏈是否延續。

請輸出合法 JSON，不要加 Markdown，不要加解釋文字。

輸出格式如下：

{
  "video_meta": {
    "week_start": "",
    "week_end": "",
    "week_label": "",
    "video_title": "Weekly Macro Expectation Check",
    "language": "zh-TW",
    "target_duration_sec": 420
  },
  "macro_summary": {
    "main_theme": "",
    "inflation_expectation_direction": "",
    "rate_driver_summary": "",
    "dollar_logic_summary": "",
    "asset_reaction_summary": "",
    "transmission_verdict": ""
  },
  "scenes": [
    {
      "scene_id": "scene_01",
      "scene_order": 1,
      "card_title": "本週主要資產走勢路徑",
      "opening_question": "本週主要市場價格到底怎麼走？",
      "answer_summary": "",
      "card_bullets": [],
      "transition_question": "但價格只是結果，真正的問題是：本週有哪些數據與事件推動了這些走勢？",
      "narration": {
        "script": ""
      }
    },
    {
      "scene_id": "scene_02",
      "scene_order": 2,
      "card_title": "本週經濟數據與事件",
      "opening_question": "本週有哪些經濟數據與事件，值得放進總經邏輯裡？",
      "answer_summary": "",
      "card_bullets": [],
      "transition_question": "這些事件不一定都指向同一方向，所以接下來要問的是：它們合起來，究竟是在推升通膨預期，還是在壓低通膨預期？",
      "narration": {
        "script": ""
      }
    },
    {
      "scene_id": "scene_03",
      "scene_order": 3,
      "card_title": "通膨預期方向",
      "opening_question": "本週通膨預期是升溫、降溫，還是呈現分歧？",
      "answer_summary": "",
      "card_bullets": [],
      "transition_question": "如果通膨預期已經出現變化，下一個問題就是：利率有沒有跟著反應？還是利率其實受到其他因素影響？",
      "narration": {
        "script": ""
      }
    },
    {
      "scene_id": "scene_04",
      "scene_order": 4,
      "card_title": "利率走勢與原因拆解",
      "opening_question": "本週利率變化，是通膨驅動，還是其他因素驅動？",
      "answer_summary": "",
      "card_bullets": [],
      "transition_question": "利率是美元的重要支撐，但市場真的有照這個邏輯走嗎？接下來要看美元、亞洲貨幣與黃金的反應。",
      "narration": {
        "script": ""
      }
    },
    {
      "scene_id": "scene_05",
      "scene_order": 5,
      "card_title": "美元、亞洲貨幣與黃金反應",
      "opening_question": "美元、亞洲貨幣與黃金，有沒有符合利率與避險邏輯？",
      "answer_summary": "",
      "card_bullets": [],
      "transition_question": "把這些變數串起來後，最後要回答的問題是：本週的總經傳導鏈，到底是成立、部分成立，還是出現背離？",
      "narration": {
        "script": ""
      }
    },
    {
      "scene_id": "scene_06",
      "scene_order": 6,
      "card_title": "本週總經傳導判斷",
      "opening_question": "本週總經傳導邏輯是否成立？",
      "answer_summary": "",
      "card_bullets": [],
      "transition_question": "下週最重要的，不是單看某一個數字，而是驗證這條傳導鏈是否延續。",
      "narration": {
        "script": ""
      }
    }
  ]
}

weekly_facts.json：
{weekly_facts_json}
""".strip()


def load_text(path: Path) -> str:
    if not path.exists():
        print(f"[WARN] Prompt file not found: {path}. Using built-in prompt.")
        return ""
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
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


def extract_prompt_sections(prompt_template: str) -> Tuple[str, str]:
    if not prompt_template.strip():
        return DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT_TEMPLATE

    system_match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', prompt_template, re.DOTALL)
    user_match = re.search(r'USER_PROMPT_TEMPLATE\s*=\s*"""(.*?)"""', prompt_template, re.DOTALL)

    if system_match and user_match:
        return system_match.group(1).strip(), user_match.group(1).strip()

    print("[WARN] Prompt file format not recognized. Using built-in prompt template.")
    return DEFAULT_SYSTEM_PROMPT, DEFAULT_USER_PROMPT_TEMPLATE


def extract_json_from_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI response does not contain a valid JSON object.")

    json_text = cleaned[start : end + 1]
    return json.loads(json_text)


def call_gemini(system_prompt: str, user_prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

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

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini API URLError: {exc}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini API response: {api_response}") from exc

    return extract_json_from_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="", help="Optional weekly output folder, e.g. output/weekly/2026-05-21")
    parser.add_argument("--output-name", type=str, default="weekly_video_scene_ai.json")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY. Add it as a GitHub Actions secret.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    facts_path = week_dir / "weekly_facts.json"

    weekly_facts = load_json(facts_path)
    prompt_template = load_text(PROMPT_PATH)
    system_prompt, user_prompt_template = extract_prompt_sections(prompt_template)

    weekly_facts_json = json.dumps(weekly_facts, ensure_ascii=False, indent=2)
    user_prompt = user_prompt_template.replace("{weekly_facts_json}", weekly_facts_json)

    print(f"[INFO] Using Gemini model: {model}")
    print(f"[INFO] Reading facts: {facts_path}")

    ai_scene = call_gemini(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        api_key=api_key,
    )

    output_path = week_dir / args.output_name
    save_json(output_path, ai_scene)

    print(f"[OK] AI weekly video scene JSON created: {output_path}")


if __name__ == "__main__":
    main()
