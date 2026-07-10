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

任務定位：
把 weekly_dialogue_story_only_v8.json 中已完成的故事稿轉成白板圖像。
圖片只根據輸入 JSON 的 storyline 與 sections 生成，不重新判斷市場主線，不加入新的總經結論，不自行補充新聞或數字。
每張 section 圖只轉譯一個 section 的核心故事節點：市場問題、事件線索、價格反應、主導因子、修正因子、背離訊號或下一段銜接。
全部圖片要像同一個系列，風格、筆觸、構圖語言要一致。

V35 對齊原則：
- 83 是圖像轉譯層，不是分析層。
- 圖像不得推翻 82 故事稿已形成的主線、修正因子、背離訊號、資產方向或下期觀察。
- 若 section 沒有明確資產方向，不要自己畫上升或下降箭頭；請用問號、分歧路口、待觀察標記或中性符號。
- 不要畫出輸入資料沒有的數字、日期、政策結論或市場因果。
- 若畫價格線或箭頭，方向必須直接來自 current_section.price_reaction 或 speaker_turn_excerpt。
- 若畫外匯或匯率，請清楚標示是匯率報價還是本幣方向。例如：USD/TWD 下降代表台幣升值；USD/KRW 下降代表韓元升值；USD/JPY 上升代表日圓偏弱。

箭頭語意硬規則：
- 每一支上升或下降箭頭都必須有唯一、清楚的指向對象；箭頭方向必須描述它直接指向的變數，不可讓同一支箭頭同時代表原因與結果。
- 若故事是「殖利率上升 → 企業融資成本提高 → 投資、產出或實體經濟承壓」，請畫成三段式因果：10Y ↑ → financing cost ↑ → business activity / factory under pressure ↓。
- 當 current_section 表示融資成本上升、偏高或形成壓力時，嚴禁把大型向下箭頭直接放在「企業融資成本 / financing cost」旁邊或指向該標籤，因為那會被解讀為融資成本下降。
- 若要表達實體經濟承壓，向下箭頭只能清楚指向投資、產出、工廠活動或企業擴張，不可指向融資成本本身。
- 若無法用箭頭清楚區分，改用壓力計、重物、煞車或被壓住的工廠圖示，不要使用容易反向解讀的箭頭。

白話化視覺語言：
- 優先視覺化「市場更關注什麼」、「主導因子」、「修正因子」、「背離訊號」、「資產驗證」、「下期觀察」。
- 避免把畫面做成抽象金融術語海報，例如定價、體制、風險溢價、傳導源。
- 圖像要幫觀眾理解故事，不要自己做新的總經判斷。

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
- simple icons, arrows, light charts, and clean symbolic objects only when they directly support the story.
- Chinese text is optional and secondary. Prefer icons, English ticker labels, and exact numeric labels first.
- Allow at most 3 short Chinese labels in one image, and each Chinese label must contain no more than 4 Chinese characters.
- Chinese labels may only be selected exactly from this approved list: 油價、通膨、利率、美元、黃金、就業、分歧、觀察、融資成本、實體經濟、企業投資、日圓、台幣、韓元、上行、下行、升值、貶值、壓力、韌性、待確認。
- Never generate a Chinese title, sentence, paragraph, chart caption, explanatory phrase, or any Chinese wording outside the approved list.
- If the model is not confident that the Chinese glyphs will be accurate and complete, omit Chinese entirely and use an icon or English ticker label instead.
- Prefer very short English labels such as CPI, PPI, 10Y, US10Y, DXY, WTI, Brent, Gold, USD/JPY, USD/TWD, or USD/KRW.
- The image must remain understandable even if every Chinese label is removed.
- Numeric labels are allowed only when the exact number already appears in current_section.price_reaction or speaker_turn_excerpt; never use sample numbers, decorative numbers, or values from another week.
- Do not draw video player UI, red progress bars, playback controls, browser chrome, subtitles, lower-third captions, watermarks, or screenshots.
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
- This is visual translation only: do not re-analyze macro conditions, do not invent a new story, and do not add conclusions not present in current_section.
- Prefer visual ideas such as: market question, dominant driver, correction factor, divergence signal, asset validation, or next-period watch.
- Use one main visual idea, plus a few supporting symbols only.
- The image should help the audience immediately feel what this section is about.
- Let the narration explain the full reasoning; the image should not become a dense infographic.
- If useful, include a very light simple chart, a direction arrow, a forked path, a pressure gauge, or a turning-point line to reflect the section's price reaction.
- Every arrow must have one unambiguous target. The arrow direction must describe the variable it directly points to, not a different downstream consequence.
- When the section says yields rise and financing costs rise or remain high, use the explicit causal chain: 10Y ↑ → financing cost ↑ → business investment / factory activity under pressure ↓. Never place a large downward arrow next to, above, or pointing at a financing-cost label, because that visually means financing costs are falling.
- If the scene needs to show real-economy pressure, point the downward arrow only at business investment, output, expansion, or factory activity. Alternatively use a weight, brake, pressure gauge, or compressed factory icon instead of an ambiguous arrow.
- Use simple macro-finance symbols only when they directly support the current section, such as oil, bond yields, gold, currency quotes, arrows, or a clean price line.
- Do not invent new macro conclusions. Do not add news, numbers, dates, labels, arrows, or causal links that are not present in current_section or speaker_turn_excerpt.
- If current_section does not clearly state an asset direction, do not draw a strong up/down arrow. Use neutral symbols such as a question mark, split arrows, balance scale, or watch-style visual.
- If current_section describes a divergence, show it as two forces pulling in different directions, not as a single confident trend.
- If current_section describes a correction factor, show it as a secondary smaller force, not as the main driver.
- If current_section describes asset validation, show the checked assets calmly; do not exaggerate or turn it into a crisis image.
- Before rendering, perform a visual-semantic check: read each arrow literally. If an arrow could make a viewer infer the opposite direction for financing cost, yield, oil, gold, DXY, or a currency, redesign that part with separate arrows or a non-directional pressure symbol.
- Text budget: no more than 6 text elements in the entire image, including ticker labels, Chinese labels, and numeric labels.
- Prefer English ticker labels and icons. Chinese is optional, not required.
- Allow at most 3 short Chinese labels, each no more than 4 Chinese characters, and only from this exact approved list: 油價、通膨、利率、美元、黃金、就業、分歧、觀察、融資成本、實體經濟、企業投資、日圓、台幣、韓元、上行、下行、升值、貶值、壓力、韌性、待確認。
- Do not create Chinese titles, Chinese sentences, chart captions, explanatory phrases, or paraphrased Chinese text. Do not place Chinese captions underneath charts.
- If accurate Chinese rendering is uncertain, omit the Chinese label and use a symbol or an English ticker instead.
- Prefer short English labels such as CPI, PPI, 10Y, US10Y, DXY, WTI, Brent, Gold, USD/JPY, USD/TWD, or USD/KRW.
- Show a numeric value only when that exact value appears in current_section.price_reaction or speaker_turn_excerpt. Do not invent, round, reuse, or decorate with any number that is absent from the current section.
- Do not render paragraphs, tables, long subtitles, handwritten Chinese sentences, or any Chinese wording outside the approved list.
- Do not draw any video player interface, red progress bar, play button, timeline bar, YouTube controls, browser frame, screenshot frame, or lower-third caption area.
- Use the whole frame naturally as a clean whiteboard composition; do not create blank placeholder boxes, marked layout zones, or UI-like frame elements.
- Use only a few high-contrast accent colors so the image remains clear after video compositing.
- Prefer accent colors such as orange, deep blue, gold, deep green, or brick red.
- Avoid pale, washed-out, low-contrast colors that may become hard to see after compositing.
- Make the visual modern, clean, whiteboard-like, and strong in storytelling.
- Maintain continuity so the next image can transition naturally from this one.

Output target:
- 16:9 image.
- Whiteboard sketch explainer / marker doodle style.
- Let the video subtitles and narration carry the full wording.
- Prefer clean English ticker labels and source-supported numeric labels.
- Optional Chinese labels must follow the approved short-label list and text budget above; omit them whenever glyph accuracy is uncertain.

Avoid:
- video player UI, progress bars, play buttons, timeline controls, YouTube-like controls, browser screenshots, lower-third caption bars
- malformed, incomplete, fake, or unapproved Chinese text
- old-fashioned PPT layout
- dense text blocks
- photorealistic portraits
- 3D glossy business graphics
- messy clutter
- sensational disaster imagery
- exaggerated crisis visuals unless the current section explicitly supports that tone
- invented asset directions, invented price levels, invented arrows, invented policy conclusions
- abstract jargon posters built around words like pricing, regime, risk premium, transmission source
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
            "v35_visual_rule": "visual translation only; do not re-analyze or invent macro conclusions",
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
