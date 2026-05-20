#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 06
Generate TTS audio for host/analyst dialogue narration using Gemini TTS.

Input:
- output/weekly/YYYY-MM-DD/narration/weekly_narration.json

Output:
- output/weekly/YYYY-MM-DD/audio/scene_01.wav ... scene_06.wav
- output/weekly/YYYY-MM-DD/audio/weekly_narration.wav

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_TTS_MODEL, default: gemini-3.1-flash-tts-preview
- GEMINI_TTS_HOST_VOICE, default: Kore
- GEMINI_TTS_ANALYST_VOICE, default: Puck
- FORCE_REBUILD_TTS, default: false
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
DEFAULT_TTS_MODEL = "gemini-2.5-flash-preview-tts"
DEFAULT_TTS_FALLBACK_MODELS = [
    "gemini-2.5-flash-preview-tts",
    "gemini-2.5-pro-preview-tts",
    "gemini-3.1-flash-tts-preview",
]
DEFAULT_HOST_VOICE = "Tom"
DEFAULT_ANALYST_VOICE = "Miranda"


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



def get_tts_model_candidates() -> List[str]:
    raw = os.getenv("GEMINI_TTS_MODEL", "").strip()
    if raw:
        candidates = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        candidates = list(DEFAULT_TTS_FALLBACK_MODELS)

    for item in DEFAULT_TTS_FALLBACK_MODELS:
        if item not in candidates:
            candidates.append(item)

    return candidates


def call_gemini_tts(text: str, model: str, voice: str, api_key: str, role_label: str) -> Dict[str, str]:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    prompt = (
        f"請用自然、穩定、專業的繁體中文財經週報語氣朗讀以下{role_label}內容。"
        "語速中等，段落之間略停頓，不要加入任何額外說明。"
        "不要朗讀角色名稱。\\n\\n"
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
        save_wav_from_pcm(path, raw, sample_rate=24000)


def concat_audio(audio_dir: Path, paths: List[Path], out_path: Path) -> None:
    concat_file = audio_dir / f"{out_path.stem}_concat_list.txt"
    concat_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in paths),
        encoding="utf-8",
    )
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(out_path)],
        check=True,
    )


def get_scene_dialogue(scene: Dict[str, Any]) -> List[Dict[str, str]]:
    dialogue = scene.get("dialogue")
    if isinstance(dialogue, list) and dialogue:
        output = []
        for turn in dialogue:
            if not isinstance(turn, dict):
                continue
            speaker = str(turn.get("speaker") or "analyst").strip()
            text = str(turn.get("text") or "").strip()
            if speaker not in {"host", "analyst"}:
                speaker = "analyst"
            if text:
                output.append({"speaker": speaker, "text": text})
        if output:
            return output

    narration = str(scene.get("narration") or "").strip()
    return [{"speaker": "analyst", "text": narration}] if narration else []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    tts_models = get_tts_model_candidates()
    host_voice = os.getenv("GEMINI_TTS_HOST_VOICE", DEFAULT_HOST_VOICE).strip() or DEFAULT_HOST_VOICE
    analyst_voice = os.getenv("GEMINI_TTS_ANALYST_VOICE", DEFAULT_ANALYST_VOICE).strip() or DEFAULT_ANALYST_VOICE

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

    scene_audio_paths: List[Path] = []
    print(f"[INFO] Generating dialogue TTS with model candidates: {', '.join(tts_models)}")
    print(f"[INFO] host_voice={host_voice}, analyst_voice={analyst_voice}")

    for scene in scenes:
        scene_id = scene.get("scene_id")
        if not scene_id:
            continue

        scene_turn_paths: List[Path] = []
        turns = get_scene_dialogue(scene)

        for idx, turn in enumerate(turns, start=1):
            speaker = turn["speaker"]
            text = turn["text"]
            voice = host_voice if speaker == "host" else analyst_voice
            role_label = "主持人" if speaker == "host" else "分析師"

            turn_path = audio_dir / "turns" / f"{scene_id}_{idx:02d}_{speaker}.wav"
            if turn_path.exists() and not flag("FORCE_REBUILD_TTS"):
                print(f"[SKIP] Turn audio exists: {turn_path}")
            else:
                print(f"[INFO] Generating {scene_id} turn {idx}: {speaker}")
                last_error = None
                for model in tts_models:
                    try:
                        print(f"[INFO] Trying TTS model: {model}")
                        audio = call_gemini_tts(text, model, voice, api_key, role_label)
                        write_audio_file(turn_path, audio)
                        last_error = None
                        break
                    except RuntimeError as exc:
                        last_error = exc
                        message = str(exc)
                        if "HTTPError 404" in message or "NOT_FOUND" in message:
                            print(f"[WARN] TTS model not available: {model}. Trying next fallback model.")
                            continue
                        raise
                if last_error is not None:
                    raise last_error

            scene_turn_paths.append(turn_path)

        if not scene_turn_paths:
            continue

        scene_out = audio_dir / f"{scene_id}.wav"
        concat_audio(audio_dir, scene_turn_paths, scene_out)
        scene_audio_paths.append(scene_out)

    if not scene_audio_paths:
        raise RuntimeError("No scene audio files generated.")

    concat_audio(audio_dir, scene_audio_paths, full_audio)
    print(f"[OK] Created {full_audio}")


if __name__ == "__main__":
    main()
