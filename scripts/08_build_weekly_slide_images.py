# Save as: scripts/08_build_weekly_slide_images.py
# -*- coding: utf-8 -*-
"""
08 - Build Weekly Slide Images from weekly_scene_package.json

V2_STABLE changes:
- scene_01.png = weekly_macro_diagram.png
- scene_02~scene_06.png = generated from weekly_scene_package.json image_prompt
- API parts order changed to: reference image first, then text prompt
- supports TARGET_SCENE_IDS for single-slide rerun, e.g. TARGET_SCENE_IDS=scene_04
- sleeps between image generations to reduce Gemini image API transient failures
- uses a stricter "visual card prompt wrapper" based on the successful NotebookLM-style cards:
  title + one visual metaphor + few labels + minimal text
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
    for x in os.getenv("IMAGE_MODEL_FALLBACKS", "").split(",")
    if x.strip()
]
FORCE_REBUILD_SLIDES = os.getenv("FORCE_REBUILD_SLIDES", "true").lower() == "true"
GEMINI_TIMEOUT_SECONDS = int(os.getenv("GEMINI_TIMEOUT_SECONDS", "90"))
MAX_IMAGE_RETRIES = int(os.getenv("MAX_IMAGE_RETRIES", "1"))
IMAGE_RETRY_SLEEP_SECONDS = int(os.getenv("IMAGE_RETRY_SLEEP_SECONDS", "10"))
IMAGE_BETWEEN_SCENES_SLEEP_SECONDS = int(os.getenv("IMAGE_BETWEEN_SCENES_SLEEP_SECONDS", "8"))

# Optional: only generate specific scenes, e.g. "scene_04" or "scene_02,scene_04"
TARGET_SCENE_IDS = [
    x.strip()
    for x in os.getenv("TARGET_SCENE_IDS", "").split(",")
    if x.strip()
]

STYLE_APPENDIX = """
Use this exact visual direction:
- 16:9 static infographic card.
- NotebookLM / whiteboard notebook style.
- off-white / beige background with subtle light-gray grid paper texture.
- black hand-drawn sketch lines.
- orange highlights, arrows, circles, underlines, question marks, pins, tags.
- small amount of navy-blue text.
- airy layout, weak or no heavy borders.
- not a corporate dashboard, not a screenshot, not a dense report page.
- one scene = one idea only.
- minimal Traditional Chinese text.
- do not show scene number, "目前焦點", engineering labels, prompt labels, or metadata.
- do not paste narration text.
- do not create long paragraphs.
- if showing numbers, make numbers large and units small.
- if using charts, use them as simple visual metaphors, not exact financial charts unless exact data is provided.
- prefer clean visual metaphor + 1 headline + up to 3 short labels.
- all visible Chinese must be Traditional Chinese.
""".strip()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Optional[Path], default: Any = None) -> Any:
    if not path or not path.exists():
        return default if default is not None else {}
    return json.loads(path.read_text(encoding="utf-8"))


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

    if not OUTPUT_WEEKLY_DIR.exists():
        raise FileNotFoundError(f"找不到資料夾：{OUTPUT_WEEKLY_DIR}")

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


def find_diagram(week_dir: Path) -> Optional[Path]:
    return first_existing([
        week_dir / "weekly_macro_diagram.png",
        week_dir / "final" / "weekly_macro_diagram.png",
        week_dir / "data" / "weekly_macro_diagram.png",
        week_dir / "images" / "weekly_macro_diagram.png",
    ])


def encode_image(path: Path) -> Optional[Dict[str, Any]]:
    if not path or not path.exists():
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
            "data": base64.b64encode(path.read_bytes()).decode("utf-8")
        }
    }


def short_json(obj: Any, max_chars: int = 1800) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...（截斷）"


def build_prompt(scene: Dict[str, Any]) -> str:
    """
    Wrap Pro-generated image_prompt with a stronger visual contract.
    This makes the GitHub API prompt closer to the successful AI Studio/manual prompts.
    """
    scene_title = str(scene.get("scene_title", "")).strip()
    scene_purpose = str(scene.get("scene_purpose", "")).strip()
    narrative_focus = str(scene.get("narrative_focus", "")).strip()
    visual_direction = str(scene.get("visual_direction", "")).strip()
    image_prompt = str(scene.get("image_prompt") or "").strip()
    on_screen_text = scene.get("on_screen_text") or {}

    if not image_prompt:
        image_prompt = f"""
Scene title: {scene_title}
Scene purpose: {scene_purpose}
Narrative focus: {narrative_focus}
Visual direction: {visual_direction}
On-screen text:
{short_json(on_screen_text)}
""".strip()

    # The wrapper converts "concept" prompts into production-ready image prompts.
    return f"""
Create one 16:9 static slide image for a weekly macro video.

This slide must be based on the following Pro-generated scene plan. Keep the narrative and visual logic, but simplify the image into a clean NotebookLM-style whiteboard card.

[Scene title]
{scene_title}

[Scene purpose]
{scene_purpose}

[Narrative focus]
{narrative_focus}

[Visual direction]
{visual_direction}

[Original image prompt from Pro]
{image_prompt}

[Suggested on-screen text, use only if helpful and keep minimal]
{short_json(on_screen_text)}

Production instructions:
{STYLE_APPENDIX}

Important:
- The image should feel like the successful clean whiteboard cards: simple metaphor, clear arrows, readable short Traditional Chinese labels.
- Do not create a complex infographic with too many words.
- Do not invent extra market facts.
- If the scene includes a relationship, show it with one simple visual metaphor such as: arrow flow, seesaw, checklist, line chart, bar chart, or pressure/weight metaphor.
- Do not include raw JSON or English descriptions in the image.
""".strip()


def call_image_model(prompt: str, reference_images: List[Path]) -> bytes:
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is missing")

    models = [IMAGE_MODEL] + [m for m in IMAGE_MODEL_FALLBACKS if m != IMAGE_MODEL]

    ref_parts = []
    for p in reference_images:
        part = encode_image(p)
        if part:
            ref_parts.append(part)

    last_error = ""
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}"

        # Important: put image reference first, then text prompt.
        # This is closer to AI Studio image-reference behavior.
        payload = {
            "contents": [{
                "role": "user",
                "parts": ref_parts + [{"text": prompt}]
            }],
            "generationConfig": {
                "temperature": 0.55,
            }
        }
        data = json.dumps(payload).encode("utf-8")

        for attempt in range(1, MAX_IMAGE_RETRIES + 1):
            print(f"[INFO] call image model={model}, attempt={attempt}/{MAX_IMAGE_RETRIES}")
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=GEMINI_TIMEOUT_SECONDS) as resp:
                    raw = resp.read()
                res = json.loads(raw.decode("utf-8"))

                for cand in res.get("candidates", []) or []:
                    for part in (cand.get("content", {}) or {}).get("parts", []) or []:
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
        print(f"[WARN] keep existing slide {output_path.name}; reason={reason}")
        return
    if diagram_path and diagram_path.exists():
        shutil.copy2(diagram_path, output_path)
        print(f"[WARN] fallback to diagram for {output_path.name}; reason={reason}")
        return
    raise RuntimeError(f"Cannot create fallback slide for {output_path.name}: {reason}")


def should_process_scene(scene_id: str) -> bool:
    if not TARGET_SCENE_IDS:
        return True
    return scene_id in TARGET_SCENE_IDS


def main() -> None:
    week_dir = find_latest_week_dir()
    slides_dir = week_dir / "slides"
    prompts_dir = slides_dir / "prompts"
    ensure_dir(slides_dir)
    ensure_dir(prompts_dir)

    package_path = first_existing([
        week_dir / "weekly_scene_package.json",
        week_dir / "narration" / "weekly_scene_package.json",
    ])
    pkg = read_json(package_path, {})
    scenes = pkg.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        raise RuntimeError("找不到 weekly_scene_package.json 或 scenes 為空，請先跑 05_generate_weekly_scene_package.py")

    diagram_path = find_diagram(week_dir)
    records = []

    print(f"[INFO] week_dir={week_dir}")
    print(f"[INFO] target_scene_ids={TARGET_SCENE_IDS or 'ALL'}")
    print(f"[INFO] image_model={IMAGE_MODEL}")

    for scene in scenes:
        sid = str(scene.get("scene_id", "")).strip()
        if not sid:
            continue

        if not should_process_scene(sid):
            print(f"[SKIP] {sid} not in TARGET_SCENE_IDS")
            continue

        out_path = slides_dir / f"{sid}.png"

        if sid == "scene_01":
            if FORCE_REBUILD_SLIDES or not out_path.exists():
                if not diagram_path:
                    raise RuntimeError("scene_01 需要 weekly_macro_diagram.png")
                shutil.copy2(diagram_path, out_path)
                print(f"[OK] scene_01 copied from {diagram_path}")
            records.append({"scene_id": sid, "path": str(out_path), "mode": "copy_diagram"})
            time.sleep(IMAGE_BETWEEN_SCENES_SLEEP_SECONDS)
            continue

        prompt = build_prompt(scene)
        prompt_path = prompts_dir / f"{sid}_image_prompt.txt"
        write_text(prompt_path, prompt)

        ok = True
        if FORCE_REBUILD_SLIDES or not out_path.exists():
            try:
                image_bytes = call_image_model(prompt, [diagram_path] if diagram_path else [])
                out_path.write_bytes(image_bytes)
                print(f"[OK] wrote {out_path}")
            except Exception as exc:
                ok = False
                fallback_slide(out_path, diagram_path, str(exc))

        records.append({
            "scene_id": sid,
            "path": str(out_path),
            "prompt": str(prompt_path),
            "generated_ok": ok,
            "mode": "image_from_scene_package_v2"
        })

        time.sleep(IMAGE_BETWEEN_SCENES_SLEEP_SECONDS)

    existing_manifest_path = slides_dir / "slides_manifest.json"
    existing_manifest = read_json(existing_manifest_path, {"records": []})
    existing_records = existing_manifest.get("records", [])
    merged = {r.get("scene_id"): r for r in existing_records if isinstance(r, dict)}
    for r in records:
        merged[r.get("scene_id")] = r

    manifest = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "week_dir": str(week_dir),
        "image_model": IMAGE_MODEL,
        "target_scene_ids": TARGET_SCENE_IDS,
        "records": list(merged.values())
    }
    existing_manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (week_dir / "weekly_slide_images_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[DONE] slides ready: {slides_dir}")


if __name__ == "__main__":
    main()
