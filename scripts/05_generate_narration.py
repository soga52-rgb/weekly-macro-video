#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Weekly Macro Video Engine V4 - Step 05
Generate six narration scripts from weekly_video_brief.json.

Input:
- output/weekly/YYYY-MM-DD/weekly_video_brief.json

Output:
- output/weekly/YYYY-MM-DD/narration/scene_01.txt ~ scene_06.txt
- output/weekly/YYYY-MM-DD/weekly_narration.json
"""

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def clean_step(step: str) -> str:
    return str(step).strip().lstrip("1234567890.、 ")


def build_scripts(brief: Dict[str, Any]) -> List[Dict[str, str]]:
    es = brief.get("executive_summary", {})
    signals = brief.get("market_signals", [])
    chain = brief.get("macro_chain", {})
    evidence = brief.get("news_evidence", {})
    steps = [clean_step(s) for s in brief.get("transmission_steps", [])]
    key_question = brief.get("key_question", "")
    next_week = brief.get("next_week_watch", {})
    watchpoints = next_week.get("watchpoints", [])

    signal_text = "、".join([f"{s.get('label', '')}" for s in signals[:3] if s.get("label")])
    step_text = "，接著".join(steps[:5])
    watch_text = "、".join(watchpoints[:3])

    scripts = [
        {
            "scene_id": "scene_01",
            "title": "Executive Summary",
            "script": (
                f"本週週報先看主線：{es.get('headline', '')}。"
                f"{es.get('summary', '')}"
                f"這代表市場不是只有單一方向，而是在利率、美元、能源與避險需求之間重新定價。"
                f"接下來，我們先用三個市場訊號，拆解本週的主要變化。"
            ),
        },
        {
            "scene_id": "scene_02",
            "title": "Market Signals",
            "script": (
                f"本週最重要的三個市場訊號是：{signal_text}。"
                + "".join([f"{s.get('label', '')}，{s.get('meaning', '')}。" for s in signals[:3]])
                + "這三個訊號合在一起，形成了本週總經傳導的起點。下一步要看的是，這些訊號如何連成一條傳導鏈。"
            ),
        },
        {
            "scene_id": "scene_03",
            "title": "Macro Chain",
            "script": (
                f"本週的總經傳導鏈可以濃縮成一句話：{chain.get('title', '')}。"
                f"{chain.get('explanation', '')}"
                f"換句話說，市場一方面看到偏緊訊號，另一方面又看到需求降溫，這讓通膨與利率判斷不再是單線條。"
                f"所以接下來要檢查，有沒有新聞或數據支持這條傳導鏈。"
            ),
        },
        {
            "scene_id": "scene_04",
            "title": "News Evidence",
            "script": (
                f"新聞佐證方面，本週可觀察的重點是：{evidence.get('title', '')}。"
                f"{evidence.get('summary', '')}"
                f"如果新聞佐證明確，這條傳導鏈的可信度就會提高；如果佐證不足，就要把它列為待觀察。"
                f"接下來，我們把整條邏輯拆成五個步驟。"
            ),
        },
        {
            "scene_id": "scene_05",
            "title": "Transmission Steps",
            "script": (
                f"把本週市場反應拆成五步來看：{step_text}。"
                f"這五步說明，本週不是只有美元或利率單獨走強，而是能源、政策訊號、利率、匯率與避險資產互相牽動。"
                f"最後，要把焦點放到下週，看看這條傳導是否延續。"
            ),
        },
        {
            "scene_id": "scene_06",
            "title": "Next Week Watch",
            "script": (
                f"下週最重要的問題是：{key_question}"
                f"觀察重點包括：{watch_text}。"
                f"如果這些條件延續，本週的傳導鏈可能持續；如果其中一項反轉，就可能出現新的市場背離。"
                f"以上就是本週 Weekly Macro Video，我們下週再繼續追蹤。"
            ),
        },
    ]

    return scripts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--brief-file", type=str, default="weekly_video_brief.json")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    brief = load_json(week_dir / args.brief_file)
    scripts = build_scripts(brief)

    out_dir = week_dir / "narration"
    out_dir.mkdir(parents=True, exist_ok=True)

    for idx, item in enumerate(scripts, start=1):
        path = out_dir / f"scene_{idx:02d}.txt"
        save_text(path, item["script"])
        print(f"[OK] Created {path}")

    package = {
        "source_brief": str(week_dir / args.brief_file),
        "scenes": scripts,
    }
    save_json(week_dir / "weekly_narration.json", package)
    print(f"[OK] Created {week_dir / 'weekly_narration.json'}")


if __name__ == "__main__":
    main()
