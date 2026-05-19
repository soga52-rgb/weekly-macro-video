#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 04 v3
Generate image cards with Gemini image model, with resume / skip-existing support.

Input:
- output/weekly/YYYY-MM-DD/weekly_image_prompts.json
  or output/weekly/YYYY-MM-DD/image_prompts/card_01.txt ~ card_06.txt

Output:
- output/weekly/YYYY-MM-DD/image_cards/card_01.png ~ card_06.png
- output/weekly/YYYY-MM-DD/weekly_image_cards_manifest.json

Environment:
- GEMINI_API_KEY             required
- GEMINI_IMAGE_MODEL         optional, default: gemini-3.1-flash-image-preview
- GEMINI_IMAGE_TIMEOUT_SEC   optional, default: 600
"""

import argparse
import base64
import json
import mimetypes
import os
import socket
import time
import urllib.error
import urllib.parse
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


def existing_card_file(out_dir: Path, card_id: str) -> Optional[Path]:
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        path = out_dir / f"{card_id}{ext}"
        if path.exists() and path.stat().st_size > 0:
            return path
    return None


def extract_inline_image(api_response: Dict[str, Any]) -> Dict[str, Any]:
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
                }

    raise RuntimeError(
        "Gemini image response does not contain inline image data: "
        + json.dumps(api_response, ensure_ascii=False)[:1200]
    )


def call_gemini_image(
    prompt: str,
    model: str,
    api_key: str,
    timeout_sec: int,
    retries: int = 3,
    sleep_sec: float = 20.0,
) -> Dict[str, Any]:
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

    last_error: Optional[Exception] = None

    for attempt in range(1, retries + 1):
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=timeout_sec) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)

        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"Gemini image HTTPError {exc.code}: {detail}")

            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                wait = sleep_sec * attempt
                print(f"[WARN] HTTP {exc.code}; retrying in {wait:.0f}s...")
                time.sleep(wait)
                continue

            raise last_error

        except (urllib.error.URLError, TimeoutError, socket.timeout, http.client.RemoteDisconnected) as exc:  # type: ignore[name-defined]
            last_error = RuntimeError(f"Gemini image connection/timeout error: {exc}")

            if attempt < retries:
                wait = sleep_sec * attempt
                print(f"[WARN] timeout/network issue; retrying in {wait:.0f}s...")
                time.sleep(wait)
                continue

            raise last_error

        except Exception as exc:
            last_error = exc
            if attempt < retries:
                wait = sleep_sec * attempt
                print(f"[WARN] unexpected issue; retrying in {wait:.0f}s... {exc}")
                time.sleep(wait)
                continue
            raise

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


def load_existing_manifest(week_dir: Path) -> Dict[str, Any]:
    manifest_path = week_dir / "weekly_image_cards_manifest.json"
    if manifest_path.exists():
        try:
            return load_json(manifest_path)
        except Exception:
            pass
    return {"week_dir": str(week_dir), "cards": []}


def upsert_manifest_card(manifest: Dict[str, Any], item: Dict[str, Any]) -> None:
    cards = manifest.setdefault("cards", [])
    for i, old in enumerate(cards):
        if old.get("card_id") == item.get("card_id"):
            cards[i] = item
            return
    cards.append(item)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--limit", type=int, default=0, help="Max number of new cards to generate.")
    parser.add_argument("--card-id", type=str, default="", help="Generate only one card id, e.g. card_03.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing card images.")
    parser.add_argument("--no-fail", action="store_true", help="Do not fail the workflow when image generation fails.")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = os.getenv("GEMINI_IMAGE_MODEL", DEFAULT_IMAGE_MODEL).strip() or DEFAULT_IMAGE_MODEL
    timeout_sec = int(os.getenv("GEMINI_IMAGE_TIMEOUT_SEC", str(DEFAULT_IMAGE_TIMEOUT_SEC)))

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    cards = load_prompt_package(week_dir)

    if args.card_id:
        cards = [c for c in cards if c.get("card_id") == args.card_id]
        if not cards:
            raise ValueError(f"No prompt found for card id: {args.card_id}")

    out_dir = week_dir / "image_cards"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_existing_manifest(week_dir)
    manifest["week_dir"] = str(week_dir)
    manifest["model"] = model

    generated_count = 0
    failures: List[str] = []

    for idx, card in enumerate(cards, start=1):
        card_id = card.get("card_id", f"card_{idx:02d}")
        prompt = card.get("prompt", "").strip()
        if not prompt:
            raise ValueError(f"Empty prompt for {card_id}")

        existing = existing_card_file(out_dir, card_id)
        if existing and not args.overwrite:
            print(f"[SKIP] {card_id} already exists: {existing}")
            upsert_manifest_card(manifest, {
                "card_id": card_id,
                "title": card.get("title", ""),
                "model": model,
                "mime_type": "existing",
                "output_file": str(existing),
                "prompt_file": str((week_dir / "image_prompts" / f"{card_id}.txt")),
                "status": "skipped_existing",
            })
            continue

        if args.limit and generated_count >= args.limit:
            print(f"[INFO] Limit reached: generated {generated_count} new card(s).")
            break

        print(f"[INFO] Generating {card_id} with model {model} ...")
        print(f"[INFO] Timeout: {timeout_sec} seconds")

        try:
            api_response = call_gemini_image(prompt, model, api_key, timeout_sec=timeout_sec)
            image_info = extract_inline_image(api_response)

            mime_type = image_info["mime_type"]
            img_bytes = base64.b64decode(image_info["data_b64"])
            ext = guess_extension(mime_type)

            out_path = out_dir / f"{card_id}{ext}"
            out_path.write_bytes(img_bytes)

            upsert_manifest_card(manifest, {
                "card_id": card_id,
                "title": card.get("title", ""),
                "model": model,
                "mime_type": mime_type,
                "output_file": str(out_path),
                "prompt_file": str((week_dir / "image_prompts" / f"{card_id}.txt")),
                "status": "success",
            })

            generated_count += 1
            print(f"[OK] Created {out_path}")

        except Exception as exc:
            message = f"{card_id}: {exc}"
            failures.append(message)
            print(f"[ERROR] {message}")

            upsert_manifest_card(manifest, {
                "card_id": card_id,
                "title": card.get("title", ""),
                "model": model,
                "mime_type": "",
                "output_file": "",
                "prompt_file": str((week_dir / "image_prompts" / f"{card_id}.txt")),
                "status": "failed",
                "error": str(exc),
            })

            if not args.no_fail:
                break

    manifest_path = week_dir / "weekly_image_cards_manifest.json"
    save_json(manifest_path, manifest)
    print(f"[OK] Updated {manifest_path}")

    if failures and not args.no_fail:
        raise RuntimeError("Image generation failed: " + " | ".join(failures))


if __name__ == "__main__":
    import http.client
    main()
