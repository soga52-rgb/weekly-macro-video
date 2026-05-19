#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V2 - Step 02
Generate AI-driven weekly_video_scene_ai.json from weekly_facts.json.

Purpose:
- Use weekly_facts.json as a NotebookLM-like source package.
- Use prompts/weekly_story_prompt_v1.txt as the fixed prompt template.
- Call Gemini API and request a structured JSON response.
- Save AI output without overwriting the existing MVP weekly_video_scene.json.

Input:
- output/weekly/YYYY-MM-DD/weekly_facts.json
- prompts/weekly_story_prompt_v1.txt

Output:
- output/weekly/YYYY-MM-DD/weekly_video_scene_ai.json

Required GitHub Secret:
- GEMINI_API_KEY

Optional environment variable:
- GEMINI_MODEL
  Default: gemini-2.5-flash
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
PROMPT_PATH = ROOT_DIR / "prompts" / "weekly_story_prompt_v1.txt"

DEFAULT_MODEL = "gemini-2.5-flash"


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def extract_prompt_sections(prompt_template: str) -> tuple[str, str]:
    """
    The prompt file stores SYSTEM_PROMPT and USER_PROMPT_TEMPLATE as readable text.
    This function extracts the triple-quoted content.
    """
    system_match = re.search(r'SYSTEM_PROMPT\s*=\s*"""(.*?)"""', prompt_template, re.DOTALL)
    user_match = re.search(r'USER_PROMPT_TEMPLATE\s*=\s*"""(.*?)"""', prompt_template, re.DOTALL)

    if not system_match or not user_match:
        raise ValueError("Prompt template must include SYSTEM_PROMPT and USER_PROMPT_TEMPLATE triple-quoted blocks.")

    return system_match.group(1).strip(), user_match.group(1).strip()


def extract_json_from_text(text: str) -> Dict[str, Any]:
    """
    Gemini should return JSON only, but this function is defensive:
    - removes markdown fences if present
    - extracts the outermost JSON object
    """
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1 or end <= start:
        raise ValueError("AI response does not contain a valid JSON object.")

    json_text = cleaned[start : end + 1]
    return json.loads(json_text)


def call_gemini(system_prompt: str, user_prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"

    payload = {
        "systemInstruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_prompt}]
            }
        ],
        "generationConfig": {
            "temperature": 0.25,
            "topP": 0.9,
            "responseMimeType": "application/json"
        }
    }

    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini API URLError: {exc}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini API response: {api_response}") from exc

    return extract_json_from_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="", help="Optional weekly output folder, e.g. output/weekly/2026-05-21")
    parser.add_argument("--output-name", type=str, default="weekly_video_scene_ai.json")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY. Add it as a GitHub Actions secret.")

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    facts_path = week_dir / "weekly_facts.json"

    weekly_facts = load_json(facts_path)
    prompt_template = load_text(PROMPT_PATH)
    system_prompt, user_prompt_template = extract_prompt_sections(prompt_template)

    weekly_facts_json = json.dumps(weekly_facts, ensure_ascii=False, indent=2)
    user_prompt = user_prompt_template.replace("{weekly_facts_json}", weekly_facts_json)

    print(f"[INFO] Using Gemini model: {model}")
    print(f"[INFO] Reading facts: {facts_path}")

    ai_scene = call_gemini(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        model=model,
        api_key=api_key,
    )

    output_path = week_dir / args.output_name
    save_json(output_path, ai_scene)

    print(f"[OK] AI weekly video scene JSON created: {output_path}")


if __name__ == "__main__":
    main()
