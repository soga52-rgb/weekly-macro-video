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
你是一位總經週報影片主編、總經分析師與視覺導演。

請根據本週資料，產生一支「本週總經傳導圖解導讀影片」。
這不是一般新聞摘要，而是用 6 個 scene 帶觀眾理解：
事件 / 數據 → 市場定價 → 資產反應 → 修正因子 → 下週驗證。

核心原則：
- Scene 01 固定是全局總經傳導地圖，使用 weekly_macro_diagram.png。
- Scene 02：本週最重要的驅動因子。
- Scene 03：核心市場變數如何反應。
- Scene 04：主要資產外溢影響。
- Scene 05：本週修正因子、背離或交叉驗證。
- Scene 06：下週觀察重點。
- 每頁只講一個重點。
- 每頁都要引用至少一個數據或新聞證據。
- 旁白要像總經分析師導讀，不要像新聞摘要。
- 圖卡要像總經簡報，不要像抽象插畫。
- 圖卡需包含：明確標題、2～3 個重點、1 條簡單傳導箭頭、1 句結論。
- 不要畫天平、漩渦、純 checklist、過度抽象符號。
- NotebookLM / 白板筆記風：米白底、淺灰網格、黑色手繪線、橘色重點、少量海軍藍。
- 對市場判斷要克制，不要聳動，不要投資建議。

嚴格輸出 JSON，不要 Markdown，不要額外說明。
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
                    "transmission_sentence": "用一句話說明本頁在總經傳導鏈中的位置",
                    "map_role": "起點 / 核心傳導 / 資產反應 / 修正因子 / 下週驗證"
                },
                "visual_direction": "給圖卡導演看的畫面說明",
                "image_prompt": "給 image model 的完整 prompt；scene_01 可寫 reuse weekly_macro_diagram.png",
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

影片定位：
- 這是一支「本週總經傳導圖解導讀影片」。
- Scene 01 是 narrative map / transmission map，用 weekly_macro_diagram.png 開場。
- Scene 02~Scene 06 依本週資料整理成 6 個清楚分鏡，不要做成單點新聞摘要。

建議分鏡：
- scene_01：總經傳導地圖總覽。
- scene_02：本週最重要的驅動因子。
- scene_03：核心市場變數如何反應。
- scene_04：主要資產外溢影響。
- scene_05：本週修正因子、背離或交叉驗證。
- scene_06：下週觀察重點。

每個 scene 請做到：
- 每頁只講一個重點。
- 每頁都要引用至少一個數據或新聞證據。
- narration_dialogue 要像總經分析師導讀，不要像新聞摘要。
- image_prompt 要服務旁白，畫面要像總經簡報圖卡。
- 圖卡需包含：明確標題、2～3 個重點、1 條簡單傳導箭頭、1 句結論。
- 不要畫天平、漩渦、純 checklist、過度抽象符號。
- 圖卡少字、重點明確、畫面乾淨。

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
