#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 05 V6
Generate host/analyst dialogue narration for:
Macro transmission diagram + Evidence Panel video.
"""

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_GEMINI_FALLBACK_MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
]


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



def get_model_candidates() -> List[str]:
    raw = os.getenv("GEMINI_MODEL", "").strip()
    if raw:
        candidates = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        candidates = list(DEFAULT_GEMINI_FALLBACK_MODELS)

    for item in DEFAULT_GEMINI_FALLBACK_MODELS:
        if item not in candidates:
            candidates.append(item)

    return candidates


def call_gemini_once(prompt: str, model: str, api_key: str) -> str:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.32,
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
    output = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    if not output:
        raise RuntimeError(f"Empty Gemini output. Preview: {raw[:1000]}")
    return output


def call_gemini_with_retry(prompt: str, model_candidates: List[str], api_key: str) -> str:
    retryable_markers = [
        "HTTPError 429",
        "HTTPError 500",
        "HTTPError 502",
        "HTTPError 503",
        "HTTPError 504",
        "UNAVAILABLE",
        "RESOURCE_EXHAUSTED",
    ]

    last_error = None

    for model in model_candidates:
        print(f"[INFO] Trying Gemini narration model: {model}")

        for attempt in range(1, 5):
            try:
                return call_gemini_once(prompt, model, api_key)
            except RuntimeError as exc:
                last_error = exc
                message = str(exc)
                is_retryable = any(marker in message for marker in retryable_markers)

                if not is_retryable:
                    raise

                wait_seconds = min(75, 10 * attempt * attempt)
                print(
                    f"[WARN] Gemini narration request failed on {model}, "
                    f"attempt {attempt}/4. Waiting {wait_seconds}s. Error: {message[:300]}"
                )

                if attempt < 4:
                    time.sleep(wait_seconds)

        print(f"[WARN] Model still unavailable after retries: {model}. Trying next model candidate.")

    if last_error is not None:
        raise last_error

    raise RuntimeError("No Gemini model candidate was available.")


def build_prompt(forest: Dict[str, Any], news: Dict[str, Any], market: Dict[str, Any]) -> str:
    return f"""
你是一位專業總經週報影片主編、總經分析師與財經節目編劇。

任務：
根據 weekly_forest_summary、weekly_news_context、weekly_market_series，
產生一支 8～10 分鐘「主持人 Tom + 分析師 Miranda」雙人對談式週報影片旁白與分鏡。
影片畫面採用：
1. 左側主畫面：同一張「總經傳導圖解」貫穿全片，使用 spotlight 聚焦不同區塊。
2. 右側 Evidence Panel：顯示對應走勢圖、新聞卡與短重點。

核心原則：
- 總經傳導圖解是主角，不是其中一張插圖。
- 每段都要沿著「走勢圖變化 → 新聞原因 → 市場解讀 → 回到傳導鏈」。
- 旁白不能只是照畫面文字唸。
- 主持人 Tom 負責開場、提問、轉場。
- 分析師 Miranda 負責用走勢圖 + 新聞內容 + 總經傳導鏈進行分析。
- 新聞是校正層，不是逐篇摘要；請挑出能解釋該段走勢的新聞。
- 畫面文字很少，完整分析放在 dialogue 裡。

影片固定 6 段：
scene_01：全圖開場。本週傳導鏈與核心數據變化。
scene_02：通膨預期。用 WTI / Brent 走勢 + 通膨/能源新聞說明再通膨起點。
scene_03：利率。用 US10Y 走勢 + Fed/長債/利率新聞說明核心變數。
scene_04：美元與亞洲貨幣。用 DXY、USDJPY、USDTWD、USDKRW 走勢 + 貨幣新聞說明外溢。
scene_05：黃金。用 Gold 走勢 + 黃金/避險/利率新聞檢查傳導鏈。
scene_06：傳導鏈強弱與下週觀察。總結主線是否成立、修正因子與下週驗證。

spotlight_target 可用值：
- overview
- drivers
- yields
- dollar_fx
- gold_risk
- next_watch

evidence_assets 可用值：
- US10Y
- DXY
- Gold
- WTI
- Brent
- USDJPY
- USDTWD
- USDKRW

evidence_news_category 可用值：
- 通膨預期
- 利率
- 貨幣
- 其他

建議對應：
scene_01：spotlight overview，assets US10Y/DXY/Gold，news 其他
scene_02：spotlight drivers，assets WTI/Brent，news 通膨預期
scene_03：spotlight yields，assets US10Y，news 利率
scene_04：spotlight dollar_fx，assets DXY/USDJPY/USDTWD/USDKRW，news 貨幣
scene_05：spotlight gold_risk，assets Gold，news 其他
scene_06：spotlight next_watch，assets US10Y/DXY/Gold，news 其他

語氣：
- 專業、克制、條理清楚。
- 不要像媒體標題或自媒體旁白。
- 避免：崩潰、狂歡、恐慌、徹底、全面、暴衝、反撲、史詩級。
- 若因果關係不是資料明確支持，請用：可能、顯示、反映、待觀察、尚未推翻主線。
- 若提到匯率貶值可能支撐出口，必須補充：實際效果仍取決於外需、進口成本與產業結構，不可過度推論。

長度：
- 全片約 8～10 分鐘。
- 每段 dialogue 合計約 450～750 個中文字。
- 每段至少 2 輪對話：主持人 → 分析師；必要時可再一輪主持人追問 → 分析師補充。
- 句子適合 TTS 朗讀，不要過長。

畫面文字規則：
- on_screen_title 是短標題。
- on_screen_bullets 只放 3～5 個短重點，每點不超過 14 個中文字。
- evidence_panel_title 是右側證據面板標題，例如「原油與通膨證據」。
- 不要把完整旁白塞進畫面。

只輸出合法 JSON，不要 Markdown。
JSON 結構：
{{
  "meta": {{
    "version": "weekly_narration_v6_evidence_panel",
    "target_duration_minutes": "8-10",
    "tone": "tom_host_miranda_analyst"
  }},
  "scenes": [
    {{
      "scene_id": "scene_01",
      "scene_title": "",
      "on_screen_title": "",
      "on_screen_bullets": ["", "", ""],
      "spotlight_target": "overview",
      "evidence_panel_title": "",
      "evidence_assets": ["US10Y", "DXY"],
      "evidence_news_category": "其他",
      "visual_direction": "",
      "dialogue": [
        {{"speaker": "host", "text": ""}},
        {{"speaker": "analyst", "text": ""}}
      ],
      "narration": "",
      "estimated_seconds": 80
    }}
  ],
  "full_narration": ""
}}

注意：
- narration 欄位請把 dialogue 內容合併成可讀文字，格式包含「主持人：」「分析師：」。
- dialogue 仍必須保留，供 TTS 依不同聲線生成。
- 每段分析一定要引用走勢圖與新聞內容，不要只講抽象概念。

weekly_forest_summary:
{compact_json(forest, 20000)}

weekly_news_context:
{compact_json(news, 18000)}

weekly_market_series:
{compact_json(market, 14000)}
"""


def flatten_dialogue(dialogue: List[Dict[str, str]]) -> str:
    lines = []
    for turn in dialogue:
        speaker = str(turn.get("speaker") or "").strip()
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        label = "主持人" if speaker == "host" else "分析師" if speaker == "analyst" else speaker
        lines.append(f"{label}：{text}")
    return "\n".join(lines)


def validate(data: Dict[str, Any]) -> Dict[str, Any]:
    scenes = data.get("scenes")
    if not isinstance(scenes, list) or len(scenes) < 6:
        raise RuntimeError("Narration JSON must contain at least 6 scenes.")

    default_scene_config = [
        ("overview", ["US10Y", "DXY", "Gold"], "其他"),
        ("drivers", ["WTI", "Brent"], "通膨預期"),
        ("yields", ["US10Y"], "利率"),
        ("dollar_fx", ["DXY", "USDJPY", "USDTWD", "USDKRW"], "貨幣"),
        ("gold_risk", ["Gold"], "其他"),
        ("next_watch", ["US10Y", "DXY", "Gold"], "其他"),
    ]
    valid_assets = {"US10Y", "DXY", "Gold", "WTI", "Brent", "USDJPY", "USDTWD", "USDKRW"}
    valid_categories = {"通膨預期", "利率", "貨幣", "其他"}

    output = []
    for i, scene in enumerate(scenes[:6], start=1):
        default_spotlight, default_assets, default_category = default_scene_config[i - 1]
        scene_id = str(scene.get("scene_id") or f"scene_{i:02d}")
        title = str(scene.get("scene_title") or f"Scene {i}").strip()
        on_screen_title = str(scene.get("on_screen_title") or title).strip()

        bullets = scene.get("on_screen_bullets") or []
        if not isinstance(bullets, list):
            bullets = []
        bullets = [str(x).strip() for x in bullets if str(x).strip()][:5]
        if not bullets:
            bullets = [on_screen_title]

        evidence_assets = scene.get("evidence_assets") or default_assets
        if not isinstance(evidence_assets, list):
            evidence_assets = default_assets
        evidence_assets = [str(x).strip() for x in evidence_assets if str(x).strip() in valid_assets]
        if not evidence_assets:
            evidence_assets = default_assets

        news_category = str(scene.get("evidence_news_category") or default_category).strip()
        if news_category not in valid_categories:
            news_category = default_category

        dialogue = scene.get("dialogue") or []
        if not isinstance(dialogue, list):
            dialogue = []

        cleaned_dialogue = []
        for turn in dialogue:
            if not isinstance(turn, dict):
                continue
            speaker = str(turn.get("speaker") or "").strip()
            text = str(turn.get("text") or "").strip()
            if speaker not in {"host", "analyst"}:
                speaker = "analyst"
            if text:
                cleaned_dialogue.append({"speaker": speaker, "text": text})

        narration = str(scene.get("narration") or "").strip()
        if not narration and cleaned_dialogue:
            narration = flatten_dialogue(cleaned_dialogue)
        if not narration:
            raise RuntimeError(f"{scene_id} narration/dialogue is empty.")
        if not cleaned_dialogue:
            cleaned_dialogue = [{"speaker": "analyst", "text": narration}]

        output.append({
            "scene_id": scene_id,
            "scene_title": title,
            "on_screen_title": on_screen_title,
            "on_screen_bullets": bullets,
            "spotlight_target": str(scene.get("spotlight_target") or default_spotlight).strip(),
            "evidence_panel_title": str(scene.get("evidence_panel_title") or "證據面板").strip(),
            "evidence_assets": evidence_assets,
            "evidence_news_category": news_category,
            "visual_direction": str(scene.get("visual_direction") or "").strip(),
            "dialogue": cleaned_dialogue,
            "narration": narration,
            "estimated_seconds": int(scene.get("estimated_seconds") or 80),
        })

    full = "\n\n".join(f"{s['scene_title']}\n{s['narration']}" for s in output)
    return {
        "meta": data.get("meta") or {"version": "weekly_narration_v6_evidence_panel"},
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

    model_candidates = get_model_candidates()
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

    print(f"[INFO] Generating V6 evidence-panel dialogue narration with model candidates: {', '.join(model_candidates)}")
    raw = call_gemini_with_retry(build_prompt(forest, news, market), model_candidates, api_key)
    data = validate(extract_json(raw))

    save_json(out_json, data)
    save_text(narration_dir / "weekly_narration_full.txt", data["full_narration"])
    for scene in data["scenes"]:
        save_text(narration_dir / f"{scene['scene_id']}.txt", scene["narration"])

    print(f"[OK] Created {out_json}")


if __name__ == "__main__":
    main()
