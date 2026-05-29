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
- TODAY_DAILY_SOURCE_URL = optional separate endpoint for today's daily summary JSON
- WEEKLY_INCLUDE_TODAY_SOURCE = true / false, default true

Output:
- data/weekly_video_source.json
- output/weekly/YYYY-MM-DD/weekly_source_text.md

Update:
- Fetch mode=weekly_video_source first.
- Then fetch TODAY_DAILY_SOURCE_URL if provided.
- If TODAY_DAILY_SOURCE_URL is not provided, fall back to mode=today_daily_source from the same Apps Script endpoint.
- If today's daily_summary.date is missing from daily_summaries, append it.
- De-duplicate by date and sort by date, so weekly history no longer misses the newest day.
"""

import argparse
import json
import os
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


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


def parse_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default

    text = str(value).strip().lower()
    if not text:
        return default

    return text in {"1", "true", "yes", "y", "on"}


def date_in_requested_range(date_text: str, start: str = "", end: str = "") -> bool:
    if not date_text:
        return False
    if start and date_text < start:
        return False
    if end and date_text > end:
        return False
    return True


def normalize_today_daily_source(today_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert mode=today_daily_source response into one daily_summaries item.

    Expected shape:
    {
      "mode": "today_daily_source",
      "daily_summary": {...},
      "visual_note": {...},
      "news_narrative": {...}
    }
    """
    if not isinstance(today_data, dict):
        return None

    day = today_data.get("daily_summary")
    if not isinstance(day, dict):
        return None

    normalized = dict(day)

    # Preserve root-level data for downstream use / traceability.
    for key in [
        "visual_note",
        "news_narrative",
        "generated_at",
        "source",
        "mode",
        "data_status",
    ]:
        value = today_data.get(key)
        if value is not None and key not in normalized:
            normalized[key] = value

    return normalized if normalized.get("date") else None


def merge_today_daily_source(
    weekly_data: Dict[str, Any],
    today_data: Dict[str, Any],
    start: str = "",
    end: str = "",
) -> Dict[str, Any]:
    """
    Merge today_daily_source into weekly_video_source without duplicating dates.

    Rules:
    - If today_daily_source.daily_summary.date is inside the requested date range
      and missing from weekly_data.daily_summaries, append it.
    - If the same date already exists, keep the existing historical item.
    - Sort by date after merge.
    """
    today_summary = normalize_today_daily_source(today_data)
    if not today_summary:
        print("[INFO] today_daily_source has no usable daily_summary; skip merge.")
        return weekly_data

    today_date = str(today_summary.get("date", "")).strip()
    if not date_in_requested_range(today_date, start, end):
        print(f"[INFO] today_daily_source date {today_date} outside requested range; skip merge.")
        return weekly_data

    summaries = weekly_data.get("daily_summaries")
    if not isinstance(summaries, list):
        summaries = []

    by_date: Dict[str, Dict[str, Any]] = {}
    undated_items = []

    for item in summaries:
        if not isinstance(item, dict):
            continue

        item_date = str(item.get("date", "")).strip()
        if item_date:
            by_date[item_date] = item
        else:
            undated_items.append(item)

    if today_date in by_date:
        print(f"[INFO] today_daily_source date {today_date} already exists in weekly history; no append.")
    else:
        print(f"[INFO] Appending today_daily_source date {today_date} into weekly daily_summaries.")
        by_date[today_date] = today_summary

    merged = [by_date[d] for d in sorted(by_date.keys())]
    if undated_items:
        merged = undated_items + merged

    weekly_data["daily_summaries"] = merged

    range_data = weekly_data.get("range")
    if not isinstance(range_data, dict):
        range_data = {}
        weekly_data["range"] = range_data

    dated = [str(x.get("date")) for x in merged if isinstance(x, dict) and x.get("date")]
    if dated:
        range_data["start_date"] = min(dated)
        range_data["end_date"] = max(dated)
        range_data["days"] = len(dated)
        weekly_data["days"] = len(dated)
        weekly_data["end_date"] = max(dated)

    weekly_data["today_daily_source_merged"] = {
        "date": today_date,
        "included": today_date in {str(x.get("date")) for x in merged if isinstance(x, dict)},
        "source_mode": today_data.get("mode"),
        "source_generated_at": today_data.get("generated_at"),
    }

    return weekly_data


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
    parser.add_argument("--today-url", type=str, default=os.getenv("TODAY_DAILY_SOURCE_URL", "").strip())
    parser.add_argument("--start", type=str, default=os.getenv("WEEKLY_SOURCE_START", "").strip())
    parser.add_argument("--end", type=str, default=os.getenv("WEEKLY_SOURCE_END", "").strip())
    parser.add_argument(
        "--include-today-source",
        action=argparse.BooleanOptionalAction,
        default=parse_bool(os.getenv("WEEKLY_INCLUDE_TODAY_SOURCE"), True),
        help="Fetch mode=today_daily_source and append it if weekly history does not contain today's date.",
    )
    args = parser.parse_args()

    if not args.url:
        raise EnvironmentError("Missing WEEKLY_SOURCE_URL. Add your Apps Script deployment URL as a GitHub Actions secret.")

    weekly_url = add_query_params(args.url, {
        "mode": "weekly_video_source",
        "start": args.start,
        "end": args.end,
    })

    print("[INFO] Fetching weekly source JSON from Apps Script endpoint...")
    data = fetch_json(weekly_url)

    if args.include_today_source:
        if args.today_url:
            today_url = args.today_url
            print("[INFO] Fetching today_daily_source JSON from TODAY_DAILY_SOURCE_URL...")
        else:
            today_url = add_query_params(args.url, {
                "mode": "today_daily_source",
            })
            print("[INFO] Fetching today_daily_source JSON from WEEKLY_SOURCE_URL mode=today_daily_source...")

        try:
            today_data = fetch_json(today_url)
            data = merge_today_daily_source(data, today_data, start=args.start, end=args.end)
        except Exception as exc:
            # Do not fail the weekly workflow if today's endpoint is temporarily unavailable.
            print(f"[WARN] Failed to merge today_daily_source: {exc}")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    save_json(DATA_DIR / "weekly_video_source.json", data)
    print(f"[OK] Saved {DATA_DIR / 'weekly_video_source.json'}")

    week_label = infer_week_label(data)
    week_dir = OUTPUT_WEEKLY_DIR / week_label
    week_dir.mkdir(parents=True, exist_ok=True)

    source_text = build_weekly_source_text(data)
    source_path = week_dir / "weekly_source_text.md"
    save_text(source_path, source_text)

    print(f"[OK] Saved {source_path}")


if __name__ == "__main__":
    main()
