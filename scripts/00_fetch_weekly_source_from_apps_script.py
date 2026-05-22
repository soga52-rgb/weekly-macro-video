#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine - Step 00
Fetch weekly source data from Google Apps Script weekly_video_source endpoint.

Input:
- env WEEKLY_SOURCE_URL
  Example:
  https://script.google.com/macros/s/xxxxx/exec

Optional env:
- WEEKLY_SOURCE_START = YYYY-MM-DD
- WEEKLY_SOURCE_END   = YYYY-MM-DD

Output:
- data/weekly_video_source.json
- data/market_history_series.json
- output/weekly/YYYY-MM-DD/weekly_source_text.md
- output/weekly/YYYY-MM-DD/weekly_market_series.json
"""

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


def add_query_params(url: str, params: Dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query))

    for key, value in params.items():
        if value:
            query[key] = value

    new_query = urllib.parse.urlencode(query)
    return urllib.parse.urlunparse(parsed._replace(query=new_query))


def fetch_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "weekly-macro-video-github-actions/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        body = response.read().decode("utf-8")

    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        preview = body[:1000]
        raise ValueError(f"Endpoint did not return valid JSON. Preview: {preview}") from exc


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def safe_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, dict)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value).strip()


def bullet_list(items: Any) -> str:
    if not items:
        return "- 資料不足"

    if isinstance(items, str):
        text = items.strip()
        return text if text else "- 資料不足"

    if isinstance(items, list):
        lines = []
        for item in items:
            if isinstance(item, dict):
                label = item.get("label") or item.get("title") or item.get("asset") or item.get("name") or ""
                meaning = item.get("meaning") or item.get("summary") or item.get("note") or item.get("value") or ""
                text = "｜".join([x for x in [safe_text(label), safe_text(meaning)] if x])
                lines.append(f"- {text}" if text else f"- {json.dumps(item, ensure_ascii=False)}")
            else:
                lines.append(f"- {safe_text(item)}")
        return "\n".join(lines) if lines else "- 資料不足"

    return f"- {safe_text(items)}"


def infer_week_label(data: Dict[str, Any]) -> str:
    range_data = data.get("range", {}) or {}
    end_date = range_data.get("end_date") or data.get("end_date")

    if end_date:
        return str(end_date)

    summaries = data.get("daily_summaries", []) or []
    dates = [x.get("date") for x in summaries if isinstance(x, dict) and x.get("date")]
    if dates:
        return str(max(dates))

    return datetime.utcnow().strftime("%Y-%m-%d")


def infer_market_week_label(data: Dict[str, Any]) -> str:
    meta = data.get("meta") or {}
    range_data = meta.get("range") or data.get("range") or {}

    end_date = range_data.get("end") or range_data.get("end_date") or data.get("end_date")
    if end_date:
        return str(end_date)

    dates = []
    for item in data.get("series") or []:
        if not isinstance(item, dict):
            continue
        for point in item.get("points") or []:
            if isinstance(point, dict) and point.get("date"):
                dates.append(str(point.get("date")))

    return max(dates) if dates else datetime.utcnow().strftime("%Y-%m-%d")


def build_daily_section(day: Dict[str, Any], index: int) -> str:
    date = safe_text(day.get("date"))
    headline = safe_text(day.get("headline"))
    executive_summary = safe_text(day.get("executive_summary"))
    macro_chain = safe_text(day.get("macro_chain"))
    divergence = safe_text(day.get("divergence"))
    visual_note = safe_text(day.get("visual_note"))
    raw = safe_text(day.get("raw_daily_summary_package"))

    parts = [
        f"## Day {index}｜{date}",
        "",
        "### 今日主線",
        headline or "資料不足",
        "",
        "### Executive Summary",
        executive_summary or "資料不足",
        "",
        "### 今日市場訊號",
        bullet_list(day.get("market_signals")),
        "",
        "### 總經傳導鏈",
        macro_chain or "資料不足",
        "",
        "### 矛盾 / 背離 / 待觀察",
        divergence or "資料不足",
        "",
        "### 市場數據摘要",
        bullet_list(day.get("market_snapshot")),
        "",
        "### 新聞佐證",
        bullet_list(day.get("news_evidence")),
        "",
        "### 待觀察問題",
        bullet_list(day.get("watchpoints")),
    ]

    if visual_note:
        parts.extend(["", "### Visual Note", visual_note])

    if raw:
        parts.extend(["", "### 原始今日總經摘要文字", raw])

    return "\n".join(parts).strip()


def build_weekly_source_text(data: Dict[str, Any]) -> str:
    range_data = data.get("range", {}) or {}
    summaries = data.get("daily_summaries", []) or []

    start_date = safe_text(range_data.get("start_date"))
    end_date = safe_text(range_data.get("end_date"))
    days = safe_text(range_data.get("days") or data.get("days") or len(summaries))
    data_status = safe_text(data.get("data_status"))

    header = [
        "# Weekly Macro Source Text",
        "",
        f"資料來源：{safe_text(data.get('source')) or 'Google Sheets weekly_video_source'}",
        f"產生時間：{safe_text(data.get('generated_at')) or '資料不足'}",
        f"週期：{start_date or '資料不足'} ～ {end_date or '資料不足'}",
        f"資料狀態：{data_status or 'unknown'}",
        f"資料天數：{days}",
        "",
        "這份文件是週報影片的主要來源。請從每日摘要中歸納本週主線、延續訊號、轉折點、背離現象、新聞佐證與下週觀察。",
        "",
        "---",
        "",
    ]

    body = []
    for idx, day in enumerate(summaries, start=1):
        if isinstance(day, dict):
            body.append(build_daily_section(day, idx))
            body.append("\n---\n")

    footer = [
        "## 週報生成任務",
        "",
        "請不要把以上內容逐日照念。請從「森林視角」回答：",
        "",
        "1. 本週市場主線如何形成？",
        "2. 哪些訊號在多個交易日反覆出現？",
        "3. 哪一天或哪個訊號造成轉折？",
        "4. 通膨預期 → 利率 → 美元 → 亞洲貨幣 / 黃金 的傳導鏈是否成立？",
        "5. 哪些地方出現背離或待觀察？",
        "6. 下週最重要的三個驗證問題是什麼？",
        "",
    ]

    return "\n".join(header + body + footer)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", type=str, default=os.getenv("WEEKLY_SOURCE_URL", "").strip())
    parser.add_argument("--start", type=str, default=os.getenv("WEEKLY_SOURCE_START", "").strip())
    parser.add_argument("--end", type=str, default=os.getenv("WEEKLY_SOURCE_END", "").strip())
    args = parser.parse_args()

    if not args.url:
        raise EnvironmentError("Missing WEEKLY_SOURCE_URL. Add your Apps Script deployment URL as a GitHub Actions secret.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1) Fetch daily narrative source from History_Data.
    weekly_url = add_query_params(args.url, {
        "mode": "weekly_video_source",
        "start": args.start,
        "end": args.end,
    })

    print("[INFO] Fetching weekly_video_source JSON from Apps Script endpoint...")
    weekly_data = fetch_json(weekly_url)

    save_json(DATA_DIR / "weekly_video_source.json", weekly_data)
    print(f"[OK] Saved {DATA_DIR / 'weekly_video_source.json'}")

    week_label = infer_week_label(weekly_data)
    week_dir = OUTPUT_WEEKLY_DIR / week_label
    week_dir.mkdir(parents=True, exist_ok=True)

    source_text = build_weekly_source_text(weekly_data)
    source_path = week_dir / "weekly_source_text.md"
    save_text(source_path, source_text)
    print(f"[OK] Saved {source_path}")

    # 2) Fetch market history series from Market_Source_Test.
    market_url = add_query_params(args.url, {
        "mode": "market_history_series",
        "start": args.start,
        "end": args.end,
    })

    print("[INFO] Fetching market_history_series JSON from Apps Script endpoint...")
    market_data = fetch_json(market_url)

    save_json(DATA_DIR / "market_history_series.json", market_data)
    print(f"[OK] Saved {DATA_DIR / 'market_history_series.json'}")

    market_week_label = infer_market_week_label(market_data)
    market_week_dir = OUTPUT_WEEKLY_DIR / market_week_label
    market_week_dir.mkdir(parents=True, exist_ok=True)

    market_path = market_week_dir / "weekly_market_series.json"
    save_json(market_path, market_data)
    print(f"[OK] Saved {market_path}")

    if market_week_label != week_label:
        print(f"[WARN] weekly_video_source week={week_label}, market_history_series week={market_week_label}")


if __name__ == "__main__":
    main()
