#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Weekly Macro Video - Step 07
Build weekly macro video with FFmpeg.

Input:
- output/weekly/YYYY-MM-DD/narration/weekly_narration.json
- output/weekly/YYYY-MM-DD/audio/scene_01.wav ... scene_06.wav
- output/weekly/YYYY-MM-DD/weekly_macro_diagram.png

Output:
- output/weekly/YYYY-MM-DD/video_assets/scene_01.png ... scene_06.png
- output/weekly/YYYY-MM-DD/final/weekly_macro_video.mp4
"""

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"

WIDTH = 1920
HEIGHT = 1080
BG = (248, 250, 252)
WHITE = (255, 255, 255)
NAVY = (15, 42, 68)
ORANGE = (245, 158, 11)
GRAY = (100, 116, 139)


def find_latest_week_dir() -> Path:
    week_dirs = [p for p in OUTPUT_WEEKLY_DIR.iterdir() if p.is_dir()]
    if not week_dirs:
        raise FileNotFoundError("No weekly output folder found under output/weekly/")
    week_dirs.sort(key=lambda p: p.name, reverse=True)
    return week_dirs[0]


def load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def find_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if path and Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> List[str]:
    text = " ".join(str(text or "").split())
    lines: List[str] = []
    current = ""
    for char in text:
        test = current + char
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def rounded(draw: ImageDraw.ImageDraw, xy: Tuple[int, int, int, int], radius: int, fill, outline=None, width: int = 1) -> None:
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def slide_base() -> Image.Image:
    img = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(img)
    draw.ellipse((-220, -220, 760, 360), fill=(255, 243, 209))
    draw.ellipse((1320, -260, 2220, 360), fill=(234, 240, 247))
    return img


def draw_header(draw: ImageDraw.ImageDraw, title: str, subtitle: str = "") -> None:
    small = find_font(28, bold=True)
    title_font = find_font(58, bold=True)
    sub_font = find_font(31)

    draw.text((90, 58), "WEEKLY MACRO SUMMARY", fill=ORANGE, font=small)
    draw.text((90, 102), title, fill=NAVY, font=title_font)

    if subtitle:
        y = 188
        for line in wrap_text(subtitle, sub_font, 1500)[:2]:
            draw.text((90, y), line, fill=GRAY, font=sub_font)
            y += 42


def crop_text(text: str, limit: int) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:limit] + ("…" if len(clean) > limit else "")


def draw_text_card(draw: ImageDraw.ImageDraw, title: str, body: str, x: int, y: int, w: int, h: int) -> None:
    title_font = find_font(46, bold=True)
    body_font = find_font(34)
    rounded(draw, (x, y, x + w, y + h), 36, WHITE, outline=(231, 231, 226), width=2)
    draw.rectangle((x, y, x + 12, y + h), fill=ORANGE)
    draw.text((x + 42, y + 34), title, fill=NAVY, font=title_font)

    ty = y + 116
    for line in wrap_text(body, body_font, w - 90)[:9]:
        draw.text((x + 42, ty), line, fill=(31, 41, 55), font=body_font)
        ty += 52


def render_text_slide(scene: Dict[str, Any], out_path: Path) -> None:
    img = slide_base()
    draw = ImageDraw.Draw(img)
    draw_header(draw, scene.get("scene_title", ""), scene.get("visual_direction", ""))
    draw_text_card(draw, "本段重點", crop_text(scene.get("narration", ""), 360), 190, 335, 1540, 500)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def render_diagram_slide(week_dir: Path, scene: Dict[str, Any], out_path: Path) -> None:
    img = slide_base()
    draw = ImageDraw.Draw(img)
    draw_header(draw, scene.get("scene_title", ""))

    diagram_path = week_dir / "weekly_macro_diagram.png"
    if diagram_path.exists():
        diagram = Image.open(diagram_path).convert("RGB")
        diagram.thumbnail((1500, 760), Image.LANCZOS)
        x = (WIDTH - diagram.width) // 2
        y = 235
        rounded(draw, (x - 18, y - 18, x + diagram.width + 18, y + diagram.height + 18), 34, WHITE, outline=(231, 231, 226), width=2)
        img.paste(diagram, (x, y))
    else:
        draw_text_card(draw, "總經傳導圖解", crop_text(scene.get("narration", ""), 260), 190, 335, 1540, 500)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)


def build_images(week_dir: Path, narration: Dict[str, Any]) -> List[Path]:
    scenes = narration.get("scenes") or []
    assets_dir = week_dir / "video_assets"
    paths: List[Path] = []

    for i, scene in enumerate(scenes, start=1):
        scene_id = scene.get("scene_id") or f"scene_{i:02d}"
        out_path = assets_dir / f"{scene_id}.png"
        if scene_id == "scene_02":
            render_diagram_slide(week_dir, scene, out_path)
        else:
            render_text_slide(scene, out_path)
        paths.append(out_path)

    return paths


def probe_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def build_video(week_dir: Path, image_paths: List[Path], narration: Dict[str, Any]) -> Path:
    scenes = narration.get("scenes") or []
    audio_dir = week_dir / "audio"
    segment_dir = week_dir / "video_segments"
    final_dir = week_dir / "final"
    segment_dir.mkdir(parents=True, exist_ok=True)
    final_dir.mkdir(parents=True, exist_ok=True)

    segments: List[Path] = []

    for scene, image_path in zip(scenes, image_paths):
        scene_id = scene.get("scene_id")
        audio_path = audio_dir / f"{scene_id}.wav"
        if not audio_path.exists():
            raise FileNotFoundError(f"Missing scene audio: {audio_path}")

        duration = max(1.0, probe_duration(audio_path))
        segment_path = segment_dir / f"{scene_id}.mp4"

        subprocess.run(
            [
                "ffmpeg", "-y",
                "-loop", "1",
                "-t", f"{duration:.3f}",
                "-i", str(image_path),
                "-i", str(audio_path),
                "-vf", "scale=1920:1080,format=yuv420p",
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "20",
                "-c:a", "aac",
                "-b:a", "192k",
                "-shortest",
                str(segment_path),
            ],
            check=True,
        )
        segments.append(segment_path)

    concat_file = segment_dir / "concat_list.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in segments), encoding="utf-8")

    out_path = final_dir / "weekly_macro_video.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(out_path)],
        check=True,
    )
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="")
    args = parser.parse_args()

    week_dir = Path(args.week_dir) if args.week_dir else find_latest_week_dir()
    narration = load_json(week_dir / "narration" / "weekly_narration.json")
    if not narration:
        raise FileNotFoundError(f"Missing narration JSON in {week_dir / 'narration'}")

    print("[INFO] Rendering scene images")
    images = build_images(week_dir, narration)

    print("[INFO] Building video")
    out = build_video(week_dir, images, narration)
    print(f"[OK] Created {out}")


if __name__ == "__main__":
    main()
