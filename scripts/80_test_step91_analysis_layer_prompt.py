#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 80 Test - Step 91 Analysis Layer Prompt

Purpose:
- Test the redesigned Step 91 analysis-layer prompt only.
- Read:
  1) weekly_market_series.json
  2) weekly_news_context.json / md
  3) macro_background_context.json / md
- Generate:
  output/weekly/YYYY-MM-DD/weekly_forest_summary_analysis_layer_test.json

This script does NOT overwrite weekly_forest_summary.json.
"""

import argparse
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
DEFAULT_MODEL = "gemini-3.5-pro"


SYSTEM_PROMPT = """
你是一位精通全球宏觀經濟、交叉資產策略與市場心理學的資深總經分析師，也是一位能把複雜市場訊號整理成清楚影片主線的總經解說者。

你的任務是根據輸入資料中的新聞、價格、市場訊號與 weekly_v35_diagnosis，產生 Step 80 / Step 91 分析層測試結果。
本次任務只驗證影片分析層，不處理圖像層與語音層。
請不要產生影片分鏡、圖片提示詞、Tom / Miranda 對話稿。

核心原則：
- 總經不是數學公式，不是 A 上升就必然 B 上升。
- 基準檢查路徑是：通膨預期 → 利率走向 → 美元指數 → 亞洲貨幣 / 黃金。
- 這只是基準路徑，不是鐵律；市場預期、資金流向與政策訊號會共同影響最後走勢。
- 每一層都必須先看 analysis_input_bundle 提供的新聞、價格、市場訊號與 weekly_v35_diagnosis，再判斷 up / down / mixed / unclear，不得預設方向。
- 若 analysis_input_bundle 提供 weekly_v35_diagnosis，請優先把它視為 rule-based 診斷層，用來統一主導因子、修正因子、背離訊號、資產驗證與下一期觀察。
- 市場矛盾不是錯誤；若價格與基準傳導不一致，請保留矛盾，並解釋它是修正因子、抵銷力量、資料不足，或新主線早期訊號。
- 分析語氣應採中性、客觀、機構級研究口吻。即使訊號明顯，也應使用「主導、壓過、支撐、削弱、修正、尚待驗證、可能代表」等分析語言描述，不把本期訊號直接定調為確定的新趨勢。
- 對市場轉向、共振或異常訊號，應說明其「目前可能代表的市場看法變化」與「後續仍需驗證的條件」。若資料只支持短期判斷，請避免將其延伸為長期結論。
- 結論應保留不確定性層次，例如「目前較像」、「短線主導」、「仍需觀察」、「資料不足以確認」；分析語氣應避免過度戲劇化或絕對化。
- 對外文字請避免使用「交易、定價、體制、風險溢價、傳導源」等生硬名詞；優先使用「主導因子、修正因子、背離訊號、資產驗證、下期觀察、市場重新評估、市場更關注」。
- 不可新增 analysis_input_bundle 沒有的數字。
- 不可創造新聞。
- 不可給投資建議。
- 資料不足請寫 unclear / 待確認。
- 請使用繁體中文。
- 請只輸出合法 JSON，不要 Markdown，不要註解。
"""


USER_PROMPT_TEMPLATE = """
資料說明：
本程式提供的 analysis_input_bundle 是 Step 80 由既有 weekly 資料組成的影片分析資料包，內容包含：
1. weekly_news_context.json / md：正式分析區間內的新聞脈絡與市場關注訊號。
2. macro_background_context.json / md：近 2～4 週仍影響正式分析區間的背景新聞。
3. weekly_market_series.json：市場價格與資產走勢；其中 analysis_series 是正式分析區間，lookback_series 是背景參考區間。
4. weekly_v35_diagnosis.json：Python rule-based V35 診斷層，提供主導因子、修正因子、背離訊號、資產驗證與下一期觀察。

重要區間原則：
- 本次正式分析區間是：{analysis_window_label}
- 本期主線、市場驗證、資產變化與結論，必須以 analysis_input_bundle.weekly_market_series.analysis_series 為準。
- lookback_series / macro_background_context 只能用作前期背景與延續性脈絡，不可當成正式分析區間的變動起點。
- 若提到 analysis window 之前的事件或價格，必須標示為「前期背景」或「延續性脈絡」。
- 不得把 lookback window 的起點數字寫成正式分析區間的漲跌起點。
- 輸出的 meta.week_range 必須等於正式分析區間：{analysis_window_label}

weekly_v35_diagnosis 使用規則：
- weekly_v35_diagnosis 是 rule-based 診斷層，不是影片旁白文案。
- 請優先使用它來對齊影片主線與網頁主線，尤其是 dominant_driver、correction_factors、divergence_signal、asset_validation、next_period_watch。
- 影片分析可以重新組織語言，但不可忽略或推翻其油價 / 通膨方向規則與資產方向。
- 若你的分層分析與 weekly_v35_diagnosis 出現張力，請寫成分歧、修正因子或待觀察，不要硬改成另一套主線。

分析順序：
一、素材盤點
- 整理本期新聞、政策訊號與市場價格反應。
- 只歸類，不急著下結論。
- 請分成：通膨 / 利率 / 美元 / 黃金 / 亞洲貨幣五類。

二、V35 主線確認
- 先讀 weekly_v35_diagnosis 的 dominant_driver、correction_factors、divergence_signal、asset_validation、next_period_watch。
- 說明本期最重要的主導因子。
- 說明哪些只是修正因子。
- 說明最重要的背離訊號。
- 說明哪些資產走勢支持或挑戰這條主線。

三、分層補充分析
請用簡潔方式補充 V35 沒有說清楚的地方：
- 通膨預期：區分通膨硬數據、油價、需求、勞動、政策預期。
- 利率走向：檢查 Fed 政策、公債供需、期限溢價、避險買債、成長擔憂。
- 美元走向：檢查利差、避險美元、美元流動性需求、非美貨幣自身弱點。
- 黃金走向：檢查利率 / 實質利率、美元、避險需求、央行買盤、地緣政治。
- 亞洲貨幣：分別檢查台幣、日圓、韓圜，不可只寫「亞幣」。

四、影片敘事收斂
請回答：
- 本期市場最後最重要的主導因子是什麼？
- 主要修正因子是什麼？
- 最值得用來開場的問題是什麼？
- 一句話應該讓觀眾記住什麼？
- 下一期要觀察什麼來驗證或推翻目前主線？

用語要求：
- 請避免「交易、定價、體制、風險溢價、傳導源」等生硬詞。
- 優先使用「主導因子、修正因子、背離訊號、資產驗證、下期觀察、市場重新評估、市場更關注」。
- JSON key 若因舊流程相容仍保留 pricing 字樣，內容文字仍請使用較自然的「走向、主導因子、修正因子」。
- 若證據不足，請明確寫 unclear / 待確認 / 待觀察，不要硬湊因果。

請輸出以下 JSON 結構。請保留所有 key，即使資料不足也要填入 unclear / 待確認 / []：

{
  "meta": {
    "source": "analysis_input_bundle",
    "data_status_note": "",
    "week_range": "",
    "analysis_window": {"start_date": "", "end_date": "", "source": ""}
  },
  "main_theme_analysis_process": {
    "material_inventory": {
      "inflation_materials": [],
      "rate_materials": [],
      "dollar_materials": [],
      "gold_materials": [],
      "asia_fx_materials": [],
      "inventory_summary": ""
    },
    "inflation_expectation_formation": {
      "energy": "",
      "supply_chain": "",
      "price_data": "",
      "demand": "",
      "labor_market": "",
      "policy_expectation": "",
      "upward_channels": [],
      "offsetting_channels": [],
      "direction": "up / down / mixed / unclear",
      "strength": "strong / medium / weak",
      "judgment": ""
    },
    "rate_pricing": {
      "direction": "up / down / mixed / unclear",
      "same_direction_as_inflation": "yes / no / mixed / unclear",
      "inflation_to_rate_transmission": "",
      "fed_policy_signal": "",
      "bond_supply_demand": "",
      "term_premium": "",
      "safe_haven_bond_demand": "",
      "growth_or_rate_cut_expectation": "",
      "dominant_driver": "inflation / policy_guidance / term_premium / bond_supply_demand / safe_haven / growth_concern / mixed / unclear",
      "judgment": ""
    },
    "dollar_pricing": {
      "direction": "up / down / mixed / unclear",
      "same_direction_as_rates": "yes / no / mixed / unclear",
      "rate_differential_effect": "",
      "safe_haven_dollar": "",
      "dollar_liquidity_demand": "",
      "other_currency_weakness": "",
      "us_relative_resilience": "",
      "dominant_driver": "rate_differential / safe_haven / liquidity / relative_growth / other_currency_weakness / mixed / unclear",
      "judgment": ""
    },
    "gold_pricing": {
      "direction": "up / down / mixed / unclear",
      "rate_real_yield_pressure": "",
      "dollar_effect": "",
      "safe_haven_demand": "",
      "central_bank_buying": "",
      "geopolitics": "",
      "dominant_driver": "rates / dollar / safe_haven / central_bank / geopolitics / mixed / unclear",
      "judgment": ""
    },
    "asia_fx_pricing": {
      "twd": {
        "direction": "up / down / mixed / unclear",
        "same_direction_as_dollar_pressure": "yes / no / mixed / unclear",
        "local_flow": "",
        "central_bank_policy": "",
        "export_or_tech_sector": "",
        "regional_risk": "",
        "judgment": ""
      },
      "jpy": {
        "direction": "up / down / mixed / unclear",
        "same_direction_as_dollar_pressure": "yes / no / mixed / unclear",
        "japan_policy": "",
        "rate_differential": "",
        "safe_haven_demand": "",
        "other_factor": "",
        "judgment": ""
      },
      "krw": {
        "direction": "up / down / mixed / unclear",
        "same_direction_as_dollar_pressure": "yes / no / mixed / unclear",
        "korea_export": "",
        "equity_flow": "",
        "regional_risk": "",
        "other_factor": "",
        "judgment": ""
      }
    },
    "market_contradictions_and_modifiers": {
      "baseline_path": "通膨預期 → 利率預期 → 美元指數 → 亞洲貨幣 / 黃金",
      "expected_baseline_script": "",
      "most_unintuitive_market_reaction": "",
      "contradiction_type": "modifier / offsetting_force / insufficient_data / early_new_theme_signal / unclear",
      "how_it_fits_main_theme": "",
      "presenter_opening_question": ""
    },
    "main_theme_next_validation": {
      "dominant_pricing_force": "",
      "offsetting_or_modifying_force": "",
      "one_sentence_to_remember": "",
      "next_validation_point": "",
      "overall_verdict": "成立 / 部分成立 / 分歧待觀察 / 待觀察",
      "uncertainty_level": "low / medium / high"
    }
  },
  "forest_summary": {
    "weekly_main_theme": "",
    "main_question": "",
    "one_sentence_verdict": "",
    "overall_verdict": "成立 / 部分成立 / 分歧待觀察 / 待觀察",
    "narrative_arc": "",
    "why_it_matters": ""
  },
  "evidence": {
    "most_important_evidence": [],
    "insufficient_evidence": [],
    "watch_items_from_news_context": []
  }
}


analysis_input_bundle:
{analysis_input_bundle_json}
"""


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def resolve_week_dir(value: str) -> Path:
    if value:
        week_dir = Path(value)
        if not week_dir.exists() and not week_dir.is_absolute():
            candidate = OUTPUT_WEEKLY_DIR / value
            if candidate.exists():
                return candidate
        return week_dir
    return find_latest_week_dir()

def infer_analysis_window_from_source(week_dir: Path) -> Dict[str, str]:
    env_start = os.getenv("ANALYSIS_START_DATE", "").strip()
    env_end = os.getenv("ANALYSIS_END_DATE", "").strip()
    if env_start and env_end:
        return {"start_date": env_start, "end_date": env_end, "label": f"{env_start} ～ {env_end}", "source": "workflow_env"}

    source_text = load_text(week_dir / "weekly_source_text.md")
    match = re.search(r"週期：\s*(\d{4}-\d{2}-\d{2})\s*[～~\-to]+\s*(\d{4}-\d{2}-\d{2})", source_text)
    if match:
        start, end = match.group(1), match.group(2)
        return {"start_date": start, "end_date": end, "label": f"{start} ～ {end}", "source": "weekly_source_text.md"}

    news_context = load_json(week_dir / "weekly_news_context.json", {})
    week_range = str(news_context.get("meta", {}).get("week_range") or "") if isinstance(news_context, dict) else ""
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:～|~|to|-)\s*(\d{4}-\d{2}-\d{2})", week_range)
    if match:
        start, end = match.group(1), match.group(2)
        return {"start_date": start, "end_date": end, "label": f"{start} ～ {end}", "source": "weekly_news_context.json"}

    return {"start_date": "", "end_date": week_dir.name, "label": week_dir.name, "source": "week_dir"}


def filter_points_by_window(points: Any, start_date: str, end_date: str) -> list:
    if not isinstance(points, list):
        return []
    filtered = []
    for point in points:
        if not isinstance(point, dict):
            continue
        date_text = str(point.get("date") or "")
        if start_date and date_text < start_date:
            continue
        if end_date and date_text > end_date:
            continue
        filtered.append(point)
    return filtered


def build_market_payload_for_analysis(weekly_market_series_json: Dict[str, Any], analysis_window: Dict[str, str]) -> Dict[str, Any]:
    start = analysis_window.get("start_date", "")
    end = analysis_window.get("end_date", "")
    series = weekly_market_series_json.get("series", [])
    analysis_series = []
    lookback_series = []

    if isinstance(series, list):
        for item in series:
            if not isinstance(item, dict):
                continue
            original_points = item.get("points") or []
            filtered_item = dict(item)
            filtered_item["points"] = filter_points_by_window(original_points, start, end)
            filtered_item["analysis_points_count"] = len(filtered_item["points"])
            filtered_item["lookback_points_count"] = len(original_points) if isinstance(original_points, list) else 0
            analysis_series.append(filtered_item)
            lookback_series.append(dict(item))

    original_meta = weekly_market_series_json.get("meta", {}) if isinstance(weekly_market_series_json.get("meta"), dict) else {}

    return {
        "meta": {
            "source": "weekly_market_series.json",
            "analysis_window": analysis_window,
            "lookback_window": original_meta.get("range", {}),
            "instruction": "Use analysis_series for this week's price validation and conclusions. Use lookback_series only as prior background/context."
        },
        "analysis_series": analysis_series,
        "lookback_series": lookback_series,
    }




def build_analysis_input_bundle(
    weekly_news_context_json: Dict[str, Any],
    weekly_news_context_md: str,
    macro_background_context_json: Dict[str, Any],
    macro_background_context_md: str,
    market_payload: Dict[str, Any],
    analysis_window: Dict[str, str],
    weekly_v35_diagnosis: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Step 80 still reads weekly files, but the prompt uses the generic name
    analysis_input_bundle so the analysis logic can later be reused by daily workflows.
    """
    return {
        "meta": {
            "source": "Step 80 assembled analysis package",
            "analysis_window": analysis_window,
            "input_files": [
                "weekly_news_context.json",
                "weekly_news_context.md",
                "macro_background_context.json",
                "macro_background_context.md",
                "weekly_market_series.json",
                "weekly_v35_diagnosis.json",
            ],
            "note": (
                "Use weekly_market_series.analysis_series for formal price validation. "
                "Use macro_background_context and lookback_series only as background/context."
            ),
        },
        "news_context": {
            "json": weekly_news_context_json,
            "markdown": weekly_news_context_md,
        },
        "background_context": {
            "json": macro_background_context_json,
            "markdown": macro_background_context_md,
        },
        "weekly_market_series": market_payload,
        "weekly_v35_diagnosis": weekly_v35_diagnosis or {},
    }


def extract_json_from_text(text: str) -> Dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    start = cleaned.find("{")
    if start == -1:
        preview = cleaned[:1000]
        raise ValueError(f"Gemini response does not contain a JSON object. Preview: {preview}")

    decoder = json.JSONDecoder()
    try:
        obj, _ = decoder.raw_decode(cleaned[start:])
    except json.JSONDecodeError as exc:
        preview = cleaned[:2000]
        raise ValueError(f"Unable to parse Gemini JSON. Error: {exc}. Preview: {preview}") from exc

    if not isinstance(obj, dict):
        raise ValueError("Gemini JSON root is not an object.")
    return obj


def call_gemini_json(system_prompt: str, user_prompt: str, model: str, api_key: str) -> Dict[str, Any]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + urllib.parse.quote(model)
        + ":generateContent?key="
        + urllib.parse.quote(api_key)
    )

    payload = {
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "topP": 0.85,
            "responseMimeType": "application/json",
        },
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=240) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini analysis layer test HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Gemini analysis layer test URLError: {exc}") from exc

    api_response = json.loads(raw)

    try:
        text = api_response["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Gemini response: {api_response}") from exc

    return extract_json_from_text(text)


def build_user_prompt(week_dir: Path) -> str:
    weekly_news_context_json = load_json(week_dir / "weekly_news_context.json", {})
    weekly_news_context_md = load_text(week_dir / "weekly_news_context.md")
    macro_background_context_json = load_json(week_dir / "macro_background_context.json", {})
    macro_background_context_md = load_text(week_dir / "macro_background_context.md")
    weekly_market_series_json = load_json(week_dir / "weekly_market_series.json", {})
    weekly_v35_diagnosis = load_json(week_dir / "weekly_v35_diagnosis.json", {})
    analysis_window = infer_analysis_window_from_source(week_dir)

    if not weekly_market_series_json:
        raise FileNotFoundError(f"Missing or empty weekly_market_series.json in {week_dir}")

    market_payload = build_market_payload_for_analysis(weekly_market_series_json, analysis_window)
    analysis_input_bundle = build_analysis_input_bundle(
        weekly_news_context_json=weekly_news_context_json,
        weekly_news_context_md=weekly_news_context_md,
        macro_background_context_json=macro_background_context_json,
        macro_background_context_md=macro_background_context_md,
        market_payload=market_payload,
        analysis_window=analysis_window,
        weekly_v35_diagnosis=weekly_v35_diagnosis,
    )

    print(f"[INFO] Analysis window: {analysis_window.get('label')} ({analysis_window.get('source')})")

    return USER_PROMPT_TEMPLATE.replace(
        "{analysis_window_label}",
        analysis_window.get("label", "資料週期待確認"),
    ).replace(
        "{analysis_input_bundle_json}",
        json.dumps(analysis_input_bundle, ensure_ascii=False, indent=2),
    )



def normalize_result_for_downstream(result: Dict[str, Any], analysis_window: Dict[str, str]) -> Dict[str, Any]:
    """
    Keep downstream Step 82 compatibility while using the new Step 80 analysis schema.
    """
    result.setdefault("meta", {})
    result["meta"]["week_range"] = analysis_window.get("label", "")
    result["meta"]["analysis_window"] = {
        "start_date": analysis_window.get("start_date", ""),
        "end_date": analysis_window.get("end_date", ""),
        "source": analysis_window.get("source", ""),
    }
    result["meta"]["data_status_note"] = (
        "分析層使用 analysis window 作為正式判斷區間；"
        "lookback / background 資料僅作前期脈絡，不作為正式區間變動起點。"
    )

    process = result.setdefault("main_theme_analysis_process", {})
    main_theme = process.get("main_theme_next_validation", {}) if isinstance(process.get("main_theme_next_validation"), dict) else {}
    contradictions = process.get("market_contradictions_and_modifiers", {}) if isinstance(process.get("market_contradictions_and_modifiers"), dict) else {}

    forest_summary = result.setdefault("forest_summary", {})
    if not forest_summary.get("weekly_main_theme"):
        forest_summary["weekly_main_theme"] = main_theme.get("dominant_pricing_force", "")
    if not forest_summary.get("main_question"):
        forest_summary["main_question"] = contradictions.get("presenter_opening_question", "")
    if not forest_summary.get("one_sentence_verdict"):
        forest_summary["one_sentence_verdict"] = main_theme.get("one_sentence_to_remember", "")
    if not forest_summary.get("overall_verdict"):
        forest_summary["overall_verdict"] = main_theme.get("overall_verdict", "待觀察")
    if not forest_summary.get("narrative_arc"):
        forest_summary["narrative_arc"] = (
            f"主導力量：{main_theme.get('dominant_pricing_force', '待確認')}；"
            f"修正力量：{main_theme.get('offsetting_or_modifying_force', '待確認')}。"
        )
    if not forest_summary.get("why_it_matters"):
        forest_summary["why_it_matters"] = main_theme.get("next_validation_point", "")

    result.setdefault("evidence", {})
    result["evidence"].setdefault("most_important_evidence", [])
    result["evidence"].setdefault("insufficient_evidence", [])
    result["evidence"].setdefault("watch_items_from_news_context", [])
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise EnvironmentError("Missing GEMINI_API_KEY.")

    model = (
        os.getenv("GEMINI_ANALYSIS_MODEL", "").strip()
        or os.getenv("GEMINI_MODEL", "").strip()
        or DEFAULT_MODEL
    )

    week_dir = resolve_week_dir(args.week_dir)

    print(f"[INFO] Step 80 analysis-layer test model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] weekly_news_context.json included: {(week_dir / 'weekly_news_context.json').exists()}")
    print(f"[INFO] weekly_news_context.md included: {(week_dir / 'weekly_news_context.md').exists()}")
    print(f"[INFO] macro_background_context.json included: {(week_dir / 'macro_background_context.json').exists()}")
    print(f"[INFO] macro_background_context.md included: {(week_dir / 'macro_background_context.md').exists()}")
    print(f"[INFO] weekly_market_series.json included: {(week_dir / 'weekly_market_series.json').exists()}")
    print(f"[INFO] weekly_v35_diagnosis.json included: {(week_dir / 'weekly_v35_diagnosis.json').exists()}")

    user_prompt = build_user_prompt(week_dir)
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)

    analysis_window = infer_analysis_window_from_source(week_dir)
    result = normalize_result_for_downstream(result, analysis_window)

    out_path = week_dir / "weekly_forest_summary_analysis_layer_test.json"
    save_json(out_path, result)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
