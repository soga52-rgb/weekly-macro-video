#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 04
Generate image cards with Gemini image model.

Input:
- output/weekly/YYYY-MM-DD/weekly_image_prompts.json
  or output/weekly/YYYY-MM-DD/image_prompts/card_01.txt ~ card_06.txt

Output:
- output/weekly/YYYY-MM-DD/image_cards/card_01.png ~ card_06.png
- output/weekly/YYYY-MM-DD/weekly_image_cards_manifest.json

Environment:
- GEMINI_API_KEY           required
- GEMINI_IMAGE_MODEL       optional, default: gemini-3-pro-image-preview
"""

import argparse
import base64
import json
import mimetypes
import os
import time
import socket
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_IMAGE_MODEL = "gemini-3.1-flash-image-preview"
DEFAULT_IMAGE_TIMEOUT_SEC = 600


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def guess_extension(mime_type: str) -> str:
    if not mime_type:
        return ".png"
    ext = mimetypes.guess_extension(mime_type)
    if ext == ".jpe":
        ext = ".jpg"
    return ext or ".png"


def extract_inline_image(api_response: Dict[str, Any]) -> Dict[str, Any]:
    """
    Find first inline image in Gemini generateContent response.
    Expected image part shape:
    {
      "inlineData": {
        "mimeType": "image/png",
        "data": "base64..."
      }
    }
    """
    candidates = api_response.get("candidates", [])
    for candidate in candidates:
        content = candidate.get("content", {})
        parts = content.get("parts", [])
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                return {
                    "mime_type": inline.get("mimeType", "image/png"),
                    "data_b64": inline["data"],
                    "text": part.get("text", "")
                }
    raise RuntimeError(f"Gemini image response does not contain inline image data: {json.dumps(api_response, ensure_ascii=False)[:1200]}")


def call_gemini_image(prompt: str, model: str, api_key: str, timeout_sec: int, retries: int = 3, sleep_sec: float = 10.0) -> Dict[str, Any]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "responseModalities": ["TEXT", "IMAGE"]
        }
    }

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"Gemini image HTTPError {exc.code}: {detail}")
            if exc.code in (429, 500, 503) and attempt < retries:
                print(f"[WARN] Gemini image attempt {attempt} failed with HTTP {exc.code}, retrying...")
                time.sleep(sleep_sec * attempt)
                continue
            raise last_error
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            last_error = RuntimeError(f"Gemini image connection/timeout error: {exc}")
            if attempt < retries:
                print(f"[WARN] Gemini image attempt {attempt} failed by timeout/network issue, retrying...")
                time.sleep(sleep_sec * attempt)
                continue
            raise last_error

    if last_error:
        raise last_error
    raise RuntimeError("Gemini image call failed unexpectedly.")


def load_prompt_package(week_dir: Path) -> List[Dict[str, str]]:
    package_path = week_dir / "weekly_image_prompts.json"
    if package_path.exists():
        data = load_json(package_path)
        cards = data.get("cards", [])
        if cards:
            return cards

    prompt_dir = week_dir / "image_prompts"
    if not prompt_dir.exists():
        raise FileNotFoundError(f"Prompt package not found: {package_path} or {prompt_dir}")

    cards = []
    for path in sorted(prompt_dir.glob("card_*.txt")):
        cards.append({
            "card_id": path.stem,
            "title": path.stem,
            "prompt": load_text(path)
        })

    if not cards:
        raise FileNotFoundError(f"No prompt files found under {prompt_dir}")
    return cards


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of cards to generate.")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    timeout_sec = int(os.getenv("GEMINI_IMAGE_TIMEOUT_SEC", str(DEFAULT_IMAGE_TIMEOUT_SEC)))
    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    cards = load_prompt_package(week_dir)
    if args.limit and args.limit > 0:
        cards = cards[: args.limit]

    out_dir = week_dir / "image_cards"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest_cards = []

    for idx, card in enumerate(cards, start=1):
        card_id = card.get("card_id", f"card_{idx:02d}")
        prompt = card.get("prompt", "").strip()
        if not prompt:
            raise ValueError(f"Empty prompt for {card_id}")

        print(f"[INFO] Generating {card_id} with model {model} ...")
        print(f"[INFO] Timeout: {timeout_sec} seconds")
        api_response = call_gemini_image(prompt, model, api_key, timeout_sec=timeout_sec)
        image_info = extract_inline_image(api_response)

        mime_type = image_info["mime_type"]
        img_bytes = base64.b64decode(image_info["data_b64"])
        ext = guess_extension(mime_type)

        out_path = out_dir / f"{card_id}{ext}"
        out_path.write_bytes(img_bytes)

        manifest_cards.append({
            "card_id": card_id,
            "title": card.get("title", ""),
            "model": model,
            "mime_type": mime_type,
            "output_file": str(out_path),
            "prompt_file": str((week_dir / "image_prompts" / f"{card_id}.txt")),
            "status": "success"
        })

        print(f"[OK] Created {out_path}")

    manifest = {
        "week_dir": str(week_dir),
        "model": model,
        "cards": manifest_cards
    }
    manifest_path = week_dir / "weekly_image_cards_manifest.json"
    save_json(manifest_path, manifest)
    print(f"[OK] Created {manifest_path}")


if __name__ == "__main__":
    main()
