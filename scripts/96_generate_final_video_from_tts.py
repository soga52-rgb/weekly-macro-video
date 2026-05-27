#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
96 Generate Final Video From TTS

Purpose:
- Compose final weekly macro video from existing Step 92/94/95 outputs.
- Do NOT regenerate script.
- Do NOT regenerate TTS.
- Use tts_audio_manifest.json as the deterministic timeline.
- Show current scene image, active speaker avatar, and dialogue subtitles.

Inputs:
- output/weekly/YYYY-MM-DD/video_dialogue_script.json
- output/weekly/YYYY-MM-DD/tts_audio_manifest.json
- output/weekly/YYYY-MM-DD/tts_audio/full_dialogue.wav
- output/weekly/YYYY-MM-DD/visual_sequence_images/scene_XX.png
- assets/tom.png optional
- assets/miranda.png optional

Outputs:
- output/weekly/YYYY-MM-DD/final/weekly_macro_video.mp4
- output/weekly/YYYY-MM-DD/final/video_composition_manifest.json
"""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps


ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_WEEKLY_DIR = ROOT_DIR / "output" / "weekly"
ASSETS_DIR = ROOT_DIR / "assets"

VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
FPS = 30

OUTER_MARGIN = 28
MAIN_TOP = 24
MAIN_HEIGHT = 520
SUBTITLE_TOP = 570
SUBTITLE_HEIGHT = 150
AVATAR_SIZE = 92

BG_DARK = (10, 14, 28)
TEXT_WHITE = (245, 247, 250)
TOM_GLOW = (56, 189, 248)
MIRANDA_GLOW = (168, 85, 247)


def parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


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


def resolve_week_dir(week_dir_arg: str) -> Path:
    if week_dir_arg:
        p = Path(week_dir_arg)
        if p.exists():
            return p
        candidate = OUTPUT_WEEKLY_DIR / week_dir_arg
        if candidate.exists():
            return candidate
        raise FileNotFoundError(f"Week folder not found: {week_dir_arg}")
    return find_latest_week_dir()


def find_font(size: int, bold: bool = False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
        "msjhbd.ttc" if bold else "msjh.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_TITLE = find_font(28, bold=True)
FONT_SUBTITLE = find_font(35, bold=True)
FONT_SPEAKER = find_font(24, bold=True)
FONT_SMALL = find_font(19, bold=False)


def run_cmd(cmd: List[str]) -> None:
    print("[CMD]", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    try:
        out = subprocess.check_output([
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ])
        return float(out.decode("utf-8").strip())
    except Exception:
        return 0.0


def safe_rel(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base)).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def find_scene_image(week_dir: Path, scene_id: str) -> Optional[Path]:
    image_dir = week_dir / "visual_sequence_images"
    for ext in [".png", ".jpg", ".jpeg", ".webp"]:
        for candidate in [image_dir / f"{scene_id}{ext}", week_dir / f"{scene_id}{ext}"]:
            if candidate.exists():
                return candidate

    if image_dir.exists():
        for p in sorted(image_dir.iterdir()):
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and p.stem == scene_id:
                return p
    return None


def make_background(scene_image: Image.Image) -> Image.Image:
    bg = ImageOps.fit(scene_image.convert("RGB"), (VIDEO_WIDTH, VIDEO_HEIGHT))
    bg = bg.filter(ImageFilter.GaussianBlur(radius=18))
    bg = ImageEnhance.Brightness(bg).enhance(0.35)
    overlay = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), BG_DARK)
    return Image.blend(bg, overlay, alpha=0.35)


def paste_main_scene(canvas: Image.Image, scene_image: Image.Image) -> None:
    max_w = VIDEO_WIDTH - OUTER_MARGIN * 2
    max_h = MAIN_HEIGHT

    img = scene_image.convert("RGB")
    img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

    x = (VIDEO_WIDTH - img.width) // 2
    y = MAIN_TOP + (MAIN_HEIGHT - img.height) // 2

    shadow = Image.new("RGBA", (img.width + 18, img.height + 18), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((9, 9, img.width + 9, img.height + 9), radius=20, fill=(0, 0, 0, 110))
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=8))
    canvas.paste(shadow.convert("RGB"), (x - 9, y - 9), shadow)

    rounded = Image.new("RGBA", img.size, (0, 0, 0, 0))
    mask = Image.new("L", img.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle((0, 0, img.width, img.height), radius=18, fill=255)
    rounded.paste(img.convert("RGBA"), (0, 0), mask)
    canvas.paste(rounded.convert("RGB"), (x, y), rounded)


def make_circle_avatar(path: Path, speaker: str, size: int) -> Image.Image:
    if path.exists():
        img = Image.open(path).convert("RGB")
        img = ImageOps.fit(img, (size, size), method=Image.Resampling.LANCZOS)
    else:
        img = Image.new("RGB", (size, size), (30, 41, 59))
        d = ImageDraw.Draw(img)
        letter = "T" if speaker == "Tom" else "M"
        font = find_font(46, bold=True)
        bbox = d.textbbox((0, 0), letter, font=font)
        d.text(((size - (bbox[2] - bbox[0])) / 2, (size - (bbox[3] - bbox[1])) / 2 - 4), letter, font=font, fill=TEXT_WHITE)

    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    md.ellipse((0, 0, size, size), fill=255)

    result = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    result.paste(img.convert("RGBA"), (0, 0), mask)
    return result


def paste_avatar(canvas: Image.Image, speaker: str) -> None:
    avatar_path = ASSETS_DIR / ("tom.png" if speaker == "Tom" else "miranda.png")
    glow_color = TOM_GLOW if speaker == "Tom" else MIRANDA_GLOW

    avatar = make_circle_avatar(avatar_path, speaker, AVATAR_SIZE)
    x = 36
    y = SUBTITLE_TOP + 28

    layer = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for pad, alpha in [(16, 36), (10, 80), (5, 150)]:
        d.ellipse((x - pad, y - pad, x + AVATAR_SIZE + pad, y + AVATAR_SIZE + pad), fill=(*glow_color, alpha))

    layer.paste(avatar, (x, y), avatar)

    label_w = 126
    label_h = 32
    label_x = x - 17
    label_y = y + AVATAR_SIZE - 4
    d.rounded_rectangle((label_x, label_y, label_x + label_w, label_y + label_h), radius=12, fill=(*glow_color, 220))
    d.text((label_x + 22, label_y + 3), speaker, font=FONT_SPEAKER, fill=TEXT_WHITE)

    canvas.paste(layer.convert("RGB"), (0, 0), layer)


def wrap_cjk_text(text: str, chars_per_line: int = 31, max_lines: int = 2) -> List[str]:
    cleaned = " ".join((text or "").replace("\n", " ").split())
    if not cleaned:
        return [""]

    lines = []
    current = ""
    for ch in cleaned:
        current += ch
        if len(current) >= chars_per_line:
            lines.append(current)
            current = ""
            if len(lines) >= max_lines:
                break
    if current and len(lines) < max_lines:
        lines.append(current)

    return lines or [cleaned[:chars_per_line]]


def draw_subtitle_band(canvas: Image.Image, speaker: str, text: str, scene_title: str) -> None:
    layer = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    for i in range(SUBTITLE_HEIGHT):
        alpha = int(80 + 150 * (i / max(1, SUBTITLE_HEIGHT - 1)))
        y = SUBTITLE_TOP + i
        d.line((0, y, VIDEO_WIDTH, y), fill=(8, 13, 27, alpha))

    accent = TOM_GLOW if speaker == "Tom" else MIRANDA_GLOW
    d.rectangle((0, SUBTITLE_TOP, VIDEO_WIDTH, SUBTITLE_TOP + 4), fill=(*accent, 220))
    d.text((170, SUBTITLE_TOP + 16), f"{speaker}｜{'主持人' if speaker == 'Tom' else '總經策略師'}", font=FONT_SMALL, fill=(*accent, 255))
    if scene_title:
        d.text((VIDEO_WIDTH - 520, SUBTITLE_TOP + 16), scene_title[:28], font=FONT_SMALL, fill=(210, 218, 230, 210))

    canvas.paste(layer.convert("RGB"), (0, 0), layer)

    d2 = ImageDraw.Draw(canvas)
    lines = wrap_cjk_text(text, chars_per_line=31, max_lines=2)
    y = SUBTITLE_TOP + 52
    for line in lines:
        d2.text((170, y), line, font=FONT_SUBTITLE, fill=TEXT_WHITE, stroke_width=2, stroke_fill=(0, 0, 0))
        y += 45


def split_text_chunks(text: str, chars_per_chunk: int) -> List[str]:
    cleaned = " ".join((text or "").replace("\n", " ").split())
    if not cleaned:
        return [""]
    return [cleaned[i:i + chars_per_chunk] for i in range(0, len(cleaned), chars_per_chunk)]


def create_frame(output_path: Path, scene_image_path: Path, speaker: str, subtitle_text: str, scene_title: str) -> None:
    scene_image = Image.open(scene_image_path)
    canvas = make_background(scene_image)
    paste_main_scene(canvas, scene_image)
    draw_subtitle_band(canvas, speaker, subtitle_text, scene_title)
    paste_avatar(canvas, speaker)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, quality=92)


def build_timeline_frames(
    week_dir: Path,
    manifest: Dict[str, Any],
    subtitle_source: str,
    chars_per_chunk: int,
    min_chunk_seconds: float,
    frames_dir: Path,
) -> Tuple[List[Tuple[Path, float]], Dict[str, Any]]:
    turns = manifest.get("turns", [])
    if not isinstance(turns, list) or not turns:
        raise ValueError("tts_audio_manifest.json has no turns.")

    frame_items: List[Tuple[Path, float]] = []
    scene_missing: List[str] = []
    total_duration = 0.0

    for turn_index, turn in enumerate(turns, start=1):
        scene_id = str(turn.get("scene_id", ""))
        speaker = str(turn.get("speaker", "Tom"))
        scene_title = str(turn.get("screen_title", ""))
        duration = float(turn.get("duration_seconds") or turn.get("estimated_seconds") or 5.0)

        scene_image = find_scene_image(week_dir, scene_id)
        if not scene_image:
            scene_missing.append(scene_id)
            fallback = frames_dir / f"fallback_{scene_id}.png"
            Image.new("RGB", (VIDEO_WIDTH, 520), (238, 232, 216)).save(fallback)
            scene_image = fallback

        if subtitle_source == "subtitle":
            text = str(turn.get("subtitle_text") or turn.get("spoken_text") or "")
            chunks = [text]
        else:
            text = str(turn.get("spoken_text") or turn.get("subtitle_text") or "")
            chunks = split_text_chunks(text, chars_per_chunk=chars_per_chunk)

        total_chars = max(1, sum(len(c) for c in chunks))
        remaining = duration

        for chunk_index, chunk in enumerate(chunks):
            if chunk_index == len(chunks) - 1:
                chunk_duration = max(min_chunk_seconds, remaining)
            else:
                chunk_duration = max(min_chunk_seconds, duration * (len(chunk) / total_chars))
                remaining -= chunk_duration

            frame_path = frames_dir / f"frame_{turn_index:03d}_{chunk_index:02d}_{speaker}.jpg"
            create_frame(
                output_path=frame_path,
                scene_image_path=scene_image,
                speaker=speaker,
                subtitle_text=chunk,
                scene_title=scene_title,
            )
            frame_items.append((frame_path, chunk_duration))
            total_duration += chunk_duration

    info = {
        "frame_count": len(frame_items),
        "scene_missing": sorted(set(scene_missing)),
        "timeline_duration_seconds": round(total_duration, 2),
    }
    return frame_items, info


def write_concat_file(path: Path, frame_items: List[Tuple[Path, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for frame_path, duration in frame_items:
            safe_path = str(frame_path.resolve()).replace("\\", "/")
            f.write(f"file '{safe_path}'\n")
            f.write(f"duration {duration:.3f}\n")
        if frame_items:
            safe_last = str(frame_items[-1][0].resolve()).replace("\\", "/")
            f.write(f"file '{safe_last}'\n")


def compose_video(concat_file: Path, full_audio: Path, output_video: Path, add_waveform: bool) -> None:
    output_video.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(full_audio),
    ]

    if add_waveform:
        filter_complex = (
            f"[0:v]fps={FPS},format=yuv420p[v30];"
            "[1:a]asplit=2[wave_in][a_out];"
            "[wave_in]showwaves=s=420x34:mode=cline:colors=0x38bdf8:rate=30[wave];"
            "[v30][wave]overlay=830:674[final_v]"
        )
        cmd += ["-filter_complex", filter_complex, "-map", "[final_v]", "-map", "[a_out]"]
    else:
        cmd += ["-vf", f"fps={FPS},format=yuv420p", "-map", "0:v", "-map", "1:a"]

    cmd += [
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "160k",
        "-shortest",
        "-movflags", "+faststart",
        str(output_video),
    ]

    run_cmd(cmd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", type=str, default="")
    parser.add_argument("--subtitle-source", type=str, default=os.getenv("VIDEO_SUBTITLE_SOURCE", "spoken"), choices=["spoken", "subtitle"])
    parser.add_argument("--chars-per-chunk", type=int, default=int(os.getenv("VIDEO_SUBTITLE_CHARS_PER_CHUNK", "42")))
    parser.add_argument("--min-chunk-seconds", type=float, default=float(os.getenv("VIDEO_MIN_CHUNK_SECONDS", "1.2")))
    parser.add_argument("--add-waveform", type=str, default=os.getenv("VIDEO_ADD_WAVEFORM", "true"))
    parser.add_argument("--keep-frames", type=str, default=os.getenv("VIDEO_KEEP_FRAMES", "false"))
    args = parser.parse_args()

    week_dir = resolve_week_dir(args.week_dir)

    manifest_path = week_dir / "tts_audio_manifest.json"
    dialogue_path = week_dir / "video_dialogue_script.json"
    full_audio = week_dir / "tts_audio" / "full_dialogue.wav"

    if not manifest_path.exists():
        raise FileNotFoundError(f"Missing {manifest_path}")
    if not dialogue_path.exists():
        raise FileNotFoundError(f"Missing {dialogue_path}")
    if not full_audio.exists():
        raise FileNotFoundError(f"Missing {full_audio}")

    manifest = load_json(manifest_path)
    dialogue = load_json(dialogue_path)

    final_dir = week_dir / "final"
    frames_dir = final_dir / "_frames_96"
    if frames_dir.exists():
        shutil.rmtree(frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Subtitle source: {args.subtitle_source}")
    print(f"[INFO] Full audio: {full_audio}")
    print(f"[INFO] Tom avatar exists: {(ASSETS_DIR / 'tom.png').exists()}")
    print(f"[INFO] Miranda avatar exists: {(ASSETS_DIR / 'miranda.png').exists()}")

    frame_items, timeline_info = build_timeline_frames(
        week_dir=week_dir,
        manifest=manifest,
        subtitle_source=args.subtitle_source,
        chars_per_chunk=args.chars_per_chunk,
        min_chunk_seconds=args.min_chunk_seconds,
        frames_dir=frames_dir,
    )

    concat_file = frames_dir / "slides.txt"
    write_concat_file(concat_file, frame_items)

    output_video = final_dir / "weekly_macro_video.mp4"
    compose_video(
        concat_file=concat_file,
        full_audio=full_audio,
        output_video=output_video,
        add_waveform=parse_bool(args.add_waveform, default=True),
    )

    output_duration = ffprobe_duration(output_video)
    composition_manifest = {
        "meta": {
            "source": "video_dialogue_script.json + tts_audio_manifest.json + scene images + avatars",
            "purpose": "Step 96 final video composition manifest",
            "week_range": (manifest.get("meta") or {}).get("week_range", ""),
            "video_width": VIDEO_WIDTH,
            "video_height": VIDEO_HEIGHT,
            "fps": FPS,
            "subtitle_source": args.subtitle_source,
            "add_waveform": parse_bool(args.add_waveform, default=True),
        },
        "inputs": {
            "dialogue_script": safe_rel(dialogue_path, ROOT_DIR),
            "tts_manifest": safe_rel(manifest_path, ROOT_DIR),
            "full_audio": safe_rel(full_audio, ROOT_DIR),
            "tom_avatar": safe_rel(ASSETS_DIR / "tom.png", ROOT_DIR) if (ASSETS_DIR / "tom.png").exists() else "",
            "miranda_avatar": safe_rel(ASSETS_DIR / "miranda.png", ROOT_DIR) if (ASSETS_DIR / "miranda.png").exists() else "",
        },
        "outputs": {
            "video_file": safe_rel(output_video, ROOT_DIR),
            "duration_seconds": round(output_duration, 2),
        },
        "timeline": timeline_info,
        "tts_meta": manifest.get("meta", {}),
        "dialogue_title": dialogue.get("title", ""),
    }
    save_json(final_dir / "video_composition_manifest.json", composition_manifest)

    if not parse_bool(args.keep_frames, default=False):
        shutil.rmtree(frames_dir, ignore_errors=True)

    print(f"[OK] Created {output_video}")
    print(f"[OK] Created {final_dir / 'video_composition_manifest.json'}")


if __name__ == "__main__":
    main()
