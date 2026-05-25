#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
94 Test Generate Video Dialogue Script - Pro Model
Input: output/weekly/YYYY-MM-DD/weekly_forest_summary.json
Output:
- video_dialogue_script.json
- video_dialogue_script.md
"""

import argparse
import json
import os
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_DIALOGUE_MODEL = "gemini-3.5-pro"

SYSTEM_PROMPT = """
你是專業總經影片腳本編輯，負責把 weekly_forest_summary.json 轉成 Tom / Miranda 雙人對談稿。

角色設定：
- Tom：主持人，負責開場、提問、轉場、替觀眾問出直覺問題。語氣自然，不做長篇分析。
- Miranda：總經策略師，負責深入淺出解釋市場邏輯、補少量新聞與數據、收斂判斷。

規則：
1. 不重新分析市場，只把 91 的分析與 92 的低文字分鏡轉成可配音對談。
2. 每個 scene 必須緊扣該 scene 的畫面主題，不要跨場景亂講。
3. 圖片上文字少，旁白要把原本字很多的說明慢慢講給觀眾聽。
4. 新聞與數據只作輔助，不要變成新聞朗讀。
5. 不給投資建議，不過度斷定，不把市場押注寫成官方已宣布。
6. 每一幕都要包含 Tom 與 Miranda。
7. subtitle_text 要比 spoken_text 短，適合畫面底部字幕。
8. 嚴格輸出合法 JSON。
9. 對談節奏可參考財經節目：Tom 像主持人一樣拋出觀眾會問的問題，Miranda 像首席總經策略師一樣拆解原因。
10. 語氣要自然、有拋接球感，但仍維持機構式總經導讀；避免過度 YouTuber 化、誇張形容或情緒化用語。
11. 不要使用「精神分裂」、「尚方寶劍」、「市場崩盤」、「全面失守」這類過度戲劇化詞彙。
"""

USER_PROMPT_TEMPLATE = """
請根據以下 weekly_forest_summary.json 產生 video_dialogue_script.json。

任務：
- 產出 Tom / Miranda 雙人對談稿。
- 每個 scene 對應一組 scene_dialogues。
- 必須依照 video_visual_scenes 的順序。
- 每個 scene 的對談必須符合 screen_title、single_message、on_screen_labels 與 visual_metaphor。
- narration_outline 是旁白骨架；macro_storyline 用來保持前後連貫；evidence 可補新聞或數據。
- Tom 提問 / 轉場；Miranda 解釋 / 補證據 / 收斂判斷。

輸出 JSON 結構：
{
  "meta": {
    "source": "weekly_forest_summary.json",
    "purpose": "Tom / Miranda dialogue script before TTS",
    "week_range": "",
    "scene_count": 0,
    "dialogue_model_note": ""
  },
  "title": "",
  "opening_hook": "",
  "speaker_profiles": {
    "Tom": {
      "display_name": "Tom",
      "role_label": "主持人",
      "voice_role": "male_host",
      "screen_position": "lower_left"
    },
    "Miranda": {
      "display_name": "Miranda",
      "role_label": "總經策略師",
      "voice_role": "female_strategist",
      "screen_position": "lower_left"
    }
  },
  "scene_dialogues": [
    {
      "scene_id": "scene_01",
      "scene_type": "",
      "screen_title": "",
      "single_message": "",
      "scene_goal": "",
      "speaker_turns": [
        {
          "turn_id": "scene_01_turn_01",
          "speaker": "Tom",
          "display_name": "Tom",
          "role_label": "主持人",
          "spoken_text": "",
          "subtitle_text": "",
          "speaker_label_text": "Tom｜主持人",
          "estimated_seconds": 0,
          "news_reference": [],
          "visual_reference": ""
        }
      ],
      "scene_summary": "",
      "avoid_saying": []
    }
  ],
  "tts_plan": {
    "voice_strategy": "Tom male host, Miranda female strategist",
    "needs_tts": true,
    "needs_speaker_label_overlay": true,
    "subtitle_mode": "turn_by_turn"
  },
  "quality_checks": {
    "scene_alignment_note": "",
    "continuity_note": "",
    "risk_control_note": ""
  }
}

長度控制：
- 每個 scene 3~5 個 speaker_turns。
- Tom 每次 1~2 句；Miranda 每次 2~3 句。
- 每個 scene 約 30~50 秒。
- 全片目標 4~6 分鐘。

語氣：
- 口語但不浮誇，像財經節目雙人對談，不像逐字念報告。
- Tom 要負責破題、提問、轉場，問題要像觀眾會自然產生的疑問。
- Miranda 要負責深入淺出，用少量新聞與數據補充說明，並保留不確定性。
- 可用「不能只看單一指標」、「市場其實在拉鋸」、「這裡關鍵不是...而是...」。
- 避免「崩盤」、「必然」、「全面失控」、「精神分裂」、「尚方寶劍」等過度戲劇化表述。
- 若提到 Fed 升息，請寫「市場重新納入升息風險」或「會議紀錄偏鷹」，不可寫成 Fed 已宣布升息。
- 每個 scene 嚴格對齊當前圖片主題，不要把下一幕內容提前講完。

weekly_forest_summary.json：
{weekly_forest_summary_json}
"""

def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]

def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)

def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")

def compact_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "meta": summary.get("meta", {}),
        "forest_summary": summary.get("forest_summary", {}),
        "common_judgment_funnel": summary.get("common_judgment_funnel", {}),
        "macro_storyline": summary.get("macro_storyline", {}),
        "macro_variables": summary.get("macro_variables", {}),
        "transmission_diagnosis": summary.get("transmission_diagnosis", {}),
        "video_visual_scenes": summary.get("video_visual_scenes", []),
        "narration_outline": summary.get("narration_outline", []),
        "evidence": summary.get("evidence", {}),
        "video_planning": summary.get("video_planning", {}),
    }

def build_user_prompt(summary: Dict[str, Any]) -> str:
    return USER_PROMPT_TEMPLATE.replace(
        "{weekly_forest_summary_json}",
        json.dumps(compact_summary(summary), ensure_ascii=False, indent=2),
    )

def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Gemini response does not contain a JSON object.")
    return json.loads(text[start:end + 1], strict=False)

def call_gemini_json(system_prompt: str, user_prompt: str, model: str, api_key: str, temperature: float) -> Dict[str, Any]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )
    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.9,
            "responseMimeType": "application/json",
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini dialogue HTTPError {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Gemini dialogue request failed or timed out: {exc}") from exc

    result = json.loads(raw)
    candidates = result.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates. Preview: {raw[:1200]}")
    parts = (candidates[0].get("content") or {}).get("parts") or []
    text = "".join(str(part.get("text", "")) for part in parts)
    if not text.strip():
        raise RuntimeError(f"Gemini returned empty text. Preview: {raw[:1200]}")
    return extract_json(text)

def estimate_seconds(text: str) -> int:
    return max(3, min(18, round(len(text or "") / 5.2)))

def normalize_dialogue(data: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    scenes = summary.get("video_visual_scenes") or []
    scene_count = len(scenes) if isinstance(scenes, list) else 0
    data.setdefault("meta", {})
    data["meta"].setdefault("source", "weekly_forest_summary.json")
    data["meta"].setdefault("purpose", "Tom / Miranda dialogue script before TTS")
    data["meta"].setdefault("week_range", (summary.get("meta") or {}).get("week_range", ""))
    data["meta"].setdefault("scene_count", scene_count)

    data.setdefault("speaker_profiles", {
        "Tom": {"display_name": "Tom", "role_label": "主持人", "voice_role": "male_host", "screen_position": "lower_left"},
        "Miranda": {"display_name": "Miranda", "role_label": "總經策略師", "voice_role": "female_strategist", "screen_position": "lower_left"},
    })

    for scene in data.get("scene_dialogues", []) or []:
        turns = scene.get("speaker_turns") or []
        for idx, turn in enumerate(turns, start=1):
            speaker = str(turn.get("speaker") or "Miranda").strip()
            if speaker not in {"Tom", "Miranda"}:
                speaker = "Miranda"
            role = "主持人" if speaker == "Tom" else "總經策略師"
            turn["speaker"] = speaker
            turn["display_name"] = speaker
            turn["role_label"] = role
            turn["speaker_label_text"] = f"{speaker}｜{role}"
            turn.setdefault("turn_id", f"{scene.get('scene_id', 'scene')}_turn_{idx:02d}")
            spoken = str(turn.get("spoken_text", ""))
            turn.setdefault("subtitle_text", spoken[:60])
            turn["estimated_seconds"] = int(turn.get("estimated_seconds") or estimate_seconds(spoken))
    data.setdefault("tts_plan", {
        "voice_strategy": "Tom male host, Miranda female strategist",
        "needs_tts": True,
        "needs_speaker_label_overlay": True,
        "subtitle_mode": "turn_by_turn",
    })
    return data

def build_markdown(data: Dict[str, Any]) -> str:
    lines: List[str] = []
    lines.append(f"# 影片雙人旁白稿｜{data.get('title', '')}")
    lines.append("")
    if data.get("opening_hook"):
        lines.append("## Opening Hook")
        lines.append("")
        lines.append(str(data.get("opening_hook", "")))
        lines.append("")
    for scene in data.get("scene_dialogues", []) or []:
        lines.append(f"## {scene.get('scene_id', '')}｜{scene.get('screen_title', '')}")
        lines.append("")
        if scene.get("single_message"):
            lines.append(f"畫面訊息：{scene.get('single_message')}")
            lines.append("")
        for turn in scene.get("speaker_turns", []) or []:
            speaker = turn.get("speaker", "")
            role = turn.get("role_label", "")
            spoken = turn.get("spoken_text", "")
            subtitle = turn.get("subtitle_text", "")
            lines.append(f"**[{speaker}｜{role}]** {spoken}")
            if subtitle:
                lines.append(f"> 字幕：{subtitle}")
            lines.append("")
        if scene.get("scene_summary"):
            lines.append(f"小結：{scene.get('scene_summary')}")
            lines.append("")
    return "\n".join(lines).strip() + "\n"

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_DIALOGUE_MODEL", DEFAULT_DIALOGUE_MODEL).strip() or DEFAULT_DIALOGUE_MODEL
    try:
        temperature = float(os.getenv("DIALOGUE_TEMPERATURE", "0.6").strip())
    except ValueError:
        temperature = 0.6

    if args.week_dir:
        week_dir = Path(args.week_dir)
        if not week_dir.exists() and not week_dir.is_absolute():
            candidate = OUTPUT_WEEKLY_DIR / args.week_dir
            if candidate.exists():
                week_dir = candidate
    else:
        week_dir = find_latest_week_dir()

    summary_path = week_dir / "weekly_forest_summary.json"
    summary = load_json(summary_path, {})
    if not summary:
        raise FileNotFoundError(f"Missing or empty weekly_forest_summary.json: {summary_path}")

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Dialogue model: {model}")
    print(f"[INFO] Dialogue temperature: {temperature}")

    data = call_gemini_json(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=build_user_prompt(summary),
        model=model,
        api_key=api_key,
        temperature=temperature,
    )
    data = normalize_dialogue(data, summary)

    json_path = week_dir / "video_dialogue_script.json"
    md_path = week_dir / "video_dialogue_script.md"
    save_json(json_path, data)
    save_text(md_path, build_markdown(data))

    print(f"[OK] Created {json_path}")
    print(f"[OK] Created {md_path}")

if __name__ == "__main__":
    main()
