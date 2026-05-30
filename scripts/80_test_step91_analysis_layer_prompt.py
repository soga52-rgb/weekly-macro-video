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
你是一位精通全球宏觀經濟、交叉資產策略與市場心理學的資深總經分析師，同時也是影音內容結構設計師。

你負責根據當週新聞、前期背景新聞與市場數據，產生 weekly_forest_summary.json 的分析層測試結果。

本次任務只驗證分析層，不處理圖像層與語音層。
請不要產生影片分鏡、圖片提示詞、Tom / Miranda 對話稿。
請只產生分析層內容。

核心原則：
- 分析層是唯一負責市場判斷與本週主線定義的層。
- 本週主線不是分析起點，而是完成分析過程後的匯總結果。
- 不得先看新聞標題就直接定題。
- 不得憑空補充資料來源沒有提供的事件。
- 若資料不足，請標示「資料不足 / 待確認」。
- 請使用繁體中文。
- 請只輸出合法 JSON，不要 Markdown，不要解釋文字。
"""


USER_PROMPT_TEMPLATE = """
資料來源：
1. weekly_news_context.json / md：當週新聞脈絡與市場關注訊號。
2. macro_background_context.json / md：近 2～4 週仍影響本週市場的背景新聞。
3. weekly_market_series.json：市場價格與資產走勢；其中 analysis_series 是正式分析區間，lookback_series 是背景參考區間。

重要區間原則：
- 本次正式分析區間是：{analysis_window_label}
- 本週主線、本週市場驗證、本週資產變化、本週結論，必須以 analysis_series 為準。
- lookback_series / macro_background_context 只能用作前期背景與延續性脈絡，不可當成本週變動起點。
- 若提到 analysis window 之前的事件或價格，必須標示為「前期背景」或「延續性脈絡」。
- 不得把 lookback window 的起點數字寫成本週漲跌起點。
- 輸出的 meta.week_range 必須等於正式分析區間：{analysis_window_label}

weekly_forest_summary.json 必須產出一組完整的「本週主線分析過程」。
頁數或段落數不固定，但至少必須包含以下分析段落：

1. 新聞脈絡
2. 市場數據驗證
3. 通膨預期綜合研判
4. 利率驅動來源
5. 美元與黃金
6. 亞洲貨幣：台、日、韓
7. 本週主線結論
8. 下週觀察

第 1～6 項是本週主線的推導過程。
第 7 項是根據第 1～6 項收斂出的本週主線結論。
第 8 項是根據本週主線與尚未確認的風險延伸出的下週觀察。

一、新聞脈絡

請根據 weekly_news_context.json / md 與 macro_background_context.json / md，整理本週新聞脈絡。

要求：
- 區分「當週新增新聞」與「前期背景新聞」。
- 依三個主題整理：
  1. 通膨
  2. 利率
  3. 美元 / 亞幣 / 黃金
- 當週新增新聞應以 weekly_news_context 為主。
- 前期背景新聞應以 macro_background_context 為主。
- 不需要摘要全部新聞，只挑選影響本週分析主線的關鍵新聞。
- 每則新聞請標示其可能作用：強化 / 抵銷 / 分歧 / 待觀察。
- 請說明這些新聞為後續哪個分析段落提供素材。

二、市場數據驗證

請根據 weekly_market_series.json 檢查市場價格如何反映新聞訊號。

要求：
- 檢查油價、利率、美元、黃金、台幣、日圓、韓圜。
- 價格驗證只描述市場走勢與對應訊號，不要直接跳到最終主線。
- 特別注意：
  - 油價是否反映能源通膨壓力降溫或升溫。
  - 美債殖利率是否跟油價同步放鬆。
  - 美元是否受利率支撐。
  - 黃金是否受到高利率壓抑或避險需求支撐。
  - 台幣、日圓、韓圜是否呈現一致或分化壓力。

三、通膨預期綜合研判

請承接新聞脈絡與市場數據驗證，判斷本週通膨預期是否形成明確單一方向。

要求：
- 前期 CPI / PPI 偏強等背景訊號，若資料中有出現，應視為支持通膨壓力的背景。
- 本週美伊和平曙光、油價走跌、能源價格壓力緩解等訊號，若資料中有出現，應視為抵銷或修正能源端通膨壓力的訊號。
- 不得只因油價單週下跌就判斷整體通膨預期降溫。
- 不得只因 CPI / PPI 偏強就忽略能源端修正。
- 結論請歸類為 strong / mixed / weak / unclear。
- 避免使用「拉扯」一詞；請使用「分歧」、「抵銷」、「不同方向力量」、「尚未形成單一方向」、「訊號交錯」。

四、利率驅動來源

本段只討論利率，不要擴到美元、亞幣、黃金。

請根據 weekly_news_context、macro_background_context 與 weekly_market_series，分析本週利率偏強或偏弱的來源。

要求：
- 從 weekly_news_context 擷取當週利率相關新聞與市場確認訊號。
- 從 macro_background_context 擷取 Fed 政策背景、CPI / PPI 背景、長債殖利率與期限溢價背景。
- 從 weekly_market_series 驗證 US10Y / 30Y 或相關利率數據。
- 利率驅動來源至少檢查：
  1. Fed 政策訊號
  2. CPI / PPI 對降息預期與長債殖利率的影響
  3. 長天期殖利率 / 期限溢價
- 不可只寫「Fed 偏鷹」這類標籤，必須說明具體內容。
- 若資料中有「Fed 會議紀錄顯示多數官員主張將升息列入選項」，應用來說明升息風險或高利率維持更久如何影響利率預期。
- 若資料中有「官員擔心關稅與能源價格推升通膨」，應用來說明 Fed 為何不容易快速轉向寬鬆。
- 結論應收斂為：利率偏強主要來自哪些來源，不得擴到其他資產。

五、美元與黃金

請承接利率驅動來源的結論，分析美元與黃金。

要求：
- 只討論美元與黃金，不擴到亞洲貨幣。
- 使用「新聞訊號 → 背景素材 → 市場驗證 → 驅動來源說明 → 結論」格式。
- 美元部分請檢查 DXY 是否受高利率或利差支撐。
- 黃金部分請檢查高利率壓抑與避險需求是否同時存在。
- 若判斷 mixed / unclear，請說明是哪兩股不同方向力量造成分歧。

六、亞洲貨幣：台、日、韓

請分開分析台幣、日圓、韓圜，不可只寫「亞幣」。

要求：
- 使用「新聞訊號 → 背景素材 → 市場驗證 → 驅動來源說明 → 結論」格式。
- 台幣請看 USDTWD。
- 日圓請看 USDJPY。
- 韓圜請看 USDKRW。
- 若資料不足，請標示待確認。
- 不要把三種貨幣混成單一結論，必須分別說明。

七、本週主線結論

請根據前面第 1～6 項分析，收斂本週主線。

要求：
- forest_summary.weekly_main_theme、main_question、one_sentence_verdict、overall_verdict 必須是完成前面分析後的匯總結果。
- 不可在分析前先行定題。
- 結論要反映新聞脈絡、數據驗證、通膨、利率、美元黃金與亞洲貨幣的整體關係。

八、下週觀察

請根據前面分析中尚未確認的風險與 watch_points，整理下週觀察。

要求：
- 只列出資料中有支撐的觀察項目。
- 不新增無資料支撐的新主題。
- 觀察項目應與本週主線直接相關。

請輸出以下 JSON 結構：

{
  "meta": {
    "source": "weekly_news_context + macro_background_context + weekly_market_series",
    "data_status_note": "",
    "week_range": ""
  },
  "main_theme_analysis_process": {
    "news_context": {
      "current_week_news": {
        "inflation": [],
        "rates": [],
        "dollar_fx_gold": []
      },
      "background_news": {
        "inflation": [],
        "rates": [],
        "dollar_fx_gold": []
      },
      "context_summary": ""
    },
    "market_validation": {
      "inflation_energy": "",
      "rates": "",
      "dollar": "",
      "gold": "",
      "asia_fx": {
        "twd": "",
        "jpy": "",
        "krw": ""
      },
      "validation_summary": ""
    },
    "inflation_expectation_judgment": {
      "signal_strength": "strong / mixed / weak / unclear",
      "supporting_signals": [],
      "offsetting_signals": [],
      "judgment": ""
    },
    "rate_driver_diagnosis": {
      "main_driver": "inflation / policy_guidance / term_premium / bond_supply_demand / mixed / unclear",
      "fed_policy_signal": "",
      "cpi_ppi_background": "",
      "long_end_yield_term_premium": "",
      "market_validation": "",
      "judgment": ""
    },
    "dollar_gold_reaction": {
      "dollar": {
        "news_signal": "",
        "background_context": "",
        "market_validation": "",
        "driver_explanation": "",
        "judgment": ""
      },
      "gold": {
        "news_signal": "",
        "background_context": "",
        "market_validation": "",
        "driver_explanation": "",
        "judgment": ""
      }
    },
    "asia_fx_reaction": {
      "twd": {
        "news_signal": "",
        "background_context": "",
        "market_validation": "",
        "driver_explanation": "",
        "judgment": ""
      },
      "jpy": {
        "news_signal": "",
        "background_context": "",
        "market_validation": "",
        "driver_explanation": "",
        "judgment": ""
      },
      "krw": {
        "news_signal": "",
        "background_context": "",
        "market_validation": "",
        "driver_explanation": "",
        "judgment": ""
      }
    },
    "weekly_main_theme_conclusion": {
      "weekly_main_theme": "",
      "main_question": "",
      "one_sentence_verdict": "",
      "overall_verdict": "成立 / 部分成立 / 分歧待觀察 / 待觀察",
      "narrative_arc": "",
      "why_it_matters": ""
    },
    "next_week_watch": []
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

weekly_news_context.json:
{weekly_news_context_json}

weekly_news_context.md:
{weekly_news_context_md}

macro_background_context.json:
{macro_background_context_json}

macro_background_context.md:
{macro_background_context_md}

weekly_market_series.json:
{weekly_market_series_json}
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
    analysis_window = infer_analysis_window_from_source(week_dir)

    if not weekly_market_series_json:
        raise FileNotFoundError(f"Missing or empty weekly_market_series.json in {week_dir}")

    market_payload = build_market_payload_for_analysis(weekly_market_series_json, analysis_window)
    print(f"[INFO] Analysis window: {analysis_window.get('label')} ({analysis_window.get('source')})")

    return USER_PROMPT_TEMPLATE.replace(
        "{analysis_window_label}",
        analysis_window.get("label", "資料週期待確認"),
    ).replace(
        "{weekly_news_context_json}",
        json.dumps(weekly_news_context_json, ensure_ascii=False, indent=2),
    ).replace(
        "{weekly_news_context_md}",
        weekly_news_context_md,
    ).replace(
        "{macro_background_context_json}",
        json.dumps(macro_background_context_json, ensure_ascii=False, indent=2),
    ).replace(
        "{macro_background_context_md}",
        macro_background_context_md,
    ).replace(
        "{weekly_market_series_json}",
        json.dumps(market_payload, ensure_ascii=False, indent=2),
    )


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

    user_prompt = build_user_prompt(week_dir)
    result = call_gemini_json(SYSTEM_PROMPT, user_prompt, model, api_key)

    analysis_window = infer_analysis_window_from_source(week_dir)
    result.setdefault("meta", {})
    result["meta"]["week_range"] = analysis_window.get("label", "")
    result["meta"]["analysis_window"] = {
        "start_date": analysis_window.get("start_date", ""),
        "end_date": analysis_window.get("end_date", ""),
        "source": analysis_window.get("source", ""),
    }
    result["meta"]["data_status_note"] = (
        "分析層使用 analysis window 作為本週正式判斷區間；"
        "lookback / background 資料僅作前期脈絡，不作為本週變動起點。"
    )

    out_path = week_dir / "weekly_forest_summary_analysis_layer_test.json"
    save_json(out_path, result)

    print(f"[OK] Created {out_path}")


if __name__ == "__main__":
    main()
