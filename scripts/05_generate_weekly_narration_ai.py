#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 05
Generate 6-scene weekly macro narration with Gemini.
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
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "y"}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def compact_json(data: Any, limit: int) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    return text if len(text) <= limit else text[:limit] + "\n...（內容過長，已截斷）"


def extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise
        return json.loads(match.group(0))


def call_gemini(prompt: str, model: str, api_key: str) -> str:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.35,
            "responseMimeType": "application/json",
        },
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=240) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTPError {exc.code}: {detail}") from exc

    data = json.loads(raw)
    parts = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise RuntimeError(f"Empty Gemini output. Preview: {raw[:1000]}")
    return text


def build_prompt(forest: Dict[str, Any], news: Dict[str, Any], market: Dict[str, Any]) -> str:
    return f"""
你是一位專業總經週報影片主編與旁白撰稿人。

任務：
根據 weekly_forest_summary、weekly_news_context、weekly_market_series，
產生一支 6～8 分鐘「週報影片」旁白稿。

定位：
每日總經摘要是「樹木」，週報影片是「森林」。
影片不是逐日整理，不是唸網頁，也不是解釋圖片怎麼生成。
影片要像總經分析師導讀週報：先講本週主線，再講傳導，再用數據與新聞驗證，最後提出下週觀察。

語氣：
專業、克制、條理清楚。
避免：崩潰、狂歡、恐慌、徹底、全面、暴衝、反撲、史詩級。
若因果關係不是資料明確支持，請用：可能、顯示、反映、待觀察、尚未推翻主線。

影片固定 6 段：
scene_01：開場，本週總經主線
scene_02：總經傳導圖解
scene_03：市場訊號與走勢
scene_04：修正因子 / 待觀察
scene_05：新聞佐證
scene_06：下週觀察

長度：
全片約 6～8 分鐘。
每段約 350～600 個中文字。
句子要適合 TTS 朗讀，不要太長。

只輸出合法 JSON，不要 Markdown。
JSON 結構：
{{
  "meta": {{
    "version": "weekly_narration_v1",
    "target_duration_minutes": "6-8",
    "tone": "professional_macro_analyst"
  }},
  "scenes": [
    {{
      "scene_id": "scene_01",
      "scene_title": "",
      "narration": "",
      "visual_direction": "",
      "estimated_seconds": 60
    }}
  ],
  "full_narration": ""
}}

weekly_forest_summary:
{compact_json(forest, 20000)}

weekly_news_context:
{compact_json(news, 16000)}

weekly_market_series:
{compact_json(market, 12000)}
"""


def validate(data: Dict[str, Any]) -> Dict[str, Any]:
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 6:
        raise RuntimeError("Narration JSON must contain at least 6 scenes.")

    output = []
    for i, scene in enumerate(scenes[:6], start=1):
        scene_id = str(scene.get("scene_id") or f"scene_{i:02d}")
        title = str(scene.get("scene_title") or f"Scene {i}").strip()
        narration = str(scene.get("narration") or "").strip()
        visual = str(scene.get("visual_direction") or "").strip()
        seconds = int(scene.get("estimated_seconds") or 60)
        if not narration:
            raise RuntimeError(f"{scene_id} narration is empty.")
        output.append({
            "scene_id": scene_id,
            "scene_title": title,
            "narration": narration,
            "visual_direction": visual,
            "estimated_seconds": seconds,
        })

    full = "\n\n".join(f"{s['scene_title']}\n{s['narration']}" for s in output)
    return {
        "meta": data.get("meta") or {"version": "weekly_narration_v1"},
        "scenes": output,
        "full_narration": data.get("full_narration") or full,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    narration_dir = week_dir / "narration"
    out_json = narration_dir / "weekly_narration.json"

    if out_json.exists() and not flag("FORCE_REBUILD_NARRATION"):
        print(f"[SKIP] Narration already exists: {out_json}")
        return

    forest = load_json(week_dir / "weekly_forest_summary.json", {})
    news = load_json(week_dir / "weekly_news_context.json", {})
    market = load_json(week_dir / "weekly_market_series.json", {})

    if not forest:
        raise FileNotFoundError(f"Missing weekly_forest_summary.json in {week_dir}")

    print(f"[INFO] Generating weekly narration with model: {model}")
    raw = call_gemini(build_prompt(forest, news, market), model, api_key)
    data = validate(extract_json(raw))

    save_json(out_json, data)
    save_text(narration_dir / "weekly_narration_full.txt", data["full_narration"])

    for scene in data["scenes"]:
        save_text(narration_dir / f"{scene['scene_id']}.txt", scene["narration"])

    print(f"[OK] Created {out_json}")


if __name__ == "__main__":
    main()
