#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 07 SLIDES ONLY

Purpose:
- Build final video directly from:
  output/weekly/YYYY-MM-DD/slides/scene_01.png ... scene_06.png
  output/weekly/YYYY-MM-DD/audio/scene_01.wav ... scene_06.wav

This version intentionally DOES NOT render old V8.5 focus/minimap pages.
It only pairs each slide image with its matching audio clip, then concatenates them.
"""

import os
import subprocess
import wave
from pathlib import Path
from typing import List, Optional

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

FPS = 30
VIDEO_W = 1920
VIDEO_H = 1080


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def find_week_dir() -> Path:
    explicit = os.getenv("WEEK_END_DATE", "").strip() or os.getenv("WEEK_DATE", "").strip()
    if explicit:
        week_dir = OUTPUT_WEEKLY_DIR / explicit
        if not week_dir.exists():
            raise FileNotFoundError(f"Target weekly folder not found: {week_dir}")
        return week_dir

    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def run(cmd: List[str]) -> None:
    print("[CMD]", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def audio_duration_seconds(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing {label}: {path}")


def build_scene_video(image_path: Path, audio_path: Path, out_path: Path) -> None:
    duration = audio_duration_seconds(audio_path)
    ensure_dir(out_path.parent)

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-framerate", str(FPS),
        "-i", str(image_path),
        "-i", str(audio_path),
        "-t", f"{duration:.3f}",
        "-vf", f"scale={VIDEO_W}:{VIDEO_H}:force_original_aspect_ratio=decrease,"
               f"pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:(oh-ih)/2:color=white,"
               f"setsar=1",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(out_path),
    ]
    run(cmd)


def concat_videos(scene_videos: List[Path], out_path: Path) -> None:
    ensure_dir(out_path.parent)
    list_path = out_path.parent / "video_concat_list.txt"
    list_path.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in scene_videos),
        encoding="utf-8",
    )

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_path),
        "-c", "copy",
        str(out_path),
    ]
    run(cmd)


def main() -> None:
    week_dir = find_week_dir()
    slides_dir = week_dir / "slides"
    audio_dir = week_dir / "audio"
    video_assets_dir = week_dir / "video_assets"
    scene_video_dir = video_assets_dir / "scene_videos"
    final_dir = week_dir / "final"

    ensure_dir(scene_video_dir)
    ensure_dir(final_dir)

    print(f"[INFO] week_dir={week_dir}")
    print(f"[INFO] slides_dir={slides_dir}")
    print(f"[INFO] audio_dir={audio_dir}")
    print("[INFO] Building video from slides/scene_XX.png + audio/scene_XX.wav")

    scene_video_paths: List[Path] = []

    for idx in range(1, 7):
        scene_id = f"scene_{idx:02d}"
        image_path = slides_dir / f"{scene_id}.png"
        audio_path = audio_dir / f"{scene_id}.wav"
        video_path = scene_video_dir / f"{scene_id}.mp4"

        require_file(image_path, f"{scene_id} slide image")
        require_file(audio_path, f"{scene_id} audio")

        print(f"[INFO] Pairing {image_path.name} + {audio_path.name}")
        build_scene_video(image_path, audio_path, video_path)
        scene_video_paths.append(video_path)

    final_path = final_dir / "weekly_macro_video.mp4"
    concat_videos(scene_video_paths, final_path)

    print(f"[OK] Created final video: {final_path}")


if __name__ == "__main__":
    main()
