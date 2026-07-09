#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Step 02
Generate the image prompt for the first block: weekly macro transmission diagram.

Input:
- output/weekly/YYYY-MM-DD/weekly_forest_summary.json
- output/weekly/YYYY-MM-DD/weekly_v35_diagnosis.json
- output/weekly/YYYY-MM-DD/weekly_news_context.json optional

Output:
- output/weekly/YYYY-MM-DD/weekly_macro_diagram_prompt.txt
- output/weekly/YYYY-MM-DD/weekly_macro_diagram_source.json

Skip logic:
- If weekly_macro_diagram.png already exists and FORCE_REBUILD_DIAGRAM is not true,
  skip prompt generation. This avoids regenerating the diagram when only page CSS/HTML changes.

V3.5 update:
- Align weekly visual prompt with the current Daily V35/V36 macro reasoning.
- Use weekly_forest_summary.json as the final narrative layer and weekly_v35_diagnosis.json as the rule-based guardrail.
- Distinguish dominant driver, correction factor, divergence signal, asset validation, and next-week watch.
- Avoid fixed "reflation-only" diagram.
- Explain rising and falling oil prices symmetrically before classifying them as the main line, a correction factor, a parallel signal, or a divergence.
- Preserve USDKRW / KRW as a visible Asia-FX validation asset when supported by the source.
- Avoid stiff front-end wording such as 「交易」「定價」「體制」「風險溢價」.
"""

import argparse
import json
import os
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


def should_force_rebuild() -> bool:
    return os.getenv("FORCE_REBUILD_DIAGRAM", "false").strip().lower() in {"1", "true", "yes", "y"}


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


def build_source_pack(forest: Dict[str, Any], news: Dict[str, Any], v35: Dict[str, Any] | None = None) -> Dict[str, Any]:
    summary = forest.get("forest_summary") or {}
    storyline = forest.get("macro_storyline") or {}
    variables = forest.get("macro_variables") or {}
    evidence = forest.get("evidence") or {}
    video = forest.get("video_planning") or {}
    v35 = v35 or {}

    # Prefer the V35 block embedded in the final Step 01 forest summary so the
    # diagram stays downstream of the final narrative. Fall back to the
    # standalone rule-based file for older forest summaries or missing fields.
    forest_compact_v35 = forest.get("weekly_v35_diagnosis", {})
    if not isinstance(forest_compact_v35, dict):
        forest_compact_v35 = {}

    external_compact_v35 = v35.get("weekly_v35_diagnosis", {}) if isinstance(v35, dict) else {}
    if not isinstance(external_compact_v35, dict):
        external_compact_v35 = {}

    compact_keys = (
        "dominant_driver",
        "correction_factors",
        "divergence_signal",
        "asset_validation",
        "next_period_watch",
    )
    forest_v35_has_content = any(forest_compact_v35.get(key) not in (None, "", []) for key in compact_keys)
    compact_v35 = forest_compact_v35 if forest_v35_has_content else external_compact_v35

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
        "weekly_v35_diagnosis": compact_v35,
        "rule_based_core_contradiction": v35.get("core_contradiction", "") if isinstance(v35, dict) else "",
        "rule_based_primary_macro_story": v35.get("primary_macro_story", "") if isinstance(v35, dict) else "",
        "rule_based_expected_chain": v35.get("expected_chain", []) if isinstance(v35, dict) else [],
        "rule_based_observed_market": v35.get("observed_market", {}) if isinstance(v35, dict) else {},
        "rule_based_asset_validation": compact_v35.get("asset_validation", []) if isinstance(compact_v35, dict) else [],
    }


def build_prompt(source: Dict[str, Any]) -> str:
    return f"""Create a 16:9 NotebookLM-style whiteboard explainer image for a weekly macro summary webpage.

Purpose:
This image is the FIRST block of a weekly macro summary webpage.
It visually summarizes the period macro conclusions from later sections:
Executive Summary, market signals, correction factors, divergence signals, news evidence, and next-week watch.
It is a weekly macro transmission diagram, not a dense report.

V3.5 macro reasoning rules:
- This is a periodic macro summary based on the formal analysis window.
- Do not assume the analysis window is always exactly 7 days.
- Use the week range / analysis window from the source content as the official period.
- Do not over-focus on only the last trading day.
- Use weekly_forest_summary.json as the final narrative layer. Its main theme, verdict, storyline, and revision/correction description should remain mutually consistent.
- Use weekly_v35_diagnosis as the primary structured guardrail when available:
  dominant_driver, correction_factors, divergence_signal, asset_validation, next_period_watch.
- weekly_v35_diagnosis is produced by the rule-based V35 diagnosis layer; do not contradict its oil / inflation direction rules or asset directions.
- Do not create a second, unrelated macro main line for the image. If wording differs between the final forest summary and V35 diagnosis, preserve the same economic direction and present the difference as a correction factor, divergence, or uncertainty.
- First identify the period dominant driver.
- Then show correction factors that challenged or softened the main driver.
- Then show asset validation: whether US10Y, DXY, WTI / Brent, Gold, USDJPY, USDTWD, and USDKRW support or contradict the story.
- Then show the key divergence: where news and asset prices did not move in the same direction.
- Finally show 2–3 next-week watch questions.
- Distinguish inflation hard data from inflation expectations.
- Indicator names are not directions. CPI, PPI, nonfarm payrolls, initial claims, unemployment, and oil inventories require explicit direction or surprise wording before they can be called hot, cooling, strong, or weak.
- Preserve the source direction. Never rewrite below-expectation, slowing, or weakening data as strong merely to fit asset prices; show it as a divergence, correction factor, or item to watch.
- If labor signals are mixed, use 就業訊號分歧 / Fed 路徑待確認. Do not turn weak payrolls plus a falling unemployment rate into 非農強勁. Labor resilience alone does not raise inflation expectations unless wage pressure or demand strength is also present.
- Determine oil direction from rule_based_observed_market.WTI / Brent and V35 asset validation first. EIA, OPEC, war, ceasefire, sanctions, inventories, and geopolitics explain the cause; they do not replace the observed oil-price direction.
- Rising oil prices increase energy costs and upward pressure on near-term inflation expectations: 油價上行，增加能源成本與短期通膨預期的上行壓力. If rising oil is not the dominant driver, show it as a correction factor or parallel signal rather than forcing it into the main line.
- Falling oil prices are inflation downside factors: 油價下行，可能緩和能源通膨壓力；若由需求疲弱造成，也可能是成長降溫訊號.
- Never imply that falling oil prices raise inflation expectations.
- If yields rise while oil falls, explain it as Fed path, high-rate expectations, Treasury supply, refinancing, or term-premium pressure outweighing the oil correction factor.
- Explain oil's own economic meaning first, then classify it as the dominant driver, a correction factor, a parallel signal, or a divergence. Do not hard-link oil moves to fiscal deficits or a high-rate main line.
- Risk-off or market psychology is not an inflation direction by itself.
- Do not write that the market "ignored" inflation. Explain which factor dominated and which factor became a correction factor.

Important title rule:
- Do NOT render a large headline inside the image.
- The webpage already has the page title「本週總經摘要」and section title「總經傳導圖解」.
- The image should start directly with diagram nodes, icons, arrows, and short labels.

Style:
- off-white / white background
- subtle light gray grid-paper texture
- bold black hand-drawn line art
- orange / warm amber accent arrows, circles, tags, pins, labels
- clean macro-finance explainer diagram
- airy, readable composition
- looks like a knowledge video card, not a corporate slide
- use icons, causal arrows, simple doodles, flow paths, question marks, magnifying glass, warning tags

Visual structure rules:
- Top-left: 本週主導因子, using short labels from the source content.
- Main chain: 本週主導因子 → 利率 / 美元 → 亞幣 / 黃金 / 風險資產.
- Lower secondary branch: 修正因子 → 油價 / 就業 / 成長 / 地緣 / 避險, depending on source content.
- Center box: 背離訊號, showing the period’s most important contradiction.
- Right-side area: 下週觀察, only 2–3 short questions.
- Bottom evidence strip if space allows: 本週證據.
- Main chain must be visually dominant.
- Correction factors are secondary and must not visually compete with the main chain.
- Do not force a fixed reflation story if the source content says otherwise.

Visible text rules:
- Use Traditional Chinese only.
- Do NOT include a large main headline inside the image.
- Use only short labels, nodes, tags, and very short questions.
- Keep visible text minimal, large, and readable.
- No long paragraphs.
- No dense report layout.
- No tables.
- Do not invent numbers or directions.
- Use the source content only as background understanding.
- Do not render long explanations as visible paragraph text.

Preferred visible wording:
- Use: 主導因子, 修正因子, 背離訊號, 市場重新評估, 市場更關注, 利率走向, 美元偏強, 亞幣承壓, 油價下行, 通膨下修因子, 下週觀察.
- Avoid visible labels using: 交易, 定價, 體制, 風險溢價, 傳導源, 通膨修正因子失效.
- If labor market weakness is mentioned, write: 勞動降溫風險 / 初領失業金上升 / 就業降溫訊號.
- Do not write: 市場交易就業降溫風險.

Source content:
- Week range: {source.get("week_range")}
- Weekly main theme: {source.get("main_theme")}
- One-sentence verdict: {source.get("one_sentence_verdict")}
- Main question: {source.get("main_question")}
- Narrative arc: {source.get("narrative_arc")}
- Story start: {source.get("story_start")}
- Main drivers: {json.dumps(source.get("main_drivers", []), ensure_ascii=False)}
- Market transmission: {source.get("market_transmission")}
- Correction factor: {source.get("revision_or_noise")}
- Story end: {source.get("story_end")}
- Macro variables: {json.dumps(source.get("macro_variables", {}), ensure_ascii=False)}
- Evidence: {json.dumps(source.get("evidence", []), ensure_ascii=False)}
- News theme: {source.get("news_theme")}
- News confirming signals: {json.dumps(source.get("news_confirming_signals", []), ensure_ascii=False)}
- News corrections: {json.dumps(source.get("news_corrections", []), ensure_ascii=False)}
- Next week questions: {json.dumps(source.get("next_week_questions", []), ensure_ascii=False)}
- Weekly V35 diagnosis: {json.dumps(source.get("weekly_v35_diagnosis", {}), ensure_ascii=False)}
- Rule-based core contradiction: {source.get("rule_based_core_contradiction")}
- Rule-based primary macro story: {source.get("rule_based_primary_macro_story")}
- Rule-based expected chain: {json.dumps(source.get("rule_based_expected_chain", []), ensure_ascii=False)}
- Rule-based observed market: {json.dumps(source.get("rule_based_observed_market", {}), ensure_ascii=False)}
- Rule-based asset validation: {json.dumps(source.get("rule_based_asset_validation", []), ensure_ascii=False)}

Suggested visible label pool:
Use these only if supported by the source content. Do not force all labels.
- 本週主導因子
- Fed 路徑
- 高利率更久
- 通膨黏性
- 通膨下修因子
- 油價下行
- 油價上行
- 長債利率
- 美元偏強
- 亞幣承壓
- 黃金壓力
- 避險需求
- 勞動降溫風險
- 就業訊號分歧
- Fed 路徑待確認
- 能源通膨上行壓力
- 成長擔憂
- 修正因子
- 背離訊號
- 本週證據
- 下週觀察

Avoid:
- large title text inside the image
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
- rewriting weak or below-expectation data as strong
- 「油價上行，但通膨預期受財政赤字與高利率主線主導」
- 「油價上行，因為財政赤字導致高利率」
- 「油價變動由財政赤字主導」
- fixed reflation-only chain when source content does not support it
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    image_path = week_dir / "weekly_macro_diagram.png"

    if image_path.exists() and not should_force_rebuild():
        print(f"[SKIP] weekly macro diagram already exists: {image_path}")
        print("[SKIP] Set FORCE_REBUILD_DIAGRAM=true to regenerate prompt and image.")
        return

    forest = load_json(week_dir / "weekly_forest_summary.json", {})
    news = load_json(week_dir / "weekly_news_context.json", {})
    v35 = load_json(week_dir / "weekly_v35_diagnosis.json", {}) or {}

    if not forest:
        raise FileNotFoundError(f"Missing weekly_forest_summary.json in {week_dir}")

    source = build_source_pack(forest, news, v35)
    prompt = build_prompt(source)

    save_json(week_dir / "weekly_macro_diagram_source.json", source)
    save_text(week_dir / "weekly_macro_diagram_prompt.txt", prompt)

    print(f"[OK] Created {week_dir / 'weekly_macro_diagram_prompt.txt'}")
    print(f"[OK] Created {week_dir / 'weekly_macro_diagram_source.json'}")


if __name__ == "__main__":
    main()
