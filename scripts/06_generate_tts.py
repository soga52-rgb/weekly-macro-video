#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 06
Generate TTS audio using Gemini 3.1 Flash TTS Preview.

Input:
- output/weekly/YYYY-MM-DD/narration/scene_01.txt ~ scene_06.txt

Output:
- output/weekly/YYYY-MM-DD/audio/scene_01.wav ~ scene_06.wav
- output/weekly/YYYY-MM-DD/weekly_audio_manifest.json

Fallback:
- If Gemini TTS fails and --no-fallback is not set, uses gTTS MP3.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_TTS_MODEL = "gemini-3.1-flash-tts-preview"
DEFAULT_TTS_VOICE = "Kore"

def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]

def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def write_wav(path: Path, pcm: bytes, channels: int = 1, rate: int = 24000, sample_width: int = 2) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

def build_tts_prompt(script: str) -> str:
    return (
        "Read the following Traditional Chinese narration in a lively but professional macro explainer tone. "
        "Pace: slightly faster than normal. "
        "Style: natural, clear, energetic, with emphasis on questions and transitions. "
        "Do not sound like reading a report. "
        "Do not read this instruction aloud.\n\n"
        + script
    )

def extract_audio_b64(response: Dict[str, Any]) -> str:
    for candidate in response.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return inline["data"]
    raise RuntimeError("Gemini TTS response does not contain inline audio data.")

def call_gemini_tts(prompt: str, model: str, voice_name: str, api_key: str) -> bytes:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name}
                }
            }
        }
    }
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini TTS HTTPError {exc.code}: {detail}") from exc
    return base64.b64decode(extract_audio_b64(json.loads(raw)))

def ensure_gtts() -> None:
    try:
        import gtts  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gTTS"])

def fallback_gtts(text: str, out_path: Path, lang: str = "zh-tw") -> None:
    ensure_gtts()
    from gtts import gTTS
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(str(out_path))

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--no-fallback", action="store_true")
    args = parser.parse_args()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")
    model = os.getenv("GEMINI_TTS_MODEL", DEFAULT_TTS_MODEL).strip() or DEFAULT_TTS_MODEL
    voice = os.getenv("GEMINI_TTS_VOICE", DEFAULT_TTS_VOICE).strip() or DEFAULT_TTS_VOICE
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    narration_dir = week_dir / "narration"
    audio_dir = week_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    scene_files = sorted(narration_dir.glob("scene_*.txt"))
    if not scene_files:
        raise FileNotFoundError(f"No narration scene files found under {narration_dir}")
    manifest: List[Dict[str, Any]] = []
    for txt_path in scene_files:
        script = txt_path.read_text(encoding="utf-8").strip()
        if not script:
            continue
        scene_id = txt_path.stem
        out_path = audio_dir / f"{scene_id}.wav"
        print(f"[INFO] Generating Gemini TTS: {scene_id}, model={model}, voice={voice}")
        try:
            pcm = call_gemini_tts(build_tts_prompt(script), model, voice, api_key)
            write_wav(out_path, pcm)
            manifest.append({
                "scene_id": scene_id,
                "text_file": str(txt_path),
                "audio_file": str(out_path),
                "engine": "Gemini TTS",
                "model": model,
                "voice": voice,
                "status": "success",
            })
            print(f"[OK] Created {out_path}")
        except Exception as exc:
            print(f"[WARN] Gemini TTS failed for {scene_id}: {exc}")
            if args.no_fallback:
                raise
            fallback_path = audio_dir / f"{scene_id}.mp3"
            print(f"[INFO] Falling back to gTTS: {fallback_path}")
            fallback_gtts(script, fallback_path)
            manifest.append({
                "scene_id": scene_id,
                "text_file": str(txt_path),
                "audio_file": str(fallback_path),
                "engine": "gTTS fallback",
                "model": "",
                "voice": "",
                "status": "fallback",
                "error": str(exc),
            })
            print(f"[OK] Created fallback {fallback_path}")
    save_json(week_dir / "weekly_audio_manifest.json", {"audio": manifest})
    print(f"[OK] Created {week_dir / 'weekly_audio_manifest.json'}")

if __name__ == "__main__":
    main()
