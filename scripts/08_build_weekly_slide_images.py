# Save as: scripts/08_build_weekly_slide_images.py
# -*- coding: utf-8 -*-
"""
08 - Build Weekly Slide Images with Gemini Image Model
TTS / IMAGE 同源版：
- Scene 01：沿用 weekly_macro_diagram.png
- Scene 02~06：讀取與 TTS 相同的來源資料，依每段旁白自動產生 NotebookLM 風格圖卡
- 不硬寫 Scene 02 一定是油價、Scene 03 一定是利率
- 每頁 prompt 會保存到 output/weekly/YYYY-MM-DD/slides/prompts/
- 若 Gemini image model 暫時 500/502，會保留舊圖；若沒有舊圖，先用 scene_01 作為 fallback，避免 workflow 中斷
"""

import base64
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview").strip()
IMAGE_MODEL_FALLBACKS = [
    x.strip()
    for x in os.getenv("IMAGE_MODEL_FALLBACKS", "gemini-2.5-flash-image").split(",")
    if x.strip()
]
FORCE_REBUILD_SLIDES = os.getenv("FORCE_REBUILD_SLIDES", "true").lower() == "true"
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "90"))
MAX_IMAGE_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "1"))
IMAGE_RETRY_SLEEP_SECONDS = int(os.getenv("IMAGE_RETRY_SLEEP_SECONDS", "10"))

SCENE_IDS = ["scene_01", "scene_02", "scene_03", "scene_04", "scene_05", "scene_06"]


STYLE_RULES = """
你是一位總經週報影片的視覺導演，請根據提供的同源資料，為該 scene 產生一張 16:9 靜態圖卡。

整體風格：
- NotebookLM / 白板筆記風格
- 米白或白色底，淺灰網格紋理
- 黑色手繪線條，橘色重點標註，少量海軍藍文字
- 單頁只講一件事
- 少字、強視覺、弱邊框
- 不要厚重資訊框，不要 dashboard 感，不要 Bloomberg 終端機感
- 不要顯示 Scene 編號、目前焦點、工程標籤
- 不要把旁白逐字稿塞滿畫面
- 畫面是旁白的視覺導引，不是完整講稿

內容規則：
- 請依該 scene 的旁白與同源資料，自行判斷最適合的主視覺
- 主視覺應取自本週總經主線，不要硬套固定主題
- 若需要數字，請只使用提供的 market data，不要自行發明
- 若需要新聞，請只使用提供的 news lines，不要自行發明
- 數字要大，單位要小
- 右側或下方文字最多 3 個短句
- 新聞最多 1~2 則，短句化呈現
- 中文請使用繁體中文，簡潔、可讀
""".strip()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text, encoding="utf-8")


def compact_json(obj: Any, max_chars: int = 8000) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（以下省略，請只根據已提供資料作圖）"


def find_latest_week_dir() -> Path:
    explicit = os.getenv("WEEK_END_DATE", "").strip() or os.getenv("WEEK_DATE", "").strip()
    if explicit:
        candidate = OUTPUT_WEEKLY_DIR / explicit
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"指定週資料夾不存在：{candidate}")

    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("找不到 output/weekly 下的週資料夾")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def find_first_existing(paths: List[Path]) -> Optional[Path]:
    for p in paths:
        if p.exists():
            return p
    return None


def load_week_context(week_dir: Path) -> Dict[str, Any]:
    return {
        "forest": read_json(find_first_existing([
            week_dir / "weekly_forest_summary.json",
            week_dir / "data" / "weekly_forest_summary.json",
            week_dir / "final" / "weekly_forest_summary.json",
        ]) or Path("__missing__"), {}),
        "news": read_json(find_first_existing([
            week_dir / "weekly_news_context.json",
            week_dir / "data" / "weekly_news_context.json",
            week_dir / "final" / "weekly_news_context.json",
        ]) or Path("__missing__"), {}),
        "market": read_json(find_first_existing([
            week_dir / "weekly_market_series.json",
            week_dir / "data" / "weekly_market_series.json",
            week_dir / "final" / "weekly_market_series.json",
        ]) or Path("__missing__"), {}),
        "narration": read_json(find_first_existing([
            week_dir / "weekly_narration.json",
            week_dir / "narration" / "weekly_narration.json",
            week_dir / "final" / "weekly_narration.json",
        ]) or Path("__missing__"), {}),
    }


def find_diagram_path(week_dir: Path) -> Optional[Path]:
    return find_first_existing([
        week_dir / "weekly_macro_diagram.png",
        week_dir / "final" / "weekly_macro_diagram.png",
        week_dir / "data" / "weekly_macro_diagram.png",
        week_dir / "images" / "weekly_macro_diagram.png",
    ])


def get_scenes(narration: Dict[str, Any]) -> List[Dict[str, Any]]:
    scenes = narration.get("scenes", [])
    if not isinstance(scenes, list):
        scenes = []
    scene_map = {
        str(s.get("scene_id", f"scene_{i+1:02d}")): s
        for i, s in enumerate(scenes)
        if isinstance(s, dict)
    }

    normalized = []
    for scene_id in SCENE_IDS:
        item = scene_map.get(scene_id, {"scene_id": scene_id})
        item["scene_id"] = scene_id
        normalized.append(item)
    return normalized


def market_digest(market: Dict[str, Any], max_assets: int = 10) -> List[Dict[str, Any]]:
    rows = []
    for item in market.get("series", []) or []:
        if not isinstance(item, dict):
            continue
        key = item.get("asset_key") or item.get("key") or item.get("asset")
        label = item.get("asset") or item.get("label") or key
        unit = item.get("unit", "")
        points = item.get("points") or item.get("values") or item.get("series") or []
        latest = None
        prev = None
        if isinstance(points, list) and points:
            def value_of(x):
                if isinstance(x, dict):
                    return x.get("value", x.get("close", x.get("price")))
                return x
            latest = value_of(points[-1])
            if len(points) >= 2:
                prev = value_of(points[-2])
        rows.append({
            "key": key,
            "label": label,
            "latest": latest,
            "previous": prev,
            "unit": unit,
        })
        if len(rows) >= max_assets:
            break
    return rows


def flatten_news(news: Dict[str, Any], max_items: int = 12) -> List[Dict[str, str]]:
    out = []

    def add_items(arr):
        for item in arr or []:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or item.get("headline") or "").strip()
            if not title:
                continue
            source = str(item.get("source") or item.get("publisher") or item.get("site") or "").strip()
            theme = str(item.get("theme") or item.get("category") or item.get("macro_category") or "").strip()
            summary = str(item.get("summary") or item.get("description") or item.get("why_it_matters") or "").strip()
            out.append({
                "source": source,
                "theme": theme,
                "title": title,
                "summary": summary,
            })
            if len(out) >= max_items:
                return

    for k in ["top_news", "items", "news", "articles"]:
        arr = news.get(k)
        if isinstance(arr, list):
            add_items(arr)
            if len(out) >= max_items:
                return out

    for k in ["categories", "news_by_category", "classified", "by_category"]:
        obj = news.get(k)
        if isinstance(obj, dict):
            for cat, arr in obj.items():
                if isinstance(arr, list):
                    for item in arr:
                        if isinstance(item, dict):
                            item = dict(item)
                            item.setdefault("category", cat)
                            add_items([item])
                            if len(out) >= max_items:
                                return out
    return out[:max_items]


def scene_text(scene: Dict[str, Any]) -> str:
    parts = []
    for k in ["scene_title", "on_screen_title", "summary", "narration", "voiceover", "script"]:
        v = scene.get(k)
        if isinstance(v, str) and v.strip():
            parts.append(f"{k}: {v.strip()}")
    dialogue = scene.get("dialogue")
    if isinstance(dialogue, list):
        lines = []
        for d in dialogue:
            if isinstance(d, dict):
                speaker = d.get("speaker", "")
                text = d.get("text", "")
                if text:
                    lines.append(f"{speaker}: {text}")
        if lines:
            parts.append("dialogue:\n" + "\n".join(lines[:10]))
    bullets = scene.get("on_screen_bullets")
    if isinstance(bullets, list) and bullets:
        parts.append("on_screen_bullets:\n" + "\n".join([str(x) for x in bullets[:5]]))
    return "\n".join(parts).strip()


def build_prompt(scene: Dict[str, Any], context: Dict[str, Any], diagram_attached: bool) -> str:
    scene_id = scene["scene_id"]

    if scene_id == "scene_01":
        return ""

    forest = context["forest"]
    news = context["news"]
    market = context["market"]

    forest_brief = {
        "meta": forest.get("meta", {}),
        "forest_summary": forest.get("forest_summary", {}),
        "macro_storyline": forest.get("macro_storyline", {}),
        "macro_variables": forest.get("macro_variables", {}),
        "evidence": forest.get("evidence", {}),
        "video_planning": forest.get("video_planning", {}),
    }

    prompt = f"""
{STYLE_RULES}

本頁 scene_id：{scene_id}

這是 TTS 旁白產生時同源的資料。請讓圖卡與旁白同步，而不是硬套固定版型。

【本 scene 旁白 / 對話 / 畫面重點】
{scene_text(scene) or "無明確旁白，請根據共同資料判斷本頁視覺重點。"}

【本週總經主線與解讀摘要】
{compact_json(forest_brief, max_chars=6500)}

【本週市場數據摘要】
{compact_json(market_digest(market), max_chars=3000)}

【本週新聞候選摘要】
{compact_json(flatten_news(news), max_chars=5000)}

【總經傳導圖】
{"已隨附 weekly_macro_diagram.png，請只拿來理解視覺語言與傳導關係；不要直接截圖拼貼，也不要畫完整小地圖。" if diagram_attached else "未隨附圖檔，請根據文字資料作圖。"}

輸出要求：
- 只產出一張 16:9 圖卡
- 畫面要和該 scene 旁白同步
- 請自行決定本頁最重要的主視覺、關鍵數字與新聞證據
- 字要少，不要塞滿；資訊過多時優先保留主視覺、大數字、1~3 個短句
- 若本頁是結尾 / 下週觀察，請做成滿版觀察重點頁
""".strip()

    return prompt


def encode_image_part(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    suffix = path.suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
    }.get(suffix)
    if not mime:
        return None
    return {
        "inlineData": {
            "mimeType": mime,
            "data": base64.b64encode(path.read_bytes()).decode("utf-8"),
        }
    }


def call_gemini_image(prompt: str, reference_images: List[Path]) -> bytes:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    model_candidates = [IMAGE_MODEL] + [m for m in IMAGE_MODEL_FALLBACKS if m != IMAGE_MODEL]
    ref_parts = []
    for path in reference_images:
        part = encode_image_part(path)
        if part:
            ref_parts.append(part)

    last_error = ""
    for model in model_candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": prompt}] + ref_parts,
            }],
            "generationConfig": {
                "temperature": 0.65,
            },
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(1, MAX_IMAGE_RETRIES + 1):
            print(f"[INFO] call image model: {model}, attempt {attempt}/{MAX_IMAGE_RETRIES}")
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as resp:
                    raw = resp.read()
                res = json.loads(raw.decode("utf-8"))
                for cand in res.get("candidates", []) or []:
                    content = cand.get("content", {}) or {}
                    for part in content.get("parts", []) or []:
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            return base64.b64decode(inline["data"])
                last_error = f"{model} returned no image data"
                print(f"[WARN] {last_error}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = f"{model} HTTP {exc.code}: {detail[:500]}"
                print(f"[WARN] {last_error}")
            except Exception as exc:
                last_error = f"{model}: {exc}"
                print(f"[WARN] {last_error}")

            if attempt < MAX_IMAGE_RETRIES:
                time.sleep(IMAGE_RETRY_SLEEP_SECONDS)

    raise RuntimeError(f"All image model calls failed. Last error: {last_error}")


def fallback_slide(output_path: Path, diagram_path: Optional[Path], reason: str) -> None:
    if output_path.exists():
        print(f"[WARN] keep existing slide: {output_path.name}; reason={reason}")
        return
    if diagram_path and diagram_path.exists():
        shutil.copy2(diagram_path, output_path)
        print(f"[WARN] fallback to diagram for {output_path.name}; reason={reason}")
        return
    raise RuntimeError(f"Cannot create fallback slide for {output_path.name}: {reason}")


def main() -> None:
    week_dir = find_latest_week_dir()
    slides_dir = week_dir / "slides"
    prompts_dir = slides_dir / "prompts"
    ensure_dir(slides_dir)
    ensure_dir(prompts_dir)

    context = load_week_context(week_dir)
    scenes = get_scenes(context["narration"])
    diagram_path = find_diagram_path(week_dir)

    if not diagram_path:
        print("[WARN] weekly_macro_diagram.png not found; scene_01 fallback may fail.")

    records = []

    for scene in scenes:
        scene_id = scene["scene_id"]
        out_path = slides_dir / f"{scene_id}.png"

        if scene_id == "scene_01":
            if FORCE_REBUILD_SLIDES or not out_path.exists():
                if diagram_path and diagram_path.exists():
                    shutil.copy2(diagram_path, out_path)
                    print(f"[OK] scene_01 copied from {diagram_path}")
                else:
                    raise RuntimeError("scene_01 requires weekly_macro_diagram.png")
            records.append({"scene_id": scene_id, "path": str(out_path), "mode": "copy_diagram"})
            continue

        prompt = build_prompt(scene, context, diagram_attached=bool(diagram_path and diagram_path.exists()))
        prompt_path = prompts_dir / f"{scene_id}_prompt.txt"
        write_text(prompt_path, prompt)

        generated_ok = True
        if FORCE_REBUILD_SLIDES or not out_path.exists():
            try:
                image_bytes = call_gemini_image(
                    prompt=prompt,
                    reference_images=[diagram_path] if diagram_path and diagram_path.exists() else [],
                )
                out_path.write_bytes(image_bytes)
                print(f"[OK] wrote {out_path}")
            except Exception as exc:
                generated_ok = False
                fallback_slide(out_path, diagram_path, str(exc))

        records.append({
            "scene_id": scene_id,
            "path": str(out_path),
            "prompt": str(prompt_path),
            "mode": "image_from_tts_source",
            "generated_ok": generated_ok,
        })

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "week_dir": str(week_dir),
        "image_model": IMAGE_MODEL,
        "records": records,
    }
    (slides_dir / "slides_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (week_dir / "weekly_slide_images_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] slides ready: {slides_dir}")


if __name__ == "__main__":
    main()
