#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 81 Test - Generate Visual Images from Step 80 Analysis Layer

Purpose:
- Test the visual-image layer using the Step 80 analysis-layer output.
- Read:
  output/weekly/YYYY-MM-DD/weekly_forest_summary_analysis_layer_test.json
- Generate:
  output/weekly/YYYY-MM-DD/analysis_layer_visual_test_images/*.png
  output/weekly/YYYY-MM-DD/analysis_layer_visual_test_images/visual_manifest.json

This script does NOT overwrite Step 92 official outputs.
"""

import argparse
import base64
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DEFAULT_IMAGE_MODEL = "gemini-3-pro-image-preview"
DEFAULT_TEMPERATURE = 0.55
DEFAULT_RETRIES = 1

ANALYSIS_FILENAME = "weekly_forest_summary_analysis_layer_test.json"
OUTPUT_DIRNAME = "analysis_layer_visual_test_images"


SYSTEM_PROMPT = """
你是一位擅長將全球總經、利率、匯率與跨資產市場邏輯，轉譯成「金融媒體導讀圖卡」的視覺資訊設計師。

你的作品風格是：
- 金融媒體 explainer graphic
- 白板式總經圖解
- editorial macro infographic
- 機構級、克制、簡潔、清楚、平面化、分析型

你的任務不是重新分析市場，而是把已完成的分析段落轉成適合影片導讀的 16:9 圖卡。

核心規則：
- 嚴格依照輸入 JSON 的內容產圖，不得新增新聞、數字、事件或市場判斷。
- 每張圖只呈現一個分析段落的核心概念。
- 使用分區結構、箭頭、框線、icon、小型數據卡與關鍵標籤。
- 讓觀眾先快速看懂結構，再由旁白深入解析。
- 使用極淡底色、乾淨留白、清楚標題、少量文字。
- 中文文字要簡短、清楚、可讀，避免長句與段落。
- 不要畫成戰場、決鬥、史詩場景、科幻海報、童書插畫、交易廣告或過度戲劇化角色。
- 不要用具象物件取代分析邏輯；icon 只作為輔助。
- 不要產生投資建議。
- 若資料不足，畫面應呈現「待觀察 / 資料不足」，不得自行補資料。
"""


GLOBAL_STYLE_GUIDE = """
全域視覺風格：
- 16:9 橫式影片圖卡。
- 極淡底色，可接近白底、淡灰、淡藍或淡米色。
- 金融媒體導讀圖卡風格，不是簡報投影片堆字。
- 大標題置頂，副標或核心句不超過一行。
- 每張圖只保留 1 個核心問題或 1 個核心結論。
- 以 2～5 個小型 icon / 數據卡 / 標籤卡呈現重點。
- 使用簡單箭頭、框線、分區與方向線表達因果。
- 避免滿版文字；避免長句；避免大量段落。
- 可以使用固定色彩區隔主題，但整體色彩要克制、淡雅。
- 數據只使用輸入段落中出現的數據，不得新增。
- 箭頭方向必須與經濟含義一致。
"""


SCENE_DEFINITIONS = [
    {
        "scene_id": "scene_01_news_context",
        "title": "新聞脈絡",
        "section_path": ["main_theme_analysis_process", "news_context"],
        "visual_instruction": """
本圖呈現「新聞脈絡」，不是最終結論。
請用由左至右三個主題區塊：
1. 通膨
2. 利率
3. 美元 / 亞幣 / 黃金

每個區塊使用固定不同顏色外框。
每個區塊上方放「當週新增新聞」，視覺比重較大。
每個區塊下方放「前期背景新聞」，視覺比重較小。
內容可以用 app icon / 小圖示卡片呈現。
目的：讓觀眾理解本週市場關注哪些消息，以及前期背景是什麼。
""",
    },
    {
        "scene_id": "scene_02_market_validation",
        "title": "市場數據驗證",
        "section_path": ["main_theme_analysis_process", "market_validation"],
        "visual_instruction": """
本圖呈現「市場價格如何驗證新聞訊號」。
請沿用三個主題區塊：
1. 通膨 / 能源：油價、能源壓力
2. 利率 / 美元：美債殖利率、DXY
3. 黃金 / 亞洲貨幣：Gold、TWD、JPY、KRW

重點是數據卡與方向箭頭，不是新聞摘要。
請讓觀眾一眼看出：哪些市場價格同向，哪些出現分歧或未同步。
""",
    },
    {
        "scene_id": "scene_03_inflation_expectation",
        "title": "通膨預期綜合研判",
        "section_path": ["main_theme_analysis_process", "inflation_expectation_judgment"],
        "visual_instruction": """
本圖呈現「通膨預期是否形成明確單一方向」。
請呈現兩類不同方向力量：
- 支持通膨壓力的訊號
- 抵銷或修正能源端通膨壓力的訊號

中央或底部放結論：mixed / 分歧 / 尚未形成單一方向。
不要使用「拉鋸」字樣。
不要把油價單週下跌畫成整體通膨已完全降溫。
""",
    },
    {
        "scene_id": "scene_04_rate_driver",
        "title": "利率驅動來源",
        "section_path": ["main_theme_analysis_process", "rate_driver_diagnosis"],
        "visual_instruction": """
本圖只討論利率，不要畫美元、亞幣或黃金。
請做成「利率驅動來源拆解圖」。
建議三個來源匯聚到中央結論：
1. Fed 政策訊號
2. CPI / PPI 背景
3. 長天期殖利率 / 期限溢價

中央結論呈現：長端殖利率維持高檔 / 利率下不來 / 利率偏強。
必須把「Fed 偏鷹」具體化成輸入內容中出現的政策訊號，不要只寫標籤。
""",
    },
    {
        "scene_id": "scene_05_dollar_gold",
        "title": "美元與黃金",
        "section_path": ["main_theme_analysis_process", "dollar_gold_reaction"],
        "visual_instruction": """
本圖只討論美元與黃金，不要擴到亞洲貨幣。
請使用左右雙區塊：
- 左：美元
- 右：黃金

每個區塊呈現：
新聞訊號 → 背景素材 → 市場驗證 → 驅動來源 → 結論
文字要極簡，不要把完整分析段落塞進畫面。
""",
    },
    {
        "scene_id": "scene_06_asia_fx",
        "title": "亞洲貨幣：台、日、韓",
        "section_path": ["main_theme_analysis_process", "asia_fx_reaction"],
        "visual_instruction": """
本圖只討論亞洲貨幣，請分成三個並列區塊：
1. 台幣 / USDTWD
2. 日圓 / USDJPY
3. 韓圜 / USDKRW

不可只寫「亞幣」。
每一區塊都要有自己的市場驗證與判斷。
若輸入資料不足，請標示待觀察。
""",
    },
    {
        "scene_id": "scene_07_weekly_main_theme",
        "title": "本週主線結論",
        "section_path": ["main_theme_analysis_process", "weekly_main_theme_conclusion"],
        "visual_instruction": """
本圖呈現本週主線結論。
這是第 1～6 段分析過程後的匯總，不是分析起點。
請不要重新列出所有細節。
請用一個清楚的核心主題、一個核心問題、一句話結論與 2～3 個關鍵證據標籤收斂整週分析。
""",
    },
    {
        "scene_id": "scene_08_next_week_watch",
        "title": "下週觀察",
        "section_path": ["main_theme_analysis_process", "next_week_watch"],
        "visual_instruction": """
本圖呈現下週觀察。
請做成 3～4 個待確認訊號或觀察卡片。
只使用輸入資料中已列出的 watch items，不新增無資料支撐的新主題。
風格像觀察清單，不是風險警告海報。
""",
    },
]


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


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


def get_by_path(data: Dict[str, Any], path: List[str]) -> Any:
    cur: Any = data
    for key in path:
        if not isinstance(cur, dict):
            return {}
        cur = cur.get(key, {})
    return cur


def compact_json(data: Any, max_chars: int = 9000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（內容過長，已截斷；請只使用可見內容）"


def build_image_prompt(scene: Dict[str, Any], section_data: Any, full_summary: Dict[str, Any]) -> str:
    forest_summary = full_summary.get("forest_summary", {})
    evidence = full_summary.get("evidence", {})

    return f"""
請根據以下分析段落，產生一張 16:9 總經影片導讀圖卡。

圖像 ID：
{scene["scene_id"]}

圖像主題：
{scene["title"]}

本週主線摘要：
{compact_json(forest_summary, max_chars=1800)}

本圖對應分析段落：
{compact_json(section_data, max_chars=7000)}

可參考證據：
{compact_json(evidence, max_chars=1800)}

全域視覺規則：
{GLOBAL_STYLE_GUIDE}

本圖特別要求：
{scene["visual_instruction"]}

輸出要求：
- 請直接生成圖片。
- 圖上文字必須是繁體中文。
- 不要新增輸入資料沒有的數字或事件。
- 不要產生長段文字。
- 不要重新判斷市場，只轉譯本段分析。
""".strip()


def call_gemini_image(prompt: str, model: str, api_key: str, temperature: float) -> Tuple[bytes, str, Optional[str]]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.85,
            "responseModalities": ["TEXT", "IMAGE"],
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini image HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini image URLError: {exc}") from exc

    api_response = json.loads(raw)
    candidates = api_response.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"No Gemini image candidates returned: {api_response}")

    text_note: Optional[str] = None

    for candidate in candidates:
        parts = ((candidate.get("content") or {}).get("parts") or [])
        for part in parts:
            if "text" in part and part.get("text"):
                text_note = part.get("text")

            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png"
                image_bytes = base64.b64decode(inline_data["data"])
                return image_bytes, mime_type, text_note

    raise RuntimeError(f"No inline image data found in Gemini response: {api_response}")


def extension_from_mime(mime_type: str) -> str:
    lowered = mime_type.lower()
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"
    if "webp" in lowered:
        return ".webp"
    return ".png"


def should_generate(path: Path, force: bool) -> bool:
    if force:
        return True
    return not path.exists() or path.stat().st_size == 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--target-scene", type=str, default=os.getenv("TARGET_SCENE_ID", "").strip())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    temperature = float(os.getenv("IMAGE_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    retries = int(os.getenv("GEMINI_IMAGE_RETRIES", str(DEFAULT_RETRIES)))
    force = args.force or os.getenv("FORCE_REBUILD_VISUALS", "false").strip().lower() in {"1", "true", "yes", "y"}

    week_dir = resolve_week_dir(args.week_dir)
    analysis_path = week_dir / ANALYSIS_FILENAME

    summary = load_json(analysis_path, {})
    if not summary:
        raise FileNotFoundError(f"Missing or empty analysis-layer test file: {analysis_path}")

    output_dir = week_dir / OUTPUT_DIRNAME
    output_dir.mkdir(parents=True, exist_ok=True)

    target_scene = args.target_scene.strip()
    scenes = [s for s in SCENE_DEFINITIONS if not target_scene or s["scene_id"] == target_scene]
    if target_scene and not scenes:
        raise ValueError(f"Unknown target scene: {target_scene}")

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Analysis input: {analysis_path}")
    print(f"[INFO] Image model: {model}")
    print(f"[INFO] Temperature: {temperature}")
    print(f"[INFO] Retries: {retries}")
    print(f"[INFO] Force rebuild: {force}")

    manifest: List[Dict[str, Any]] = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        section_data = get_by_path(summary, scene["section_path"])
        if not section_data:
            print(f"[WARN] Empty section for {scene_id}: {scene['section_path']}")

        prompt = build_image_prompt(scene, section_data, summary)
        prompt_path = output_dir / f"{scene_id}_prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        image_path = output_dir / f"{scene_id}.png"

        if not should_generate(image_path, force):
            print(f"[SKIP] Exists: {image_path}")
            manifest.append({
                "scene_id": scene_id,
                "title": scene["title"],
                "image_path": str(image_path.relative_to(ROOT_DIR)),
                "prompt_path": str(prompt_path.relative_to(ROOT_DIR)),
                "status": "skipped_exists",
            })
            continue

        last_error = ""
        for attempt in range(retries + 1):
            try:
                print(f"[INFO] Generating {scene_id} attempt {attempt + 1}/{retries + 1}")
                image_bytes, mime_type, text_note = call_gemini_image(prompt, model, api_key, temperature)
                ext = extension_from_mime(mime_type)

                final_image_path = image_path
                if ext != ".png":
                    final_image_path = output_dir / f"{scene_id}{ext}"

                final_image_path.write_bytes(image_bytes)

                manifest.append({
                    "scene_id": scene_id,
                    "title": scene["title"],
                    "image_path": str(final_image_path.relative_to(ROOT_DIR)),
                    "prompt_path": str(prompt_path.relative_to(ROOT_DIR)),
                    "mime_type": mime_type,
                    "text_note": text_note or "",
                    "status": "generated",
                })
                print(f"[OK] Saved {final_image_path}")
                break
            except Exception as exc:
                last_error = str(exc)
                print(f"[WARN] Failed {scene_id}: {last_error}")
                if attempt < retries:
                    time.sleep(5 + attempt * 5)
        else:
            manifest.append({
                "scene_id": scene_id,
                "title": scene["title"],
                "prompt_path": str(prompt_path.relative_to(ROOT_DIR)),
                "status": "failed",
                "error": last_error,
            })

    save_json(output_dir / "visual_manifest.json", {
        "source": str(analysis_path.relative_to(ROOT_DIR)),
        "image_model": model,
        "temperature": temperature,
        "scenes": manifest,
    })

    print(f"[OK] Saved manifest: {output_dir / 'visual_manifest.json'}")


if __name__ == "__main__":
    main()
