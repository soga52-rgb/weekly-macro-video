#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 83 - Story Direct-to-Image Generator

Purpose:
- Read Step 82 story-only dialogue output.
- Directly generate images from the story sections.
- Keep one coherent whiteboard / sketch-explainer style across the whole set.
- Support generating all sections or only one selected section for testing.
- Support a cheapest preview mode that renders only the first scene.
- Avoid a separate prompt-manifest generation step to reduce complexity and cost.

Input:
- output/weekly/<week_dir>/weekly_dialogue_story_only_v8.json

Outputs:
- output/weekly/<week_dir>/story_visual_images/scene_01.png ...
- output/weekly/<week_dir>/story_visual_images/story_visual_images_manifest_v9.json
- output/weekly/<week_dir>/story_visual_images/story_visual_prompts_v9.json

Environment variables / CLI:
- WEEK_DIR: optional week directory.
- TARGET_SCENE_ID: optional. Accepts values like 1, s1, scene_01, vis_01.
- PREVIEW_ONLY_FIRST: optional. true/false. If true and TARGET_SCENE_ID is empty, only render the first scene.
- FORCE_REBUILD_VISUALS: true/false.
- GEMINI_API_KEY: required.
- GEMINI_IMAGE_MODEL: optional, default gemini-3.1-flash-image-preview.
- IMAGE_TEMPERATURE: optional, default 0.55.
- GEMINI_IMAGE_RETRIES: optional, default 2.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DIALOGUE_JSON_FILENAME = "weekly_dialogue_story_only_v8.json"
OUTPUT_DIRNAME = "story_visual_images"
MANIFEST_FILENAME = "story_visual_images_manifest_v9.json"
PROMPTS_FILENAME = "story_visual_prompts_v9.json"

DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_TEMPERATURE = 0.55
DEFAULT_RETRIES = 2


SYSTEM_PROMPT = """
你是頂級知識型圖解頻道（如 Vox、RSA Animate）與機構級總經節目的首席白板插畫師。

你的任務是把一份已經寫好的 Tom / Miranda 總經故事稿，直接轉譯成影片使用的單張畫面。
你不是重新分析市場，也不是重寫腳本；你是把故事轉成有畫面感、好理解、可連續觀看的視覺。

核心風格要求：
1. 白板手繪風格（whiteboard animation style）/ 手繪圖解（sketch explainer）/ 極簡線條插畫。
2. 背景乾淨，以白底或極淺底為主。
3. 以黑色線條為主，搭配少量高對比點綴色，整組圖保持統一風格。
4. 點綴色必須清楚、醒目、合成後仍容易辨識；避免粉淡色、灰淡色、低飽和色、接近背景色的顏色。
5. 使用簡單符號、icon、箭頭、線條、簡單圖表、抽象比喻，不要複雜寫實人物，不要 3D 科技感，不要廉價圖庫感。
6. 畫面是為了支撐語音敘事，所以要有故事感、延續感與轉場感。
7. 每張圖只抓一個主概念，避免塞滿資訊。
8. 文字必須非常少，只保留必要的繁體中文短標籤與少量關鍵數字。
9. 可以使用白板式的物理隱喻：磁鐵、天平、彈簧、裂開房子、雨傘、油桶、橋、箭頭、簡單線圖等。
10. 不要把畫面做成傳統 PPT、密集表格或複雜簡報頁。
11. 全部圖片要像同一個系列，風格、筆觸、構圖語言要一致。
12. 畫面中央偏下必須預留人物頭像區，右下角必須預留台詞字幕區；這兩區不要放關鍵資訊、重要箭頭、主要 icon 或關鍵數字。
13. 主要圖解內容請集中在左側、上方、中央偏上，讓後續影片合成時不會被頭像與字幕遮住。
14. 不要直接把人物頭像、字幕框或完整台詞畫進圖片；Step 83 只負責畫底圖與預留安全區。
""".strip()


GLOBAL_VISUAL_STYLE = """
Series visual language:
- 16:9 macro explainer video frame.
- whiteboard animation / marker sketch / minimalist doodle.
- clean white or very light background.
- black marker lines as main drawing language.
- use only 1-3 high-contrast accent colors when needed.
- prefer high-contrast accent colors such as orange, deep blue, gold, deep green, brick red.
- avoid pale pinks, washed-out grays, low-saturation pastels, and colors too close to the background.
- lots of whitespace, clean composition, modern and memorable.
- simple icons, arrows, light charts, symbolic objects.
- keep the center-lower area clean for the speaker avatar overlay.
- keep the lower-right area clean for the subtitle box overlay.
- place the most important content mostly on the left side, upper half, and center-upper area.
- Traditional Chinese only for very short labels if text is needed.
- maintain continuity across all scenes so the full video feels like one story.
- avoid PPT look, avoid stock-photo look, avoid photorealistic faces, avoid clutter.
""".strip()


def env_bool(name: str, default: str = "false") -> bool:
    value = os.getenv(name, default).strip().lower()
    return value in {"1", "true", "yes", "y", "on"}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Failed to read JSON: {path} | {exc}")
        return default


def save_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def save_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def compact_json(data: Any, max_chars: int = 4500) -> str:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n... [truncated]"


def latest_week_dir() -> Path:
    if not OUTPUT_WEEKLY_DIR.exists():
        raise FileNotFoundError(f"Missing output weekly directory: {OUTPUT_WEEKLY_DIR}")
    candidates = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not candidates:
        raise FileNotFoundError(f"No weekly output directories under: {OUTPUT_WEEKLY_DIR}")
    return sorted(candidates, key=lambda p: p.name)[-1]


def resolve_week_dir(week_dir_arg: str) -> Path:
    week_dir_arg = (week_dir_arg or "").strip()
    if not week_dir_arg:
        return latest_week_dir()

    raw = Path(week_dir_arg)
    if raw.is_absolute():
        return raw
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", week_dir_arg):
        return OUTPUT_WEEKLY_DIR / week_dir_arg
    return ROOT_DIR / raw


def extract_sections(dialogue: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections = dialogue.get("sections")
    if not isinstance(sections, list):
        return []

    results: List[Dict[str, Any]] = []
    for idx, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue
        item = dict(section)
        item.setdefault("section_id", f"s{idx}")
        item["visual_id"] = f"scene_{idx:02d}"
        item["visual_index"] = idx
        results.append(item)
    return results


def normalize_target_scene(raw: str, sections: List[Dict[str, Any]]) -> str:
    text = (raw or "").strip().lower()
    if not text:
        return ""

    by_index = {str(i): sec["section_id"].lower() for i, sec in enumerate(sections, start=1)}
    for sec in sections:
        section_id = str(sec.get("section_id", "")).strip().lower()
        visual_id = str(sec.get("visual_id", "")).strip().lower()
        if text in {section_id, visual_id}:
            return section_id
        if text.startswith("vis_") or text.startswith("scene_"):
            m = re.search(r"(\d+)$", text)
            if m and m.group(1).lstrip("0") in by_index:
                return by_index[m.group(1).lstrip("0")]

    m = re.fullmatch(r"s?(\d+)", text)
    if m:
        key = m.group(1).lstrip("0") or "0"
        return by_index.get(key, "")

    return text


def section_turn_lines(section: Dict[str, Any], max_turns: int = 6) -> str:
    turns = section.get("speaker_turns")
    if not isinstance(turns, list):
        return ""
    lines: List[str] = []
    for turn in turns[:max_turns]:
        if not isinstance(turn, dict):
            continue
        speaker = str(turn.get("speaker", "")).strip()
        spoken = str(turn.get("spoken_text", "")).strip()
        if speaker and spoken:
            lines.append(f"[{speaker}] {spoken}")
    return "\n".join(lines)


def build_context_bundle(dialogue: Dict[str, Any], sections: List[Dict[str, Any]], current_idx: int) -> Dict[str, Any]:
    meta = dialogue.get("meta") if isinstance(dialogue.get("meta"), dict) else {}
    storyline = dialogue.get("storyline") if isinstance(dialogue.get("storyline"), dict) else {}
    current = sections[current_idx]
    prev_title = sections[current_idx - 1].get("section_title", "") if current_idx > 0 else ""
    next_title = sections[current_idx + 1].get("section_title", "") if current_idx + 1 < len(sections) else ""

    return {
        "week_range": meta.get("week_range", ""),
        "story_thesis": meta.get("story_thesis", ""),
        "opening_question": storyline.get("opening_question", ""),
        "closing_callback": storyline.get("closing_callback", ""),
        "current_section": {
            "section_id": current.get("section_id", ""),
            "visual_id": current.get("visual_id", ""),
            "section_title": current.get("section_title", ""),
            "story_purpose": current.get("story_purpose", ""),
            "event_setup": current.get("event_setup", ""),
            "price_reaction": current.get("price_reaction", ""),
            "driver_judgment": current.get("driver_judgment", ""),
            "macro_interpretation": current.get("macro_interpretation", ""),
            "micro_pain_point": current.get("micro_pain_point", ""),
            "dilemma": current.get("dilemma", ""),
            "tom_insight_line": current.get("tom_insight_line", ""),
            "bridge_question": current.get("bridge_question", ""),
            "speaker_turn_excerpt": section_turn_lines(current, max_turns=8),
        },
        "continuity": {
            "previous_section_title": prev_title,
            "next_section_title": next_title,
            "section_count": len(sections),
            "section_number": current_idx + 1,
        },
    }


def build_image_prompt(dialogue: Dict[str, Any], sections: List[Dict[str, Any]], current_idx: int) -> str:
    bundle = build_context_bundle(dialogue, sections, current_idx)
    current = bundle["current_section"]
    continuity = bundle["continuity"]

    return f"""
Create one single image for a macro-finance explainer video.

{GLOBAL_VISUAL_STYLE}

This is part of a continuous image series for one video episode.
The style, visual language, and storytelling tone must remain consistent across all scenes.
This image should feel like one chapter within a connected narrative, not an isolated poster.

Full-episode context:
{compact_json({
    'week_range': bundle['week_range'],
    'story_thesis': bundle['story_thesis'],
    'opening_question': bundle['opening_question'],
    'closing_callback': bundle['closing_callback'],
}, 1800)}

Current scene context:
{compact_json(current, 3800)}

Continuity cues:
- Section number: {continuity['section_number']} / {continuity['section_count']}
- Previous section: {continuity['previous_section_title'] or '(none)'}
- Next section: {continuity['next_section_title'] or '(none)'}

Design instructions:
- Translate the current section into a simple but memorable visual scene.
- Use one main visual idea, plus a few supporting symbols only.
- The image should help the audience immediately feel what this section is about.
- Let the narration explain the full reasoning; the image should not become a dense infographic.
- If useful, include a very light simple chart, a direction arrow, or a turning-point line to reflect price action.
- If useful, use symbolic objects such as an oil barrel, bond yield line, magnet, house, umbrella, gold bar, scale, spring, bridge, shield, arrows, or currency icons.
- Keep on-screen text minimal: at most one short Traditional Chinese title and up to 2-4 tiny labels or numbers.
- Do not render paragraphs, tables, or long subtitles.
- Keep the center-lower area visually clean for a future speaker avatar overlay.
- Keep the lower-right area visually clean for a future subtitle box overlay.
- Do not place the main causal arrow, key chart turning point, important icon cluster, or critical numbers inside those reserved areas.
- Concentrate the key story elements in the left area, upper area, and center-upper area.
- Use only a few high-contrast accent colors so the image remains clear after video compositing.
- Prefer accent colors such as orange, deep blue, gold, deep green, or brick red.
- Avoid pale, washed-out, low-contrast colors that may become hard to see after compositing.
- Make the visual modern, clean, whiteboard-like, and strong in storytelling.
- Maintain continuity so the next image can transition naturally from this one.

Output target:
- 16:9 image.
- Whiteboard sketch explainer / marker doodle style.
- Traditional Chinese only for any visible text.

Avoid:
- old-fashioned PPT layout
- dense text blocks
- photorealistic portraits
- 3D glossy business graphics
- messy clutter
- sensational disaster imagery
- conflicting visual styles
""".strip()


def find_inline_image_and_text(api_response: Dict[str, Any]) -> Tuple[Optional[bytes], Optional[str], Optional[str]]:
    note_text: Optional[str] = None
    mime_type: Optional[str] = None

    for candidate in api_response.get("candidates") or []:
        content = candidate.get("content") or {}
        for part in content.get("parts") or []:
            if part.get("text") and not note_text:
                note_text = part.get("text")
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue
            data = inline_data.get("data")
            if data:
                mime_type = inline_data.get("mimeType") or inline_data.get("mime_type") or "image/png"
                return base64.b64decode(data), mime_type, note_text
    return None, mime_type, note_text


def call_gemini_image(prompt: str, model: str, api_key: str, temperature: float) -> Tuple[bytes, str, Optional[str]]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "systemInstruction": {
            "parts": [{"text": SYSTEM_PROMPT}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": temperature,
            "topP": 0.9,
            "responseModalities": ["TEXT", "IMAGE"],
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
    image_bytes, mime_type, note_text = find_inline_image_and_text(api_response)
    if not image_bytes:
        preview = json.dumps(api_response, ensure_ascii=False)[:1500]
        raise RuntimeError(f"No inline image found in Gemini response. Preview: {preview}")

    return image_bytes, (mime_type or "image/png"), note_text


def call_gemini_image_with_retry(
    prompt: str,
    model: str,
    api_key: str,
    retries: int,
    temperature: float,
) -> Tuple[bytes, str, Optional[str]]:
    last_error: Optional[Exception] = None
    for attempt in range(1, retries + 1):
        try:
            if attempt > 1:
                print(f"[INFO] Retry image generation attempt {attempt}/{retries}")
            return call_gemini_image(prompt, model, api_key, temperature)
        except Exception as exc:
            last_error = exc
            print(f"[WARN] Image generation attempt {attempt}/{retries} failed: {exc}")
            if attempt < retries:
                time.sleep(5 * attempt)
    raise RuntimeError(str(last_error) if last_error else "Image generation failed")


def extension_from_mime(mime_type: str) -> str:
    lowered = mime_type.lower()
    if "jpeg" in lowered or "jpg" in lowered:
        return ".jpg"
    if "webp" in lowered:
        return ".webp"
    return ".png"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default=os.getenv("WEEK_DIR", "").strip())
    parser.add_argument("--target-scene", type=str, default=os.getenv("TARGET_SCENE_ID", "").strip())
    parser.add_argument("--preview-only-first", action="store_true", default=env_bool("PREVIEW_ONLY_FIRST", "false"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    temperature = float(os.getenv("IMAGE_TEMPERATURE", str(DEFAULT_TEMPERATURE)))
    retries = int(os.getenv("GEMINI_IMAGE_RETRIES", str(DEFAULT_RETRIES)))
    force_rebuild = args.force or env_bool("FORCE_REBUILD_VISUALS", "false")
    preview_only_first = bool(args.preview_only_first)

    week_dir = resolve_week_dir(args.week_dir)
    if not week_dir.exists():
        raise FileNotFoundError(f"Week directory not found: {week_dir}")

    dialogue_path = week_dir / DIALOGUE_JSON_FILENAME
    dialogue = load_json(dialogue_path, {})
    if not dialogue:
        raise FileNotFoundError(f"Missing or empty dialogue JSON: {dialogue_path}")

    sections = extract_sections(dialogue)
    if not sections:
        raise RuntimeError("No valid sections found in dialogue JSON.")

    normalized_target = normalize_target_scene(args.target_scene, sections)
    if preview_only_first and not normalized_target and sections:
        normalized_target = str(sections[0].get("section_id", "s1")).strip().lower()

    out_dir = week_dir / OUTPUT_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: Dict[str, Any] = {
        "meta": {
            "type": "story_visual_images_v9",
            "source": DIALOGUE_JSON_FILENAME,
            "week_dir": str(week_dir),
            "image_model": model,
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "target_scene": normalized_target or "",
            "preview_only_first": preview_only_first,
            "style": "whiteboard sketch explainer / minimalist marker doodle / consistent video series",
        },
        "images": [],
        "failed_images": [],
    }

    prompt_records: List[Dict[str, Any]] = []

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Dialogue input: {dialogue_path}")
    print(f"[INFO] Image model: {model}")
    print(f"[INFO] Temperature: {temperature}")
    print(f"[INFO] Retries: {retries}")
    print(f"[INFO] Force rebuild: {force_rebuild}")
    print(f"[INFO] Preview only first: {preview_only_first}")
    print(f"[INFO] Target scene raw: {args.target_scene or '(all)'}")
    print(f"[INFO] Target scene normalized: {normalized_target or '(all)'}")

    for idx, section in enumerate(sections):
        section_id = str(section.get("section_id", f"s{idx+1}")).strip()
        visual_id = str(section.get("visual_id", f"scene_{idx+1:02d}")).strip()

        if normalized_target and normalized_target != section_id.lower():
            print(f"[SKIP] target={normalized_target}; skip {section_id}/{visual_id}")
            continue

        prompt = build_image_prompt(dialogue, sections, idx)
        out_basename = visual_id
        out_path = out_dir / f"{out_basename}.png"

        prompt_records.append({
            "section_id": section_id,
            "visual_id": visual_id,
            "section_title": section.get("section_title", ""),
            "prompt": prompt,
        })

        try:
            if out_path.exists() and not force_rebuild:
                print(f"[SKIP] Image already exists: {out_path}")
                note_text = None
            else:
                image_bytes, mime_type, note_text = call_gemini_image_with_retry(
                    prompt=prompt,
                    model=model,
                    api_key=api_key,
                    retries=retries,
                    temperature=temperature,
                )

                actual_ext = extension_from_mime(mime_type)
                actual_path = out_dir / f"{out_basename}{actual_ext}"
                save_binary(actual_path, image_bytes)
                if actual_path != out_path:
                    if out_path.exists():
                        out_path.unlink()
                    if actual_ext != ".png":
                        # keep a png alias path name stable when extension differs is not practical without conversion;
                        # just point manifest to actual file.
                        out_path = actual_path
                else:
                    out_path = actual_path
                print(f"[OK] Created {out_path}")

            manifest["images"].append({
                "section_id": section_id,
                "visual_id": visual_id,
                "section_title": section.get("section_title", ""),
                "path": str(out_path),
                "status": "created_or_existing",
            })
        except Exception as exc:
            error_message = str(exc)
            print(f"[WARN] Failed to generate {visual_id}: {error_message}")
            manifest["failed_images"].append({
                "section_id": section_id,
                "visual_id": visual_id,
                "section_title": section.get("section_title", ""),
                "error": error_message,
            })

    save_json(out_dir / MANIFEST_FILENAME, manifest)
    save_json(out_dir / PROMPTS_FILENAME, prompt_records)

    print(f"[OK] Wrote {out_dir / MANIFEST_FILENAME}")
    print(f"[OK] Wrote {out_dir / PROMPTS_FILENAME}")


if __name__ == "__main__":
    main()
