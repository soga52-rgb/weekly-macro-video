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
- Derive the visible FX labels from the observed weekly directions instead of a fixed strong-dollar template.
- Treat DXY, Asia FX, and Gold as parallel validation branches when their directions diverge.
- Exclude raw news directional wording from the image prompt when it can overwrite the formal-window result.
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



def build_visual_guardrails(
    v35: Dict[str, Any],
    compact_v35: Dict[str, Any],
    next_week_questions: List[str],
) -> Dict[str, Any]:
    """Build deterministic current-period labels for the image prompt.

    DXY is a broad dollar basket, while USDJPY / USDTWD / USDKRW are bilateral
    exchange rates. They may move in different directions during the same week.
    Therefore, Asia FX is classified from all three bilateral rates and is not
    automatically treated as a downstream consequence of DXY.
    """

    observed = v35.get("observed_market", {}) if isinstance(v35, dict) else {}
    if not isinstance(observed, dict):
        observed = {}

    def direction(asset: str) -> str:
        item = observed.get(asset, {})
        if not isinstance(item, dict):
            return ""
        value = str(item.get("direction") or "").strip().lower()
        return value if value in {"up", "down", "flat"} else ""

    rate_direction = direction("US10Y")
    dxy_direction = direction("DXY")
    gold_direction = direction("Gold")
    wti_direction = direction("WTI")
    brent_direction = direction("Brent")

    rate_label = {
        "up": "美債殖利率上行",
        "down": "美債殖利率下行",
        "flat": "美債殖利率平盤",
    }.get(rate_direction, "美債殖利率方向不足")

    dxy_label = {
        "up": "美元指數偏強",
        "down": "美元指數偏弱",
        "flat": "美元指數變化有限",
    }.get(dxy_direction, "美元指數方向不足")

    asia_specs = (
        ("USDJPY", "日圓"),
        ("USDTWD", "台幣"),
        ("USDKRW", "韓元"),
    )
    asia_directions: Dict[str, str] = {}
    asia_detail_labels: List[str] = []

    for asset, currency in asia_specs:
        asset_direction = direction(asset)
        if not asset_direction:
            continue
        asia_directions[asset] = asset_direction
        if asset_direction == "up":
            asia_detail_labels.append(f"{currency}承壓（{asset}↑）")
        elif asset_direction == "down":
            asia_detail_labels.append(f"{currency}相對走強（{asset}↓）")
        else:
            asia_detail_labels.append(f"{currency}變化有限（{asset}持平）")

    known_asia = [value for value in asia_directions.values() if value in {"up", "down", "flat"}]
    directional_asia = [value for value in known_asia if value in {"up", "down"}]

    if len(known_asia) == 3 and all(value == "up" for value in known_asia):
        asia_state = "亞洲貨幣普遍承壓"
        asia_is_mixed = False
    elif len(known_asia) == 3 and all(value == "down" for value in known_asia):
        asia_state = "亞洲貨幣普遍走強"
        asia_is_mixed = False
    elif len(set(directional_asia)) >= 2:
        asia_state = "亞洲貨幣走勢分歧"
        asia_is_mixed = True
    elif directional_asia:
        asia_state = "亞洲貨幣方向未完全一致"
        asia_is_mixed = True
    else:
        asia_state = "亞洲貨幣方向不足"
        asia_is_mixed = False

    oil_up = wti_direction == "up" or brent_direction == "up"
    oil_down = wti_direction == "down" or brent_direction == "down"
    if oil_up and not oil_down:
        oil_label = "油價上行"
    elif oil_down and not oil_up:
        oil_label = "油價下行"
    elif oil_up and oil_down:
        oil_label = "油價走勢分歧"
    else:
        oil_label = "油價方向不足"

    gold_is_divergence = (
        gold_direction == "down"
        and rate_direction != "up"
        and dxy_direction != "up"
    )
    if gold_is_divergence:
        gold_label = "黃金下行，但未獲利率或美元驗證"
    else:
        gold_label = {
            "up": "黃金上行",
            "down": "黃金下行",
            "flat": "黃金變化有限",
        }.get(gold_direction, "黃金方向不足")

    next_watch_text = "｜".join(text(item) for item in next_week_questions)
    high_rate_watch_only = (
        rate_direction != "up"
        and ("高利率" in next_watch_text or "higher for longer" in next_watch_text.lower())
    )

    allowed_labels = [
        "本週主導因子",
        "修正因子",
        "背離訊號",
        "本週證據",
        "下週觀察",
        rate_label,
        dxy_label,
        asia_state,
        oil_label,
        gold_label,
    ]
    allowed_labels.extend(asia_detail_labels)

    forbidden_labels: List[str] = []
    if rate_direction == "flat":
        forbidden_labels.extend([
            "殖利率上行",
            "殖利率下行",
            "高利率更久（作為本週已確認結果）",
        ])
    if dxy_direction == "down":
        forbidden_labels.append("美元偏強")
    elif dxy_direction == "up":
        forbidden_labels.append("美元偏弱")
    if asia_is_mixed:
        forbidden_labels.extend([
            "亞幣承壓（作為亞洲貨幣整體結論）",
            "亞幣走強（作為亞洲貨幣整體結論）",
        ])
    if oil_up and not oil_down:
        forbidden_labels.append("油價下行")
    elif oil_down and not oil_up:
        forbidden_labels.append("油價上行")
    if gold_is_divergence:
        forbidden_labels.extend([
            "黃金下跌＝強美元壓力",
            "黃金下跌＝殖利率上行",
        ])

    return {
        "rate_direction": rate_direction or "unknown",
        "rate_label": rate_label,
        "dxy_direction": dxy_direction or "unknown",
        "dxy_label": dxy_label,
        "asia_state": asia_state,
        "asia_is_mixed": asia_is_mixed,
        "asia_detail_labels": asia_detail_labels,
        "gold_direction": gold_direction or "unknown",
        "gold_label": gold_label,
        "gold_is_divergence": gold_is_divergence,
        "oil_label": oil_label,
        "high_rate_watch_only": high_rate_watch_only,
        "allowed_current_labels": allowed_labels,
        "forbidden_current_labels": forbidden_labels,
        "dxy_asia_structure": (
            "DXY 與亞洲貨幣必須並列呈現，不得畫成單向因果鏈。"
            if asia_is_mixed
            else "DXY 與亞洲貨幣可作為相互驗證節點，但仍不得省略各自實際方向。"
        ),
        "news_directional_fields_excluded_from_prompt": True,
    }


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
    next_week_questions = shorten_list(video.get("next_week_questions"), 4)
    visual_guardrails = build_visual_guardrails(v35, compact_v35, next_week_questions)

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
        "next_week_questions": next_week_questions,
        "news_theme": news.get("weekly_news_theme", ""),
        # Keep raw news direction fields in the audit source only. They are not
        # inserted into the image prompt because event-window wording can conflict
        # with the formal-window weekly result.
        "news_confirming_signals_audit_only": shorten_list(news.get("confirming_signals"), 5),
        "news_corrections_audit_only": shorten_list(news.get("news_based_corrections"), 3),
        "top_news_audit_only": shorten_list(news.get("top_news"), 4),
        "visual_guardrails": visual_guardrails,
        "weekly_v35_diagnosis": compact_v35,
        "rule_based_core_contradiction": v35.get("core_contradiction", "") if isinstance(v35, dict) else "",
        "rule_based_primary_macro_story": v35.get("primary_macro_story", "") if isinstance(v35, dict) else "",
        "rule_based_expected_chain": v35.get("expected_chain", []) if isinstance(v35, dict) else [],
        "rule_based_observed_market": v35.get("observed_market", {}) if isinstance(v35, dict) else {},
        "rule_based_asset_validation": compact_v35.get("asset_validation", []) if isinstance(compact_v35, dict) else [],
    }


def build_prompt(source: Dict[str, Any]) -> str:
    guardrails = source.get("visual_guardrails", {})
    if not isinstance(guardrails, dict):
        guardrails = {}

    allowed_labels = guardrails.get("allowed_current_labels", [])
    forbidden_labels = guardrails.get("forbidden_current_labels", [])
    asia_details = guardrails.get("asia_detail_labels", [])

    return f"""Create a 16:9 NotebookLM-style whiteboard explainer image for a weekly macro summary webpage.

Purpose:
This image is the FIRST block of a weekly macro summary webpage.
It visually summarizes the period macro conclusions from later sections:
Executive Summary, market signals, correction factors, divergence signals, evidence, and next-week watch.
It is a weekly macro transmission diagram, not a dense report.

V3.5 macro reasoning rules:
- This is a periodic macro summary based on the formal analysis window.
- Do not assume the analysis window is always exactly 7 days.
- Use the week range / analysis window from the source content as the official period.
- Do not over-focus on only the last trading day.
- Use weekly_forest_summary.json as the final narrative layer.
- Use weekly_v35_diagnosis and rule_based_observed_market as the authoritative direction guardrails.
- Current-period observed market directions override generic macro templates and event-window news wording.
- Do not create a second, unrelated macro main line for the image.
- First identify the period dominant driver.
- Then show the forces pushing rates up and down.
- Then show the observed US10Y result.
- Treat DXY, Asia FX, and Gold as parallel asset-validation branches when their directions diverge.
- Then show the key divergence and 2–3 next-week watch questions.
- Distinguish inflation hard data from inflation expectations.
- Indicator names are not directions. CPI, PPI, nonfarm payrolls, initial claims, unemployment, and oil inventories require explicit direction or surprise wording.
- Preserve the source direction. Never rewrite slowing or weakening data as strong merely to fit asset prices.
- Determine oil direction from rule_based_observed_market.WTI / Brent and V35 asset validation first.
- Rising oil prices increase near-term energy-inflation pressure.
- Falling oil prices may ease energy-inflation pressure.
- Risk-off or market psychology is not an inflation direction by itself.
- Do not write that the market ignored inflation. Explain which forces offset each other.
- Raw news confirming / correction fields are intentionally excluded from this image prompt. The final forest summary and V35 formal-window result already incorporate the relevant facts.

Strict cross-asset consistency rules:
- DXY is a broad dollar index. USDJPY, USDTWD, and USDKRW are bilateral exchange rates. Their directions do not have to be identical.
- Only use the aggregate label「亞洲貨幣普遍承壓」when USDJPY, USDTWD, and USDKRW all rise.
- Only use the aggregate label「亞洲貨幣普遍走強」when USDJPY, USDTWD, and USDKRW all fall.
- When the three Asia-FX rates do not move in the same direction, use「亞洲貨幣走勢分歧」and show the individual JPY / TWD / KRW directions.
- When Asia FX is mixed, do not draw a single causal arrow from DXY to an aggregate Asia-FX conclusion.
- If Gold falls without US10Y rising or DXY strengthening, show「黃金背離／原因待確認」rather than a strong-dollar or high-rate causal explanation.
- If US10Y is flat, show opposing forces offsetting each other. Do not turn it into a confirmed higher-for-longer result.
- If「高利率維持更久」appears only in next-period watch, keep it inside the 下週觀察 box.

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
- Top-left: 本週主導因子.
- Main chain: 主導因子中的上行與下行力量 → US10Y 實際方向.
- From the US10Y result, branch into parallel validation areas:
  1) DXY actual direction
  2) Asia FX aggregate state plus JPY / TWD / KRW details
  3) Gold actual direction and divergence status
- Lower secondary branch: 修正因子.
- Center box: 背離訊號.
- Right-side area: 下週觀察, only 2–3 short questions.
- Bottom evidence strip if space allows: 本週證據.
- Main chain must be visually dominant.
- Correction factors are secondary and must not visually compete with the main chain.
- Do not force a fixed reflation, strong-dollar, or Asia-currency-pressure story.

Current-period deterministic visual guardrails:
- Rate result: {guardrails.get("rate_label", "")}
- DXY result: {guardrails.get("dxy_label", "")}
- Asia-FX result: {guardrails.get("asia_state", "")}
- Asia-FX details: {json.dumps(asia_details, ensure_ascii=False)}
- Gold result: {guardrails.get("gold_label", "")}
- Oil result: {guardrails.get("oil_label", "")}
- DXY / Asia structure: {guardrails.get("dxy_asia_structure", "")}
- Higher-for-longer watch-only: {guardrails.get("high_rate_watch_only", False)}
- Allowed current-period labels: {json.dumps(allowed_labels, ensure_ascii=False)}
- Forbidden or contradictory labels: {json.dumps(forbidden_labels, ensure_ascii=False)}

Visible text rules:
- Use Traditional Chinese only.
- Do NOT include a large main headline inside the image.
- Use only short labels, nodes, tags, and very short questions.
- Keep visible text minimal, large, and readable.
- No long paragraphs.
- No dense report layout.
- No tables.
- Do not invent numbers or directions.
- Do not choose a familiar label from a generic macro template when it conflicts with the deterministic guardrails.

Preferred structural wording:
- 主導因子
- 修正因子
- 背離訊號
- 市場重新評估
- 利率走向
- 本週證據
- 下週觀察
- For market-direction labels, use only the deterministic current-period labels listed above.

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
- News theme, background only: {source.get("news_theme")}
- Next week questions: {json.dumps(source.get("next_week_questions", []), ensure_ascii=False)}
- Weekly V35 diagnosis: {json.dumps(source.get("weekly_v35_diagnosis", {}), ensure_ascii=False)}
- Rule-based core contradiction: {source.get("rule_based_core_contradiction")}
- Rule-based primary macro story: {source.get("rule_based_primary_macro_story")}
- Rule-based expected chain: {json.dumps(source.get("rule_based_expected_chain", []), ensure_ascii=False)}
- Rule-based observed market: {json.dumps(source.get("rule_based_observed_market", {}), ensure_ascii=False)}
- Rule-based asset validation: {json.dumps(source.get("rule_based_asset_validation", []), ensure_ascii=False)}

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
- using「美元偏強」when DXY is down
- using「美元偏弱」when DXY is up
- using「亞幣承壓」as an aggregate conclusion when Asia FX is mixed
- omitting USDKRW when it is the opposing Asia-FX direction
- drawing DXY → 亞幣承壓 as a causal chain when the bilateral rates are mixed
- explaining Gold weakness with strong dollar or rising yields when neither is observed
- showing「高利率更久」as a current-period result when US10Y is flat
- fixed reflation-only or strong-dollar-only chains when source content does not support them
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
