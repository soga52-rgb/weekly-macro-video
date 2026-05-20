#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Step 03
Generate weekly macro transmission diagram image with Gemini image model.

Input:
- output/weekly/YYYY-MM-DD/weekly_macro_diagram_prompt.txt

Output:
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png

Required env:
- GEMINI_API_KEY

Optional env:
- GEMINI_IMAGE_MODEL, default: gemini-3.1-flash-image-preview
- FORCE_REBUILD_DIAGRAM, default: false

Skip logic:
- If weekly_macro_diagram.png already exists and FORCE_REBUILD_DIAGRAM is not true,
  skip image generation. This avoids repeated image-model calls when only page CSS/HTML changes.
"""

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def should_force_rebuild() -> bool:
    return os.getenv("FORCE_REBUILD_DIAGRAM", "false").strip().lower() in {"1", "true", "yes", "y"}


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def save_binary(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def find_inline_image(api_response: Dict[str, Any]) -> Optional[bytes]:
    candidates = api_response.get("candidates") or []

    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []

        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if not inline_data:
                continue

            data = inline_data.get("data")
            if not data:
                continue

            return base64.b64decode(data)

    return None


def call_gemini_image(prompt: str, model: str, api_key: str) -> bytes:
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
        },
    }

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini image HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini image URLError: {exc}") from exc

    api_response = json.loads(raw)
    image_bytes = find_inline_image(api_response)

    if not image_bytes:
        preview = json.dumps(api_response, ensure_ascii=False)[:1500]
        raise RuntimeError(f"No inline image found in Gemini response. Preview: {preview}")

    return image_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    out_path = week_dir / "weekly_macro_diagram.png"
    if out_path.exists() and not should_force_rebuild():
        print(f"[SKIP] Diagram image already exists: {out_path}")
        print("[SKIP] Set FORCE_REBUILD_DIAGRAM=true to regenerate image.")
        return

    prompt = load_text(week_dir / "weekly_macro_diagram_prompt.txt")

    print(f"[INFO] Generating weekly macro diagram image with model: {model}")
    image_bytes = call_gemini_image(prompt, model, api_key)

    save_binary(out_path, image_bytes)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
