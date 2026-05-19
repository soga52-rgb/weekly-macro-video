#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 06
Generate TTS audio files from narration scripts.

Default engine:
- gTTS, output MP3.
- This is a lightweight first version for GitHub Actions.
- Later this can be replaced with Gemini TTS or OpenAI TTS.

Input:
- output/weekly/YYYY-MM-DD/narration/scene_01.txt ~ scene_06.txt

Output:
- output/weekly/YYYY-MM-DD/audio/scene_01.mp3 ~ scene_06.mp3
- output/weekly/YYYY-MM-DD/weekly_audio_manifest.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


def ensure_gtts() -> None:
    try:
        import gtts  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gTTS"])


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def save_json(path: Path, data: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--lang", type=str, default="zh-tw")
    parser.add_argument("--slow", action="store_true")
    args = parser.parse_args()

    ensure_gtts()
    from gtts import gTTS

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    narration_dir = week_dir / "narration"
    audio_dir = week_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    scene_files = sorted(narration_dir.glob("scene_*.txt"))
    if not scene_files:
        raise FileNotFoundError(f"No narration scene files found under {narration_dir}")

    manifest: List[Dict] = []
    for txt_path in scene_files:
        text = txt_path.read_text(encoding="utf-8").strip()
        if not text:
            continue

        out_path = audio_dir / f"{txt_path.stem}.mp3"
        print(f"[INFO] Generating TTS: {out_path}")

        tts = gTTS(text=text, lang=args.lang, slow=args.slow)
        tts.save(str(out_path))

        manifest.append({
            "scene_id": txt_path.stem,
            "text_file": str(txt_path),
            "audio_file": str(out_path),
            "engine": "gTTS",
            "lang": args.lang,
        })
        print(f"[OK] Created {out_path}")

    save_json(week_dir / "weekly_audio_manifest.json", {"audio": manifest})
    print(f"[OK] Created {week_dir / 'weekly_audio_manifest.json'}")


if __name__ == "__main__":
    main()
