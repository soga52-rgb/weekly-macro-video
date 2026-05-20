#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 05
Generate AI narration summary + six full narration scripts.

Purpose:
- Do NOT use the short image-card brief as the whole script.
- Use weekly_facts.json as the detailed source.
- Use weekly_video_brief.json only as the visual/headline guide.
- Produce a 6~8 minute analysis-style narration, not a card-reading script.
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
DEFAULT_MODEL = "gemini-3.1-flash-lite-preview"

SYSTEM_PROMPT = """
你是一位專業總經分析影片主持人與腳本主編。

你要把週報資料寫成 6～8 分鐘的繁體中文解說影片旁白。
請注意：圖片只是輔助視覺，不是逐字朗讀對象。
你的任務不是描述圖片，而是用圖片作為提示，講出本週真正的總經主線、資料是否符合預期、傳導鏈成立或背離的原因。

風格：
- 像知識型 YouTube / NotebookLM 影片導讀
- 專業但口語
- 有問題推進
- 有轉折、有判斷、有結論
- 不要像財經報告照稿唸
- 不要像投資建議
"""

USER_PROMPT_TEMPLATE = """
以下有兩份資料：

1. weekly_facts.json：
完整資料來源，包含市場路徑、事件、通膨因素、利率因素、資產反應。
這是旁白分析的主要依據。

2. weekly_video_brief.json：
給圖卡與 image model 用的短版內容。
這只作為影片視覺與主線參考，不可直接照念。

請根據這兩份資料，輸出：
A. weekly_narration_summary
B. 六段 narration scripts

重要要求：
1. 影片總長目標 6～8 分鐘。
2. 每段約 65～85 秒。
3. 每段 script 約 320～460 個中文字。
4. 不要描述圖片上有什麼。
5. 不要照念圖卡文字。
6. 要補充「為什麼」與「是否符合預期」。
7. 要明確說出傳導鏈：通膨預期 → 利率 → 美元 → 亞洲貨幣 / 黃金。
8. 必須說明本週哪些地方成立、哪些地方背離或待觀察。
9. 若資料不足，明確說「資料不足，暫不判斷」，不要亂補新聞。
10. 使用繁體中文。
11. 只輸出合法 JSON，不要加 Markdown。

六段內容安排：

Scene 01｜開場主線
- 不要只說標題。
- 先抓本週最大市場問題。
- 要說明為什麼這週值得看。
- 結尾引出「先看數據與價格怎麼走」。

Scene 02｜本週市場訊號與數據路徑
- 說明主要資產本週怎麼走。
- 判斷是一路走升、先高後低、震盪、還是分歧。
- 說出這些走勢初步看起來符合什麼邏輯。
- 結尾引出「這些訊號如何影響通膨預期」。

Scene 03｜通膨預期
- 說明推升通膨預期的因素。
- 說明壓低或限制通膨預期的因素。
- 判斷通膨預期是升溫、降溫、還是分歧。
- 結尾引出「利率是否跟著通膨邏輯走」。

Scene 04｜利率與 Fed / 債市因素
- 說明利率走勢是否只由通膨驅動。
- 拆解 Fed、經濟韌性、債市供需、避險需求等非通膨因素。
- 判斷利率走勢符合預期、部分符合、還是背離。
- 結尾引出「美元與亞洲貨幣是否跟著利率反應」。

Scene 05｜美元、亞洲貨幣、黃金
- 說明美元走勢是否符合利率邏輯。
- 說明亞洲貨幣是否承壓。
- 說明黃金是否出現背離，若黃金走強，要解釋避險或風險需求。
- 結尾引出「整條傳導鏈是否成立」。

Scene 06｜總經傳導判斷與下週觀察
- 給出本週傳導鏈 verdict：成立 / 部分成立 / 背離 / 待觀察。
- 明確說出原因。
- 給 3 個下週觀察重點。
- 結尾要像影片收束，不要像報告結論。

請輸出 JSON 結構：

{
  "weekly_narration_summary": {
    "main_question": "",
    "main_theme": "",
    "expected_chain": "",
    "actual_market_path": "",
    "inflation_view": "",
    "rate_view": "",
    "fx_gold_view": "",
    "verdict": "",
    "key_tensions": ["", "", ""],
    "next_week_focus": ["", "", ""]
  },
  "scenes": [
    {
      "scene_id": "scene_01",
      "title": "",
      "role": "",
      "script": ""
    }
  ]
}

weekly_facts.json:
{weekly_facts_json}

weekly_video_brief.json:
{weekly_video_brief_json}
"""

def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path: Path, data: Dict[str, Any]) -> None:
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

def extract_json_from_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response does not contain valid JSON.")
    return json.loads(cleaned[start:end + 1])

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
        "generationConfig": {"temperature": 0.35, "topP": 0.9, "responseMimeType": "application/json"}
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
        raise RuntimeError(f"Gemini narration HTTPError {exc.code}: {detail}") from exc
    api_response = json.loads(raw)
    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {api_response}") from exc
    return extract_json_from_text(text)

def normalize_scenes(data: Dict[str, Any]) -> List[Dict[str, str]]:
    scenes = data.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("No scenes returned by Gemini.")
    output = []
    for idx, scene in enumerate(scenes[:6], start=1):
        output.append({
            "scene_id": scene.get("scene_id") or f"scene_{idx:02d}",
            "title": scene.get("title") or f"Scene {idx}",
            "role": scene.get("role") or "",
            "script": scene.get("script") or "",
        })
    if len(output) < 6:
        raise ValueError(f"Expected 6 scenes, got {len(output)}")
    return output

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    facts = load_json(week_dir / "weekly_facts.json")
    brief = load_json(week_dir / "weekly_video_brief.json")
    user_prompt = USER_PROMPT_TEMPLATE.replace(
        "{weekly_facts_json}", json.dumps(facts, ensure_ascii=False, indent=2)
    ).replace(
        "{weekly_video_brief_json}", json.dumps(brief, ensure_ascii=False, indent=2)
    )
    print(f"[INFO] Generating AI narration with model: {model}")
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)
    summary = result.get("weekly_narration_summary", {})
    scenes = normalize_scenes(result)
    save_json(week_dir / "weekly_narration_summary.json", summary)
    save_json(week_dir / "weekly_narration.json", {
        "source_facts": str(week_dir / "weekly_facts.json"),
        "source_brief": str(week_dir / "weekly_video_brief.json"),
        "style": "ai_analysis_narration_v1",
        "scenes": scenes,
    })
    out_dir = week_dir / "narration"
    out_dir.mkdir(parents=True, exist_ok=True)
    for idx, scene in enumerate(scenes, start=1):
        path = out_dir / f"scene_{idx:02d}.txt"
        save_text(path, scene["script"])
        print(f"[OK] Created {path}")
    print(f"[OK] Created {week_dir / 'weekly_narration_summary.json'}")
    print(f"[OK] Created {week_dir / 'weekly_narration.json'}")

if __name__ == "__main__":
    main()
