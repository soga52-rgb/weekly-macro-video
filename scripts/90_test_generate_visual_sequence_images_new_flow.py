#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Visual Sequence Image Generator - Step 90 Test (New Flow)

Purpose:
- TEST SCRIPT, file name intentionally starts with 90
- Read weekly_forest_summary.json produced by Step 01
- Use video_planning.visual_sequence as the single source of truth
- Directly generate the whole image set without going through the old
  image-prompt workflow

Input:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json

Output:
- output/weekly/YYYY-MM-DD/visual_sequence_images/{visual_id}.png
- output/weekly/YYYY-MM-DD/visual_sequence_images/visual_sequence_manifest.json
- output/weekly/YYYY-MM-DD/weekly_web_hero.png
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png  (compatibility alias)

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_IMAGE_MODEL, default: gemini-3.1-flash-image-preview
- FORCE_REBUILD_VISUALS, default: false

Notes:
- This script follows the new flow:
  Step 01 weekly_forest_summary.json -> Step 90 test direct image generation
- It does not use the old image prompt workflow.
"""

import argparse
import base64
import json
import os
import shutil
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def should_force_rebuild() -> bool:
    return os.getenv("FORCE_REBUILD_VISUALS", "false").strip().lower() in {"1", "true", "yes", "y"}


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def find_inline_image(api_response: Dict[str, Any]) -> Optional[bytes]:
    candidates = api_response.get("candidates") or []

    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []

        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue

            data = inline_data.get("data")
            if not data:
                continue

            return base64.b64decode(data)

    return None


def call_gemini_image(prompt: str, model: str, api_key: str) -> bytes:
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
            "temperature": 0.35,
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini image HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini image URLError: {exc}") from exc

    api_response = json.loads(raw)
    image_bytes = find_inline_image(api_response)

    if not image_bytes:
        preview = json.dumps(api_response, ensure_ascii=False)[:1500]
        raise RuntimeError(f"No inline image found in Gemini response. Preview: {preview}")

    return image_bytes


def build_visual_prompt(
    forest_summary: Dict[str, Any],
    visual: Dict[str, Any],
    is_web_hero: bool = False,
) -> str:
    forest = forest_summary.get("forest_summary", {})
    storyline = forest_summary.get("macro_storyline", {})
    macro_variables = forest_summary.get("macro_variables", {})
    video = forest_summary.get("video_planning", {})
    title = video.get("suggested_video_title", "")
    thesis = video.get("video_thesis", "")
    opening_hook = video.get("opening_hook", "")

    visual_title = visual.get("visual_title", "")
    visual_purpose = visual.get("visual_purpose", "")
    visual_concept = visual.get("visual_concept", "")
    key_labels = visual.get("key_labels") or []

    hero_note = ""
    if is_web_hero:
        hero_note = (
            "This visual is the selected web hero / final summary image. "
            "Make it especially clear, balanced, and representative of the week's core macro logic."
        )

    key_labels_text = " / ".join([str(x) for x in key_labels if str(x).strip()])

    return f"""
Create a polished editorial infographic image in a World Economic Forum-style macro explainer aesthetic.

This image is part of a weekly macro explainer series. Do not re-analyze the market. Only visualize the provided brief faithfully.

Overall series context:
- Suggested video title: {title}
- Core thesis: {thesis}
- Opening hook: {opening_hook}
- Weekly main theme: {forest.get("weekly_main_theme", "")}
- Main question: {forest.get("main_question", "")}
- One-sentence verdict: {forest.get("one_sentence_verdict", "")}
- Story start: {storyline.get("story_start", "")}
- Main drivers: {", ".join(storyline.get("main_drivers", []) if isinstance(storyline.get("main_drivers", []), list) else [])}
- Market transmission: {storyline.get("market_transmission", "")}
- Revision or noise: {storyline.get("revision_or_noise", "")}
- Story end: {storyline.get("story_end", "")}

Macro variable cues:
- Inflation: {macro_variables.get("inflation_view", "")}
- Rates: {macro_variables.get("rate_view", "")}
- Dollar / FX: {macro_variables.get("dollar_fx_view", "")}
- Asia FX: {macro_variables.get("asia_fx_view", "")}
- Gold: {macro_variables.get("gold_view", "")}
- Energy: {macro_variables.get("energy_view", "")}

Current visual brief:
- Visual title: {visual_title}
- Visual purpose: {visual_purpose}
- Visual concept: {visual_concept}
- Key labels: {key_labels_text}

Style requirements:
- Sophisticated, global-macro, policy-forum presentation style
- Clean layout, premium editorial infographic quality
- Clear hierarchy and readable labels
- Visually persuasive but not sensational
- Suitable for use in a macro explainer website or briefing deck
- Use concise Traditional Chinese labels when labels are shown
- Avoid clutter
- Do not add brand logos or watermarks
- {hero_note}
""".strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    summary_path = week_dir / "weekly_forest_summary.json"
    forest_summary = load_json(summary_path, {})
    if not forest_summary:
        raise FileNotFoundError(f"Missing or empty weekly_forest_summary.json: {summary_path}")

    video_planning = forest_summary.get("video_planning", {})
    visual_sequence = video_planning.get("visual_sequence") or []
    if not isinstance(visual_sequence, list) or not visual_sequence:
        raise ValueError("weekly_forest_summary.json does not contain a usable video_planning.visual_sequence array.")

    web_hero = video_planning.get("web_hero_visual", {}) or {}
    web_hero_visual_id = str(web_hero.get("source_visual_id", "")).strip()

    out_dir = week_dir / "visual_sequence_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "meta": {
            "source": "weekly_forest_summary.json",
            "image_model": model,
            "week_dir": str(week_dir),
        },
        "images": [],
        "web_hero_visual_id": web_hero_visual_id,
    }

    print(f"[INFO] Generating visual sequence images with model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] visual_sequence count: {len(visual_sequence)}")

    generated_paths: Dict[str, Path] = {}

    for idx, visual in enumerate(visual_sequence, start=1):
        if not isinstance(visual, dict):
            continue

        visual_id = str(visual.get("visual_id") or f"visual_{idx:02d}").strip()
        if not visual_id:
            visual_id = f"visual_{idx:02d}"

        out_path = out_dir / f"{visual_id}.png"
        is_hero = visual_id == web_hero_visual_id

        if out_path.exists() and not should_force_rebuild():
            print(f"[SKIP] Image already exists: {out_path}")
        else:
            prompt = build_visual_prompt(forest_summary, visual, is_web_hero=is_hero)
            image_bytes = call_gemini_image(prompt, model, api_key)
            save_binary(out_path, image_bytes)
            print(f"[OK] Created {out_path}")

        generated_paths[visual_id] = out_path
        manifest["images"].append({
            "visual_id": visual_id,
            "path": str(out_path),
            "source_segment_id": visual.get("source_segment_id", ""),
            "visual_title": visual.get("visual_title", ""),
            "visual_purpose": visual.get("visual_purpose", ""),
            "is_web_hero_candidate": bool(visual.get("is_web_hero_candidate", False)),
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

    manifest_path = out_dir / "visual_sequence_manifest.json"
    save_json(manifest_path, manifest)
    print(f"[OK] Created {manifest_path}")


if __name__ == "__main__":
    main()
