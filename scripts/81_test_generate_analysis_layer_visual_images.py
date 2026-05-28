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
- 現代金融媒體 explainer graphic
- 白板式總經圖解
- editorial macro infographic
- 機構級、克制、簡潔、清楚、平面化、分析型
- 中心主題明確、周圍訊號節點輕量、淡線連結、留白充足

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
- effect、signal、judgment 類欄位可作為構圖參考，但不得原樣顯示在圖片上。
- 圖片文字不要出現「強化、抵銷、分歧、mixed、整體判斷、觀察重點、重要證據、總結、summary、judgment、effect、signal、watch、evidence」等內部判斷標籤或欄位名稱，除非該詞是本頁核心結論。
- 若資料不足，畫面應呈現「待觀察 / 資料不足」，不得自行補資料。
"""


GLOBAL_STYLE_GUIDE = """
全域視覺風格：
- 16:9 橫式影片圖卡。
- 整張圖主背景使用乾淨白底或近白底，不要大面積灰底、濁色底或暗淡底色。
- 現代金融媒體導讀圖卡風格，畫面要像 explainer graphic，而不是資訊堆疊。
- 大標題置頂，副標或核心句盡量精簡；若該頁指定只留大標題，請不要額外再加副標。
- 每張圖只保留 1 個核心問題或 1 個核心結論。
- 畫面要簡潔，寧可少不要滿；若素材過多，請先濃縮成短句，不要全部塞上去。
- 每頁僅保留必要資訊，避免過多卡片、過多 icon、過多箭頭。
- 整體採用現代金融媒體圖解語言：白底、短標籤、細線、輕量節點、清楚留白與分析型 icon。
- 構圖需依各頁分析內容自然選擇，不同頁面可採三區塊、雙區塊、中心焦點、並列比較、清單或路徑圖等不同版型。
- 主要結論或核心變數應形成畫面焦點；其他訊號以較小節點、短標籤或小型數據卡輔助。
- 線條要細、色塊要淡、節點要輕；保留足夠留白與層次節奏。
- 系列圖卡要有一致的視覺語言，但不要每一頁都套用同一版型；請讓構圖隨主題自然變化，避免單調。
- 配色採「白底 + 彩色細框 + 少量重點色」；不要使用大面積深色或灰濁色塊。
- 區塊以白底搭配彩色細框區分；可用區塊代表色放在標題線、icon、重點數字或細邊框。
- 以 2～5 個小型 icon / 數據卡 / 短標籤呈現重點，但不要做底部「重要證據 / 觀察重點」標籤列。
- 區塊內資訊卡請使用白底細框、極淡同色系底卡、半透明淺底或直接排在白底區塊內。
- 卡片邊界要輕，不能搶過主題區塊外框；整體應像整合式資訊圖。
- 使用細線、淡箭頭、分區與方向線表達因果。
- 避免滿版文字；避免長句；避免大量段落。
- 可以使用固定色彩區隔主題，但整體色彩要明亮、克制、乾淨。
- 數據只使用輸入段落中出現的數據，不得新增。
- 箭頭方向必須與經濟含義一致。
"""


SCENE_DEFINITIONS = [
    {
        "scene_id": "scene_01_news_context",
        "title": "新聞資訊",
        "section_path": ["main_theme_analysis_process"],
        "visual_instruction": """
本圖是整個分析流程的導入頁，合併呈現「新聞與背景新聞盤點」以及「市場價格驗證」。
大標題只留「新聞資訊」，不要再放副標。

請用由左至右三個主題區塊：
1. 通膨
2. 利率
3. 美元 / 亞幣 / 黃金

每個區塊使用白底 + 固定不同顏色細框，不要使用大面積灰濁色底。
每個區塊內分成上下兩部分：
- 上半部：新聞資訊
- 下半部：市場驗證

上半部的新聞資訊請再分成：
- 當週新聞
- 前期新聞
文字只使用這兩個名稱，不要寫「當週新增新聞」或「前期背景新聞」。

內容可以用 app icon / 小圖示卡片呈現，但卡片必須融入各自白底區塊，不要使用突兀白色浮卡或重陰影。
請優先用白底細框、極淡同色系底卡、弱陰影或直接融入區塊。
每張卡只放新聞事件或關鍵訊號，不放語音稿式完整解釋。
每個區塊只保留最重要的 1～2 則當週新聞與 1～2 則前期新聞；若素材過多，請濃縮成短標籤，不要全部塞滿。

下半部的市場驗證請只放對應主題最有代表性的價格反應、方向箭頭、短數據條或小型數據卡，讓觀眾快速看出市場如何回應新聞訊號。
市場驗證只要簡短，不要把完整分析段落塞進圖中。

區塊內容方向可參考以下簡化邏輯：
- 通膨區塊：可呈現如美伊和平協議傳聞、CPI / PPI 偏強、美伊談判反覆；市場驗證以油價或能源價格反應為主。
- 利率區塊：當週新聞由上至下可優先呈現美債殖利率、Fed 會議紀錄、房市數據；前期新聞可呈現關稅、能源；市場驗證以 US10Y / 30Y 等利率反應為主。
- 美元 / 亞幣 / 黃金區塊：區塊內資訊請盡量用短標籤，例如美元指數強勢、亞洲貨幣弱勢、黃金偏強；市場驗證可用 DXY、USDJPY、USDTWD、USDKRW、Gold 等代表性資產。

目的：讓觀眾在同一頁同時理解本週關注哪些消息，以及市場價格如何回應，並帶出本週後續分析的亮點或矛盾點。
不要放「總結」「整體判斷」「重要證據」「觀察重點」等底部區塊或欄位。
不要在卡片右下角顯示括號標籤，如「（強化）」「（抵銷）」「（分歧）」等。
""",
    },
    {
        "scene_id": "scene_02_inflation_expectation",
        "title": "通膨預期綜合研判",
        "section_path": ["main_theme_analysis_process", "inflation_expectation_judgment"],
        "visual_instruction": """
本圖呈現「通膨預期是否形成明確單一方向」。
請呈現兩類不同方向力量：
- 支持通膨壓力的訊號
- 抵銷或修正能源端通膨壓力的訊號

中央或底部放結論：mixed / 分歧 / 尚未形成單一方向。
不要使用「拉扯」字樣。
不要把油價單週下跌畫成整體通膨已完全降溫。
畫面以簡潔分析圖解為主，不要過度裝飾。
""",
    },
    {
        "scene_id": "scene_03_rate_driver",
        "title": "利率驅動來源",
        "section_path": ["main_theme_analysis_process", "rate_driver_diagnosis"],
        "visual_instruction": """
本圖只討論利率，不要畫美元、亞幣或黃金。
請做成「現代金融媒體式利率驅動來源圖解」。

建議構圖：
- 中央主視覺：長端殖利率維持高檔 / 利率下不來 / 利率偏強。
- 周圍三個輕量訊號節點：
  1. Fed 政策訊號
  2. CPI / PPI 背景
  3. 長天期殖利率 / 期限溢價
- 三個節點用細線或淡箭頭匯流到中央主視覺。
- 底部若需要市場驗證，只保留一條極短數據條，例如 US10Y 高位震盪、30Y 突破 5.1%。

必須把「Fed 偏鷹」具體化成輸入內容中出現的政策訊號，不要只寫標籤。
畫面要有現代金融圖解感，三個來源作為輕量訊號節點圍繞中央主題即可，整體保留留白與層次。
""",
    },
    {
        "scene_id": "scene_04_dollar_gold",
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
        "scene_id": "scene_05_asia_fx",
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
        "scene_id": "scene_06_weekly_main_theme",
        "title": "本週主線結論",
        "section_path": ["main_theme_analysis_process", "weekly_main_theme_conclusion"],
        "visual_instruction": """
本圖呈現本週主線結論。
這是前面分析過程後的匯總，不是分析起點。
請不要重新列出所有細節。
請用一個清楚的核心主題、一個核心問題、一句話結論與 2～3 個關鍵證據標籤收斂整週分析。
""",
    },
    {
        "scene_id": "scene_07_next_week_watch",
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


SCENE_LOOKUP = {scene["scene_id"]: scene for scene in SCENE_DEFINITIONS}
SCENE_INDEX_LOOKUP = {f"{index:02d}": scene["scene_id"] for index, scene in enumerate(SCENE_DEFINITIONS, start=1)}


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


def normalize_target_scene(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""

    if value in SCENE_LOOKUP:
        return value

    lowered = value.lower()
    if lowered in SCENE_LOOKUP:
        return lowered

    m = re.fullmatch(r"(?:scene_)?(\d{1,2})(?:_(.*))?", lowered)
    if not m:
        raise ValueError(f"Unknown target scene: {raw}")

    num = f"{int(m.group(1)):02d}"
    suffix = (m.group(2) or "").strip()

    if suffix:
        candidate = f"scene_{num}_{suffix}"
        if candidate in SCENE_LOOKUP:
            return candidate

    candidate = SCENE_INDEX_LOOKUP.get(num)
    if candidate:
        return candidate

    raise ValueError(f"Unknown target scene: {raw}")


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

輔助資料：
{compact_json(evidence, max_chars=1800)}

注意：輔助資料只供理解，不得在圖上以「總結」「重要證據」「觀察重點」等欄位標題或底部標籤列呈現。

全域視覺規則：
{GLOBAL_STYLE_GUIDE}

本圖特別要求：
{scene["visual_instruction"]}

輸出要求：
- 請直接生成圖片。
- 圖上文字必須是繁體中文。
- 不要新增輸入資料沒有的數字或事件。
- 不要產生長段文字。
- 不要使用突兀白色浮卡、重陰影或便條紙式卡片；資訊卡應以淡色、細線、低對比方式融入背景。
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

    normalized_target_scene = normalize_target_scene(args.target_scene)
    scenes = [s for s in SCENE_DEFINITIONS if not normalized_target_scene or s["scene_id"] == normalized_target_scene]

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Analysis input: {analysis_path}")
    print(f"[INFO] Image model: {model}")
    print(f"[INFO] Temperature: {temperature}")
    print(f"[INFO] Retries: {retries}")
    print(f"[INFO] Force rebuild: {force}")
    print(f"[INFO] Target scene raw: {args.target_scene or '(all)'}")
    print(f"[INFO] Target scene normalized: {normalized_target_scene or '(all)'}")

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
