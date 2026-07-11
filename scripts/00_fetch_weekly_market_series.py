#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Summary Page - Fetch Weekly Market Series

Purpose:
- Fetch market history series from Google Apps Script endpoint.
- Save the result for the weekly macro page chart section.
- Support custom analysis window by passing start/end to the Apps Script endpoint.
- Build display-only derived cross-rate series before the webpage step.

Derived series:
- JPY/TWD = USD/TWD ÷ USD/JPY
- Meaning: how many New Taiwan dollars one Japanese yen can exchange for.
- Only dates available in both USD/TWD and USD/JPY are used.
- Derived series are stored under top-level `derived_series`, not `series`,
  so V35 / Step 01 / Step 80 continue to use only original market series.

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
from typing import Any, Dict, List, Optional, Tuple


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


SOURCE_KEY_ALIASES = {
    "USDJPY": {
        "USDJPY",
        "USD/JPY",
        "USDJPY=X",
        "美元/日圓",
        "美元／日圓",
    },
    "USDTWD": {
        "USDTWD",
        "USD/TWD",
        "USDTWD=X",
        "美元/台幣",
        "美元／台幣",
        "美元/新台幣",
        "美元／新台幣",
    },
}


DERIVED_KEY = "JPYTWD"
DERIVED_FORMULA = "USDTWD / USDJPY"


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


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


def normalize_token(value: Any) -> str:
    return str(value or "").strip().upper().replace(" ", "").replace("／", "/")


def identify_source_key(item: Dict[str, Any]) -> str:
    """Identify USDJPY / USDTWD without broad substring matching."""
    exact_fields = (
        item.get("asset_key"),
        item.get("key"),
        item.get("symbol"),
        item.get("ticker"),
    )

    alias_lookup: Dict[str, str] = {}
    for canonical, aliases in SOURCE_KEY_ALIASES.items():
        alias_lookup[normalize_token(canonical)] = canonical
        for alias in aliases:
            alias_lookup[normalize_token(alias)] = canonical

    for value in exact_fields:
        token = normalize_token(value)
        if token in alias_lookup:
            return alias_lookup[token]

    human_fields = (
        item.get("asset"),
        item.get("name"),
        item.get("label"),
        item.get("title"),
    )
    human_text = "|".join(normalize_token(value) for value in human_fields if value)

    for canonical, aliases in SOURCE_KEY_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            token = normalize_token(alias)
            if token and token in human_text:
                return canonical

    return ""


def find_source_series(series: List[Any], target_key: str) -> Optional[Dict[str, Any]]:
    for item in series:
        if not isinstance(item, dict):
            continue
        if identify_source_key(item) == target_key:
            return item
    return None


def to_float(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    if number in (float("inf"), float("-inf")):
        return None
    return number


def points_by_date(item: Dict[str, Any]) -> Dict[str, float]:
    """Build date -> value map. Invalid points are ignored."""
    result: Dict[str, float] = {}
    points = item.get("points")
    if not isinstance(points, list):
        return result

    for point in points:
        if not isinstance(point, dict):
            continue

        date_text = str(point.get("date") or "").strip()
        value = to_float(point.get("value"))

        if not date_text or value is None:
            continue

        result[date_text] = value

    return result


def build_jpytwd_derived_series(series: List[Any]) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    Build JPY/TWD from same-date USD/TWD and USD/JPY observations.

    Formula:
        JPY/TWD = USD/TWD / USD/JPY

    The result is display-only and intentionally kept outside the original
    `series` list to avoid changing V35 / Step 01 / Step 80 analysis inputs.
    """
    usd_jpy = find_source_series(series, "USDJPY")
    usd_twd = find_source_series(series, "USDTWD")

    status: Dict[str, Any] = {
        "asset_key": DERIVED_KEY,
        "formula": DERIVED_FORMULA,
        "status": "not_created",
        "usd_jpy_found": bool(usd_jpy),
        "usd_twd_found": bool(usd_twd),
        "usd_jpy_points": 0,
        "usd_twd_points": 0,
        "common_date_points": 0,
    }

    if not usd_jpy or not usd_twd:
        missing = []
        if not usd_jpy:
            missing.append("USDJPY")
        if not usd_twd:
            missing.append("USDTWD")
        status["reason"] = "Missing source series: " + ", ".join(missing)
        return None, status

    usd_jpy_map = points_by_date(usd_jpy)
    usd_twd_map = points_by_date(usd_twd)

    status["usd_jpy_points"] = len(usd_jpy_map)
    status["usd_twd_points"] = len(usd_twd_map)

    common_dates = sorted(set(usd_jpy_map) & set(usd_twd_map))
    derived_points: List[Dict[str, Any]] = []

    for date_text in common_dates:
        usd_jpy_value = usd_jpy_map[date_text]
        usd_twd_value = usd_twd_map[date_text]

        if usd_jpy_value == 0:
            continue

        jpytwd_value = usd_twd_value / usd_jpy_value
        derived_points.append({
            "date": date_text,
            "value": round(jpytwd_value, 8),
        })

    status["common_date_points"] = len(derived_points)

    if not derived_points:
        status["reason"] = "No valid common-date observations between USDJPY and USDTWD."
        return None, status

    status["status"] = "created"

    derived_series: Dict[str, Any] = {
        "asset_key": DERIVED_KEY,
        "key": DERIVED_KEY,
        "asset": "日圓／台幣",
        "name": "日圓／台幣",
        "label": "日圓／台幣",
        "symbol": "JPYTWD_DERIVED",
        "unit": "TWD per JPY",
        "decimals": 4,
        "derived": True,
        "display_only": True,
        "include_in_diagnosis": False,
        "source": "Calculated from same-date USD/TWD and USD/JPY observations",
        "formula": DERIVED_FORMULA,
        "meaning": "1 Japanese yen expressed in New Taiwan dollars",
        "points": derived_points,
    }

    return derived_series, status


def upsert_derived_series(data: Dict[str, Any]) -> None:
    """Create or replace JPYTWD in top-level `derived_series`."""
    source_series = data.get("series")
    if not isinstance(source_series, list):
        return

    derived_item, status = build_jpytwd_derived_series(source_series)

    existing = data.get("derived_series")
    if not isinstance(existing, list):
        existing = []

    # Keep unrelated derived series, but replace the prior JPYTWD result.
    kept: List[Any] = []
    for item in existing:
        if not isinstance(item, dict):
            kept.append(item)
            continue
        item_key = normalize_token(item.get("asset_key") or item.get("key"))
        if item_key != DERIVED_KEY:
            kept.append(item)

    if derived_item is not None:
        kept.append(derived_item)

    data["derived_series"] = kept

    meta = data.get("meta")
    if not isinstance(meta, dict):
        meta = {}
        data["meta"] = meta

    derived_meta = meta.get("derived_series")
    if not isinstance(derived_meta, dict):
        derived_meta = {}
        meta["derived_series"] = derived_meta

    derived_meta[DERIVED_KEY] = status

    if derived_item is not None:
        print(
            "[OK] Created display-only derived series JPYTWD: "
            f"{status['common_date_points']} common-date points "
            f"({DERIVED_FORMULA})"
        )
    else:
        print(f"[WARN] JPYTWD derived series was not created: {status.get('reason', 'unknown reason')}")


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

    # Build display-only cross-rate data before saving the market payload.
    # The result is stored under `derived_series`, leaving original `series`
    # untouched for V35 and other analysis steps.
    upsert_derived_series(data)

    save_json(DATA_DIR / "weekly_market_series.json", data)
    save_json(week_dir / "weekly_market_series.json", data)

    print(f"[OK] Saved {DATA_DIR / 'weekly_market_series.json'}")
    print(f"[OK] Saved {week_dir / 'weekly_market_series.json'}")


if __name__ == "__main__":
    main()
