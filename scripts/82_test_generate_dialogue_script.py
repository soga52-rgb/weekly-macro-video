#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 82 Test - Generate Dialogue Script from Step 80 Analysis Layer

Purpose:
- Test the narration / dialogue layer using the Step 80 analysis-layer output.
- Read:
  output/weekly/YYYY-MM-DD/weekly_forest_summary_analysis_layer_test.json
  output/weekly/YYYY-MM-DD/analysis_layer_visual_test_images/visual_manifest.json optional
- Generate:
  output/weekly/YYYY-MM-DD/weekly_dialogue_script_analysis_layer_test.json
  output/weekly/YYYY-MM-DD/weekly_dialogue_script_analysis_layer_test.md

This script does NOT overwrite Step 94 official outputs.
It does NOT generate audio files.
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

DEFAULT_MODEL = "gemini-3.5-pro"

ANALYSIS_FILENAME = "weekly_forest_summary_analysis_layer_test.json"
VISUAL_MANIFEST_PATH = "analysis_layer_visual_test_images/visual_manifest.json"
OUT_JSON_FILENAME = "weekly_dialogue_script_analysis_layer_test.json"
OUT_MD_FILENAME = "weekly_dialogue_script_analysis_layer_test.md"


SYSTEM_PROMPT = """
你是專業機構級總經影片編劇與台詞設計師，負責把已完成的 Step 80 分析層結果，轉譯成 Tom（主持人）與 Miranda（首席總經策略師）可直接進入後續 TTS 的正式雙人逐句對談稿。

你的任務不是重新分析市場，而是把分析層內容轉成自然、清楚、有節奏的語音導讀。

角色定位：
- Tom：主持人，代表具備基礎財經知識的觀眾。他負責提出觀眾會問的問題、銜接畫面、控制節奏。
- Miranda：首席總經策略師，負責解釋新聞、數據、通膨、利率、美元、黃金與亞洲貨幣的因果關係。

核心規則：
- 不得重新判斷市場主線。
- 不得改寫 Step 80 分析層的主要因果。
- 不得新增輸入資料沒有的新聞、數字或事件。
- 視覺圖卡上的短標籤，只是畫面提示；語音稿要負責把短標籤補成觀眾聽得懂的脈絡。
- 不要照念 JSON 欄位名稱。
- 不要說「這一頁先不急著下結論」「這張圖的功能是」這種後設說明。
- 每一段都要像正式影片旁白，而不是工作說明。
- 請使用繁體中文。
- 請只輸出合法 JSON，不要 Markdown，不要解釋文字。
"""


USER_PROMPT_TEMPLATE = """
請根據以下 Step 80 分析層結果，產生 Tom / Miranda 雙人語音稿測試版。

輸入資料：
1. weekly_forest_summary_analysis_layer_test.json：已完成的分析層結果。
2. visual_manifest.json：若有提供，代表目前視覺層預計出現的圖卡順序。若未提供，請依分析層順序生成語音段落。

重要原則：
- 語音層只做轉譯，不重新分析。
- 每個 scene 的語音稿要對應一張圖卡或一個分析段落。
- 圖卡上只放短標籤，語音稿要補足背景、因果與銜接。
- 但是不要把後面段落的結論提前講完。
- 每段開頭要自然銜接上一段。
- 每段結尾要自然帶到下一段。
- 對話要正式、清楚、機構級，但不要太硬。
- Tom 不要過度裝傻；Miranda 不要長篇演講。
- 每句適合 TTS，避免過長句。
- 不要使用「拉扯」一詞，請改用「分歧」「抵銷」「不同方向力量」「訊號交錯」「尚未形成單一方向」。
- 不要輸出投資建議。

語音節奏：
- 每個 scene 建議 6～10 句對話。
- 每句盡量 15～35 個中文字。
- Tom 負責引導問題與轉場。
- Miranda 負責解釋分析重點。
- 若內容複雜，請拆成多句，不要塞成一大段。

請依照目前分析層骨架生成語音稿：
1. 新聞資訊 + 市場價格驗證
2. 通膨預期綜合研判
3. 利率驅動來源
4. 美元與黃金
5. 亞洲貨幣：台、日、韓
6. 本週主線結論
7. 下週觀察

第一段「新聞資訊 + 市場價格驗證」特別要求：
- 直接進入內容，不要說「這一頁先不急著下結論」。
- Tom 可說：「我們先看本週市場的三組關鍵訊號：通膨、利率，以及美元、亞幣與黃金。」
- Miranda 要把畫面上的 icon / 短標籤補成脈絡。
- 不要把完整通膨結論、完整利率結論提前講完。
- 這段只要建立新聞與價格的初步脈絡。

請輸出 JSON 結構如下：

{
  "meta": {
    "source": "weekly_forest_summary_analysis_layer_test.json",
    "week_range": "",
    "script_type": "Tom_Miranda_dialogue_test",
    "note": ""
  },
  "dialogue_structure": {
    "total_scenes": 0,
    "estimated_duration_minutes": "",
    "style_note": ""
  },
  "scenes": [
    {
      "scene_id": "",
      "scene_title": "",
      "visual_reference": "",
      "scene_goal": "",
      "dialogue": [
        {
          "speaker": "Tom",
          "line": ""
        },
        {
          "speaker": "Miranda",
          "line": ""
        }
      ],
      "transition_to_next": ""
    }
  ],
  "full_script_plain_text": "",
  "tts_notes": {
    "voice_pair": "Tom / Miranda",
    "pace": "",
    "avoid_terms": []
  }
}

Step 80 analysis JSON:
{analysis_json}

Visual manifest JSON:
{visual_manifest_json}
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


def compact_json(data: Any, max_chars: int = 60000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（內容過長，已截斷；請只使用可見內容）"


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


def build_prompt(week_dir: Path) -> str:
    analysis = load_json(week_dir / ANALYSIS_FILENAME, {})
    if not analysis:
        raise FileNotFoundError(f"Missing or empty analysis file: {week_dir / ANALYSIS_FILENAME}")

    visual_manifest = load_json(week_dir / VISUAL_MANIFEST_PATH, {})

    return USER_PROMPT_TEMPLATE.replace(
        "{analysis_json}",
        compact_json(analysis, max_chars=60000),
    ).replace(
        "{visual_manifest_json}",
        compact_json(visual_manifest, max_chars=12000),
    )


def build_markdown(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = result.get("meta", {}) or {}
    lines.append("# Weekly Dialogue Script Analysis Layer Test")
    lines.append("")
    if meta.get("week_range"):
        lines.append(f"- Week: {meta.get('week_range')}")
    lines.append(f"- Type: {meta.get('script_type', 'Tom_Miranda_dialogue_test')}")
    lines.append("")

    for scene in result.get("scenes", []) or []:
        if not isinstance(scene, dict):
            continue
        lines.append(f"## {scene.get('scene_id', '')}｜{scene.get('scene_title', '')}".strip())
        goal = scene.get("scene_goal", "")
        if goal:
            lines.append(f"**Scene goal:** {goal}")
            lines.append("")

        dialogue = scene.get("dialogue", []) or []
        for item in dialogue:
            if not isinstance(item, dict):
                continue
            speaker = item.get("speaker", "")
            line = item.get("line", "")
            if speaker or line:
                lines.append(f"**{speaker}：** {line}")
                lines.append("")

        transition = scene.get("transition_to_next", "")
        if transition:
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

    out_json = week_dir / OUT_JSON_FILENAME
    save_json(out_json, result)
    print(f"[OK] Saved {out_json}")

    out_md = week_dir / OUT_MD_FILENAME
    save_text(out_md, build_markdown(result))
    print(f"[OK] Saved {out_md}")


if __name__ == "__main__":
    main()
