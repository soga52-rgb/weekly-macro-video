#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Step 02
Generate the image prompt for the first block: weekly macro transmission diagram.

Input:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json
- output/weekly/YYYY-MM-DD/weekly_news_context.json optional

Output:
- output/weekly/YYYY-MM-DD/weekly_macro_diagram_prompt.txt
- output/weekly/YYYY-MM-DD/weekly_macro_diagram_source.json

Purpose:
- The first section of the weekly macro page is an image-based macro transmission diagram.
- The diagram is not generated first. It summarizes sections 2~7:
  Executive Summary, market signals, revision factors, news evidence, and next-week watch.
- The image itself is generated later by gemini-3.1-flash-image-preview.
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
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


def as_list(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def shorten_list(values: Any, limit: int = 4) -> List[str]:
    out = []
    for item in as_list(values):
        if isinstance(item, dict):
            line = item.get("driver") or item.get("title") or item.get("theme") or item.get("main_point") or item.get("why_it_matters") or ""
            impact = item.get("impact") or item.get("summary") or ""
            combined = "｜".join([x for x in [text(line), text(impact)] if x])
            if combined:
                out.append(combined)
        else:
            if text(item):
                out.append(text(item))
    return out[:limit]


def build_source_pack(forest: Dict[str, Any], news: Dict[str, Any]) -> Dict[str, Any]:
    summary = forest.get("forest_summary") or {}
    storyline = forest.get("macro_storyline") or {}
    variables = forest.get("macro_variables") or {}
    evidence = forest.get("evidence") or {}
    video = forest.get("video_planning") or {}

    return {
        "week_range": (forest.get("meta") or {}).get("week_range", ""),
        "main_theme": summary.get("weekly_main_theme", ""),
        "one_sentence_verdict": summary.get("one_sentence_verdict", ""),
        "main_question": summary.get("main_question", ""),
        "narrative_arc": summary.get("narrative_arc", ""),
        "story_start": storyline.get("story_start", ""),
        "main_drivers": shorten_list(storyline.get("main_drivers"), 5),
        "market_transmission": storyline.get("market_transmission", ""),
        "revision_or_noise": storyline.get("revision_or_noise", ""),
        "story_end": storyline.get("story_end", ""),
        "macro_variables": {
            "inflation": variables.get("inflation_view", ""),
            "rate": variables.get("rate_view", ""),
            "dollar_fx": variables.get("dollar_fx_view", ""),
            "asia_fx": variables.get("asia_fx_view", ""),
            "gold": variables.get("gold_view", ""),
            "energy": variables.get("energy_view", ""),
        },
        "evidence": shorten_list(evidence.get("most_important_evidence"), 5),
        "next_week_questions": shorten_list(video.get("next_week_questions"), 4),
        "news_theme": news.get("weekly_news_theme", ""),
        "news_confirming_signals": shorten_list(news.get("confirming_signals"), 5),
        "news_corrections": shorten_list(news.get("news_based_corrections"), 3),
        "top_news": shorten_list(news.get("top_news"), 4),
    }


def build_prompt(source: Dict[str, Any]) -> str:
    # Use source information only as background; visible text must be short.
    return f"""Create a 16:9 NotebookLM-style whiteboard explainer image for a weekly macro summary webpage.

Purpose:
This image is the FIRST block of a weekly macro summary webpage.
It should visually summarize the conclusions from the later webpage sections:
Executive Summary, market signals, revision factors, news evidence, and next-week watch.
It is a visual macro transmission diagram, not a dense report.

Style:
- off-white or white background
- subtle light gray grid texture
- bold black hand-drawn line art
- orange accent arrows, circles, tags, pins
- clean macro-finance explainer diagram
- airy, video-friendly composition
- looks like a knowledge video card, not a corporate slide
- use icons, causal arrows, simple doodles, flow paths, question marks, magnifying glass, warning tags

Visible text rules:
- Use Traditional Chinese only.
- Use one short main headline.
- Use only short labels, nodes, tags, and very short questions.
- Keep visible text minimal, large, and readable.
- No long paragraphs.
- No dense report layout.
- No tables.
- Do not invent numbers or directions.
- Use the source content only as background understanding.
- Do not render long explanations as visible paragraph text.

Main concept:
Create a weekly macro transmission diagram:
drivers → inflation/rates → dollar → Asia FX / gold → revision factors → next week watch

Source content:
- Week range: {source.get("week_range")}
- Weekly main theme: {source.get("main_theme")}
- One-sentence verdict: {source.get("one_sentence_verdict")}
- Main question: {source.get("main_question")}
- Narrative arc: {source.get("narrative_arc")}
- Story start: {source.get("story_start")}
- Main drivers: {json.dumps(source.get("main_drivers", []), ensure_ascii=False)}
- Market transmission: {source.get("market_transmission")}
- Revision factor: {source.get("revision_or_noise")}
- Story end: {source.get("story_end")}
- Macro variables: {json.dumps(source.get("macro_variables", {{}}), ensure_ascii=False)}
- Evidence: {json.dumps(source.get("evidence", []), ensure_ascii=False)}
- News theme: {source.get("news_theme")}
- News confirming signals: {json.dumps(source.get("news_confirming_signals", []), ensure_ascii=False)}
- News corrections: {json.dumps(source.get("news_corrections", []), ensure_ascii=False)}
- Next week questions: {json.dumps(source.get("next_week_questions", []), ensure_ascii=False)}

Suggested visible structure:
- headline: 本週總經傳導圖解
- short nodes such as: 再通膨、長債利率、美元偏強、亞幣承壓、黃金壓力、修正因子、下週驗證
- one orange marker on the key correction or uncertainty point
- do not include full source text

Avoid:
- dense slide layout
- table
- long paragraphs
- small unreadable text
- cluttered UI
- stock dashboard style
- Bloomberg terminal style
- exact NotebookLM logo
- Google branding
- fake extra data
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()

    forest = load_json(week_dir / "weekly_forest_summary.json", {})
    news = load_json(week_dir / "weekly_news_context.json", {})

    if not forest:
        raise FileNotFoundError(f"Missing weekly_forest_summary.json in {week_dir}")

    source = build_source_pack(forest, news)
    prompt = build_prompt(source)

    save_json(week_dir / "weekly_macro_diagram_source.json", source)
    save_text(week_dir / "weekly_macro_diagram_prompt.txt", prompt)

    print(f"[OK] Created {week_dir / 'weekly_macro_diagram_prompt.txt'}")
    print(f"[OK] Created {week_dir / 'weekly_macro_diagram_source.json'}")


if __name__ == "__main__":
    main()
