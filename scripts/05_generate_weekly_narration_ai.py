#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 05 V7
Generate host/analyst dialogue narration with multimodal visual context.

What changed in V7:
- Gemini no longer receives only JSON text.
- It also receives:
  1) weekly_macro_diagram.png
  2) a screenshot of index.html as market/news visual evidence context
- This helps Gemini write a video script that follows the actual visual layout,
  instead of producing a generic macro narration.

Input:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json
- output/weekly/YYYY-MM-DD/weekly_news_context.json
- output/weekly/YYYY-MM-DD/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png
- output/weekly/YYYY-MM-DD/index.html

Output:
- output/weekly/YYYY-MM-DD/narration/weekly_narration.json
- output/weekly/YYYY-MM-DD/narration/weekly_narration_full.txt
- output/weekly/YYYY-MM-DD/narration/scene_01.txt ... scene_06.txt
- output/weekly/YYYY-MM-DD/visual_context/weekly_page_snapshot.jpg

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_MODEL, default model candidates:
  gemini-2.5-pro, gemini-3.1-flash-lite, gemini-2.5-flash
- FORCE_REBUILD_NARRATION, default false
"""

import argparse
import base64
import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DEFAULT_GEMINI_FALLBACK_MODELS = [
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
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


def resize_image_for_api(src: Path, dst: Path, max_width: int = 1600, quality: int = 82) -> Path:
    """Resize/compress screenshot to keep API payload stable."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        if img.width > max_width:
            new_height = int(img.height * max_width / img.width)
            img = img.resize((max_width, new_height), Image.LANCZOS)
        img.save(dst, format="JPEG", quality=quality, optimize=True)
    return dst


def capture_index_snapshot(week_dir: Path) -> Optional[Path]:
    """Render local index.html into a visual context screenshot for Gemini."""
    index_html = week_dir / "index.html"
    if not index_html.exists():
        print(f"[WARN] index.html not found, skip page snapshot: {index_html}")
        return None

    out_dir = week_dir / "visual_context"
    out_dir.mkdir(parents=True, exist_ok=True)
    raw_png = out_dir / "weekly_page_snapshot_raw.png"
    final_jpg = out_dir / "weekly_page_snapshot.jpg"

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        print(f"[WARN] Playwright not available, skip page snapshot. {exc}")
        return None

    url = index_html.resolve().as_uri()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1920, "height": 2200}, device_scale_factor=1)
            page.goto(url, wait_until="load", timeout=60000)
            page.wait_for_timeout(1500)
            page.screenshot(path=str(raw_png), full_page=True)
            browser.close()

        resize_image_for_api(raw_png, final_jpg, max_width=1600, quality=78)
        print(f"[INFO] Created visual context snapshot: {final_jpg}")
        return final_jpg

    except Exception as exc:
        print(f"[WARN] Failed to capture index snapshot, skip page snapshot. {exc}")
        return None


def image_to_inline_part(path: Path, fallback_mime: str = "image/png") -> Dict[str, Any]:
    mime_type = mimetypes.guess_type(path.name)[0] or fallback_mime
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {
        "inlineData": {
            "mimeType": mime_type,
            "data": data,
        }
    }


def clean_dialogue_text(text: str) -> str:
    """Remove accidental role/name prefixes from model dialogue text."""
    cleaned = str(text or "").strip()
    patterns = [
        r"^(主持人|分析師)\s*[:：]\s*",
        r"^(Tom|Miranda|Kore|Puck|puck|kore)\s*[,，:：]\s*",
        r"^(主持人|分析師)\s*(Tom|Miranda|Kore|Puck|puck|kore)?\s*[,，:：]\s*",
    ]

    for _ in range(3):
        before = cleaned
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        if cleaned == before:
            break

    return cleaned


def flatten_dialogue(dialogue: List[Dict[str, str]]) -> str:
    lines = []
    for turn in dialogue:
        speaker = str(turn.get("speaker") or "").strip()
        text = clean_dialogue_text(str(turn.get("text") or "").strip())
        if not text:
            continue
        label = "主持人" if speaker == "host" else "分析師" if speaker == "analyst" else speaker
        lines.append(f"{label}：{text}")
    return "\n".join(lines)


def build_system_instruction() -> str:
    return """
你是一位專業總經週報影片主編、總經分析師與財經節目編劇。

你正在替一支 8～10 分鐘的總經週報影片撰寫分鏡與雙人對談旁白。
請嚴格遵守：
1. 總經傳導圖解是全片主角，不是插圖。
2. 市場訊號與新聞佐證頁是證據面板，用來輔助驗證圖解。
3. 每段旁白必須沿著：
   走勢圖變化 → 新聞原因 → 市場解讀 → 回到傳導鏈。
4. 不要寫一般總經摘要；要寫「導讀畫面」的影片腳本。
5. 主持人角色固定是 host，負責開場、提問、轉場。
6. 分析師角色固定是 analyst，負責解釋走勢圖、新聞與傳導鏈。
7. dialogue[].text 開頭禁止出現 Tom、Miranda、主持人、分析師等角色前綴。
   但允許在自然對話中短暫稱呼對方，例如「Miranda，從這個訊號來看...」或「Tom 你好」。
8. 畫面文字必須短，完整分析放在 dialogue。
9. 語氣專業、克制、條理清楚，不要聳動。
10. 如果提到匯率貶值有助出口，必須補充實際效果仍取決於外需、進口成本與產業結構。

你會看到兩張圖片：
- 圖片一：總經傳導圖解，是影片主地圖。
- 圖片二：本週市場訊號與新聞佐證頁，是走勢圖與新聞證據來源。
請在腳本中使用「左側」、「順著箭頭」、「圖解下方」、「右側證據面板」等空間引導語，但不要過度描述圖片外觀。
"""


def build_user_prompt(forest: Dict[str, Any], news: Dict[str, Any], market: Dict[str, Any]) -> str:
    return f"""
請根據隨附的兩張圖片與下列 JSON 資料，產生 V7 多模態版 weekly_narration.json。

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

對白風格與 JSON 格式範例（請務必模仿此口語化、有互動感的語氣，並填入 dialogue 陣列中）：
[
  {{
    "speaker": "host",
    "text": "各位投資朋友大家好，歡迎收看本週的總經週報。這週我們觀察到的最重要證據，就是圖解下方的30年期美債殖利率突破了 5.1%。Miranda，從這個訊號來看，目前這條傳導鏈走到什麼階段了？"
  }},
  {{
    "speaker": "analyst",
    "text": "Tom 你好。這反映出一個明確的總經路徑：市場正在重新定價「高利率將維持更久」的新常態。我們順著畫面左側的走勢圖可以看到，這股壓力正直接衝擊貨幣市場的定價。"
  }},
  {{
    "speaker": "host",
    "text": "也就是說，目前市場的主要定價邏輯，完全扣合我們圖解上半部的這條路徑囉？"
  }}
]

輸出規則：
- 只輸出合法 JSON，不要 Markdown。
- 每段 dialogue 合計約 550～850 個中文字。
- 每段至少 host → analyst → host 或 host → analyst 兩輪。
- narration 欄位請把 dialogue 合併成可讀文字，格式包含「主持人：」「分析師：」。
- dialogue 仍必須保留，供 TTS 分聲線使用。

JSON 結構：
{{
  "meta": {{
    "version": "weekly_narration_v7_multimodal_visual_context_fewshot",
    "target_duration_minutes": "8-10",
    "tone": "visual_guided_host_analyst_dialogue"
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
      "estimated_seconds": 90
    }}
  ],
  "full_narration": ""
}}

weekly_forest_summary:
{compact_json(forest, 18000)}

weekly_news_context:
{compact_json(news, 16000)}

weekly_market_series:
{compact_json(market, 12000)}
"""


def call_gemini_once(
    user_prompt: str,
    image_parts: List[Dict[str, Any]],
    model: str,
    api_key: str,
) -> str:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    parts: List[Dict[str, Any]] = [{"text": user_prompt}]
    parts.extend(image_parts)

    payload = {
        "system_instruction": {
            "parts": [{"text": build_system_instruction()}]
        },
        "contents": [
            {
                "role": "user",
                "parts": parts,
            }
        ],
        "generationConfig": {
            "temperature": 0.65,
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
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini HTTPError {exc.code}: {detail}") from exc

    data = json.loads(raw)
    parts_out = (((data.get("candidates") or [{}])[0].get("content") or {}).get("parts") or [])
    output = "\n".join(p.get("text", "") for p in parts_out if isinstance(p, dict)).strip()
    if not output:
        raise RuntimeError(f"Empty Gemini output. Preview: {raw[:1000]}")
    return output


def call_gemini_with_retry(
    user_prompt: str,
    image_parts: List[Dict[str, Any]],
    model_candidates: List[str],
    api_key: str,
) -> str:
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
        print(f"[INFO] Trying Gemini multimodal narration model: {model}")

        for attempt in range(1, 5):
            try:
                return call_gemini_once(user_prompt, image_parts, model, api_key)
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
    valid_spotlights = {"overview", "drivers", "yields", "dollar_fx", "gold_risk", "next_watch"}

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

        spotlight = str(scene.get("spotlight_target") or default_spotlight).strip()
        if spotlight not in valid_spotlights:
            spotlight = default_spotlight

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
            text = clean_dialogue_text(str(turn.get("text") or "").strip())
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
            cleaned_dialogue = [{"speaker": "analyst", "text": clean_dialogue_text(narration)}]

        output.append({
            "scene_id": scene_id,
            "scene_title": title,
            "on_screen_title": on_screen_title,
            "on_screen_bullets": bullets,
            "spotlight_target": spotlight,
            "evidence_panel_title": str(scene.get("evidence_panel_title") or "證據面板").strip(),
            "evidence_assets": evidence_assets,
            "evidence_news_category": news_category,
            "visual_direction": str(scene.get("visual_direction") or "").strip(),
            "dialogue": cleaned_dialogue,
            "narration": flatten_dialogue(cleaned_dialogue),
            "estimated_seconds": int(scene.get("estimated_seconds") or 90),
        })

    full = "\n\n".join(f"{s['scene_title']}\n{s['narration']}" for s in output)
    return {
        "meta": data.get("meta") or {"version": "weekly_narration_v7_multimodal_visual_context_fewshot"},
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

    image_parts: List[Dict[str, Any]] = []
    diagram_path = week_dir / "weekly_macro_diagram.png"
    if diagram_path.exists():
        print(f"[INFO] Attach macro diagram image: {diagram_path}")
        image_parts.append(image_to_inline_part(diagram_path, "image/png"))
    else:
        print(f"[WARN] weekly_macro_diagram.png not found: {diagram_path}")

    snapshot_path = capture_index_snapshot(week_dir)
    if snapshot_path and snapshot_path.exists():
        print(f"[INFO] Attach page snapshot image: {snapshot_path}")
        image_parts.append(image_to_inline_part(snapshot_path, "image/jpeg"))

    if not image_parts:
        print("[WARN] No visual context images attached. Narration will be text-only.")

    user_prompt = build_user_prompt(forest, news, market)

    print(f"[INFO] Generating V7 multimodal visual-context narration with model candidates: {', '.join(model_candidates)}")
    raw = call_gemini_with_retry(user_prompt, image_parts, model_candidates, api_key)
    data = validate(extract_json(raw))

    save_json(out_json, data)
    save_text(narration_dir / "weekly_narration_full.txt", data["full_narration"])

    for scene in data["scenes"]:
        save_text(narration_dir / f"{scene['scene_id']}.txt", scene["narration"])

    print(f"[OK] Created {out_json}")


if __name__ == "__main__":
    main()
