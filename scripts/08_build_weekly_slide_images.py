# Save as: scripts/08_build_weekly_slide_images.py

import os
import re
import json
import base64
import urllib.request
import urllib.error
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = ROOT / "output" / "weekly"

IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image-preview")
IMAGE_MODEL_FALLBACKS = [
    s.strip() for s in os.getenv("IMAGE_MODEL_FALLBACKS", "gemini-2.5-flash-image").split(",") if s.strip()
]
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
FORCE_REBUILD_SLIDES = os.getenv("FORCE_REBUILD_SLIDES", "false").lower() == "true"
REQUEST_TIMEOUT = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "300"))
MAX_IMAGE_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "3"))
RETRY_SLEEP_SECONDS = int(os.getenv("IMAGE_RETRY_SLEEP_SECONDS", "20"))

SCENE_IMAGE_NAMES = {
    "scene_01": "scene_01.png",
    "scene_02": "scene_02.png",
    "scene_03": "scene_03.png",
    "scene_04": "scene_04.png",
    "scene_05": "scene_05.png",
    "scene_06": "scene_06.png",
}

ASSET_LABELS = {
    "US10Y": "美國10年期公債殖利率",
    "DXY": "美元指數",
    "Gold": "黃金",
    "WTI": "西德州原油",
    "Brent": "布蘭特原油",
    "USDJPY": "美元／日圓",
    "USDTWD": "美元／台幣",
    "USDKRW": "美元／韓元",
}

UNIT_SHORT = {
    "%": "%",
    "USD/bbl": "USD/bbl",
    "USD/oz": "USD/oz",
    "JPY": "JPY",
    "TWD": "TWD",
    "KRW": "KRW",
    "": "",
}

NOTEBOOK_STYLE = """
Design a static 16:9 slide in a NotebookLM-style whiteboard note aesthetic.
Visual style requirements:
- off-white / white background
- very subtle light gray grid texture
- black hand-drawn linework
- orange accent marks, circles, arrows, pins, highlights
- a small amount of navy-blue text or data emphasis
- airy layout, weak borders, no thick boxes, almost transparent panels
- elegant note-card feeling, like a clean visual explainer page
- no clutter, no dashboard feel, no Bloomberg terminal style
- visible text must be Traditional Chinese only
- use very little text; keep it short and highly readable
- numbers should be large, units very small
- the slide is visual guidance only; narration is the main body
""".strip()


def read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_week_end(meta: Dict[str, Any]) -> str:
    week_range = str(meta.get("week_range", "")).strip()
    m = re.search(r"(\d{4}-\d{2}-\d{2}).*?(\d{4}-\d{2}-\d{2})", week_range)
    if m:
        return m.group(2)
    env_week = os.getenv("WEEK_END_DATE", "").strip()
    if env_week:
        return env_week
    return datetime.utcnow().strftime("%Y-%m-%d")


def load_week_context(week_dir: Path) -> Dict[str, Any]:
    forest = read_json(week_dir / "weekly_forest_summary.json")
    news = read_json(week_dir / "weekly_news_context.json")
    market = read_json(week_dir / "weekly_market_series.json")
    narration = read_json(week_dir / "weekly_narration.json")
    plan = read_json(week_dir / "weekly_slide_plan.json")
    return {
        "forest": forest,
        "news": news,
        "market": market,
        "narration": narration,
        "plan": plan,
    }


def market_series_map(market: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for item in market.get("series", []) or []:
        key = item.get("asset_key")
        if key:
            result[key] = item
    return result


def latest_asset_text(series_item: Dict[str, Any]) -> str:
    points = series_item.get("points", []) or []
    if not points:
        return ""
    last = points[-1]
    value = last.get("value")
    unit = UNIT_SHORT.get(series_item.get("unit", ""), series_item.get("unit", ""))
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        if abs(value) >= 100:
            number = f"{value:,.1f}"
        elif abs(value) >= 10:
            number = f"{value:,.2f}"
        else:
            number = f"{value:,.3f}".rstrip("0").rstrip(".")
    else:
        number = str(value)
    return f"{number} {unit}".strip()


def latest_asset_block(series_map: Dict[str, Dict[str, Any]], asset_keys: List[str]) -> List[Dict[str, str]]:
    blocks = []
    for key in asset_keys:
        item = series_map.get(key)
        if not item:
            continue
        blocks.append({
            "key": key,
            "label": ASSET_LABELS.get(key, key),
            "value": latest_asset_text(item),
        })
    return blocks


def pick_news_lines(news: Dict[str, Any], keywords: List[str], limit: int = 2) -> List[str]:
    candidates = []
    for item in news.get("top_news", []) or []:
        title = str(item.get("title", "")).strip()
        source = str(item.get("source", "")).strip()
        theme = str(item.get("theme", "")).strip().lower()
        hay = f"{title} {source} {theme}".lower()
        score = sum(1 for kw in keywords if kw.lower() in hay)
        if score > 0:
            candidates.append((score, f"{source}｜{title}" if source else title))
    if not candidates:
        for item in (news.get("top_news", []) or [])[:limit]:
            title = str(item.get("title", "")).strip()
            source = str(item.get("source", "")).strip()
            if title:
                candidates.append((0, f"{source}｜{title}" if source else title))
    return [t for _, t in sorted(candidates, key=lambda x: x[0], reverse=True)[:limit]]


def short_points_from_text(items: List[str], limit: int = 3, max_len: int = 28) -> List[str]:
    output = []
    for item in items:
        if not item:
            continue
        text = re.sub(r"\s+", " ", str(item)).strip()
        text = text.replace("。", "")
        text = text.replace("；", "，")
        if len(text) > max_len:
            text = text[:max_len].rstrip("，, ") + "…"
        output.append(text)
        if len(output) >= limit:
            break
    return output


def get_visual_brief(context: Dict[str, Any]) -> Dict[str, Any]:
    forest = context["forest"]
    news = context["news"]
    market = context["market"]
    narration = context["narration"]
    plan = context.get("plan") or {}
    series_map = market_series_map(market)

    forest_summary = forest.get("forest_summary", {}) or {}
    macro_storyline = forest.get("macro_storyline", {}) or {}
    macro_vars = forest.get("macro_variables", {}) or {}
    evidence = forest.get("evidence", {}) or {}
    video_planning = forest.get("video_planning", {}) or {}

    scene_dialogues = {}
    for scene in narration.get("scenes", []) or []:
        scene_dialogues[scene.get("scene_id")] = scene

    default_plan = {
        "scene_02": {
            "headline": "油價高檔 → 通膨黏性",
            "topic": "通膨預期 / 原油",
            "main_visual": "只畫油價與通膨的單一主視覺：油桶 / 火焰 / CPI 上升箭頭 / 再通膨標記。不要畫完整流程圖。",
            "assets": ["WTI", "Brent"],
            "points": short_points_from_text([
                macro_vars.get("energy_view", ""),
                forest_summary.get("one_sentence_verdict", ""),
                (news.get("macro_drivers", [{}])[0] or {}).get("impact", ""),
            ]),
            "news_lines": pick_news_lines(news, ["油", "原油", "通膨", "energy", "inflation"]),
            "reference_scene": scene_dialogues.get("scene_02", {}),
        },
        "scene_03": {
            "headline": "長債利率重新定價",
            "topic": "利率 / 美債殖利率",
            "main_visual": "只畫利率與殖利率上行的主視覺：債券殖利率曲線、上升箭頭、Higher for Longer 標記。不要畫其他主題。",
            "assets": ["US10Y"],
            "points": short_points_from_text([
                macro_vars.get("rate_view", ""),
                *(evidence.get("most_important_evidence", []) or []),
            ]),
            "news_lines": pick_news_lines(news, ["殖利率", "美債", "利率", "bond", "yield", "rate"]),
            "reference_scene": scene_dialogues.get("scene_03", {}),
        },
        "scene_04": {
            "headline": "強美元外溢至亞洲貨幣",
            "topic": "美元 / 亞洲貨幣",
            "main_visual": "只畫美元與亞洲貨幣的主視覺：DXY 向上、日圓/台幣/韓元承壓箭頭。不要畫完整流程圖。",
            "assets": ["DXY", "USDJPY", "USDTWD", "USDKRW"],
            "points": short_points_from_text([
                macro_vars.get("dollar_fx_view", ""),
                macro_vars.get("asia_fx_view", ""),
                "觀察亞洲央行是否干預",
            ]),
            "news_lines": pick_news_lines(news, ["美元", "亞幣", "日圓", "台幣", "韓元", "currency", "fx"]),
            "reference_scene": scene_dialogues.get("scene_04", {}),
        },
        "scene_05": {
            "headline": "黃金壓力與修正因子",
            "topic": "黃金 / 修正因子",
            "main_visual": "只畫黃金與修正因子的單一主視覺：金條、避險符號、房市疲軟 / 成長擔憂的小標記。不要畫完整流程圖。",
            "assets": ["Gold", "DXY"],
            "points": short_points_from_text([
                macro_vars.get("gold_view", ""),
                macro_storyline.get("revision_or_noise", ""),
                "成長放緩是否升級為主導因子",
            ]),
            "news_lines": pick_news_lines(news, ["黃金", "房市", "成長", "gold", "housing", "slowdown"]),
            "reference_scene": scene_dialogues.get("scene_05", {}),
        },
    }

    for sid, conf in (plan.get("scenes", {}) or {}).items():
        if sid in default_plan:
            default_plan[sid].update(conf)

    week_range = forest.get("meta", {}).get("week_range") or news.get("meta", {}).get("week_range") or ""
    next_questions = (video_planning.get("next_week_questions") or [])[:5]
    if not next_questions:
        next_questions = (forest.get("evidence", {}).get("watch_items_from_daily_summaries") or [])[:5]

    return {
        "week_range": week_range,
        "main_theme": forest_summary.get("weekly_main_theme", ""),
        "one_sentence": forest_summary.get("one_sentence_verdict", ""),
        "default_plan": default_plan,
        "next_questions": next_questions,
        "series_map": series_map,
    }


def build_scene_prompt(scene_id: str, brief: Dict[str, Any]) -> str:
    if scene_id == "scene_06":
        next_questions = short_points_from_text(brief.get("next_questions", []), limit=5, max_len=26)
        items_text = "\n".join([f"- {q}" for q in next_questions])
        return f"""
{NOTEBOOK_STYLE}
Create Scene 06 as a full-page closing slide for a weekly macro video.
Visible structure:
- no scene label
- no heavy border
- one centered or slightly upper-centered short title: 「下週觀察重點」
- 3 to 5 large observation items arranged like pinned whiteboard notes or hand-marked bullet points
- each item should have a tiny symbolic icon or doodle only, such as: 美債? / 勞動力↑↓ / 央行 / 美元 / 黃金
- use very short phrases only
- page should feel like a clean summary board
- do not add extra explanation paragraphs
Week background:
- week range: {brief.get('week_range', '')}
- main theme: {brief.get('main_theme', '')}
Observation items:
{items_text}
""".strip()

    conf = brief["default_plan"][scene_id]
    asset_blocks = latest_asset_block(brief["series_map"], conf.get("assets", []))
    asset_text = "\n".join([f"- {x['label']}: {x['value']}" for x in asset_blocks]) or "- 無"
    point_text = "\n".join([f"- {x}" for x in conf.get("points", [])[:3]]) or "- 依旁白主線呈現"
    news_text = "\n".join([f"- {x}" for x in conf.get("news_lines", [])[:2]]) or "- 依本週代表性新聞呈現"
    narration = (conf.get("reference_scene", {}) or {}).get("narration", "")

    return f"""
{NOTEBOOK_STYLE}
Create {scene_id} as one static slide for a weekly macro video.
Page goal:
- this page explains only one topic: {conf.get('topic', '')}
- one single main visual on the left side
- lower-left: 1 to 2 big-number data callouts from the provided key metrics
- right side: exactly 3 short bullet points only
- bottom area: 1 to 2 short news source lines
- remove engineering labels such as Scene 02, 目前焦點, 驅動因子
- do not place a minimap
- do not use heavy panel borders
- keep the layout airy and like a summarized notebook page
Main visual guidance:
{conf.get('main_visual', '')}
Visible text guidance:
- short headline: 「{conf.get('headline', '')}」
- 3 bullets only, short, direct, readable
- big numbers, very small units
- news lines can show source + short title
- do not render long paragraphs
Background context only, not all visible:
- week range: {brief.get('week_range', '')}
- weekly main theme: {brief.get('main_theme', '')}
- weekly verdict: {brief.get('one_sentence', '')}
- related narration excerpt: {narration}
Key metrics:
{asset_text}
Three short bullet ideas:
{point_text}
News lines:
{news_text}
""".strip()


def read_file_base64(path: Path) -> Optional[Dict[str, str]]:
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
    data = base64.b64encode(path.read_bytes()).decode("utf-8")
    return {"mimeType": mime, "data": data}


def call_gemini_image(prompt: str, api_key: str, model_candidates: List[str], reference_images: Optional[List[Path]] = None) -> bytes:
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing")

    ref_parts = []
    for p in reference_images or []:
        encoded = read_file_base64(p)
        if encoded:
            ref_parts.append({"inlineData": encoded})

    last_error = ""
    for model in model_candidates:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        payload = {
            "contents": [{
                "role": "user",
                "parts": [{"text": prompt}] + ref_parts,
            }],
            "generationConfig": {
                "temperature": 0.6,
            },
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(1, MAX_IMAGE_RETRIES + 1):
            req = urllib.request.Request(
                url,
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                print(f"[INFO] image model call: model={model}, attempt={attempt}/{MAX_IMAGE_RETRIES}")
                with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                    raw = resp.read()
                res = json.loads(raw.decode("utf-8"))
                candidates = res.get("candidates", []) or []
                for cand in candidates:
                    content = cand.get("content", {}) or {}
                    for part in content.get("parts", []) or []:
                        inline = part.get("inlineData") or part.get("inline_data")
                        if inline and inline.get("data"):
                            return base64.b64decode(inline["data"])
                last_error = f"{model} returned no image data"
                print(f"[WARN] {last_error}")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="ignore")
                last_error = f"{model} / HTTP {exc.code} / {detail[:300]}"
                print(f"[WARN] image model failed: {last_error}")
            except Exception as exc:
                last_error = f"{model} / {exc}"
                print(f"[WARN] image model failed: {last_error}")

            if attempt < MAX_IMAGE_RETRIES:
                time.sleep(RETRY_SLEEP_SECONDS)

    raise RuntimeError(f"All image model candidates failed. Last error: {last_error}")


def copy_fallback_image(output_path: Path, diagram_path: Optional[Path], scene_id: str, reason: str) -> None:
    """
    Keep workflow alive when Gemini image generation has temporary 5xx errors.
    Priority:
    1. keep existing scene image if it already exists
    2. copy weekly_macro_diagram.png as a placeholder image
    This prevents one temporary image-model failure from aborting all generated slides.
    """
    if output_path.exists():
        print(f"[WARN] keep existing {scene_id}: {output_path} / reason={reason}")
        return
    if diagram_path and diagram_path.exists():
        shutil.copy2(diagram_path, output_path)
        print(f"[WARN] fallback copied diagram to {output_path} / reason={reason}")
        return
    raise RuntimeError(f"{scene_id} failed and no fallback image is available: {reason}")


def generate_image_or_fallback(prompt: str, output_path: Path, model_candidates: List[str], reference_images: List[Path], scene_id: str, diagram_path: Optional[Path]) -> bool:
    try:
        image_bytes = call_gemini_image(
            prompt=prompt,
            api_key=GEMINI_API_KEY,
            model_candidates=model_candidates,
            reference_images=reference_images,
        )
        write_slide(output_path, image_bytes)
        return True
    except Exception as exc:
        copy_fallback_image(output_path, diagram_path, scene_id, str(exc))
        return False

def write_slide(output_path: Path, image_bytes: bytes) -> None:
    output_path.write_bytes(image_bytes)
    print(f"[OK] wrote {output_path}")


def save_manifest(week_dir: Path, records: List[Dict[str, Any]]) -> None:
    manifest_path = week_dir / "weekly_slide_images_manifest.json"
    manifest_path.write_text(
        json.dumps({
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "image_model": IMAGE_MODEL,
            "records": records,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def main() -> None:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is required")

    explicit_week = os.getenv("WEEK_END_DATE", "").strip()
    if explicit_week:
        week_dir = OUTPUT_ROOT / explicit_week
    else:
        latest_candidates = sorted([p for p in OUTPUT_ROOT.glob("*") if p.is_dir()])
        if not latest_candidates:
            raise RuntimeError("No weekly output directory found under output/weekly")
        week_dir = latest_candidates[-1]

    context = load_week_context(week_dir)
    forest_meta = context["forest"].get("meta", {}) or {}
    week_end = parse_week_end(forest_meta)
    if week_dir.name != week_end and (OUTPUT_ROOT / week_end).exists():
        week_dir = OUTPUT_ROOT / week_end
        context = load_week_context(week_dir)

    slides_dir = week_dir / "slides"
    ensure_dir(slides_dir)

    diagram_path = week_dir / "weekly_macro_diagram.png"
    brief = get_visual_brief(context)
    model_candidates = [IMAGE_MODEL] + [m for m in IMAGE_MODEL_FALLBACKS if m != IMAGE_MODEL]

    records: List[Dict[str, Any]] = []

    # Scene 01: directly reuse the full macro diagram as the full-page opening slide.
    scene_01_output = slides_dir / SCENE_IMAGE_NAMES["scene_01"]
    if FORCE_REBUILD_SLIDES or not scene_01_output.exists():
        if not diagram_path.exists():
            raise RuntimeError(f"Scene 01 requires existing diagram: {diagram_path}")
        shutil.copy2(diagram_path, scene_01_output)
        print(f"[OK] copied scene 01 from {diagram_path}")
    records.append({"scene_id": "scene_01", "path": str(scene_01_output.name), "mode": "copy_diagram"})

    # Scene 02-05: image model generation.
    for scene_id in ["scene_02", "scene_03", "scene_04", "scene_05"]:
        output_path = slides_dir / SCENE_IMAGE_NAMES[scene_id]
        prompt = build_scene_prompt(scene_id, brief)
        generated_ok = True
        if FORCE_REBUILD_SLIDES or not output_path.exists():
            generated_ok = generate_image_or_fallback(
                prompt=prompt,
                output_path=output_path,
                model_candidates=model_candidates,
                reference_images=[diagram_path] if diagram_path.exists() else [],
                scene_id=scene_id,
                diagram_path=diagram_path,
            )
        records.append({"scene_id": scene_id, "path": str(output_path.name), "mode": "image_model", "generated_ok": generated_ok, "prompt_excerpt": prompt[:200]})

    # Scene 06: full-page next-week watch slide.
    scene_06_output = slides_dir / SCENE_IMAGE_NAMES["scene_06"]
    prompt = build_scene_prompt("scene_06", brief)
    generated_ok = True
    if FORCE_REBUILD_SLIDES or not scene_06_output.exists():
        generated_ok = generate_image_or_fallback(
            prompt=prompt,
            output_path=scene_06_output,
            model_candidates=model_candidates,
            reference_images=[],
            scene_id="scene_06",
            diagram_path=diagram_path if diagram_path.exists() else None,
        )
    records.append({"scene_id": "scene_06", "path": str(scene_06_output.name), "mode": "image_model", "generated_ok": generated_ok, "prompt_excerpt": prompt[:200]})

    save_manifest(week_dir, records)
    print(f"[DONE] weekly slide images ready: {slides_dir}")


if __name__ == "__main__":
    main()
