#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 06
Generate TTS audio for weekly narration using Gemini TTS.

Input:
- output/weekly/YYYY-MM-DD/narration/weekly_narration.json

Output:
- output/weekly/YYYY-MM-DD/audio/scene_01.wav ... scene_06.wav
- output/weekly/YYYY-MM-DD/audio/weekly_narration.wav
"""

import argparse
import base64
import json
import os
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional


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


def flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes", "y"}


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_wav_from_pcm(path: Path, pcm_data: bytes, sample_rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_data)


def find_inline_audio(api_response: Dict[str, Any]) -> Optional[Dict[str, str]]:
    candidates = api_response.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue
            data = inline_data.get("data")
            if data:
                return {
                    "mime_type": inline_data.get("mimeType") or inline_data.get("mime_type") or "",
                    "data": data,
                }
    return None


def call_gemini_tts(text: str, model: str, voice: str, api_key: str) -> Dict[str, str]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    prompt = (
        "請用自然、穩定、專業的繁體中文財經週報語氣朗讀以下內容。"
        "語速中等，段落之間略停頓，不要加入任何額外說明。\n\n"
        + text
    )

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice
                    }
                }
            },
        },
    }

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini TTS HTTPError {exc.code}: {detail}") from exc

    audio = find_inline_audio(json.loads(raw))
    if not audio:
        raise RuntimeError(f"No inline audio found in Gemini TTS response. Preview: {raw[:1500]}")
    return audio


def write_audio_file(path: Path, audio: Dict[str, str]) -> None:
    mime_type = (audio.get("mime_type") or "").lower()
    raw = base64.b64decode(audio["data"])
    path.parent.mkdir(parents=True, exist_ok=True)

    if "wav" in mime_type or raw[:4] == b"RIFF":
        path.write_bytes(raw)
    else:
        # Gemini TTS preview may return raw PCM/L16.
        save_wav_from_pcm(path, raw, sample_rate=24000)


def concat_wavs(audio_dir: Path, scene_paths: List[Path], out_path: Path) -> None:
    concat_file = audio_dir / "tts_concat_list.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in scene_paths),
        encoding="utf-8",
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(out_path)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_TTS_MODEL", DEFAULT_TTS_MODEL).strip() or DEFAULT_TTS_MODEL
    voice = os.getenv("GEMINI_TTS_VOICE", DEFAULT_TTS_VOICE).strip() or DEFAULT_TTS_VOICE

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    narration = load_json(week_dir / "narration" / "weekly_narration.json")
    audio_dir = week_dir / "audio"
    full_audio = audio_dir / "weekly_narration.wav"

    if full_audio.exists() and not flag("FORCE_REBUILD_TTS"):
        print(f"[SKIP] TTS audio already exists: {full_audio}")
        return

    scenes = narration.get("scenes") or []
    if not scenes:
        raise RuntimeError("weekly_narration.json has no scenes.")

    scene_paths: List[Path] = []
    print(f"[INFO] Generating TTS with model: {model}, voice: {voice}")

    for scene in scenes:
        scene_id = scene.get("scene_id")
        text = str(scene.get("narration") or "").strip()
        if not scene_id or not text:
            continue

        out_path = audio_dir / f"{scene_id}.wav"
        if out_path.exists() and not flag("FORCE_REBUILD_TTS"):
            print(f"[SKIP] Scene audio exists: {out_path}")
        else:
            print(f"[INFO] Generating audio: {scene_id}")
            write_audio_file(out_path, call_gemini_tts(text, model, voice, api_key))
        scene_paths.append(out_path)

    if not scene_paths:
        raise RuntimeError("No scene audio files generated.")

    concat_wavs(audio_dir, scene_paths, full_audio)
    print(f"[OK] Created {full_audio}")


if __name__ == "__main__":
    main()
