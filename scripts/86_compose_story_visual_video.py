#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 86 | Compose Story Visual Video

Purpose:
- Combine Step 83 story images with Step 85 edge-tts dialogue segment audio.
- Preserve the exact Step 82 spoken_text; do not regenerate or rewrite narration.
- Add Tom / Miranda speaker avatar, speaker name, compact waveform, and transcript-style subtitles.
- Export an MP4 for end-to-end video validation.

Inputs:
- output/weekly/<week>/weekly_dialogue_story_only_v8.json
- output/weekly/<week>/story_visual_images/scene_01.jpg ...
- output/weekly/<week>/story_audio/segments/seg_000_Tom.mp3 ...

Outputs:
- output/weekly/<week>/story_video/story_visual_video_test.mp4
- output/weekly/<week>/story_video/story_turn_timeline.json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except Exception as exc:
    raise RuntimeError("Pillow is required. Please install pillow before running Step 86.") from exc


VIDEO_W = 1280
VIDEO_H = 720
FPS = 30
AVATAR_SIZE = 118
SCENE_FADE_SEC = 0.24
SUBTITLE_FONT_SIZE = 32
SPEAKER_FONT_SIZE = 27
MAX_SUBTITLE_CHARS_PER_LINE = 20
MAX_SUBTITLE_LINES = 2
WAVEFORM_W = 500
WAVEFORM_H = 42
WAVEFORM_X = 170
WAVEFORM_Y = 114


# -----------------------------------------------------------------------------
# Utilities
# -----------------------------------------------------------------------------

def run(cmd: list[str]) -> None:
    print("[CMD]", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    out = subprocess.check_output(cmd).decode("utf-8").strip()
    return float(out)


def latest_week_dir(explicit_week_dir: str | None) -> Path:
    if explicit_week_dir:
        p = Path(explicit_week_dir)
        if p.exists():
            return p
        p2 = Path("output/weekly") / explicit_week_dir
        if p2.exists():
            return p2
        raise FileNotFoundError(f"Week directory not found: {explicit_week_dir}")

    base = Path("output/weekly")
    if not base.exists():
        raise FileNotFoundError("output/weekly not found")
    candidates = sorted([p for p in base.iterdir() if p.is_dir()])
    if not candidates:
        raise FileNotFoundError("No weekly output directory found")
    return candidates[-1]


def resolve_dialogue_json(week_dir: Path, explicit_path: str | None) -> Path:
    if explicit_path:
        p = Path(explicit_path)
        if p.exists():
            return p
        p2 = week_dir / explicit_path
        if p2.exists():
            return p2
        raise FileNotFoundError(f"Dialogue JSON not found: {explicit_path}")

    patterns = [
        "weekly_dialogue_story_only_v*.json",
        "weekly_dialogue_story_only*.json",
        "weekly_dialogue_script*.json",
    ]
    candidates: list[Path] = []
    for pattern in patterns:
        candidates.extend(sorted(week_dir.glob(pattern)))
    if not candidates:
        raise FileNotFoundError("No dialogue JSON found under week_dir")
    return candidates[-1]


def resolve_scene_images(week_dir: Path) -> list[Path]:
    image_dir = week_dir / "story_visual_images"
    if not image_dir.exists():
        raise FileNotFoundError(f"story_visual_images not found: {image_dir}")

    images = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.webp"):
        images.extend(image_dir.glob("scene_" + ext.split("*")[-1]))
    # More robust: collect all scene_* files and sort naturally by stem.
    images = list(image_dir.glob("scene_*.*"))
    images = [p for p in images if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    images = sorted(images, key=lambda p: p.stem)
    if not images:
        raise FileNotFoundError("No scene images found in story_visual_images")
    return images


def resolve_segment_audio_dir(week_dir: Path) -> Path:
    seg_dir = week_dir / "story_audio" / "segments"
    if not seg_dir.exists():
        raise FileNotFoundError(f"Segment audio directory not found: {seg_dir}")
    return seg_dir


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_sections(dialogue_data: dict) -> list[dict]:
    if isinstance(dialogue_data.get("story_sections"), list):
        return dialogue_data["story_sections"]
    if isinstance(dialogue_data.get("sections"), list):
        return dialogue_data["sections"]
    if isinstance(dialogue_data.get("scene_dialogues"), list):
        return dialogue_data["scene_dialogues"]
    raise ValueError("Unable to find sections array in dialogue JSON")


def section_title(section: dict, idx: int) -> str:
    return (
        section.get("title")
        or section.get("section_title")
        or section.get("name")
        or section.get("id")
        or f"section_{idx + 1:02d}"
    )


def section_id(section: dict, idx: int) -> str:
    return (
        section.get("section_id")
        or section.get("id")
        or section.get("scene_id")
        or f"s{idx + 1}"
    )


def normalize_speaker(raw: str) -> str:
    x = (raw or "").strip().lower()
    if x.startswith("tom"):
        return "Tom"
    if x.startswith("miranda"):
        return "Miranda"
    return raw or "Speaker"


def waveform_color(speaker: str) -> str:
    return "0xc084fc" if normalize_speaker(speaker) == "Miranda" else "0x38bdf8"


def split_transcript(text: str, chars_per_line: int = MAX_SUBTITLE_CHARS_PER_LINE, max_lines: int = MAX_SUBTITLE_LINES) -> list[str]:
    """Split spoken_text into subtitle chunks for transcript-style rolling display."""
    text = (text or "").strip()
    if not text:
        return [""]

    chunk_len = chars_per_line * max_lines
    chunks = []
    for i in range(0, len(text), chunk_len):
        piece = text[i:i + chunk_len]
        lines = [piece[j:j + chars_per_line] for j in range(0, len(piece), chars_per_line)]
        chunks.append("\n".join(lines[:max_lines]))
    return chunks or [text]


def find_font_path() -> str | None:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Regular.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def write_textfile(path: Path, text: str) -> None:
    path.write_text(text or "", encoding="utf-8")


# -----------------------------------------------------------------------------
# Avatar generation
# -----------------------------------------------------------------------------

def make_avatar(path: Path, speaker: str, font_path: str | None) -> None:
    bg = (51, 102, 204, 255) if speaker == "Tom" else (186, 85, 211, 255)
    fg = (255, 255, 255, 255)
    img = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, AVATAR_SIZE - 4, AVATAR_SIZE - 4), fill=bg)

    initial = "T" if speaker == "Tom" else "M"
    if font_path:
        try:
            font = ImageFont.truetype(font_path, 58)
        except Exception:
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), initial, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text(((AVATAR_SIZE - tw) / 2, (AVATAR_SIZE - th) / 2 - 4), initial, fill=fg, font=font)
    img.save(path)


# -----------------------------------------------------------------------------
# Timeline building
# -----------------------------------------------------------------------------

def build_section_scene_buckets(sections: list[dict], scene_images: list[Path]) -> list[list[dict]]:
    sec_records = []
    for idx, sec in enumerate(sections):
        sec_records.append({
            "section_index": idx + 1,
            "section_id": section_id(sec, idx),
            "title": section_title(sec, idx),
            "speaker_turns": sec.get("speaker_turns") or [],
        })

    if len(sec_records) <= len(scene_images):
        buckets = [[rec] for rec in sec_records]
        while len(buckets) < len(scene_images):
            buckets.append([])
    else:
        buckets = [[rec] for rec in sec_records[:len(scene_images) - 1]]
        buckets.append(sec_records[len(scene_images) - 1:])
    return buckets


def sorted_segment_files(segment_dir: Path) -> list[Path]:
    files = sorted(segment_dir.glob("seg_*.mp3"))
    if not files:
        files = sorted(segment_dir.glob("seq_*.mp3"))
    if not files:
        raise FileNotFoundError(f"No segment mp3 files found in {segment_dir}")
    return files


def build_turn_timeline(dialogue_json: Path, scene_images: list[Path], segment_dir: Path) -> dict:
    dialogue_data = load_json(dialogue_json)
    sections = extract_sections(dialogue_data)
    buckets = build_section_scene_buckets(sections, scene_images)

    turn_records = []
    global_turn_index = 0
    for scene_idx, bucket in enumerate(buckets, start=1):
        image_path = scene_images[scene_idx - 1]
        for sec in bucket:
            for turn in sec["speaker_turns"]:
                global_turn_index += 1
                speaker = normalize_speaker(turn.get("speaker", "Speaker"))
                spoken = (turn.get("spoken_text") or "").strip()
                turn_records.append({
                    "global_turn_index": global_turn_index,
                    "scene_index": scene_idx,
                    "scene_image": str(image_path),
                    "section_id": sec["section_id"],
                    "section_title": sec["title"],
                    "speaker": speaker,
                    "spoken_text": spoken,
                    "subtitle_text": (turn.get("subtitle_text") or "").strip(),
                    "estimated_seconds": float(turn.get("estimated_seconds") or 0),
                })

    segment_files = sorted_segment_files(segment_dir)
    if len(segment_files) != len(turn_records):
        print(f"[WARN] Segment count ({len(segment_files)}) != turn count ({len(turn_records)}).")
        usable = min(len(segment_files), len(turn_records))
        turn_records = turn_records[:usable]
        segment_files = segment_files[:usable]

    start_sec = 0.0
    for i, (turn, seg_file) in enumerate(zip(turn_records, segment_files), start=1):
        dur = ffprobe_duration(seg_file)
        turn["segment_index"] = i
        turn["segment_audio"] = str(seg_file)
        turn["start_sec"] = round(start_sec, 3)
        turn["duration_sec"] = round(dur, 3)
        turn["end_sec"] = round(start_sec + dur, 3)
        start_sec += dur

    return {
        "dialogue_json": str(dialogue_json),
        "segment_dir": str(segment_dir),
        "turn_count": len(turn_records),
        "scene_count": len(scene_images),
        "total_duration": round(start_sec, 3),
        "turns": turn_records,
    }


# -----------------------------------------------------------------------------
# FFmpeg filter helpers
# -----------------------------------------------------------------------------

def drawtext_textfile_filter(
    input_label: str,
    output_label: str,
    textfile: Path,
    fontfile: str | None,
    fontsize: int,
    x: str,
    y: str,
    boxcolor: str,
    fontcolor: str = "white",
    enable: str | None = None,
) -> str:
    parts = [f"[{input_label}]drawtext="]
    if fontfile:
        parts.append(f"fontfile='{fontfile}':")
    parts.append(f"textfile='{textfile.as_posix()}':")
    parts.append(f"fontsize={fontsize}:")
    parts.append(f"fontcolor={fontcolor}:")
    parts.append(f"x={x}:y={y}:")
    parts.append("line_spacing=8:")
    parts.append("box=1:boxborderw=18:")
    parts.append(f"boxcolor={boxcolor}")
    if enable:
        parts.append(f":enable='{enable}'")
    parts.append(f"[{output_label}]")
    return "".join(parts)


# -----------------------------------------------------------------------------
# Clip rendering
# -----------------------------------------------------------------------------

def render_turn_clip(turn: dict, out_path: Path, avatar_map: dict[str, Path], font_path: str | None,
                     fade_in: bool, fade_out: bool) -> None:
    bg_image = turn["scene_image"]
    seg_audio = turn["segment_audio"]
    duration = max(0.35, float(turn["duration_sec"]))
    speaker = normalize_speaker(turn["speaker"])
    transcript_chunks = split_transcript(turn.get("spoken_text") or "")

    text_dir = out_path.parent / "_text"
    text_dir.mkdir(parents=True, exist_ok=True)
    speaker_file = text_dir / f"speaker_{turn['segment_index']:03d}.txt"
    write_textfile(speaker_file, speaker)

    chunk_files = []
    for i, chunk in enumerate(transcript_chunks):
        chunk_file = text_dir / f"subtitle_{turn['segment_index']:03d}_{i:02d}.txt"
        write_textfile(chunk_file, chunk)
        chunk_files.append(chunk_file)

    avatar_input = avatar_map[speaker]
    wave_color = waveform_color(speaker)

    filters = [
        f"[0:v]scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
        f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:white,format=rgba[bg]",
        f"[2:v]scale={AVATAR_SIZE}:{AVATAR_SIZE}[av]",
        f"[1:a]showwaves=s={WAVEFORM_W}x{WAVEFORM_H}:mode=cline:colors={wave_color}:rate={FPS},format=rgba[wave]",
        "[bg][av]overlay=36:36[v1]",
    ]

    current = "v1"
    speaker_label = drawtext_textfile_filter(
        input_label=current,
        output_label="v2",
        textfile=speaker_file,
        fontfile=font_path,
        fontsize=SPEAKER_FONT_SIZE,
        x="170",
        y="74",
        boxcolor="black@0.45",
    )
    filters.append(speaker_label)
    current = "v2"

    filters.append(f"[{current}][wave]overlay={WAVEFORM_X}:{WAVEFORM_Y}:format=auto[vwave]")
    current = "vwave"

    chunk_duration = duration / max(len(chunk_files), 1)
    for i, chunk_file in enumerate(chunk_files):
        start = i * chunk_duration
        end = duration if i == len(chunk_files) - 1 else (i + 1) * chunk_duration
        output_label = f"vsub{i:02d}"
        enable_expr = f"between(t,{start:.3f},{end:.3f})"
        subtitle_filter = drawtext_textfile_filter(
            input_label=current,
            output_label=output_label,
            textfile=chunk_file,
            fontfile=font_path,
            fontsize=SUBTITLE_FONT_SIZE,
            x="(w-text_w)/2",
            y="h-text_h-52",
            boxcolor="black@0.64",
            enable=enable_expr,
        )
        filters.append(subtitle_filter)
        current = output_label

    fade_filters = []
    if fade_in:
        fade_filters.append(f"fade=t=in:st=0:d={SCENE_FADE_SEC}")
    if fade_out and duration > SCENE_FADE_SEC:
        fade_filters.append(f"fade=t=out:st={max(0, duration - SCENE_FADE_SEC):.3f}:d={SCENE_FADE_SEC}")

    if fade_filters:
        filters.append(f"[{current}]{','.join(fade_filters)}[vout]")
        vout = "vout"
    else:
        vout = current

    filter_complex = ";".join(filters)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{duration:.3f}", "-i", bg_image,
        "-i", seg_audio,
        "-i", str(avatar_input),
        "-filter_complex", filter_complex,
        "-map", f"[{vout}]",
        "-map", "1:a:0",
        "-r", str(FPS),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    run(cmd)


def concat_clips(clip_paths: list[Path], concat_file: Path, out_path: Path) -> None:
    with open(concat_file, "w", encoding="utf-8") as f:
        for p in clip_paths:
            f.write(f"file '{p.resolve()}'\n")
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(out_path),
    ]
    run(cmd)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="", help="Week folder or full path. Leave blank to use latest.")
    parser.add_argument("--dialogue-json", default="", help="Optional explicit dialogue json path.")
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args()

    week_dir = latest_week_dir(args.week_dir or None)
    dialogue_json = resolve_dialogue_json(week_dir, args.dialogue_json or None)
    scene_images = resolve_scene_images(week_dir)
    segment_dir = resolve_segment_audio_dir(week_dir)

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Dialogue JSON: {dialogue_json}")
    print(f"[INFO] Scene image count: {len(scene_images)}")
    print(f"[INFO] Segment dir: {segment_dir}")

    out_dir = week_dir / "story_video"
    clip_dir = out_dir / "clips"
    avatar_dir = out_dir / "avatars"
    out_dir.mkdir(parents=True, exist_ok=True)
    clip_dir.mkdir(parents=True, exist_ok=True)
    avatar_dir.mkdir(parents=True, exist_ok=True)

    timeline_json = out_dir / "story_turn_timeline.json"
    final_video = out_dir / "story_visual_video_test.mp4"

    if final_video.exists() and not args.force_rebuild:
        print(f"[SKIP] Output already exists: {final_video}")
        print("[TIP] Use --force-rebuild to regenerate")
        return

    font_path = find_font_path()
    avatar_map = {
        "Tom": avatar_dir / "tom_avatar.png",
        "Miranda": avatar_dir / "miranda_avatar.png",
    }
    make_avatar(avatar_map["Tom"], "Tom", font_path)
    make_avatar(avatar_map["Miranda"], "Miranda", font_path)

    timeline = build_turn_timeline(dialogue_json, scene_images, segment_dir)
    with open(timeline_json, "w", encoding="utf-8") as f:
        json.dump(timeline, f, ensure_ascii=False, indent=2)
    print(f"[OK] Wrote {timeline_json}")

    clip_paths: list[Path] = []
    turns = timeline["turns"]
    for idx, turn in enumerate(turns):
        prev_scene = turns[idx - 1]["scene_index"] if idx > 0 else None
        next_scene = turns[idx + 1]["scene_index"] if idx < len(turns) - 1 else None
        this_scene = turn["scene_index"]
        fade_in = idx == 0 or this_scene != prev_scene
        fade_out = idx == len(turns) - 1 or this_scene != next_scene

        clip_path = clip_dir / f"turn_{turn['segment_index']:03d}.mp4"
        render_turn_clip(turn, clip_path, avatar_map, font_path, fade_in, fade_out)
        clip_paths.append(clip_path)

    concat_file = out_dir / "clips_concat.txt"
    concat_clips(clip_paths, concat_file, final_video)

    print(f"[OK] Created {final_video}")
    print(f"[OK] Total turns: {timeline['turn_count']}")
    print(f"[OK] Total duration: {timeline['total_duration']} sec")


if __name__ == "__main__":
    main()
