#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 04 helper - update weekly macro page video block only.

Purpose:
- DO NOT rebuild the whole weekly page.
- Only update / insert the video section inside an existing
  output/weekly/YYYY-MM-DD/index.html.
- Preserve all other page content edited earlier.

Inputs:
- Existing output/weekly/YYYY-MM-DD/index.html
- Existing story video file under the same week folder

Default video candidates:
1) story_video/story_visual_video_test.mp4
2) story_video/story_visual_video.mp4
3) story_video/final_story_video.mp4

Default poster candidates:
1) story_visual_images/scene_01.jpg
2) story_visual_images/scene_01.png
3) story_visual_images/vis_01.jpg
4) story_visual_images/vis_01.png

Usage:
  python scripts/04_update_weekly_page_video_only.py --week-dir output/weekly/2026-07-09
"""

from __future__ import annotations

import argparse
import html
import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

VIDEO_MARKER_START = "<!-- WEEKLY_VIDEO_SECTION_START -->"
VIDEO_MARKER_END = "<!-- WEEKLY_VIDEO_SECTION_END -->"

VIDEO_CANDIDATES = [
    "story_video/story_visual_video_test.mp4",
    "story_video/story_visual_video.mp4",
    "story_video/final_story_video.mp4",
]

POSTER_CANDIDATES = [
    "story_visual_images/scene_01.jpg",
    "story_visual_images/scene_01.png",
    "story_visual_images/vis_01.jpg",
    "story_visual_images/vis_01.png",
]


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def find_first_existing(base_dir: Path, candidates: list[str]) -> Path | None:
    for rel in candidates:
        path = base_dir / rel
        if path.exists():
            return path
    return None


def rel_url(from_dir: Path, to_path: Path) -> str:
    return to_path.relative_to(from_dir).as_posix() if to_path.is_relative_to(from_dir) else to_path.relative_to(from_dir).as_posix()


def build_video_section(video_src: str, poster_src: str | None, video_name: str) -> str:
    poster_attr = f' poster="{html.escape(poster_src)}"' if poster_src else ""
    poster_hint = (
        f'<div style="font-size:12px;color:#6b7280;margin-top:10px;">封面：{html.escape(poster_src)}</div>'
        if poster_src
        else ""
    )
    return f"""
{VIDEO_MARKER_START}
<section id="weekly-story-video" style="margin:24px 0 32px 0;">
  <div style="background:#fff;border:1px solid #e5e7eb;border-radius:24px;padding:20px 20px 16px 20px;box-shadow:0 10px 30px rgba(15,23,42,0.04);">
    <div style="display:flex;align-items:center;gap:10px;margin-bottom:14px;">
      <span style="display:inline-block;width:6px;height:28px;border-radius:999px;background:#f59e0b;"></span>
      <h2 style="margin:0;font-size:32px;line-height:1.2;color:#0f2945;font-weight:800;">本週總經影片</h2>
    </div>
    <div style="background:#0b1220;border-radius:20px;overflow:hidden;">
      <video controls playsinline preload="metadata" style="display:block;width:100%;height:auto;background:#000;"{poster_attr}>
        <source src="{html.escape(video_src)}" type="video/mp4">
        您的瀏覽器不支援影片播放，請改用
        <a href="{html.escape(video_src)}">直接開啟影片</a>。
      </video>
    </div>
    <div style="font-size:13px;color:#64748b;margin-top:10px;word-break:break-all;">
      影片來源：{html.escape(video_name)}
    </div>
    {poster_hint}
  </div>
</section>
{VIDEO_MARKER_END}
""".strip()


def replace_marked_block(html_text: str, section_html: str) -> str | None:
    pattern = re.compile(
        re.escape(VIDEO_MARKER_START) + r".*?" + re.escape(VIDEO_MARKER_END),
        flags=re.DOTALL,
    )
    if pattern.search(html_text):
        return pattern.sub(section_html, html_text, count=1)
    return None


def replace_known_video_section(html_text: str, section_html: str) -> str | None:
    patterns = [
        r"<section[^>]*id=[\"']weekly-story-video[\"'][^>]*>.*?</section>",
        r"<section[^>]*>.*?本週總經影片.*?</section>",
        r"<section[^>]*>.*?本週影片尚未產生.*?</section>",
    ]
    for raw in patterns:
        pattern = re.compile(raw, flags=re.DOTALL)
        if pattern.search(html_text):
            return pattern.sub(section_html, html_text, count=1)
    return None


def insert_video_section(html_text: str, section_html: str) -> str:
    insertion_patterns = [
        r"(<main[^>]*>)",
        r"(</header>)",
        r"(<body[^>]*>)",
    ]
    for raw in insertion_patterns:
        pattern = re.compile(raw, flags=re.DOTALL | re.IGNORECASE)
        match = pattern.search(html_text)
        if match:
            end = match.end(1)
            return html_text[:end] + "\n" + section_html + "\n" + html_text[end:]

    return section_html + "\n" + html_text


def update_html_video_only(index_path: Path, week_dir: Path) -> None:
    if not index_path.exists():
        raise FileNotFoundError(f"Weekly page not found: {index_path}")

    video_path = find_first_existing(week_dir, VIDEO_CANDIDATES)
    if not video_path:
        raise FileNotFoundError(
            "No story video found under week dir. Expected one of: " + ", ".join(VIDEO_CANDIDATES)
        )

    poster_path = find_first_existing(week_dir, POSTER_CANDIDATES)

    index_dir = index_path.parent
    video_src = video_path.relative_to(index_dir).as_posix()
    poster_src = poster_path.relative_to(index_dir).as_posix() if poster_path else None
    section_html = build_video_section(video_src, poster_src, video_path.name)

    original = index_path.read_text(encoding="utf-8")

    updated = replace_marked_block(original, section_html)
    if updated is None:
        updated = replace_known_video_section(original, section_html)
    if updated is None:
        updated = insert_video_section(original, section_html)

    index_path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    index_path = week_dir / "index.html"

    update_html_video_only(index_path=index_path, week_dir=week_dir)
    print(f"[OK] Updated weekly page video section only: {index_path}")


if __name__ == "__main__":
    main()
