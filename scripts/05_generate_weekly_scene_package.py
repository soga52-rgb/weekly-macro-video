# Save as: scripts/05_generate_weekly_scene_package.py
# -*- coding: utf-8 -*-
"""
05 - Generate weekly_scene_package.json with Gemini Pro

Purpose:
- Pro acts as the weekly video editor-in-chief.
- It reads the same source universe that narration/TTS and image cards should share.
- It outputs ONE scene package used by both:
  1) TTS branch: narration_dialogue / narration_text
  2) IMAGE branch: image_prompt / visual_direction

Important:
- Do NOT hard-code scene_02=oil, scene_03=rates, scene_04=dollar, scene_05=gold.
- Scene roles should grow from the weekly macro narrative.
- Scene 01 remains the full macro transmission diagram opening.
"""

import json
import os
import re
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro").strip()
GEMINI_FALLBACK_MODELS = [
    x.strip()
    for x in os.getenv("GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-2.5-flash").split(",")
    if x.strip()
]
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "240"))
MAX_RETRIES = int(os.getenv("GEMINI_MAX_RETRIES", "2"))
RETRY_SLEEP_SECONDS = int(os.getenv("GEMINI_RETRY_SLEEP_SECONDS", "20"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Optional[Path], default: Any = None) -> Any:
    if not path or not path.exists():
        return default if default is not None else {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_text(path: Optional[Path]) -> str:
    if not path or not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def write_json(path: Path, obj: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def find_latest_week_dir() -> Path:
    explicit = os.getenv("WEEK_END_DATE", "").strip() or os.getenv("WEEK_DATE", "").strip()
    if explicit:
        p = OUTPUT_WEEKLY_DIR / explicit
        if not p.exists():
            raise FileNotFoundError(f"指定週資料夾不存在：{p}")
        return p
    dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not dirs:
        raise FileNotFoundError("找不到 output/weekly 下的週資料夾")
    dirs.sort(key=lambda p: p.name, reverse=True)
    return dirs[0]


def first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def compact(obj: Any, max_chars: int = 12000) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=2) if not isinstance(obj, str) else obj
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（已截斷，請只根據可見資料判斷，不要自行補造）"


def load_week_context(week_dir: Path) -> Dict[str, Any]:
    return {
        "forest": read_json(first_existing([
            week_dir / "weekly_forest_summary.json",
            week_dir / "data" / "weekly_forest_summary.json",
            week_dir / "final" / "weekly_forest_summary.json",
        ]), {}),
        "news": read_json(first_existing([
            week_dir / "weekly_news_context.json",
            week_dir / "data" / "weekly_news_context.json",
            week_dir / "final" / "weekly_news_context.json",
        ]), {}),
        "market": read_json(first_existing([
            week_dir / "weekly_market_series.json",
            week_dir / "data" / "weekly_market_series.json",
            week_dir / "final" / "weekly_market_series.json",
        ]), {}),
        "macro_page_text": read_text(first_existing([
            week_dir / "weekly_macro_page_text.txt",
            week_dir / "final" / "weekly_macro_page_text.txt",
            week_dir / "weekly_page_text.txt",
            week_dir / "final" / "weekly_page_text.txt",
        ])),
        "diagram_prompt": read_text(first_existing([
            week_dir / "weekly_macro_diagram_prompt.txt",
            week_dir / "final" / "weekly_macro_diagram_prompt.txt",
            week_dir / "data" / "weekly_macro_diagram_prompt.txt",
        ])),
    }


def system_instruction() -> str:
    return """
你是一位總經週報影片總編輯、總經分析師、財經節目編劇與視覺導演。

你要根據本週資料建立一條有因果關係的「總經敘事」，並同時規劃：
1. TTS 語音旁白
2. IMAGE 圖卡生成提示詞

核心原則：
- 不要把 scene_02~scene_06 的主題寫死；請根據本週資料自己決定本週最合理分鏡。
- Scene 01 固定是全局開場，使用 weekly_macro_diagram.png 作為畫面主體。
- Scene 02~Scene 05 應依本週主線自然拆解：核心驅動、核心傳導、外溢影響、修正因子或交叉驗證。
- Scene 06 通常作為下週觀察或結尾收斂；但具體重點要依本週資料決定。
- 每個 scene 都要同時輸出 narration_dialogue 與 image_prompt。
- 圖卡是旁白的視覺導引，不是把旁白全文塞進畫面。
- 圖卡風格固定為 NotebookLM / 白板筆記風：米白底、淺灰網格、黑色手繪線、橘色重點、少量海軍藍、少字、強視覺、弱邊框。
- 對市場判斷要客觀克制，不要聳動，不要投資建議。

上午 narration 成功版本的核心邏輯必須保留：
- 這不是一般財經新聞摘要，而是「本週總經傳導圖解」的導讀影片。
- Scene 01 不是結論頁，也不是 summary conclusion；Scene 01 是 narrative map / transmission map，作用是先給觀眾本週總經地圖。
- 影片採用「總覽先行，順敘展開」：先用 Scene 01 建立全局，再從傳導鏈起點一路往後拆解。
- 總經傳導圖是全片主角，旁白要帶觀眾沿著傳導鏈走。
- Scene 02~Scene 05 的主題不可硬寫死，但排序應優先遵守本週 core_transmission_chain 的因果順序：
  1. 傳導起點：例如通膨預期、油價、政策衝擊、就業或其他本週核心驅動。
  2. 核心傳導變數：例如利率、殖利率、降息預期、流動性。
  3. 中段資產反應：例如美元指數、風險偏好、信用或其他市場定價。
  4. 外溢資產 / 修正因子 / 交叉驗證：例如亞洲貨幣、黃金、成長擔憂、房市或其他反向力量。
- 若本週資料顯示另一種傳導順序更合理，可以調整，但每頁仍必須交代與 core_transmission_chain 的關係。
- Scene 06 用於下週觀察重點，收斂「哪些數據或事件會驗證這條傳導鏈是否延續或翻轉」。
- 每段都要明確呈現：市場走勢或數據變化 → 新聞/事件原因 → 市場解讀 → 回到總經傳導鏈。
- 不要只做單點主題頁；scene_02~scene_05 每頁都必須說明自己在 core_transmission_chain 裡的位置。
- 每個 scene 的 narration_dialogue 必須回答：
  1. 本頁接續上一頁哪個總經節點？
  2. 本頁變數如何推動下一個節點？
  3. 哪個資產數據或新聞證據驗證這段傳導？
- image_prompt 也必須保留這種鏈條感，但不要回到複雜小地圖；請用單頁主視覺呈現「上一節點 → 本頁節點 → 下一節點」或「主線 → 修正因子 → 資產反應」。

- 嚴格輸出 JSON，不要 Markdown，不要額外說明。
""".strip()


def build_prompt(context: Dict[str, Any]) -> str:
    schema = {
        "meta": {
            "generated_at": "ISO timestamp",
            "package_version": "scene_package_v1",
            "scene_count": 6,
            "main_theme": "本週總經主題，一句話",
            "core_transmission_chain": ["節點1", "節點2", "節點3"],
            "primary_driver": "本週最重要驅動",
            "revision_factor": "主要修正因子或反向風險"
        },
        "scenes": [
            {
                "scene_id": "scene_01",
                "scene_role": "opening_overview / transmission_start / core_transmission / asset_reaction / revision_or_cross_validation / conclusion_and_outlook",
                "narrative_order": 1,
                "scene_title": "本頁標題",
                "scene_purpose": "本頁存在目的",
                "narrative_focus": "本頁敘事重點",
                "supporting_assets": ["asset_key"],
                "supporting_news": ["新聞標題或新聞類型"],
                "chain_position": {
                    "previous_node": "上一個總經節點，若無則空字串",
                    "current_node": "本頁所在總經節點",
                    "next_node": "下一個總經節點，若無則空字串",
                    "transmission_sentence": "用一句話說明上一節點如何傳到本頁、本頁如何影響下一節點",
                    "map_role": "本頁在 Scene 01 總經傳導圖中的角色，例如：起點 / 中段傳導 / 資產反應 / 修正因子 / 下週驗證"
                },
                "visual_direction": "給圖卡導演看的畫面說明，必須說明本頁如何呈現傳導鏈位置",
                "image_prompt": "給 image model 的完整 prompt；scene_01 可寫 reuse weekly_macro_diagram.png；scene_02~06 必須保留傳導鏈語意",
                "on_screen_text": {
                    "headline": "短標題",
                    "key_numbers": [{"label": "DXY", "value": "99.3", "unit": ""}],
                    "short_bullets": ["最多三點"],
                    "news_lines": ["最多二則"]
                },
                "narration_dialogue": [
                    {"speaker": "host", "text": "主持人台詞"},
                    {"speaker": "analyst", "text": "分析師台詞"}
                ],
                "tts_notes": "語速、停頓、強調提示，可空白"
            }
        ]
    }

    return f"""
請根據以下同源資料，產出 weekly_scene_package.json。

重要：
- 先判讀本週資料，再決定 scene_02~scene_06 的分工。
- 不要硬套 scene_02=油價、scene_03=利率、scene_04=美元、scene_05=黃金。
- 若本週主線剛好是這樣，才可以如此安排；否則依本週資料調整。
- Scene 01 固定為 weekly_macro_diagram.png 開場。
- Scene 02~06 要同時服務 TTS 與 IMAGE。
- 每個 scene 的 narration_dialogue 與 image_prompt 必須講同一件事。
- 但你必須保留上午 narration 的成功邏輯：這是一支「總經傳導圖解導讀影片」，不是單點新聞評論。
- Scene 01 要定位為 narrative map / transmission map，不是 conclusion summary。它先給觀眾本週地圖。
- Scene 02~Scene 05 要採「順敘展開」：優先沿著 core_transmission_chain 的因果順序逐段導讀。
- Scene 02 通常應承接傳導起點；Scene 03 承接核心傳導；Scene 04 承接中段資產反應；Scene 05 承接外溢資產、修正因子或交叉驗證；但若本週資料顯示其他排列更合理，可由你動態調整。
- Scene 06 收斂成下週觀察，重點是哪些事件或數據會驗證這條傳導鏈延續、翻轉或被修正。
- scene_02~scene_05 不能只是孤立主題，必須沿著 core_transmission_chain 逐段導讀。
- 每頁都要輸出 narrative_order 與 chain_position，說明 previous_node、current_node、next_node、map_role 與 transmission_sentence。
- narration_dialogue 中請自然說出這段傳導關係，例如「上一段我們看到...，這會推動...，因此下一步要看...」。
- image_prompt 中也請描述本頁的鏈條角色，例如「用簡化的三節點或因果箭頭呈現：上一節點 → 本頁節點 → 下一節點」，但畫面仍要少字、單一主視覺。

輸出 JSON schema 範例：
{json.dumps(schema, ensure_ascii=False, indent=2)}

【weekly_forest_summary】
{compact(context.get("forest", {}), 15000)}

【weekly_market_series】
{compact(context.get("market", {}), 11000)}

【weekly_news_context】
{compact(context.get("news", {}), 15000)}

【weekly_macro_page_text】
{compact(context.get("macro_page_text", ""), 9000)}

【weekly_macro_diagram_prompt_or_context】
{compact(context.get("diagram_prompt", ""), 6000)}

請輸出一份完整 JSON：
- meta
- scenes：必須剛好 6 個 scene，scene_id 從 scene_01 到 scene_06
- scene_01 的 image_prompt 請標註 reuse weekly_macro_diagram.png
- scene_02~scene_06 的 image_prompt 必須可直接交給 IMAGE model 畫 16:9 圖卡
""".strip()


def extract_json(text: str) -> Dict[str, Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?", "", raw).strip()
        raw = re.sub(r"```$", "", raw).strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return json.loads(raw[start:end + 1])
    raise ValueError("Gemini response does not contain valid JSON")


def call_gemini_text(prompt: str) -> Dict[str, Any]:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACK_MODELS if m != GEMINI_MODEL]
    last_error = ""

    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "system_instruction": {"parts": [{"text": system_instruction()}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.45,
                "responseMimeType": "application/json"
            }
        }
        data = json.dumps(payload).encode("utf-8")
        for attempt in range(1, MAX_RETRIES + 1):
            print(f"[INFO] call Gemini text model={model}, attempt={attempt}/{MAX_RETRIES}")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as resp:
                    raw = resp.read()
                res = json.loads(raw.decode("utf-8"))
                text_parts = []
                for cand in res.get("candidates", []) or []:
                    for part in (cand.get("content", {}) or {}).get("parts", []) or []:
                        if "text" in part:
                            text_parts.append(part["text"])
                text = "\n".join(text_parts).strip()
                if not text:
                    raise RuntimeError("empty response text")
                return extract_json(text)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = f"{model} HTTP {exc.code}: {detail[:500]}"
                print(f"[WARN] {last_error}")
            except Exception as exc:
                last_error = f"{model}: {exc}"
                print(f"[WARN] {last_error}")
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)

    raise RuntimeError(f"All Gemini text calls failed. Last error: {last_error}")


def validate_package(pkg: Dict[str, Any]) -> Dict[str, Any]:
    scenes = pkg.get("scenes")
    if not isinstance(scenes, list):
        raise ValueError("weekly_scene_package missing scenes list")

    # Normalize to 6 scenes.
    scene_by_id = {}
    for i, scene in enumerate(scenes):
        if isinstance(scene, dict):
            sid = str(scene.get("scene_id") or f"scene_{i+1:02d}")
            scene_by_id[sid] = scene

    normalized = []
    for idx in range(1, 7):
        sid = f"scene_{idx:02d}"
        scene = scene_by_id.get(sid, {"scene_id": sid})
        scene["scene_id"] = sid
        scene.setdefault("narrative_order", idx)
        scene.setdefault("scene_title", "本週總經傳導地圖" if sid == "scene_01" else f"Scene {idx:02d}")
        scene.setdefault("narration_dialogue", [])
        scene.setdefault("image_prompt", "reuse weekly_macro_diagram.png" if sid == "scene_01" else "")
        if sid == "scene_01":
            scene.setdefault("scene_role", "opening_narrative_map")
            scene.setdefault("scene_purpose", "先給觀眾本週總經傳導地圖，作為後續順敘展開的導覽。")
        scene.setdefault("chain_position", {
            "previous_node": "",
            "current_node": "",
            "next_node": "",
            "transmission_sentence": "",
            "map_role": "總覽地圖" if sid == "scene_01" else ""
        })
        normalized.append(scene)

    # Keep exactly scene_01~scene_06 output names, but preserve the Pro-assigned narrative_order inside each scene.
    pkg["scenes"] = normalized
    meta = pkg.setdefault("meta", {})
    meta["generated_at"] = meta.get("generated_at") or datetime.utcnow().isoformat() + "Z"
    meta["package_version"] = meta.get("package_version") or "scene_package_v1"
    meta["scene_count"] = 6
    return pkg


def export_legacy_narration(week_dir: Path, pkg: Dict[str, Any]) -> None:
    """
    For compatibility with existing 06 TTS scripts.
    """
    narration = {
        "meta": pkg.get("meta", {}),
        "scenes": []
    }
    full_lines = []

    for scene in pkg["scenes"]:
        sid = scene["scene_id"]
        dialogue = scene.get("narration_dialogue", []) or []
        narration["scenes"].append({
            "scene_id": sid,
            "narrative_order": scene.get("narrative_order", ""),
            "scene_title": scene.get("scene_title", ""),
            "scene_purpose": scene.get("scene_purpose", ""),
            "chain_position": scene.get("chain_position", {}),
            "narrative_focus": scene.get("narrative_focus", ""),
            "on_screen_title": (scene.get("on_screen_text") or {}).get("headline", scene.get("scene_title", "")),
            "on_screen_bullets": (scene.get("on_screen_text") or {}).get("short_bullets", []),
            "dialogue": dialogue,
            "narration": "\n".join([f"{d.get('speaker','')}: {d.get('text','')}" for d in dialogue if isinstance(d, dict)])
        })
        full_lines.append(f"## {sid} {scene.get('scene_title','')}")
        for d in dialogue:
            if isinstance(d, dict):
                full_lines.append(f"{d.get('speaker','')}: {d.get('text','')}")
        full_lines.append("")

    write_json(week_dir / "weekly_narration.json", narration)
    ensure_dir(week_dir / "narration")
    write_json(week_dir / "narration" / "weekly_narration.json", narration)
    write_text(week_dir / "weekly_narration_full.txt", "\n".join(full_lines))


def main() -> None:
    week_dir = find_latest_week_dir()
    context = load_week_context(week_dir)
    prompt = build_prompt(context)

    ensure_dir(week_dir / "prompts")
    write_text(week_dir / "prompts" / "05_scene_package_prompt.txt", prompt)

    pkg = call_gemini_text(prompt)
    pkg = validate_package(pkg)

    write_json(week_dir / "weekly_scene_package.json", pkg)
    write_json(week_dir / "narration" / "weekly_scene_package.json", pkg)
    export_legacy_narration(week_dir, pkg)

    print(f"[OK] weekly_scene_package generated: {week_dir / 'weekly_scene_package.json'}")
    print(f"[OK] legacy narration generated: {week_dir / 'weekly_narration.json'}")


if __name__ == "__main__":
    main()
