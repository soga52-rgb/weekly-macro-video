#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 80 - Weekly Video Analysis Layer (legacy test output name retained for workflow compatibility)

Purpose:
- Generate the formal analysis layer used by the downstream weekly video story workflow.
- Keep the existing output filename for workflow compatibility.
- Read:
  1) weekly_v35_diagnosis.json (authoritative diagnosis)
  2) weekly_market_series.json (formal-window price validation)
  3) compact representative articles from weekly_news_context.json (evidence only)
- Do not send weekly_news_context.md, background context, or news-generated narrative fields to Gemini.
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

你的任務是以 weekly_v35_diagnosis 為主線權威、以正式區間價格為方向驗證，並以少量代表新聞作事件佐證，產生 Step 80 / Step 91 分析層結果。
本次任務只驗證影片分析層，不處理圖像層與語音層。
請不要產生影片分鏡、圖片提示詞、Tom / Miranda 對話稿。

核心原則：
- 總經不是數學公式，不是 A 上升就必然 B 上升。
- 基準檢查路徑是：通膨預期 → 利率走向 → 美元指數 → 亞洲貨幣 / 黃金。
- 這只是基準路徑，不是鐵律；市場預期、資金流向與政策訊號會共同影響最後走勢。
- 每一層都必須先看 analysis_input_bundle 提供的 weekly_v35_diagnosis 與正式區間市場價格，再判斷 up / down / mixed / unclear，不得預設方向。
- weekly_v35_diagnosis 是本流程的主線權威：dominant_driver 決定本期主線，correction_factors 決定修正因子，divergence_signal 決定主要背離，asset_validation 決定資產驗證，next_period_watch 決定下期觀察。
- representative_news_evidence 只提供原始文章標題、來源、日期與分類作事件佐證，不得取代、重排或推翻 V35 主線。
- 不得沿用新聞檔先前生成的 weekly_news_theme、macro_drivers、confirming_signals、contradicting_signals、news_based_corrections、watch_points 或 editor_note_for_forest_summary；這些二次分析欄位已刻意排除。
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
本程式提供的 analysis_input_bundle 是聚焦後的 Step 80 影片分析資料包，內容只包含：
1. weekly_v35_diagnosis.json：Python rule-based V35 診斷層，也是本期主線權威。
2. weekly_market_series.json 的 analysis_series：正式分析區間內的市場價格與資產走勢。
3. representative_news_evidence：由 weekly_news_context.json 篩出的少量代表文章，只保留原始標題、來源、發布時間與分類，僅作事件佐證。

本程式刻意不提供：
- weekly_news_context.md。
- macro_background_context.json / md。
- weekly_news_context.json 中已由前一個模型生成的主線、驅動因子、修正因子、待觀察與編輯結論。
原因是這些二次分析文字可能帶入過期事件、舊敘事或與正式市場方向不一致的判斷。

重要區間原則：
- 本次正式分析區間是：{analysis_window_label}
- 本期主線先以 analysis_input_bundle.weekly_v35_diagnosis 為準；市場驗證、資產變化與方向必須以 analysis_input_bundle.weekly_market_series.analysis_series 為準。
- 本資料包不提供 lookback / background 敘事，不得自行引入正式分析區間之外的舊事件。
- 不得把代表新聞標題中的推測、評論或條件句改寫成已確認的市場事實。
- 輸出的 meta.week_range 必須等於正式分析區間：{analysis_window_label}

weekly_v35_diagnosis 使用規則：
- weekly_v35_diagnosis 是 rule-based 診斷層，不是影片旁白文案，但它是本流程的主線權威。
- forest_summary.weekly_main_theme 必須與 weekly_v35_diagnosis.weekly_v35_diagnosis.dominant_driver 語意一致，不得另立主線。
- main_theme_next_validation.dominant_pricing_force 必須與 dominant_driver 語意一致。
- correction_factors 只能作修正力量，不得升格成新的共同主導因子。
- divergence_signal 必須保留在市場矛盾與背離說明中。
- asset_validation 決定資產方向與主要驗證；next_period_watch 決定下期觀察。
- 影片分析可以重新組織語言，但不可忽略或推翻其油價 / 通膨方向規則、資產方向與亞洲貨幣分化判斷。
- 若分層分析與 weekly_v35_diagnosis 出現張力，請寫成分歧、修正因子或待觀察，不要硬改成另一套主線。

油價方向規則：
- 油價方向必須優先依 weekly_v35_diagnosis.observed_market 或 weekly_market_series.analysis_series 中 WTI / Brent 的實際方向，不得只憑新聞標題猜測。
- WTI / Brent 上行：代表能源成本與短期通膨預期的上行壓力增加；若不是本期主線，應列為修正因子或並行訊號。
- WTI / Brent 下行：可能緩和能源通膨壓力；若由需求疲弱造成，也應同時視為成長降溫訊號。
- 不得把油價變動直接寫成由財政赤字、高利率或公債供需所造成；這些因子可影響利率，但不是油價方向的直接原因。

就業方向規則：
- 指標名稱不等於方向。只有看到「上升 / 高於預期 / 下降 / 低於預期」等明確方向，才能判斷初領失業金、非農、失業率或薪資。
- 初領失業金上升或高於預期才屬就業降溫；下降或低於預期才屬就業偏強。
- 非農低於預期或明顯放緩屬就業降溫；非農高於預期或明顯強勁才屬就業偏強。
- 失業率下降先視為勞動市場韌性，不可單獨改寫成全面就業強勁；若非農偏弱但失業率下降，應呈現為就業訊號分歧。
- laborStrength 本身不得直接推升綜合通膨預期；只有薪資壓力、需求偏強、通膨硬數據或能源供給風險，才可作為通膨預期上行來源。
- 不得為了配合 US10Y、DXY 或其他資產方向，而把低於預期、轉弱或混合的就業新聞改寫成強勁。

美元方向規則：
- 美元方向優先以 DXY 實際走勢判斷；新聞只用來解釋利差、避險美元、流動性需求或非美貨幣自身因素。
- 新聞只出現「美元 / DXY」名稱但沒有明確方向時，不得自行判定美元走強或走弱。

代表新聞使用規則：
- representative_news_evidence 不是主線結論，只是事件證據。
- 只能引用文章標題直接支持的事件，不得從標題自行延伸出財政赤字、期限溢價、資金流、央行態度或政策因果。
- 若代表新聞中沒有明確提及某原因，該原因必須寫 unclear / 待確認。
- 不得把單日新聞中的油價回落、美元走弱或黃金上漲，改寫成正式分析區間的週線方向；週線方向一律以 analysis_series / V35 observed_market 為準。
- 韓元若與美元方向背離，而代表新聞沒有直接證據說明原因，請寫「具體原因待確認」，不得自行補成資金流支撐。

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
    """Resolve one formal analysis window shared by V35, web, and video layers."""
    env_start = os.getenv("ANALYSIS_START_DATE", "").strip()
    env_end = os.getenv("ANALYSIS_END_DATE", "").strip()
    if env_start and env_end:
        return {"start_date": env_start, "end_date": env_end, "label": f"{env_start} ～ {env_end}", "source": "workflow_env"}

    market_series = load_json(week_dir / "weekly_market_series.json", {})
    if isinstance(market_series, dict):
        meta = market_series.get("meta", {}) if isinstance(market_series.get("meta"), dict) else {}
        requested = meta.get("requested_analysis_window", {}) if isinstance(meta.get("requested_analysis_window"), dict) else {}
        start = str(requested.get("start_date") or "").strip()
        end = str(requested.get("end_date") or "").strip()
        if start and end:
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "weekly_market_series.meta.requested_analysis_window",
            }

    news_context = load_json(week_dir / "weekly_news_context.json", {})
    if isinstance(news_context, dict):
        meta = news_context.get("meta", {}) if isinstance(news_context.get("meta"), dict) else {}
        analysis_window = meta.get("analysis_window", {}) if isinstance(meta.get("analysis_window"), dict) else {}
        start = str(analysis_window.get("start_date") or "").strip()
        end = str(analysis_window.get("end_date") or "").strip()
        if start and end:
            return {
                "start_date": start,
                "end_date": end,
                "label": f"{start} ～ {end}",
                "source": "weekly_news_context.meta.analysis_window",
            }

        week_range = str(meta.get("week_range") or "").strip()
        match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:～|~|to|-)\s*(\d{4}-\d{2}-\d{2})", week_range)
        if match:
            start, end = match.group(1), match.group(2)
            return {"start_date": start, "end_date": end, "label": f"{start} ～ {end}", "source": "weekly_news_context.meta.week_range"}

    source_text = load_text(week_dir / "weekly_source_text.md")
    match = re.search(r"週期：\s*(\d{4}-\d{2}-\d{2})\s*[～~\-to]+\s*(\d{4}-\d{2}-\d{2})", source_text)
    if match:
        start, end = match.group(1), match.group(2)
        return {"start_date": start, "end_date": end, "label": f"{start} ～ {end}", "source": "weekly_source_text.md"}

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

    return {
        "meta": {
            "source": "weekly_market_series.json",
            "analysis_window": analysis_window,
            "instruction": "Use analysis_series as the only price source for this week's validation and conclusions."
        },
        "analysis_series": analysis_series,
    }




def normalize_article_title(value: Any) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    return re.sub(r"\W+", "", text)[:120]


def build_representative_news_evidence(news_context: Dict[str, Any], max_items: int = 8) -> Dict[str, Any]:
    """
    Keep only compact article-level evidence for Step 80.

    Deliberately exclude all model-generated narrative fields from weekly_news_context,
    including weekly_news_theme, macro_drivers, confirming/contradicting signals,
    corrections, watch points, and editor notes.
    """
    categories = news_context.get("news_categories", {}) if isinstance(news_context, dict) else {}
    title_to_category: Dict[str, str] = {}
    if isinstance(categories, dict):
        for category, items in categories.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                key = normalize_article_title(item.get("title"))
                if key and key not in title_to_category:
                    title_to_category[key] = str(category or "")

    generic_why_prefixes = (
        "補充本週",
        "本週總經新聞候選",
    )
    generic_titles = {
        "鉅亨網鉅亨網",
        "news.cnyes.comnews.cnyes.com",
    }

    selected = []
    seen = set()

    def add_item(item: Any, category_hint: str = "") -> None:
        if len(selected) >= max_items or not isinstance(item, dict):
            return
        title = re.sub(r"\s+", " ", str(item.get("title") or "").strip())
        key = normalize_article_title(title)
        if not key or key in seen or key in generic_titles:
            return
        why = str(item.get("why_it_matters") or "").strip()
        if why.startswith(generic_why_prefixes):
            return
        seen.add(key)
        selected.append({
            "category": category_hint or title_to_category.get(key, ""),
            "title": title,
            "source": str(item.get("source") or "").strip(),
            "published_at": str(item.get("published_at") or "").strip(),
        })

    top_news = news_context.get("top_news", []) if isinstance(news_context, dict) else []
    if isinstance(top_news, list):
        for item in top_news:
            add_item(item)

    # Fallback only when top_news has too little clean evidence.
    if len(selected) < 3 and isinstance(categories, dict):
        for category in ["通膨預期", "利率", "貨幣", "其他"]:
            items = categories.get(category, [])
            if not isinstance(items, list):
                continue
            for item in items:
                add_item(item, category_hint=category)
                if len(selected) >= max_items:
                    break
            if len(selected) >= max_items:
                break

    return {
        "selection_rule": (
            "Article-level evidence only. Full news narrative, markdown, background context, "
            "watch points, corrections, and editor conclusions are excluded."
        ),
        "articles": selected,
    }



def build_analysis_input_bundle(
    representative_news_evidence: Dict[str, Any],
    market_payload: Dict[str, Any],
    analysis_window: Dict[str, str],
    weekly_v35_diagnosis: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a focused Step 80 package with V35 as the authoritative diagnosis."""
    return {
        "meta": {
            "source": "Step 80 focused V35-authority package",
            "analysis_window": analysis_window,
            "input_files": [
                "weekly_v35_diagnosis.json",
                "weekly_market_series.json",
                "weekly_news_context.json (representative article fields only)",
            ],
            "excluded_inputs": [
                "weekly_news_context.md",
                "macro_background_context.json",
                "macro_background_context.md",
                "weekly_news_context generated narrative fields",
            ],
            "note": (
                "Use weekly_v35_diagnosis as the authoritative storyline. "
                "Use weekly_market_series.analysis_series for formal price validation. "
                "Use representative_news_evidence only as article-level event support."
            ),
        },
        "weekly_v35_diagnosis": weekly_v35_diagnosis,
        "weekly_market_series": market_payload,
        "representative_news_evidence": representative_news_evidence,
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
    weekly_market_series_json = load_json(week_dir / "weekly_market_series.json", {})
    weekly_v35_diagnosis = load_json(week_dir / "weekly_v35_diagnosis.json", {})
    analysis_window = infer_analysis_window_from_source(week_dir)

    if not weekly_market_series_json:
        raise FileNotFoundError(f"Missing or empty weekly_market_series.json in {week_dir}")

    compact_v35 = (
        weekly_v35_diagnosis.get("weekly_v35_diagnosis", {})
        if isinstance(weekly_v35_diagnosis, dict)
        else {}
    )
    if not isinstance(compact_v35, dict) or not compact_v35:
        raise FileNotFoundError(
            f"Missing or empty weekly_v35_diagnosis.weekly_v35_diagnosis in {week_dir}. "
            "Run scripts/macro_v35_diagnosis.py before Step 80."
        )

    market_payload = build_market_payload_for_analysis(weekly_market_series_json, analysis_window)
    representative_news_evidence = build_representative_news_evidence(weekly_news_context_json)
    analysis_input_bundle = build_analysis_input_bundle(
        representative_news_evidence=representative_news_evidence,
        market_payload=market_payload,
        analysis_window=analysis_window,
        weekly_v35_diagnosis=weekly_v35_diagnosis,
    )

    print(f"[INFO] Analysis window: {analysis_window.get('label')} ({analysis_window.get('source')})")
    print(f"[INFO] Representative news articles included: {len(representative_news_evidence.get('articles', []))}")

    return USER_PROMPT_TEMPLATE.replace(
        "{analysis_window_label}",
        analysis_window.get("label", "資料週期待確認"),
    ).replace(
        "{analysis_input_bundle_json}",
        json.dumps(analysis_input_bundle, ensure_ascii=False, indent=2),
    )


def map_v35_verdict(value: Any) -> str:
    text = str(value or "").strip()
    if "部分" in text:
        return "部分成立"
    if "分歧" in text:
        return "分歧待觀察"
    if text in {"支持", "成立"}:
        return "成立"
    if text in {"不支持", "待觀察"}:
        return "待觀察"
    return ""


def local_currency_direction(pair_direction: str) -> str:
    if pair_direction == "up":
        return "down"
    if pair_direction == "down":
        return "up"
    return pair_direction or "unclear"


def normalize_result_for_downstream(
    result: Dict[str, Any],
    analysis_window: Dict[str, str],
    weekly_v35_diagnosis: Dict[str, Any],
) -> Dict[str, Any]:
    """Keep Step 82 compatibility and enforce V35 authority after Gemini generation."""
    compact_v35 = (
        weekly_v35_diagnosis.get("weekly_v35_diagnosis", {})
        if isinstance(weekly_v35_diagnosis, dict)
        else {}
    )
    observed = (
        weekly_v35_diagnosis.get("observed_market", {})
        if isinstance(weekly_v35_diagnosis, dict)
        else {}
    )
    dominant_driver = str(
        compact_v35.get("dominant_driver")
        or weekly_v35_diagnosis.get("primary_macro_story")
        or "待確認"
    ).strip()
    correction_factors = compact_v35.get("correction_factors", [])
    if not isinstance(correction_factors, list):
        correction_factors = []
    divergence_signal = str(compact_v35.get("divergence_signal") or "").strip()
    next_period_watch = compact_v35.get("next_period_watch", [])
    if not isinstance(next_period_watch, list):
        next_period_watch = []
    v35_verdict = map_v35_verdict(weekly_v35_diagnosis.get("final_judgment"))

    result.setdefault("meta", {})
    result["meta"]["week_range"] = analysis_window.get("label", "")
    result["meta"]["analysis_window"] = {
        "start_date": analysis_window.get("start_date", ""),
        "end_date": analysis_window.get("end_date", ""),
        "source": analysis_window.get("source", ""),
    }
    result["meta"]["data_status_note"] = (
        "分析層只使用正式 analysis window；weekly_v35_diagnosis 為主線權威；"
        "市場價格用於方向驗證；代表新聞只作事件佐證；"
        "weekly_news_context.md、背景新聞與新聞模型先前生成的主線文字均未送入 Gemini。"
    )
    result["meta"]["v35_authority_applied"] = True
    result["meta"]["v35_dominant_driver"] = dominant_driver

    process = result.setdefault("main_theme_analysis_process", {})
    main_theme = process.setdefault("main_theme_next_validation", {})
    contradictions = process.setdefault("market_contradictions_and_modifiers", {})

    # Hard lock the dominant storyline and verdict to V35.
    main_theme["dominant_pricing_force"] = dominant_driver
    if correction_factors:
        main_theme["offsetting_or_modifying_force"] = "；".join(str(x) for x in correction_factors[:3] if str(x).strip())
    if next_period_watch:
        main_theme["next_validation_point"] = "；".join(str(x) for x in next_period_watch[:3] if str(x).strip())
    if v35_verdict:
        main_theme["overall_verdict"] = v35_verdict
    if divergence_signal:
        contradictions["how_it_fits_main_theme"] = divergence_signal

    # Hard lock observable asset directions to V35.
    rate_pricing = process.setdefault("rate_pricing", {})
    dollar_pricing = process.setdefault("dollar_pricing", {})
    gold_pricing = process.setdefault("gold_pricing", {})
    asia_fx = process.setdefault("asia_fx_pricing", {})
    rate_pricing["direction"] = str(observed.get("US10Y", {}).get("direction") or "unclear")
    dollar_pricing["direction"] = str(observed.get("DXY", {}).get("direction") or "unclear")
    gold_pricing["direction"] = str(observed.get("Gold", {}).get("direction") or "unclear")
    for key, asset in [("jpy", "USDJPY"), ("twd", "USDTWD"), ("krw", "USDKRW")]:
        bucket = asia_fx.setdefault(key, {})
        bucket["direction"] = local_currency_direction(str(observed.get(asset, {}).get("direction") or ""))

    forest_summary = result.setdefault("forest_summary", {})
    forest_summary["weekly_main_theme"] = dominant_driver
    if not forest_summary.get("main_question"):
        forest_summary["main_question"] = contradictions.get("presenter_opening_question", "")
    if not forest_summary.get("one_sentence_verdict"):
        forest_summary["one_sentence_verdict"] = main_theme.get("one_sentence_to_remember", "")
    if v35_verdict:
        forest_summary["overall_verdict"] = v35_verdict
    elif not forest_summary.get("overall_verdict"):
        forest_summary["overall_verdict"] = main_theme.get("overall_verdict", "待觀察")
    if not forest_summary.get("narrative_arc"):
        forest_summary["narrative_arc"] = (
            f"主導力量：{dominant_driver}；"
            f"修正力量：{main_theme.get('offsetting_or_modifying_force', '待確認')}。"
        )
    if not forest_summary.get("why_it_matters"):
        forest_summary["why_it_matters"] = main_theme.get("next_validation_point", "")

    evidence = result.setdefault("evidence", {})
    asset_validation = compact_v35.get("asset_validation", [])
    if isinstance(asset_validation, list) and asset_validation:
        evidence["most_important_evidence"] = asset_validation[:6]
    else:
        evidence.setdefault("most_important_evidence", [])
    evidence.setdefault("insufficient_evidence", [])
    if next_period_watch:
        evidence["watch_items_from_news_context"] = next_period_watch[:5]
    else:
        evidence.setdefault("watch_items_from_news_context", [])
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

    print(f"[INFO] Step 80 analysis-layer model: {model}")
    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] weekly_v35_diagnosis.json included: {(week_dir / 'weekly_v35_diagnosis.json').exists()}")
    print(f"[INFO] weekly_market_series.json included: {(week_dir / 'weekly_market_series.json').exists()}")
    print(f"[INFO] weekly_news_context.json used as compact article evidence: {(week_dir / 'weekly_news_context.json').exists()}")
    print("[INFO] weekly_news_context.md excluded from Gemini input: True")
    print("[INFO] macro_background_context excluded from Gemini input: True")

    user_prompt = build_user_prompt(week_dir)
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)

    analysis_window = infer_analysis_window_from_source(week_dir)
    weekly_v35_diagnosis = load_json(week_dir / "weekly_v35_diagnosis.json", {})
    result = normalize_result_for_downstream(result, analysis_window, weekly_v35_diagnosis)

    out_path = week_dir / "weekly_forest_summary_analysis_layer_test.json"
    save_json(out_path, result)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
