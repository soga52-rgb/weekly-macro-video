#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Visual Sequence Image Generator - Step 92 Test

Purpose:
- Read weekly_forest_summary.json produced by Step 91.
- Support both current compatibility flow and new layered flow.
- Prefer overview_visual first.
- Then use presentation_pages for current 92 compatibility.
- Optionally use video_visual_scenes when VISUAL_SOURCE=video_scenes.
- Generate selected image(s) through Gemini image model.
- Save images back to output/weekly/<week>/ for GitHub workflow commit.

Input:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json

Output:
- output/weekly/YYYY-MM-DD/visual_sequence_images/{visual_id}.png
- output/weekly/YYYY-MM-DD/visual_sequence_images/visual_sequence_manifest.json
- output/weekly/YYYY-MM-DD/weekly_web_hero.png
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_IMAGE_MODEL, default: gemini-3-pro-image-preview
- FORCE_REBUILD_VISUALS, default: false
- TARGET_VISUAL_ID, optional: overview_01, vis_01, scene_01, etc.
- GEMINI_IMAGE_RETRIES, default: 2
- VISUAL_SOURCE, default: presentation_pages
  - presentation_pages: overview_visual + presentation_pages
  - video_scenes: overview_visual + video_visual_scenes
- IMAGE_TEMPERATURE, default: 0.35
"""

import argparse
import base64
import json
import os
import shutil
import socket
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_IMAGE_MODEL = "gemini-3-pro-image-preview"


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)).strip()
    try:
        return float(raw)
    except ValueError:
        return default


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def find_inline_image(api_response: Dict[str, Any]) -> Optional[bytes]:
    for candidate in api_response.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue
            data = inline_data.get("data")
            if data:
                return base64.b64decode(data)
    return None


def call_gemini_image(prompt: str, model: str, api_key: str, temperature: float) -> bytes:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=360) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini image HTTPError {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
        raise RuntimeError(f"Gemini image request failed or timed out: {exc}") from exc

    api_response = json.loads(raw)
    image_bytes = find_inline_image(api_response)

    if not image_bytes:
        preview = json.dumps(api_response, ensure_ascii=False)[:1500]
        raise RuntimeError(f"No inline image found in Gemini response. Preview: {preview}")

    return image_bytes


def call_gemini_image_with_retry(
    prompt: str,
    model: str,
    api_key: str,
    retries: int,
    temperature: float,
) -> bytes:
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"[INFO] Retry image generation attempt {attempt}/{retries}")
            return call_gemini_image(prompt, model, api_key, temperature)
        except Exception as exc:
            last_error = exc
            print(f"[WARN] Image generation attempt {attempt}/{retries} failed: {exc}")

    raise RuntimeError(str(last_error) if last_error else "Image generation failed")


def compact_json(data: Any, max_chars: int = 2500) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def block_lines(blocks: Any, limit: int = 3) -> str:
    if not isinstance(blocks, list):
        return ""
    lines: List[str] = []
    for block in blocks[:limit]:
        if not isinstance(block, dict):
            continue
        title = str(block.get("block_title", "")).strip()
        body = str(block.get("block_body", "")).strip()
        hint = str(block.get("evidence_hint", "")).strip()
        line = f"- {title}: {body}"
        if hint:
            line += f"｜{hint}"
        lines.append(line.strip())
    return "\n".join(lines)


def build_overview_item(summary: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    overview = summary.get("overview_visual")
    if not isinstance(overview, dict) or not overview:
        return None

    item = dict(overview)
    item.setdefault("visual_id", "overview_01")
    item.setdefault("page_type", "overview_dashboard")
    item.setdefault("visual_title", item.get("visual_title") or "本週總經傳遞總覽")
    item.setdefault("visual_purpose", item.get("viewer_message", "整週總覽母頁"))
    item.setdefault("visual_concept", (item.get("summary_block") or {}).get("body", ""))
    item.setdefault("source_layer", "overview_visual")
    return item


def build_items_from_presentation_pages(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    pages = summary.get("presentation_pages")
    if not isinstance(pages, list):
        return []

    items: List[Dict[str, Any]] = []
    for idx, page in enumerate(pages, start=1):
        if not isinstance(page, dict):
            continue
        brief = page.get("visual_brief") if isinstance(page.get("visual_brief"), dict) else {}
        visual_id = str(page.get("visual_id") or f"vis_{idx:02d}").strip()
        items.append({
            "visual_id": visual_id,
            "page_type": page.get("page_type", ""),
            "source_segment_id": page.get("page_id", f"page_{idx:02d}"),
            "visual_title": page.get("page_title", ""),
            "visual_purpose": page.get("viewer_message", ""),
            "visual_concept": page.get("conclusion", ""),
            "viewer_question": page.get("viewer_question", ""),
            "blocks": page.get("blocks", []),
            "key_labels": brief.get("key_labels", []),
            "style_note": brief.get("style_note", ""),
            "source_layer": "presentation_pages",
        })
    return items


def build_items_from_video_scenes(summary: Dict[str, Any]) -> List[Dict[str, Any]]:
    scenes = summary.get("video_visual_scenes")
    if not isinstance(scenes, list):
        return []

    narration_map: Dict[str, Dict[str, Any]] = {}
    for item in summary.get("narration_outline") or []:
        if isinstance(item, dict):
            narration_map[str(item.get("narration_id", ""))] = item

    items: List[Dict[str, Any]] = []
    for idx, scene in enumerate(scenes, start=1):
        if not isinstance(scene, dict):
            continue
        visual_id = str(scene.get("visual_id") or scene.get("scene_id") or f"scene_{idx:02d}").strip()
        narration = narration_map.get(str(scene.get("voiceover_link", "")), {})
        items.append({
            "visual_id": visual_id,
            "page_type": scene.get("scene_type", ""),
            "source_segment_id": scene.get("scene_id", f"scene_{idx:02d}"),
            "visual_title": scene.get("screen_title", ""),
            "visual_purpose": scene.get("single_message", ""),
            "visual_concept": scene.get("diagram_structure_brief") or scene.get("visual_metaphor", ""),
            "key_labels": scene.get("on_screen_labels", []),
            "must_show_numbers": scene.get("must_show_numbers", []),
            "narration_summary": narration.get("key_points", []),
            "avoid_saying": narration.get("avoid_saying", []),
            "source_layer": "video_visual_scenes",
        })
    return items


def build_visual_items(summary: Dict[str, Any], visual_source: str) -> Tuple[List[Dict[str, Any]], str]:
    items: List[Dict[str, Any]] = []

    overview = build_overview_item(summary)
    if overview:
        items.append(overview)

    if visual_source == "video_scenes":
        items.extend(build_items_from_video_scenes(summary))
    else:
        items.extend(build_items_from_presentation_pages(summary))

    if items:
        hero_id = "overview_01" if any(str(x.get("visual_id")) == "overview_01" for x in items) else str(items[0].get("visual_id", ""))
        return items, hero_id

    video_planning = summary.get("video_planning", {}) or {}
    visual_sequence = video_planning.get("visual_sequence") or []
    if not isinstance(visual_sequence, list) or not visual_sequence:
        raise ValueError("No usable overview_visual, presentation_pages, video_visual_scenes, or video_planning.visual_sequence found.")

    legacy_items = []
    for idx, visual_id in enumerate(visual_sequence, start=1):
        legacy_items.append({
            "visual_id": str(visual_id),
            "page_type": "legacy",
            "visual_title": str(visual_id),
            "visual_purpose": "",
            "visual_concept": "",
            "source_layer": "video_planning.visual_sequence",
        })

    web_hero = video_planning.get("web_hero_visual", {}) or {}
    hero_id = str(web_hero.get("source_visual_id", "")).strip() or str(legacy_items[0].get("visual_id", ""))
    return legacy_items, hero_id


VIDEO_SCENE_IMAGE_PROMPT_TEMPLATE = """
Create ONE Traditional Chinese low-text macro diagram frame for a video.

Task focus:
- Current scene only.
- The image should work as a clean visual anchor for voiceover.
- The scene should present one core market relationship, not the full weekly report.

Current scene:
- Scene type: {page_type}
- Screen title: {title}
- Single message: {purpose}
- Diagram structure brief: {concept}
- On-screen labels: {labels_text}
- Must-show numbers: {numbers_text}

Narration reference for context:
{narration_text}

Tone and layout:
- Clean macro relationship map.
- Light cream background.
- Hand-drawn black outlines.
- Soft beige / pale yellow blocks.
- Clear arrows, simple boxes, relation lines, pressure layers, support layers, divergence marks, and observation nodes.
- One title, 2-4 short labels, and 0-2 key numbers.
- Large empty space around the central relationship so the image remains readable on video.
- Suitable for a 16:9 video frame with voiceover.

Scene type guidance:
- overview: show the core divergence or transmission split as a central relationship map with 2-4 labels.
- inflation_expectation: focus on energy, oil, supply shock, and inflation expectation transmission.
- rate_expectation: focus on Fed, bond yields, US10Y / US30Y, term premium, and policy repricing.
- dollar_index: focus on DXY, rate differential, growth concern, and currency pressure.
- asia_fx_gold: focus on Asian currencies and gold as two related but distinct market responses.
- next_week_roadmap: show a simple watchpoint map or timeline with 3 observation nodes.

Text discipline:
- Use short financial labels instead of paragraphs.
- Use market variables and numbers as labels.
- Keep the frame analytical, calm, and business-simple.
- Use logos-free, watermark-free original diagram elements.
""".strip()


OVERVIEW_IMAGE_PROMPT_TEMPLATE = """
Create a Traditional Chinese macro visual note in a clean hand-drawn editorial style.

Purpose:
- Generate a viewer-facing macro diagram, not an internal analysis document.
- Make the market conclusion visible at first glance.
- Use evidence as short labels inside blocks.
- Keep the image readable as a web hero or report visual.

Weekly context:
- Theme: {theme}
- Verdict: {verdict}
- Transmission: {transmission}
- Revision/noise: {revision_noise}

Internal diagnosis reference:
{diagnosis_text}

Current visual:
- Source layer: {source_layer}
- Page type: {page_type}
- Title: {title}
- Viewer message: {purpose}
- Core concept / conclusion: {concept}
- Key labels: {labels_text}
- Blocks:
{blocks_text}

Overview structure if applicable:
{overview_text}

Layout direction:
- Use a central macro transmission map.
- Arrange drivers, transmission chain, divergence points, validation cards, and watch items as clear blocks.
- Use arrows to show cause and effect.
- Use separated zones for policy, rates, dollar / FX, commodities, gold, and watchpoints when relevant.
- Put the main conclusion near the visual center or upper third.

Style:
- Light cream / off-white background.
- Hand-drawn black outlines.
- Soft beige / yellow blocks.
- Rounded boxes and clear arrows.
- Simple analytical icons only when they help identify a market variable.
- Business-simple, macro explainer style.
- Readable Traditional Chinese text.
- One clear title, 3-6 short labels, and a small number of key figures.
- Logos-free, watermark-free original diagram elements.
- {hero_note}
""".strip()


def build_visual_prompt(summary: Dict[str, Any], visual: Dict[str, Any], is_web_hero: bool = False) -> str:
    forest = summary.get("forest_summary", {})
    storyline = summary.get("macro_storyline", {})
    diagnosis = summary.get("transmission_diagnosis", {})

    page_type = str(visual.get("page_type", "")).strip()
    title = str(visual.get("visual_title", "")).strip()
    purpose = str(visual.get("visual_purpose", "")).strip()
    concept = str(visual.get("visual_concept", "")).strip()
    source_layer = str(visual.get("source_layer", "")).strip()

    key_labels = visual.get("key_labels") or []
    numbers = visual.get("must_show_numbers") or []
    labels_text = " / ".join(str(x) for x in key_labels if str(x).strip())
    numbers_text = " / ".join(str(x) for x in numbers if str(x).strip())

    blocks_text = block_lines(visual.get("blocks", []), limit=3)

    narration_text = ""
    if visual.get("narration_summary"):
        narration_text = "\n".join(f"- {x}" for x in visual.get("narration_summary", [])[:3])

    if source_layer == "video_visual_scenes":
        return VIDEO_SCENE_IMAGE_PROMPT_TEMPLATE.format(
            page_type=page_type,
            title=title,
            purpose=purpose,
            concept=concept,
            labels_text=labels_text,
            numbers_text=numbers_text,
            narration_text=narration_text,
        )

    overview_text = ""
    if page_type == "overview_dashboard":
        overview_text = compact_json({
            "main_diagram": visual.get("main_diagram", {}),
            "summary_block": visual.get("summary_block", {}),
            "transmission_chain_block": visual.get("transmission_chain_block", {}),
            "validation_cards": visual.get("validation_cards", []),
            "watch_items": visual.get("watch_items", []),
        }, max_chars=2800)

    hero_note = ""
    if is_web_hero:
        hero_note = "This image is the web hero / overview image. Make it feel like a complete one-page overview with sparse, readable text."

    return OVERVIEW_IMAGE_PROMPT_TEMPLATE.format(
        theme=forest.get("weekly_main_theme", ""),
        verdict=forest.get("one_sentence_verdict", ""),
        transmission=storyline.get("market_transmission", ""),
        revision_noise=storyline.get("revision_or_noise", ""),
        diagnosis_text=compact_json(diagnosis, max_chars=1800),
        source_layer=source_layer,
        page_type=page_type,
        title=title,
        purpose=purpose,
        concept=concept,
        labels_text=labels_text,
        blocks_text=blocks_text,
        overview_text=overview_text,
        hero_note=hero_note,
    )

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    visual_source = os.getenv("VISUAL_SOURCE", "presentation_pages").strip().lower()
    if visual_source not in {"presentation_pages", "video_scenes"}:
        visual_source = "presentation_pages"

    if args.week_dir:
        week_dir = Path(args.week_dir)
        if not week_dir.exists() and not week_dir.is_absolute():
            candidate = OUTPUT_WEEKLY_DIR / args.week_dir
            if candidate.exists():
                week_dir = candidate
    else:
        week_dir = find_latest_week_dir()

    summary_path = week_dir / "weekly_forest_summary.json"
    summary = load_json(summary_path, {})
    if not summary:
        raise FileNotFoundError(f"Missing or empty weekly_forest_summary.json: {summary_path}")

    visual_items, web_hero_visual_id = build_visual_items(summary, visual_source=visual_source)

    out_dir = week_dir / "visual_sequence_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "meta": {
            "source": "weekly_forest_summary.json",
            "visual_source": visual_source,
            "image_model": model,
            "week_dir": str(week_dir),
        },
        "images": [],
        "failed_images": [],
        "web_hero_visual_id": web_hero_visual_id,
    }

    force_rebuild = env_bool("FORCE_REBUILD_VISUALS", "false")
    target_id = os.getenv("TARGET_VISUAL_ID", "").strip()
    retries = env_int("GEMINI_IMAGE_RETRIES", 2)
    temperature = env_float("IMAGE_TEMPERATURE", 0.35)

    print(f"[INFO] Generating visual images with model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] visual_source: {visual_source}")
    print(f"[INFO] visual item count: {len(visual_items)}")
    print(f"[INFO] force_rebuild: {force_rebuild}")
    print(f"[INFO] target_visual_id: {target_id or '(all)'}")
    print(f"[INFO] retries: {retries}")
    print(f"[INFO] image temperature: {temperature}")

    generated_paths: Dict[str, Path] = {}

    for idx, visual in enumerate(visual_items, start=1):
        if not isinstance(visual, dict):
            continue

        visual_id = str(visual.get("visual_id") or f"visual_{idx:02d}").strip() or f"visual_{idx:02d}"

        if target_id and visual_id != target_id:
            print(f"[SKIP] Target visual is {target_id}; skip {visual_id}")
            continue

        out_path = out_dir / f"{visual_id}.png"
        is_hero = visual_id == web_hero_visual_id

        try:
            if out_path.exists() and not force_rebuild:
                print(f"[SKIP] Image already exists: {out_path}")
            else:
                prompt = build_visual_prompt(summary, visual, is_web_hero=is_hero)
                image_bytes = call_gemini_image_with_retry(
                    prompt=prompt,
                    model=model,
                    api_key=api_key,
                    retries=retries,
                    temperature=temperature,
                )
                save_binary(out_path, image_bytes)
                print(f"[OK] Created {out_path}")

            if out_path.exists():
                generated_paths[visual_id] = out_path

            manifest["images"].append({
                "visual_id": visual_id,
                "path": str(out_path),
                "source_layer": visual.get("source_layer", ""),
                "source_segment_id": visual.get("source_segment_id", ""),
                "visual_title": visual.get("visual_title", ""),
                "visual_purpose": visual.get("visual_purpose", ""),
                "status": "created_or_existing",
            })

        except Exception as exc:
            error_message = str(exc)
            print(f"[WARN] Failed to generate {visual_id}: {error_message}")
            manifest["failed_images"].append({
                "visual_id": visual_id,
                "source_layer": visual.get("source_layer", ""),
                "source_segment_id": visual.get("source_segment_id", ""),
                "visual_title": visual.get("visual_title", ""),
                "error": error_message,
            })

    if web_hero_visual_id and web_hero_visual_id in generated_paths:
        hero_source = generated_paths[web_hero_visual_id]
        weekly_web_hero = week_dir / "weekly_web_hero.png"
        weekly_macro_diagram = week_dir / "weekly_macro_diagram.png"

        shutil.copyfile(hero_source, weekly_web_hero)
        shutil.copyfile(hero_source, weekly_macro_diagram)

        manifest["web_hero_output"] = {
            "source_visual_id": web_hero_visual_id,
            "weekly_web_hero": str(weekly_web_hero),
            "weekly_macro_diagram_compat": str(weekly_macro_diagram),
        }

        print(f"[OK] Set web hero image from {hero_source.name}")
        print(f"[OK] Updated {weekly_web_hero}")
        print(f"[OK] Updated compatibility alias {weekly_macro_diagram}")
    elif web_hero_visual_id:
        print(f"[WARN] Web hero visual was selected but not generated successfully: {web_hero_visual_id}")

    manifest_path = out_dir / "visual_sequence_manifest.json"
    save_json(manifest_path, manifest)
    print(f"[OK] Created {manifest_path}")


if __name__ == "__main__":
    main()
