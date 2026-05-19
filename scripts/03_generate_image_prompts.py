#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 03
Generate image prompts from weekly_video_brief.json.

Input:
- output/weekly/YYYY-MM-DD/weekly_video_brief.json
- prompts/weekly_image_card_prompt_template_v2.txt

Output:
- output/weekly/YYYY-MM-DD/image_prompts/card_01.txt ~ card_06.txt
- output/weekly/YYYY-MM-DD/weekly_image_prompts.json
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
TEMPLATE_PATH = ROOT_DIR / "prompts" / "weekly_image_card_prompt_template_v2.txt"


def load_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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


def extract_block(template: str, name: str) -> str:
    pattern = rf'{name}\s*=\s*"""(.*?)"""'
    match = re.search(pattern, template, re.DOTALL)
    if not match:
        raise ValueError(f"Template block not found: {name}")
    return match.group(1).strip()


def compact_signals(signals: List[Dict[str, Any]]) -> str:
    lines = []
    for item in signals[:3]:
        icon = item.get("icon", "")
        label = item.get("label", "")
        meaning = item.get("meaning", "")
        lines.append(f"- {icon} {label}｜{meaning}")
    return "\n".join(lines)


def compact_steps(steps: List[str]) -> str:
    lines = []
    for idx, step in enumerate(steps[:5], start=1):
        clean = str(step).strip()
        clean = re.sub(r"^\d+\.\s*", "", clean)
        lines.append(f"{idx}. {clean}")
    return "\n".join(lines)


def compact_watchpoints(points: List[str]) -> str:
    lines = []
    for item in points[:3]:
        lines.append(f"- {item}")
    return "\n".join(lines)


def build_prompt(base: str, rules: str, card_block: str, negative: str, replacements: Dict[str, str]) -> str:
    text = "\n\n".join([base, rules, card_block, negative])
    for key, value in replacements.items():
        text = text.replace("{" + key + "}", value or "")
    return text.strip()


def build_card_prompts(brief: Dict[str, Any], template: str) -> List[Dict[str, str]]:
    base = extract_block(template, "STYLE_BASE")
    rules = extract_block(template, "TEXT_RULES")
    negative = extract_block(template, "NEGATIVE_PROMPT")

    executive = brief.get("executive_summary", {})
    signals = brief.get("market_signals", [])
    chain = brief.get("macro_chain", {})
    evidence = brief.get("news_evidence", {})
    steps = brief.get("transmission_steps", [])
    key_question = brief.get("key_question", "")
    next_week = brief.get("next_week_watch", {})

    cards = [
        {
            "card_id": "card_01",
            "title": "Executive Summary",
            "block": "CARD_01_EXECUTIVE_SUMMARY",
            "replacements": {
                "headline": executive.get("headline", ""),
                "summary": executive.get("summary", ""),
                "key_question": key_question,
            },
        },
        {
            "card_id": "card_02",
            "title": "Market Signals",
            "block": "CARD_02_MARKET_SIGNALS",
            "replacements": {
                "market_signals": compact_signals(signals),
            },
        },
        {
            "card_id": "card_03",
            "title": "Macro Chain",
            "block": "CARD_03_MACRO_CHAIN",
            "replacements": {
                "macro_chain_title": chain.get("title", ""),
                "macro_chain_explanation": chain.get("explanation", ""),
            },
        },
        {
            "card_id": "card_04",
            "title": "News Evidence",
            "block": "CARD_04_NEWS_EVIDENCE",
            "replacements": {
                "news_title": evidence.get("title", ""),
                "news_summary": evidence.get("summary", ""),
            },
        },
        {
            "card_id": "card_05",
            "title": "Five-step Transmission",
            "block": "CARD_05_TRANSMISSION_STEPS",
            "replacements": {
                "transmission_steps": compact_steps(steps),
            },
        },
        {
            "card_id": "card_06",
            "title": "Next Week Watch",
            "block": "CARD_06_NEXT_WEEK_WATCH",
            "replacements": {
                "key_question": key_question,
                "next_week_headline": next_week.get("headline", ""),
                "watchpoints": compact_watchpoints(next_week.get("watchpoints", [])),
            },
        },
    ]

    output = []
    for card in cards:
        card_block = extract_block(template, card["block"])
        prompt = build_prompt(
            base=base,
            rules=rules,
            card_block=card_block,
            negative=negative,
            replacements=card["replacements"],
        )
        output.append({
            "card_id": card["card_id"],
            "title": card["title"],
            "prompt": prompt,
        })

    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--brief-file", type=str, default="weekly_video_brief.json")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    brief_path = week_dir / args.brief_file

    brief = load_json(brief_path)
    template = load_text(TEMPLATE_PATH)

    prompts = build_card_prompts(brief, template)

    prompt_dir = week_dir / "image_prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)

    for item in prompts:
        path = prompt_dir / f"{item['card_id']}.txt"
        save_text(path, item["prompt"])
        print(f"[OK] Created {path}")

    package = {
        "source_brief": str(brief_path),
        "template": str(TEMPLATE_PATH),
        "cards": prompts,
    }
    save_json(week_dir / "weekly_image_prompts.json", package)

    print(f"[OK] Created {week_dir / 'weekly_image_prompts.json'}")


if __name__ == "__main__":
    main()
