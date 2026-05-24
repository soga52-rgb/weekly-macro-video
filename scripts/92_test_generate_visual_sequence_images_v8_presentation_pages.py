#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Visual Sequence Image Generator - Step 90 Test (New Flow)

Purpose:
- TEST SCRIPT, file name intentionally starts with 90
- Read weekly_forest_summary.json produced by Step 01
- Prefer overview_visual and presentation_pages as the source of truth
- Fall back to video_planning.visual_sequence for old summaries
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
- TARGET_VISUAL_ID, optional: generate only one visual_id, e.g. vis_01
- GEMINI_IMAGE_RETRIES, default: 2

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
import socket
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


def target_visual_id() -> str:
    return os.getenv("TARGET_VISUAL_ID", "").strip()


def gemini_image_retries() -> int:
    raw = os.getenv("GEMINI_IMAGE_RETRIES", "2").strip()
    try:
        return max(1, int(raw))
    except ValueError:
        return 2


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def call_gemini_image_with_retry(prompt: str, model: str, api_key: str, retries: int) -> bytes:
    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"[INFO] Retry image generation attempt {attempt}/{retries}")
            return call_gemini_image(prompt, model, api_key)
        except Exception as exc:
            last_error = exc
            print(f"[WARN] Image generation attempt {attempt}/{retries} failed: {exc}")

    raise RuntimeError(str(last_error) if last_error else "Image generation failed")


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
            "temperature": 0.9,
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


def build_visual_prompt(
    forest_summary: Dict[str, Any],
    visual: Dict[str, Any],
    is_web_hero: bool = False,
) -> str:
    forest = forest_summary.get("forest_summary", {})
    storyline = forest_summary.get("macro_storyline", {})
    diagnosis = forest_summary.get("transmission_diagnosis", {})
    page_type = str(visual.get("page_type", "")).strip()
    title = str(visual.get("visual_title") or visual.get("page_title") or "").strip()
    purpose = str(visual.get("visual_purpose") or visual.get("viewer_message") or "").strip()
    concept = str(visual.get("visual_concept") or visual.get("conclusion") or "").strip()
    key_labels = visual.get("key_labels") or []
    key_labels_text = " / ".join([str(x) for x in key_labels if str(x).strip()])

    blocks = visual.get("blocks") if isinstance(visual.get("blocks"), list) else []
    blocks_text = ""
    if blocks:
        lines = []
        for block in blocks[:4]:
            if not isinstance(block, dict):
                continue
            lines.append(
                f"- {block.get('block_title', '')}: {block.get('block_body', '')} {block.get('evidence_hint', '')}".strip()
            )
        blocks_text = "\n".join(lines)

    overview_text = ""
    if page_type == "overview_dashboard":
        overview_text = json.dumps({
            "main_diagram": visual.get("main_diagram", {}),
            "summary_block": visual.get("summary_block", {}),
            "transmission_chain_block": visual.get("transmission_chain_block", {}),
            "validation_cards": visual.get("validation_cards", []),
            "watch_items": visual.get("watch_items", []),
        }, ensure_ascii=False, indent=2)

    hero_note = ""
    if is_web_hero:
        hero_note = (
            "This is the web hero / overview output. Make it read like a complete one-page overview dashboard, "
            "with a clear top title, one main transmission diagram, a short summary block, a transmission chain, "
            "small validation cards, and watch items."
        )

    return f"""
Create a Traditional Chinese macro visual note in the same style as the daily macro transmission diagram.

Important:
- Visualize the viewer-facing presentation page only.
- Do not expose internal analysis labels such as 「新聞驗證」 as a required standalone block unless the page itself explicitly asks for it.
- News and evidence should be naturally embedded inside market-signal blocks or conclusion blocks.
- The conclusion must be visually clear and not buried.

Weekly context:
- Weekly theme: {forest.get("weekly_main_theme", "")}
- One-sentence verdict: {forest.get("one_sentence_verdict", "")}
- Market transmission: {storyline.get("market_transmission", "")}
- Revision or noise: {storyline.get("revision_or_noise", "")}

Internal diagnosis for reference only:
{json.dumps(diagnosis, ensure_ascii=False)[:2500]}

Current presentation page:
- Page type: {page_type}
- Title: {title}
- Purpose / viewer message: {purpose}
- Core concept / conclusion: {concept}
- Key labels: {key_labels_text}
- Blocks:
{blocks_text}

Overview structure if applicable:
{overview_text}

Style requirements:
- Match the daily macro transmission diagram style: clean light cream/off-white background, hand-drawn black outlines, soft beige/yellow blocks, rounded boxes, simple doodle icons, and clear arrows.
- Keep the page viewer-facing and result-oriented. Show what the viewer should understand, not the full internal reasoning method.
- For overview_dashboard: create a one-page overview mother page with main diagram + summary + transmission chain + small validation cards + watch items.
- For explanation pages: use a clean title plus 2-3 large content blocks and one clearly separated conclusion area.
- Keep text sparse and readable: one large Traditional Chinese title, short block titles, short key phrases, and very few numbers.
- Avoid repeated news items across blocks.
- Avoid dense charts, tiny text, complex axes, long paragraphs, financial terminal styling, WEF style, logos, and watermarks.
- {hero_note}
""".strip()


def build_visual_items(forest_summary: Dict[str, Any]) -> tuple[list[Dict[str, Any]], str]:
    """
    New source-of-truth:
    1) overview_visual -> overview_01
    2) presentation_pages -> viewer-facing explanation visuals

    Fallback:
    - video_planning.visual_sequence
    """
    items: list[Dict[str, Any]] = []

    overview = forest_summary.get("overview_visual")
    if isinstance(overview, dict) and overview:
        overview_item = dict(overview)
        overview_item.setdefault("visual_id", overview_item.get("visual_id") or "overview_01")
        overview_item.setdefault("page_type", "overview_dashboard")
        overview_item.setdefault("visual_title", overview_item.get("visual_title") or "本週總經傳遞總覽")
        overview_item.setdefault("visual_purpose", overview_item.get("viewer_message", "整週總覽母頁"))
        overview_item.setdefault("visual_concept", (overview_item.get("summary_block") or {}).get("body", ""))
        overview_item.setdefault("key_labels", [])
        items.append(overview_item)

    pages = forest_summary.get("presentation_pages")
    if isinstance(pages, list) and pages:
        for idx, page in enumerate(pages, start=1):
            if not isinstance(page, dict):
                continue
            brief = page.get("visual_brief") if isinstance(page.get("visual_brief"), dict) else {}
            item = {
                "visual_id": page.get("visual_id") or f"vis_{idx:02d}",
                "page_type": page.get("page_type", ""),
                "source_segment_id": page.get("page_id", f"page_{idx:02d}"),
                "visual_title": page.get("page_title", ""),
                "visual_purpose": page.get("viewer_message", ""),
                "visual_concept": page.get("conclusion", ""),
                "key_labels": brief.get("key_labels", []),
                "blocks": page.get("blocks", []),
                "viewer_question": page.get("viewer_question", ""),
                "conclusion": page.get("conclusion", ""),
                "is_web_hero_candidate": False,
            }
            items.append(item)

    if items:
        hero_id = "overview_01" if any(str(x.get("visual_id")) == "overview_01" for x in items) else str(items[0].get("visual_id", ""))
        return items, hero_id

    video_planning = forest_summary.get("video_planning", {}) or {}
    visual_sequence = video_planning.get("visual_sequence") or []
    if not isinstance(visual_sequence, list) or not visual_sequence:
        raise ValueError("weekly_forest_summary.json does not contain overview_visual/presentation_pages or usable video_planning.visual_sequence.")

    web_hero = video_planning.get("web_hero_visual", {}) or {}
    return visual_sequence, str(web_hero.get("source_visual_id", "")).strip()

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    if args.week_dir:
        week_dir = Path(args.week_dir)
        if not week_dir.exists() and not week_dir.is_absolute():
            candidate = OUTPUT_WEEKLY_DIR / args.week_dir
            if candidate.exists():
                week_dir = candidate
    else:
        week_dir = find_latest_week_dir()

    summary_path = week_dir / "weekly_forest_summary.json"
    forest_summary = load_json(summary_path, {})
    if not forest_summary:
        raise FileNotFoundError(f"Missing or empty weekly_forest_summary.json: {summary_path}")

    visual_sequence, web_hero_visual_id = build_visual_items(forest_summary)

    out_dir = week_dir / "visual_sequence_images"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "meta": {
            "source": "weekly_forest_summary.json",
            "image_model": model,
            "week_dir": str(week_dir),
        },
        "images": [],
        "failed_images": [],
        "web_hero_visual_id": web_hero_visual_id,
    }

    force_rebuild = should_force_rebuild()
    target_id = target_visual_id()
    retries = gemini_image_retries()

    print(f"[INFO] Generating visual sequence images with model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] visual_sequence count: {len(visual_sequence)}")
    print(f"[INFO] force_rebuild: {force_rebuild}")
    print(f"[INFO] target_visual_id: {target_id or '(all)'}")
    print(f"[INFO] gemini_image_retries: {retries}")

    generated_paths: Dict[str, Path] = {}

    for idx, visual in enumerate(visual_sequence, start=1):
        if not isinstance(visual, dict):
            continue

        visual_id = str(visual.get("visual_id") or f"visual_{idx:02d}").strip()
        if not visual_id:
            visual_id = f"visual_{idx:02d}"

        if target_id and visual_id != target_id:
            print(f"[SKIP] Target visual is {target_id}; skip {visual_id}")
            continue

        out_path = out_dir / f"{visual_id}.png"
        is_hero = visual_id == web_hero_visual_id

        try:
            if out_path.exists() and not force_rebuild:
                print(f"[SKIP] Image already exists: {out_path}")
            else:
                prompt = build_visual_prompt(forest_summary, visual, is_web_hero=is_hero)
                image_bytes = call_gemini_image_with_retry(prompt, model, api_key, retries)
                save_binary(out_path, image_bytes)
                print(f"[OK] Created {out_path}")

            if out_path.exists():
                generated_paths[visual_id] = out_path
            manifest["images"].append({
                "visual_id": visual_id,
                "path": str(out_path),
                "source_segment_id": visual.get("source_segment_id", ""),
                "visual_title": visual.get("visual_title", ""),
                "visual_purpose": visual.get("visual_purpose", ""),
                "is_web_hero_candidate": bool(visual.get("is_web_hero_candidate", False)),
                "status": "created_or_existing",
            })

        except Exception as exc:
            error_message = str(exc)
            print(f"[WARN] Failed to generate {visual_id}: {error_message}")
            manifest["failed_images"].append({
                "visual_id": visual_id,
                "source_segment_id": visual.get("source_segment_id", ""),
                "visual_title": visual.get("visual_title", ""),
                "error": error_message,
            })
            continue

    if not generated_paths:
        print("[WARN] No images were generated successfully. Manifest will still be saved for debugging.")

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
