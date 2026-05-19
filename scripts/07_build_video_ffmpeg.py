#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 07
Build final video with FFmpeg.

Input:
- output/weekly/YYYY-MM-DD/image_cards/card_01.png ~ card_06.png
- output/weekly/YYYY-MM-DD/audio/scene_01.mp3 ~ scene_06.mp3

Fallback image folders:
- image_cards
- brief_cards
- ai_cards
- cards

Output:
- output/weekly/YYYY-MM-DD/final/weekly_macro_video.mp4
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def require_ffmpeg() -> None:
    if not shutil.which("ffmpeg"):
        raise EnvironmentError("ffmpeg not found.")
    if not shutil.which("ffprobe"):
        raise EnvironmentError("ffprobe not found.")


def audio_duration_sec(path: Path) -> float:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


def find_image_files(week_dir: Path) -> List[Path]:
    for folder in ["image_cards", "brief_cards", "ai_cards", "cards"]:
        card_dir = week_dir / folder
        if card_dir.exists():
            images = sorted(list(card_dir.glob("card_*.png")) + list(card_dir.glob("card_*.jpg")) + list(card_dir.glob("card_*.jpeg")))
            if images:
                print(f"[INFO] Using image folder: {card_dir}")
                return images
    raise FileNotFoundError("No card images found. Expected image_cards/card_01.png etc.")


def find_audio_files(week_dir: Path) -> List[Path]:
    audio_dir = week_dir / "audio"
    audios = sorted(list(audio_dir.glob("scene_*.mp3")) + list(audio_dir.glob("scene_*.wav")) + list(audio_dir.glob("scene_*.m4a")))
    if not audios:
        raise FileNotFoundError(f"No audio files found under {audio_dir}")
    return audios


def build_scene_video(image: Path, audio: Path, out_path: Path) -> None:
    duration = audio_duration_sec(audio)
    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", "30",
        "-i", str(image),
        "-i", str(audio),
        "-t", f"{duration:.3f}",
        "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def concat_videos(scene_videos: List[Path], final_path: Path) -> None:
    concat_file = final_path.parent / "concat_list.txt"
    lines = []
    for path in scene_videos:
        lines.append(f"file '{path.resolve()}'")
    concat_file.write_text("\n".join(lines), encoding="utf-8")

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(final_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    require_ffmpeg()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    images = find_image_files(week_dir)
    audios = find_audio_files(week_dir)

    count = min(len(images), len(audios))
    if count == 0:
        raise RuntimeError("No image/audio pairs available.")
    if len(images) != len(audios):
        print(f"[WARN] Image count ({len(images)}) and audio count ({len(audios)}) differ. Using first {count} pairs.")

    work_dir = week_dir / "video_work"
    final_dir = week_dir / "final"
    work_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    scene_videos: List[Path] = []
    for i in range(count):
        out_path = work_dir / f"scene_{i + 1:02d}.mp4"
        print(f"[INFO] Building scene {i + 1}: {images[i].name} + {audios[i].name}")
        build_scene_video(images[i], audios[i], out_path)
        scene_videos.append(out_path)
        print(f"[OK] Created {out_path}")

    final_path = final_dir / "weekly_macro_video.mp4"
    concat_videos(scene_videos, final_path)
    print(f"[OK] Created final video: {final_path}")


if __name__ == "__main__":
    main()
