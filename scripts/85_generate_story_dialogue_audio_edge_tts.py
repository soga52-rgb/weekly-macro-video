#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Step 85 - Generate Story Dialogue Audio with edge-tts

Purpose:
- Read Step 82 story-only dialogue JSON.
- Convert each speaker_turn.spoken_text into audio using edge-tts.
- Preserve the original script exactly; do NOT rewrite, summarize, or regenerate narration.
- Use separate voices for Tom and Miranda.
- Merge all turn-level mp3 files into one full dialogue mp3.
- Produce an audio timeline JSON for later video composition.

Input:
- output/weekly/<week_dir>/weekly_dialogue_story_only_v8.json

Outputs:
- output/weekly/<week_dir>/story_audio/segments/seg_000_Tom.mp3 ...
- output/weekly/<week_dir>/story_audio/full_dialogue.mp3
- output/weekly/<week_dir>/story_audio/audio_timeline.json
- output/weekly/<week_dir>/story_audio/tts_manifest.json

Environment variables / CLI:
- WEEK_DIR: optional week directory.
- TOM_VOICE: default zh-CN-YunxiNeural
- MIRANDA_VOICE: default zh-TW-HsiaoChenNeural
- TTS_RATE: default -8%
- TTS_VOLUME: default +0%
- TOM_PITCH: default -5Hz
- MIRANDA_PITCH: default +0Hz
- FORCE_REBUILD_AUDIO: true/false
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

DIALOGUE_JSON_FILENAME = "weekly_dialogue_story_only_v8.json"

OUTPUT_DIRNAME = "story_audio"
SEGMENTS_DIRNAME = "segments"
FULL_AUDIO_FILENAME = "full_dialogue.mp3"
TIMELINE_FILENAME = "audio_timeline.json"
MANIFEST_FILENAME = "tts_manifest.json"

DEFAULT_TOM_VOICE = "zh-TW-YunJheNeural"
DEFAULT_MIRANDA_VOICE = "zh-TW-HsiaoChenNeural"
DEFAULT_TTS_RATE = "-8%"
DEFAULT_TTS_VOLUME = "+0%"
DEFAULT_TOM_PITCH = "-5Hz"
DEFAULT_MIRANDA_PITCH = "+0Hz"


def env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "y", "on"}


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


def check_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is required but was not found in PATH.")


def edge_tts_command() -> List[str]:
    edge_tts_exe = shutil.which("edge-tts")
    if edge_tts_exe:
        return [edge_tts_exe]
    return [sys.executable, "-m", "edge_tts"]


def clean_text(text: str) -> str:
    """
    Prepare text for edge-tts.

    This does not rewrite narration. It only removes markdown markers and adds
    small punctuation pauses around finance-specific English acronyms and
    numeric values so TTS sounds less rushed.
    """
    text = str(text or "").strip()
    text = text.replace("*", "").replace("#", "")

    # Add micro-pauses around uppercase finance terms: WTI, PIMCO, AI, CPI, DXY, etc.
    text = re.sub(r"(?<![A-Za-z])([A-Z]{2,})(?![A-Za-z])", r"，\1，", text)

    # Add micro-pauses around key decimal numbers and percentages: 87.36, 4.453%, etc.
    text = re.sub(r"([0-9]+\.[0-9]+%?)", r"，\1，", text)

    # Clean duplicated punctuation introduced by the pause rules.
    text = re.sub(r"，+", "，", text)
    text = text.replace("，。", "。").replace("。，", "。")
    text = text.replace("，？", "？").replace("？，", "？")
    text = text.replace("，！", "！").replace("！，", "！")
    text = text.replace("，，", "，")

    text = re.sub(r"\s+", " ", text)
    return text


def speaker_voice(speaker: str, tom_voice: str, miranda_voice: str) -> str:
    normalized = speaker.strip().lower()
    if normalized == "miranda":
        return miranda_voice
    return tom_voice


def extract_turns(dialogue: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections = dialogue.get("sections")
    if not isinstance(sections, list):
        return []

    turns: List[Dict[str, Any]] = []

    for section_index, section in enumerate(sections, start=1):
        if not isinstance(section, dict):
            continue

        section_id = str(section.get("section_id") or f"s{section_index}").strip()
        scene_id = f"scene_{section_index:02d}"
        section_title = str(section.get("section_title", "")).strip()
        speaker_turns = section.get("speaker_turns")

        if not isinstance(speaker_turns, list):
            continue

        for turn_index, turn in enumerate(speaker_turns, start=1):
            if not isinstance(turn, dict):
                continue

            speaker = str(turn.get("speaker", "")).strip() or "Tom"
            text = clean_text(turn.get("spoken_text", ""))
            if not text:
                continue

            turns.append({
                "turn_id": f"turn_{len(turns):03d}",
                "section_id": section_id,
                "scene_id": scene_id,
                "section_title": section_title,
                "turn_index_in_section": turn_index,
                "speaker": speaker,
                "spoken_text": text,
                "subtitle_text": str(turn.get("subtitle_text", "")).strip(),
                "estimated_seconds": turn.get("estimated_seconds", ""),
            })

    return turns


def generate_segment_audio(
    text: str,
    voice: str,
    out_path: Path,
    rate: str,
    volume: str,
    pitch: str,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    command = edge_tts_command()

    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)

    try:
        cmd = command + [
            "--file", str(tmp_path),
            "--voice", voice,
            f"--rate={rate}",
            f"--volume={volume}",
            f"--pitch={pitch}",
            "--write-media", str(out_path),
        ]
        subprocess.run(cmd, check=True, timeout=120)
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass


def ffprobe_duration(audio_path: Path) -> float:
    try:
        raw = subprocess.check_output([
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ])
        return float(raw.decode("utf-8").strip())
    except Exception as exc:
        print(f"[WARN] Failed to read duration for {audio_path}: {exc}")
        return 0.0


def concat_audio(segment_paths: List[Path], out_path: Path) -> None:
    if not segment_paths:
        raise RuntimeError("No audio segments to concatenate.")

    list_path = out_path.parent / "audio_concat_list.txt"
    list_path.write_text(
        "\n".join(f"file '{p.resolve()}'" for p in segment_paths) + "\n",
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg",
        "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default=os.getenv("WEEK_DIR", "").strip())
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    check_ffmpeg()

    week_dir = resolve_week_dir(args.week_dir)
    if not week_dir.exists():
        raise FileNotFoundError(f"Week directory not found: {week_dir}")

    dialogue_path = week_dir / DIALOGUE_JSON_FILENAME
    dialogue = load_json(dialogue_path, {})
    if not dialogue:
        raise FileNotFoundError(f"Missing or empty dialogue JSON: {dialogue_path}")

    tom_voice = os.getenv("TOM_VOICE", DEFAULT_TOM_VOICE).strip() or DEFAULT_TOM_VOICE
    miranda_voice = os.getenv("MIRANDA_VOICE", DEFAULT_MIRANDA_VOICE).strip() or DEFAULT_MIRANDA_VOICE
    rate = os.getenv("TTS_RATE", DEFAULT_TTS_RATE).strip() or DEFAULT_TTS_RATE
    volume = os.getenv("TTS_VOLUME", DEFAULT_TTS_VOLUME).strip() or DEFAULT_TTS_VOLUME
    tom_pitch = os.getenv("TOM_PITCH", DEFAULT_TOM_PITCH).strip() or DEFAULT_TOM_PITCH
    miranda_pitch = os.getenv("MIRANDA_PITCH", DEFAULT_MIRANDA_PITCH).strip() or DEFAULT_MIRANDA_PITCH
    force_rebuild = args.force or env_bool("FORCE_REBUILD_AUDIO", "false")

    out_dir = week_dir / OUTPUT_DIRNAME
    segments_dir = out_dir / SEGMENTS_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    segments_dir.mkdir(parents=True, exist_ok=True)

    turns = extract_turns(dialogue)
    if not turns:
        raise RuntimeError("No speaker turns found in dialogue JSON.")

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Dialogue input: {dialogue_path}")
    print(f"[INFO] Turn count: {len(turns)}")
    print(f"[INFO] Tom voice: {tom_voice}")
    print(f"[INFO] Miranda voice: {miranda_voice}")
    print(f"[INFO] Rate: {rate}")
    print(f"[INFO] Volume: {volume}")
    print(f"[INFO] Tom pitch: {tom_pitch}")
    print(f"[INFO] Miranda pitch: {miranda_pitch}")
    print(f"[INFO] Force rebuild: {force_rebuild}")

    timeline: List[Dict[str, Any]] = []
    segment_paths: List[Path] = []
    cursor = 0.0

    for i, turn in enumerate(turns):
        speaker = str(turn["speaker"])
        voice = speaker_voice(speaker, tom_voice, miranda_voice)
        current_pitch = miranda_pitch if speaker.strip().lower() == "miranda" else tom_pitch
        safe_speaker = re.sub(r"[^A-Za-z0-9]+", "", speaker) or "Speaker"
        seg_path = segments_dir / f"seg_{i:03d}_{safe_speaker}.mp3"

        if seg_path.exists() and seg_path.stat().st_size > 0 and not force_rebuild:
            print(f"[SKIP] Existing audio: {seg_path}")
        else:
            print(f"[INFO] Generate {speaker} audio {i+1}/{len(turns)} | pitch={current_pitch}")
            generate_segment_audio(
                text=turn["spoken_text"],
                voice=voice,
                out_path=seg_path,
                rate=rate,
                volume=volume,
                pitch=current_pitch,
            )

        duration = ffprobe_duration(seg_path)
        start = cursor
        end = cursor + duration
        cursor = end
        segment_paths.append(seg_path)

        timeline.append({
            **turn,
            "voice": voice,
            "pitch": current_pitch,
            "audio_path": str(seg_path),
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "duration_seconds": round(duration, 3),
        })

    full_audio = out_dir / FULL_AUDIO_FILENAME
    print("[INFO] Concatenate audio segments...")
    concat_audio(segment_paths, full_audio)

    full_duration = ffprobe_duration(full_audio)

    manifest = {
        "meta": {
            "type": "story_edge_tts_audio_v1",
            "source_dialogue": str(dialogue_path),
            "output_audio": str(full_audio),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "tom_voice": tom_voice,
            "miranda_voice": miranda_voice,
            "tts_rate": rate,
            "tts_volume": volume,
            "tom_pitch": tom_pitch,
            "miranda_pitch": miranda_pitch,
            "turn_count": len(turns),
            "full_duration_seconds": round(full_duration, 3),
            "note": "edge-tts reads Step 82 spoken_text with light punctuation pauses for more natural TTS; no narration regeneration.",
        },
        "timeline_file": str(out_dir / TIMELINE_FILENAME),
    }

    save_json(out_dir / TIMELINE_FILENAME, timeline)
    save_json(out_dir / MANIFEST_FILENAME, manifest)

    print(f"[OK] Created full audio: {full_audio}")
    print(f"[OK] Created timeline: {out_dir / TIMELINE_FILENAME}")
    print(f"[OK] Created manifest: {out_dir / MANIFEST_FILENAME}")


if __name__ == "__main__":
    main()
