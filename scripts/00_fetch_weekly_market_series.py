#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Fetch Weekly Market Series

Purpose:
- Fetch market history series from Google Apps Script endpoint.
- Save the result for the weekly macro page chart section.
- Support custom analysis window by passing start/end to the Apps Script endpoint.

Required env:
- WEEKLY_MARKET_SERIES_URL

Optional env / CLI:
- ANALYSIS_START_DATE / --start = YYYY-MM-DD
- ANALYSIS_END_DATE   / --end   = YYYY-MM-DD

Output:
- data/weekly_market_series.json
- output/weekly/YYYY-MM-DD/weekly_market_series.json
"""

import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


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


def add_query_params(url: str, params: Dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query))

    for key, value in params.items():
        value = (value or "").strip()
        if value:
            query[key] = value

    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def fetch_json(url: str) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "weekly-macro-page-market-series/1.0",
            "Accept": "application/json,text/plain,*/*",
        },
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Market series HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Market series URLError: {exc}") from exc

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        preview = raw[:1000]
        raise RuntimeError(f"Market series endpoint did not return valid JSON. Preview: {preview}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("Market series endpoint JSON root must be an object.")

    if "series" not in data or not isinstance(data["series"], list):
        raise RuntimeError("Market series JSON must contain a list field: series")

    return data


def resolve_week_dir(week_dir_arg: str) -> Path:
    week_dir_arg = (week_dir_arg or "").strip()
    if not week_dir_arg:
        return find_latest_week_dir()

    raw = Path(week_dir_arg)
    if raw.is_absolute():
        return raw

    if len(week_dir_arg) == 10 and week_dir_arg[4] == "-" and week_dir_arg[7] == "-":
        return OUTPUT_WEEKLY_DIR / week_dir_arg

    return ROOT_DIR / raw


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--start", type=str, default=os.getenv("ANALYSIS_START_DATE", "").strip())
    parser.add_argument("--end", type=str, default=os.getenv("ANALYSIS_END_DATE", "").strip())
    args = parser.parse_args()

    url = os.getenv("WEEKLY_MARKET_SERIES_URL", "").strip()
    if not url:
        raise EnvironmentError("Missing WEEKLY_MARKET_SERIES_URL.")

    week_dir = resolve_week_dir(args.week_dir)

    fetch_url = add_query_params(url, {
        "start": args.start,
        "end": args.end,
    })

    print("[INFO] Fetching weekly market series from Apps Script endpoint")
    if args.start or args.end:
        print(f"[INFO] Requested market series window: {args.start or '(default start)'} ～ {args.end or '(default end)'}")
    print(f"[INFO] Output week dir: {week_dir}")

    data = fetch_json(fetch_url)

    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        data["meta"] = meta

    meta["requested_analysis_window"] = {
        "start_date": args.start,
        "end_date": args.end,
        "source": "workflow_env_or_cli",
    }

    save_json(DATA_DIR / "weekly_market_series.json", data)
    save_json(week_dir / "weekly_market_series.json", data)

    print(f"[OK] Saved {DATA_DIR / 'weekly_market_series.json'}")
    print(f"[OK] Saved {week_dir / 'weekly_market_series.json'}")


if __name__ == "__main__":
    main()
