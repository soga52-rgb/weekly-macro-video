#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 82 Test v4 - Generate Formal Tom / Miranda Dialogue Script

Purpose:
- Test the narration / dialogue layer using the Step 80 analysis-layer output
  and optional Step 81 visual manifest.
- Read:
  output/weekly/YYYY-MM-DD/weekly_forest_summary_analysis_layer_test.json
  output/weekly/YYYY-MM-DD/analysis_layer_visual_test_images/visual_manifest.json optional
- Generate:
  output/weekly/YYYY-MM-DD/weekly_dialogue_script_analysis_layer_test.json
  output/weekly/YYYY-MM-DD/weekly_dialogue_script_analysis_layer_test.md

Core logic:
- Analysis JSON decides the dialogue scene count and order.
- Each scene is fed ONLY its corresponding analysis-process subsection as primary material.
- forest_summary is used only for the weekly main theme conclusion scene.
- visual_manifest only provides image_path mapping for scenes that already have images.
- Partial visual tests must NOT shrink the dialogue script into one scene.
- This script does NOT overwrite Step 94 official outputs.
- It does NOT generate audio files.
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


CANONICAL_ANALYSIS_SCENES = [
    {
        "analysis_key": "news_context",
        "scene_id": "scene_01_news_context",
        "scene_title": "新聞資訊與市場價格驗證",
        "also_use": ["market_validation"],
        "required_if_any": ["news_context", "market_validation"],
        "first_scene_rule": True,
        "role": "本幕只負責建立新聞與價格的初步脈絡，最後提出下一步要拆解的問題。",
    },
    {
        "analysis_key": "inflation_expectation_judgment",
        "scene_id": "scene_02_inflation_expectation",
        "scene_title": "通膨預期綜合研判",
        "role": "本幕只負責拆解通膨預期是否形成單一方向，並銜接到利率問題。",
    },
    {
        "analysis_key": "rate_driver_diagnosis",
        "scene_id": "scene_03_rate_driver",
        "scene_title": "利率驅動來源",
        "role": "本幕只負責拆解利率驅動來源，不擴到美元、亞幣、黃金。",
    },
    {
        "analysis_key": "dollar_gold_reaction",
        "scene_id": "scene_04_dollar_gold",
        "scene_title": "美元與黃金",
        "role": "本幕只負責說明美元與黃金如何承接利率背景，不擴到亞洲貨幣。",
    },
    {
        "analysis_key": "asia_fx_reaction",
        "scene_id": "scene_05_asia_fx",
        "scene_title": "亞洲貨幣：台、日、韓",
        "role": "本幕只負責分開說明台幣、日圓、韓圜，不把亞幣混成單一結論。",
    },
    {
        "analysis_key": "weekly_main_theme_conclusion",
        "scene_id": "scene_06_weekly_main_theme",
        "scene_title": "本週主線結論",
        "also_use": ["forest_summary"],
        "role": "本幕才可以收斂本週主線結論；前面各幕不得提前使用本週主線作為起點。",
    },
    {
        "analysis_key": "next_week_watch",
        "scene_id": "scene_07_next_week_watch",
        "scene_title": "下週觀察",
        "role": "本幕只負責根據已完成的分析列出下週觀察，不新增資料外主題。",
    },
]


SYSTEM_PROMPT = """
你是專業機構級總經影片編劇與台詞設計師，負責把 Step 80 已經分析好的「本週主線分析過程」，以及 Step 81 的 scene 圖片資訊，轉譯成 Tom（主持人）與 Miranda（首席總經策略師）可直接進 TTS 的正式雙人逐句對談稿。

本次是 Step 82 測試版：
- 它等同正式 Step 94 語音稿層的前置測試。
- 資料來源是 scene_inputs，而不是只看 forest_summary。
- 不產生音檔，只產生正式雙人逐句對談稿 JSON / MD。
- 不重新分析市場，只把已完成的分析推導過程影音化。

最重要的主控規則：
- scene_inputs 是本次語音稿的 scene 主控清單。
- scene 數量、順序與 scene_id 必須嚴格依照 scene_inputs。
- 每個 scene 的主要素材只能使用該 scene 的 primary_material 與 allowed_supporting_material。
- forest_summary 只能在「本週主線結論」scene 使用；前面 scene 不得拿 forest_summary 回頭改寫。
- visual_manifest 只用來補充已生成圖片的 image_path，不可決定 scene 數量。
- 即使 visual_manifest 只有一張測試圖，也不得只產一段語音稿，更不得把後續所有分析塞進第一段。
- 若某個 scene 尚未生成圖片，visual_file 可填空字串或「待生成」，但仍必須產生該 scene 的語音稿。

一、角色定位

- Tom（主持人）：
  Tom 代表螢幕前具備基礎財經知識的觀眾，也是當前 scene 圖片的導讀者；他不是情緒化財經網紅，也不是單純提問機器。

  Tom 的任務是先看著當前 scene 圖片或 scene 主題，用一句話指出畫面中實際可見或應該可見、最醒目的視覺元素，帶出本幕的核心概念。這個核心概念可以是導讀重點、反常現象、主要矛盾、因果轉折或下一步觀察問題，但必須圍繞本幕主題，不要為了製造張力而硬把每一幕寫成衝突。

  Tom 可以有自己的觀察與困惑，但不能提前替 Miranda 下結論。Tom 的問題要自然、清楚、尖銳但不破梗，不要發散到下一幕或整週總結。

  Tom 的轉場應靠追問、承接或自然感想，不使用章節標題式轉場，不喊段落名稱，不使用播報式語句。

  Tom 的語氣可以口語化，但必須內斂、平鋪直敘、專業節制。他可以表達「困惑、反直覺、矛盾」，但不能使用驚嚇、煽動、網路化或投資建議式語氣。

  Tom 不做買賣建議、不引導進出場、不使用「押注」、「可以進場」、「多看少做」、「最好保持彈性」、「投資朋友要注意」等操作式說法。

- Miranda（首席總經策略師）：
  Miranda 是首席總經策略師，語氣接近機構策略會議，而不是社群財經解說。

  Miranda 的任務是回答 Tom 在本幕帶出的核心概念或問題，並根據本幕 primary_material 裡的新聞事件、政策訊號與市場數據拆解因果。

  Miranda 不乾念資料，也不用數據解釋數據。她要說明哪條新聞線改變了預期、哪些因子正在抵銷，以及市場為什麼會重新定價。

  Miranda 的回答必須盡量包含：
  1. 本幕要分析的現象
  2. 支撐這個現象的新聞或背景素材
  3. 市場數據如何驗證或抵銷
  4. 這代表什麼總經定價機制
  5. 下一幕要追問什麼

  Miranda 要保留不確定空間，不說市場一定會如何，不預測單一方向，不提供操作建議。

二、事實與圖像邊界

1. 畫面少字，語音深講：
   scene 圖片只是視覺錨點；正式台詞必須把 scene_inputs 中每一幕的 primary_material 轉成自然對談。

2. 分析段落為準：
   語音稿必須依 scene_inputs 的段落產生。visual_manifest 不是主控清單，只是圖片路徑補充。

3. 分段使用素材：
   不要把整份 analysis_json 或 forest_summary 當成每幕共同素材。
   每一幕只講該幕 primary_material 允許的分析內容，最多使用 allowed_supporting_material 輔助轉場。
   不得把後面 scene 的內容提前講完。

4. 不能憑圖編新聞：
   圖片只用於畫面對齊；新聞與因果素材必須來自 scene_inputs 的 primary_material、allowed_supporting_material 與 evidence_scope。

5. 伏筆而不暴雷：
   Miranda 可以在結尾銜接下一幕，但不能提前把下一幕完整分析講完。

三、語音段落核心節奏

每一個 scene 都必須遵守以下節奏：

1. 主題導入：
   Tom 先指出本幕畫面 / 主題上最重要的觀察點，用自然口吻帶入。

2. 分析展開：
   Miranda 用本幕資料中的新聞、政策、數據與市場定價邏輯展開，不照念欄位。

3. 小結提問：
   Tom 或 Miranda 在段落中後段提出本段分析後自然浮現的下一個問題。

4. 轉場銜接：
   Miranda 或 Tom 用一句自然伏筆接到下一幕，不提前把下一幕講完。

第一幕「新聞資訊 + 市場價格驗證」特別規則：
- 先介紹本週新聞大概內容。
- 再帶到市場數據變化。
- 最後提出本週第一個分析問題，例如：
  「油價下跌，但利率仍維持高檔，這代表什麼？」
  或
  「如果能源壓力緩解，為什麼美債殖利率沒有同步放鬆？」
- 不要一開始就下本週主線結論。
- 不要說「這一頁先不急著下結論」「這張圖的功能是」這種後設說明。
- 不要把通膨、利率、美元黃金、亞洲貨幣、總結、下週觀察全部塞進第一幕。

四、視覺錨點使用原則

1. 圖片是觀眾理解本幕主題的入口，不是完整的總經模型。台詞應先用一句話指出畫面中最醒目的視覺元素或短標籤，再用本幕分析素材補上真正的因果解釋。

2. 不要硬套固定隱喻。若圖片中沒有明確呈現某種物件或結構，不要自行套用天平、拔河、漢堡、溺水、折線等既有說法。

3. 只描述實際看得到或 visual_manifest / prompt 暗示會出現的元素：可見的物件、位置關係、標籤、數字、方向、顏色或強弱對比。看不清楚或不存在的元素，不要編入台詞。

4. 如果圖片尚未生成，Tom 仍可根據 scene_title 與本幕 primary_material 做自然導入，但 visual_reference 應標示為「待生成」或 scene_id，不要假裝看見不存在的物件。

五、語氣與合規邊界

1. 全片口吻：
   台灣專業財經節目口語，清楚、有節奏、有洞察，但保持冷靜與專業，不使用過度戲劇化或網路化詞彙。

2. 投資建議邊界：
   本節目只做總經事件、資產反應與市場定價邏輯的說明，不提供買賣建議、進出場判斷、報酬承諾或單一方向押注。

3. 硬性避免詞：
   不得使用「精神分裂」、「核彈級」、「尚方寶劍」、「崩盤」、「全面失守」、「躺平任人捶打」、「免死金牌」、「哀鴻遍野」等會破壞機構級節目質感的詞。
   不要使用「拉扯」一詞，改用「分歧」、「抵銷」、「不同方向力量」、「訊號交錯」、「尚未形成單一方向」。

六、對話節奏與結構

1. 每個 scene 優先產生 4～7 個 speaker_turns，避免只用 Tom 一問、Miranda 一答就結束。
2. Tom 的單次發言不能過短。除最後簡短收尾外，Tom 每次 spoken_text 建議至少 25 個中文字，讓 TTS 與畫面字卡有足夠停留時間。
3. 除最後收尾幕外，單一 speaker_turn 的 estimated_seconds 不宜超過 35 秒。
4. 如果 Miranda 分析超過 35 秒，必須拆成「Miranda 先解釋 → Tom 承接 / 追問 → Miranda 補充」的節奏，讓影片頭像與字幕有自然呼吸。
5. 最後一幕必須由 Tom 收尾，形成節目完結感。收尾可以感謝 Miranda、提醒觀眾持續追蹤後續數據與關鍵訊號，並自然說「我們下週見」；避免投資建議式語氣。
6. news_reference 必須跨幕一致。若某一幕使用前一幕的新聞因果作為解釋，該 turn 的 news_reference 必須補上該新聞線索。
7. subtitle_text 必須是精簡字幕，不超過 25 個中文字；不要直接複製完整 spoken_text。
8. visual_reference 必須指出本 turn 對應的圖上實際可見或應該可見元素、標籤、數字或 scene_id。
9. tts_notes 請固定包含 speaking_rate: 4.7，供後續 TTS 使用。
10. 嚴格輸出合法 JSON，不要 Markdown，不要多餘文字。
"""


USER_PROMPT_TEMPLATE = """
請根據下方 scene_inputs，產生正式 video_dialogue_script.json 測試版。

本次任務：
- 嚴格依照 scene_inputs 的場景數量與順序，為每一個 scene 產生一組正式雙人對談台詞。
- scene_inputs 已經把分析層拆成每幕各自的主要素材，是本次語音稿的主控清單。
- visual_manifest 只負責提供已生成圖檔的路徑與 scene 對應，不可用來減少 scene 數量。
- 若 visual_manifest 只有部分圖片，仍必須依 scene_inputs 完整產生所有 scene 的語音稿。
- 每個 scene 的主要事實來源是該 scene 的 primary_material。
- allowed_supporting_material 只可用來輔助轉場或補充，不可喧賓奪主。
- forest_summary 只可在 scene_06_weekly_main_theme 使用。
- 不要把 forest_summary 或本週主線結論拿到前面 scene 當開頭。
- 請遵守 SYSTEM_PROMPT 中的角色定位、事實邊界、圖文對齊、語氣合規、對話節奏與 news_reference 規則。
- subtitle_text 必須是精簡字幕，不超過 25 個中文字；不要直接複製完整 spoken_text。
- visual_reference 必須指出本 turn 對應的圖上實際可見或應該可見物件、標籤、數字或 scene_id；如果圖片尚未生成，填 scene_id 或「待生成」。
- news_reference 必須列出本 turn 用到的新聞 / 政策 / 數據線索；沒有就填空陣列。
- estimated_seconds 請以中文 TTS 合理語速估算，單一 turn 原則上不超過 35 秒。

輸出 JSON 結構：

{
  "meta": {
    "source": "scene_inputs derived from weekly_forest_summary_analysis_layer_test.json + visual_manifest.json",
    "week_range": "",
    "script_type": "video_dialogue_script_test",
    "version_note": "Step 82 v4 test version: scene-specific analysis materials"
  },
  "dialogue_structure": {
    "total_scenes": 0,
    "estimated_duration_minutes": "",
    "style_note": "",
    "scene_order_source": "scene_inputs"
  },
  "scene_dialogues": [
    {
      "scene_id": "",
      "scene_title": "",
      "visual_file": "",
      "scene_goal": "",
      "scene_narrative_role": "主題導入 / 分析展開 / 小結提問 / 轉場",
      "speaker_turns": [
        {
          "turn_id": "s01_t01",
          "speaker": "Tom",
          "spoken_text": "",
          "subtitle_text": "",
          "visual_reference": "",
          "news_reference": [],
          "estimated_seconds": 0
        }
      ],
      "scene_transition": {
        "transition_question": "",
        "next_scene_hint": ""
      }
    }
  ],
  "full_script_plain_text": "",
  "tts_notes": {
    "voice_pair": "Tom / Miranda",
    "pace": "",
    "speaking_rate": 4.7,
    "avoid_terms": []
  }
}

scene_inputs：
{scene_inputs_json}
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


def compact_json(data: Any, max_chars: int = 100000) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（內容過長，已截斷；請只使用可見內容）"


def has_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict)):
        return len(value) > 0
    return True


def build_visual_map(visual_manifest: Dict[str, Any]) -> Dict[str, Dict[str, str]]:
    visual_map: Dict[str, Dict[str, str]] = {}
    scenes = visual_manifest.get("scenes", [])
    if not isinstance(scenes, list):
        return visual_map

    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = str(scene.get("scene_id", "")).strip()
        if not scene_id:
            continue
        visual_map[scene_id] = {
            "image_path": str(scene.get("image_path", "") or scene.get("visual_file", "") or ""),
            "title": str(scene.get("title", "") or scene.get("scene_title", "") or ""),
            "status": str(scene.get("status", "") or ""),
        }

    return visual_map


def extract_scene_material(
    analysis: Dict[str, Any],
    scene_def: Dict[str, Any],
    process: Dict[str, Any],
) -> Dict[str, Any]:
    analysis_key = scene_def["analysis_key"]
    material: Dict[str, Any] = {
        analysis_key: process.get(analysis_key, {}),
    }

    for extra_key in scene_def.get("also_use", []):
        if extra_key == "forest_summary":
            material["forest_summary"] = analysis.get("forest_summary", {})
        else:
            material[extra_key] = process.get(extra_key, {})

    return material


def build_scene_inputs(analysis: Dict[str, Any], visual_manifest: Dict[str, Any]) -> Dict[str, Any]:
    process = analysis.get("main_theme_analysis_process", {})
    if not isinstance(process, dict):
        process = {}

    evidence = analysis.get("evidence", {})
    visual_map = build_visual_map(visual_manifest)
    scene_inputs: List[Dict[str, Any]] = []

    for scene_def in CANONICAL_ANALYSIS_SCENES:
        required_keys = scene_def.get("required_if_any", [scene_def["analysis_key"]])
        if not any(has_content(process.get(key)) for key in required_keys):
            continue

        scene_id = scene_def["scene_id"]
        visual_info = visual_map.get(scene_id, {})
        primary_material = extract_scene_material(analysis, scene_def, process)

        allowed_supporting_material: Dict[str, Any] = {
            "evidence_scope": evidence,
        }

        # Only conclusion scene may receive forest_summary.
        if scene_def["analysis_key"] == "weekly_main_theme_conclusion":
            allowed_supporting_material["forest_summary"] = analysis.get("forest_summary", {})

        scene_inputs.append({
            "scene_id": scene_id,
            "scene_title": scene_def["scene_title"],
            "scene_role": scene_def.get("role", ""),
            "primary_material_keys": list(primary_material.keys()),
            "primary_material": primary_material,
            "allowed_supporting_material": allowed_supporting_material,
            "visual_file": visual_info.get("image_path", ""),
            "visual_status": visual_info.get("status", "not_generated") if visual_info else "not_generated",
            "visual_note": (
                "圖片已生成，可依圖卡短標籤作為視覺錨點。"
                if visual_info.get("image_path")
                else "圖片尚未生成，請以 scene_title 與 primary_material 作為語音錨點。"
            ),
        })

    # Preserve future analysis sections instead of silently dropping them.
    known_keys = set()
    for scene in scene_inputs:
        known_keys.update(scene.get("primary_material_keys", []))

    for key, value in process.items():
        if key in known_keys or not has_content(value):
            continue
        scene_index = len(scene_inputs) + 1
        safe_key = re.sub(r"[^a-z0-9_]+", "_", key.lower())
        scene_inputs.append({
            "scene_id": f"scene_{scene_index:02d}_{safe_key}",
            "scene_title": key,
            "scene_role": "新增分析段落，請根據 primary_material 轉成語音稿。",
            "primary_material_keys": [key],
            "primary_material": {key: value},
            "allowed_supporting_material": {"evidence_scope": evidence},
            "visual_file": "",
            "visual_status": "not_generated",
            "visual_note": "圖片尚未生成，請以 scene_title 與 primary_material 作為語音錨點。",
        })

    return {
        "source": "analysis_json.main_theme_analysis_process",
        "rule": "Each scene receives only its own analysis subsection as primary material. forest_summary is restricted to weekly_main_theme_conclusion.",
        "total_scenes": len(scene_inputs),
        "scenes": scene_inputs,
    }


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
    scene_inputs = build_scene_inputs(analysis, visual_manifest)

    print(f"[INFO] Scene input count: {scene_inputs.get('total_scenes', 0)}")
    for scene in scene_inputs.get("scenes", []):
        print(
            f"[INFO] Scene: {scene.get('scene_id')} | "
            f"keys={scene.get('primary_material_keys')} | "
            f"visual_status={scene.get('visual_status')} | "
            f"visual_file={scene.get('visual_file') or '(none)'}"
        )

    # Save scene inputs for debugging, without requiring another API call to inspect.
    save_json(week_dir / "weekly_dialogue_scene_inputs_debug.json", scene_inputs)

    return USER_PROMPT_TEMPLATE.replace(
        "{scene_inputs_json}",
        compact_json(scene_inputs, max_chars=100000),
    )


def build_markdown(result: Dict[str, Any]) -> str:
    lines: List[str] = []
    meta = result.get("meta", {}) or {}
    lines.append("# Weekly Dialogue Script Analysis Layer Test")
    lines.append("")
    if meta.get("week_range"):
        lines.append(f"- Week: {meta.get('week_range')}")
    lines.append(f"- Type: {meta.get('script_type', 'video_dialogue_script_test')}")
    lines.append("")

    scenes = result.get("scene_dialogues") or result.get("scenes") or []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        scene_id = scene.get("scene_id", "")
        title = scene.get("scene_title", "")
        lines.append(f"## {scene_id}｜{title}".strip())

        visual_file = scene.get("visual_file", "")
        if visual_file:
            lines.append(f"**Visual file:** {visual_file}")
        goal = scene.get("scene_goal", "")
        if goal:
            lines.append(f"**Scene goal:** {goal}")
        if visual_file or goal:
            lines.append("")

        turns = scene.get("speaker_turns") or scene.get("dialogue") or []
        for item in turns:
            if not isinstance(item, dict):
                continue
            speaker = item.get("speaker", "")
            text = item.get("spoken_text") or item.get("line", "")
            subtitle = item.get("subtitle_text", "")
            visual_reference = item.get("visual_reference", "")
            news_reference = item.get("news_reference", [])
            estimated_seconds = item.get("estimated_seconds", "")

            if speaker or text:
                lines.append(f"**{speaker}：** {text}")
                if subtitle:
                    lines.append(f"  - 字幕：{subtitle}")
                if visual_reference:
                    lines.append(f"  - 視覺：{visual_reference}")
                if news_reference:
                    lines.append(f"  - 參考：{', '.join(map(str, news_reference))}")
                if estimated_seconds:
                    lines.append(f"  - 秒數：{estimated_seconds}")
                lines.append("")

        transition = scene.get("scene_transition", {})
        if isinstance(transition, dict):
            tq = transition.get("transition_question", "")
            nh = transition.get("next_scene_hint", "")
            if tq or nh:
                lines.append(f"_Transition: {tq} {nh}_".strip())
                lines.append("")
        elif isinstance(transition, str) and transition:
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
