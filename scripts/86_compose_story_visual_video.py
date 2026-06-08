#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Step 86 | Compose Story Visual Video

This version:
- Uses Step 83 scene images.
- Uses Step 85 edge-tts segment mp3 files.
- Uses assets/tom.png and assets/miranda.png as speaker avatars.
- Scales and pads Step 83 scene images upward on a white 16:9 canvas for a clean lower caption area.
- Shows the active speaker avatar in the lower-left area, with a constant subtle glowing halo.
- Shows transcript subtitles in a lighter translucent dark glass-style lower dialogue panel.
- Uses one-line centered subtitles with a softer regular CJK font.
- Adds a subtle live audio waveform inside the subtitle panel.
- Splits subtitles automatically from spoken_text by punctuation and length.
- Times subtitle pages by text length against the actual mp3 segment duration.
- Removes waveform.
- Removes the speaker-name gray label.
- Uses drawtext expansion=none to avoid '%' subtitle errors.
- Keeps intermediate clips in a temporary directory; repo keeps only final mp4 + timeline json.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except Exception as exc:
    raise RuntimeError("Pillow is required. Please install pillow before running Step 86.") from exc


VIDEO_W = 1280
VIDEO_H = 720
FPS = 30

# Scene image is first scaled down and placed near the top on a white canvas.
# This keeps all Step 83 content intact while creating clean space for avatar/subtitles.
SCENE_SCALE_FACTOR = 0.80
SCENE_PAD_TOP = 12
SCENE_TARGET_W = int(VIDEO_W * SCENE_SCALE_FACTOR)
SCENE_TARGET_H = int(VIDEO_H * SCENE_SCALE_FACTOR)

# Lower-left speaker avatar.
AVATAR_SIZE = 108
RING_SIZE = 136
AVATAR_X = 50
AVATAR_Y = VIDEO_H - AVATAR_SIZE - 26
RING_X = AVATAR_X - (RING_SIZE - AVATAR_SIZE) // 2
RING_Y = AVATAR_Y - (RING_SIZE - AVATAR_SIZE) // 2

# Subtitle panel sits beside the avatar.
# Keep it medium-width and one-line so it does not cover too much of the scene image.
SUBTITLE_FONT_SIZE = 30
SUBTITLE_CHARS_PER_LINE = 31
SUBTITLE_LINES_PER_PAGE = 1
SUBTITLE_MAX_CHARS_PER_PAGE = SUBTITLE_CHARS_PER_LINE * SUBTITLE_LINES_PER_PAGE
SUBTITLE_BOX_X = 188
SUBTITLE_BOX_W = 850
SUBTITLE_BOX_H = 96
SUBTITLE_BOX_Y = VIDEO_H - SUBTITLE_BOX_H - 26

# Center subtitle text inside the dialogue box, slightly above the waveform.
SUBTITLE_TEXT_X_EXPR = f"{SUBTITLE_BOX_X}+({SUBTITLE_BOX_W}-text_w)/2"
SUBTITLE_TEXT_Y_EXPR = f"{SUBTITLE_BOX_Y}+({SUBTITLE_BOX_H}-text_h)/2-12"

# Subtle waveform inside the lower part of the subtitle panel.
WAVE_W = 620
WAVE_H = 22
WAVE_X = SUBTITLE_BOX_X + (SUBTITLE_BOX_W - WAVE_W) // 2
WAVE_Y = SUBTITLE_BOX_Y + SUBTITLE_BOX_H - 30

# Timing guardrails for automatically paged subtitles.
# These are soft guardrails. If the audio is very short, the actual display time is still bounded by duration.
SUBTITLE_MIN_PAGE_SEC = 0.85

FADE_SEC = 0.24


PUNCTUATION_PATTERN = re.compile(r"([^，。；！？!?;：:、]+[，。；！？!?;：:、]?)")


def run(cmd: list[str]) -> None:
    print("[CMD]", " ".join(str(x) for x in cmd))
    subprocess.run(cmd, check=True)


def ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]).decode("utf-8").strip()
    return float(out)


def latest_week_dir(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        p2 = Path("output/weekly") / explicit
        if p2.exists():
            return p2
        raise FileNotFoundError(f"Week directory not found: {explicit}")

    base = Path("output/weekly")
    if not base.exists():
        raise FileNotFoundError("output/weekly not found")
    dirs = sorted([p for p in base.iterdir() if p.is_dir()])
    if not dirs:
        raise FileNotFoundError("No weekly output directory found")
    return dirs[-1]


def resolve_dialogue_json(week_dir: Path, explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if p.exists():
            return p
        p2 = week_dir / explicit
        if p2.exists():
            return p2
        raise FileNotFoundError(f"Dialogue JSON not found: {explicit}")

    preferred = [
        week_dir / "weekly_dialogue_story_only_v8.json",
        week_dir / "weekly_dialogue_story_only_v8_11.json",
        week_dir / "weekly_dialogue_story_only.json",
    ]
    for p in preferred:
        if p.exists():
            return p

    candidates = []
    for pattern in ("weekly_dialogue_story_only_v*.json", "weekly_dialogue_story_only*.json"):
        candidates.extend(sorted(week_dir.glob(pattern)))
    if candidates:
        return candidates[-1]

    fallback = sorted(week_dir.glob("weekly_dialogue_script*.json"))
    if fallback:
        print("[WARN] Falling back to weekly_dialogue_script*.json because story-only JSON was not found.")
        return fallback[-1]

    raise FileNotFoundError("No dialogue JSON found under week_dir")


def resolve_scene_images(week_dir: Path) -> list[Path]:
    d = week_dir / "story_visual_images"
    if not d.exists():
        raise FileNotFoundError(f"story_visual_images not found: {d}")
    images = [p for p in d.glob("scene_*.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}]
    images = sorted(images, key=lambda p: p.stem)
    if not images:
        raise FileNotFoundError("No scene images found in story_visual_images")
    return images


def resolve_segment_dir(week_dir: Path) -> Path:
    d = week_dir / "story_audio" / "segments"
    if not d.exists():
        raise FileNotFoundError(f"Segment audio directory not found: {d}")
    return d


def sorted_segment_files(segment_dir: Path) -> list[Path]:
    files = sorted(segment_dir.glob("seg_*.mp3"))
    if not files:
        files = sorted(segment_dir.glob("seq_*.mp3"))
    if not files:
        raise FileNotFoundError(f"No segment mp3 files found in {segment_dir}")
    return files


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def extract_sections(data: dict) -> list[dict]:
    if isinstance(data.get("sections"), list):
        return data["sections"]
    if isinstance(data.get("story_sections"), list):
        return data["story_sections"]
    if isinstance(data.get("scene_dialogues"), list):
        return data["scene_dialogues"]
    raise ValueError("Unable to find sections array in dialogue JSON")


def section_id(sec: dict, idx: int) -> str:
    return sec.get("section_id") or sec.get("id") or f"s{idx+1}"


def section_title(sec: dict, idx: int) -> str:
    return sec.get("section_title") or sec.get("title") or sec.get("name") or f"section_{idx+1:02d}"


def normalize_speaker(raw: str) -> str:
    x = (raw or "").strip().lower()
    if x.startswith("tom"):
        return "Tom"
    if x.startswith("miranda"):
        return "Miranda"
    return raw or "Speaker"


def speaker_rgba(speaker: str) -> tuple[int, int, int, int]:
    """
    Speaker accent colors:
    - Tom: warm yellow border/ring
    - Miranda: purple border/ring
    """
    return (196, 120, 255, 255) if normalize_speaker(speaker) == "Miranda" else (255, 210, 64, 255)


def speaker_wave_hex(speaker: str) -> str:
    return "c478ff" if normalize_speaker(speaker) == "Miranda" else "ffd240"


def visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def break_long_piece(piece: str, max_chars: int) -> list[str]:
    piece = piece.strip()
    if not piece:
        return []
    return [piece[i:i + max_chars] for i in range(0, len(piece), max_chars)]


def wrap_subtitle_page(text: str) -> str:
    text = (text or "").strip()
    lines = []
    for start in range(0, len(text), SUBTITLE_CHARS_PER_LINE):
        lines.append(text[start:start + SUBTITLE_CHARS_PER_LINE])
    return "\n".join(lines[:SUBTITLE_LINES_PER_PAGE])


def split_subtitles(text: str) -> list[str]:
    """
    Split a spoken_text turn into readable subtitle pages.

    Rules:
    - Prefer punctuation boundaries, so subtitles change near natural pauses.
    - Keep each page to a medium-width dialogue box: about 2 lines.
    - Fall back to fixed-length chunks only when a sentence is too long.
    """
    text = re.sub(r"\s+", "", (text or "").strip())
    if not text:
        return [""]

    pieces = [m.group(0).strip() for m in PUNCTUATION_PATTERN.finditer(text) if m.group(0).strip()]
    if not pieces:
        pieces = break_long_piece(text, SUBTITLE_MAX_CHARS_PER_PAGE)

    pages: list[str] = []
    current = ""

    for raw_piece in pieces:
        sub_pieces = break_long_piece(raw_piece, SUBTITLE_MAX_CHARS_PER_PAGE)
        for piece in sub_pieces:
            if not current:
                current = piece
                continue

            if visible_len(current + piece) <= SUBTITLE_MAX_CHARS_PER_PAGE:
                current += piece
            else:
                pages.append(wrap_subtitle_page(current))
                current = piece

    if current:
        pages.append(wrap_subtitle_page(current))

    return pages or [""]


def subtitle_windows(chunks: list[str], duration: float) -> list[tuple[float, float]]:
    """
    Compute display windows for subtitle pages.

    The previous implementation assigned equal time to each page. This version
    assigns time by text length, which tracks TTS speed more naturally while still
    using only the actual mp3 duration from Step 85.
    """
    n = max(len(chunks), 1)
    if n == 1:
        return [(0.0, duration)]

    # If the segment is very short, equal timing is safer than overfitting.
    if duration <= SUBTITLE_MIN_PAGE_SEC * n:
        each = duration / n
        return [
            (i * each, duration if i == n - 1 else (i + 1) * each)
            for i in range(n)
        ]

    weights = [max(visible_len(c), 6) for c in chunks]
    base = SUBTITLE_MIN_PAGE_SEC
    remaining = max(0.0, duration - base * n)
    total_weight = float(sum(weights)) or 1.0
    lengths = [base + remaining * (w / total_weight) for w in weights]

    windows = []
    t = 0.0
    for i, length in enumerate(lengths):
        start = t
        end = duration if i == n - 1 else min(duration, t + length)
        windows.append((start, end))
        t = end
    return windows


def font_path() -> str | None:
    candidates = [
        "assets/fonts/NotoSansTC-Regular.otf",
        "assets/fonts/NotoSansCJK-Regular.ttc",
        "assets/fonts/NotoSansTC-Medium.otf",
        "assets/fonts/NotoSansCJK-Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansTC-Regular.otf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.otf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return None


def write_text(path: Path, text: str) -> None:
    path.write_text(text or "", encoding="utf-8")


def circle_mask(size: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.ellipse((0, 0, size - 1, size - 1), fill=255)
    return m


def crop_square(img: Image.Image) -> Image.Image:
    w, h = img.size
    s = min(w, h)
    return img.crop(((w-s)//2, (h-s)//2, (w+s)//2, (h+s)//2))


def make_initial_avatar(out: Path, speaker: str, fp: str | None) -> None:
    bg = (220, 170, 28, 255) if speaker == "Tom" else (186, 85, 211, 255)
    img = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255, 255, 255, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((4, 4, AVATAR_SIZE-4, AVATAR_SIZE-4), fill=bg)
    try:
        font = ImageFont.truetype(fp, 52) if fp else ImageFont.load_default()
    except Exception:
        font = ImageFont.load_default()
    initial = "T" if speaker == "Tom" else "M"
    box = d.textbbox((0, 0), initial, font=font)
    tw, th = box[2]-box[0], box[3]-box[1]
    d.text(((AVATAR_SIZE-tw)/2, (AVATAR_SIZE-th)/2-4), initial, fill=(255,255,255,255), font=font)
    img.save(out)


def make_avatar_from_asset(src: Path, out: Path, speaker: str) -> None:
    img = Image.open(src).convert("RGBA")
    img = crop_square(img).resize((AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=135, threshold=3))
    avatar = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255,255,255,0))
    avatar.paste(img, (0, 0), circle_mask(AVATAR_SIZE))
    d = ImageDraw.Draw(avatar)
    c = speaker_rgba(speaker)
    d.ellipse((1, 1, AVATAR_SIZE-2, AVATAR_SIZE-2), outline=(255,255,255,235), width=3)
    d.ellipse((5, 5, AVATAR_SIZE-6, AVATAR_SIZE-6), outline=(c[0], c[1], c[2], 255), width=5)
    avatar.save(out)


def make_ring(out: Path, speaker: str) -> None:
    c = speaker_rgba(speaker)
    img = Image.new("RGBA", (RING_SIZE, RING_SIZE), (255,255,255,0))
    d = ImageDraw.Draw(img)
    # Constant subtle halo, not flashing.
    for width, alpha, inset in [(12, 18, 11), (8, 34, 15), (4, 64, 19)]:
        d.ellipse((inset, inset, RING_SIZE-inset, RING_SIZE-inset), outline=(c[0], c[1], c[2], alpha), width=width)
    d.ellipse((23, 23, RING_SIZE-24, RING_SIZE-24), outline=(255, 255, 255, 140), width=3)
    d.ellipse((26, 26, RING_SIZE-27, RING_SIZE-27), outline=(c[0], c[1], c[2], 96), width=3)
    img = img.filter(ImageFilter.GaussianBlur(radius=0.9))
    img.save(out)


def make_subtitle_panel(out: Path) -> None:
    """
    Create a lighter translucent dark glass-style subtitle panel.

    The panel separates subtitles from the whiteboard scene, but stays lower and
    softer than a heavy black bar.
    """
    shadow = Image.new("RGBA", (SUBTITLE_BOX_W + 18, SUBTITLE_BOX_H + 18), (255, 255, 255, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle(
        (9, 9, SUBTITLE_BOX_W + 8, SUBTITLE_BOX_H + 8),
        radius=24,
        fill=(0, 0, 0, 66),
    )
    shadow = shadow.filter(ImageFilter.GaussianBlur(radius=6))

    panel = Image.new("RGBA", (SUBTITLE_BOX_W + 18, SUBTITLE_BOX_H + 18), (255, 255, 255, 0))
    panel.alpha_composite(shadow, (0, 0))

    d = ImageDraw.Draw(panel)
    rect = (9, 9, SUBTITLE_BOX_W + 8, SUBTITLE_BOX_H + 8)

    d.rounded_rectangle(
        rect,
        radius=24,
        fill=(15, 23, 42, 138),
        outline=(255, 255, 255, 96),
        width=2,
    )

    highlight = Image.new("RGBA", (SUBTITLE_BOX_W, SUBTITLE_BOX_H), (255, 255, 255, 0))
    hd = ImageDraw.Draw(highlight)
    hd.rounded_rectangle(
        (0, 0, SUBTITLE_BOX_W - 1, int(SUBTITLE_BOX_H * 0.45)),
        radius=22,
        fill=(255, 255, 255, 18),
    )
    panel.alpha_composite(highlight, (9, 9))

    panel = panel.filter(ImageFilter.GaussianBlur(radius=0.12))
    panel.crop((9, 9, SUBTITLE_BOX_W + 9, SUBTITLE_BOX_H + 9)).save(out)


def prepare_avatars(tmp_dir: Path, fp: str | None) -> dict[str, dict[str, Path]]:
    assets = {"Tom": Path("assets/tom.png"), "Miranda": Path("assets/miranda.png")}
    result = {}
    for speaker, src in assets.items():
        base = tmp_dir / f"{speaker.lower()}_avatar.png"
        ring = tmp_dir / f"{speaker.lower()}_ring.png"
        if src.exists():
            print(f"[INFO] Using avatar asset for {speaker}: {src}")
            make_avatar_from_asset(src, base, speaker)
        else:
            print(f"[WARN] Missing avatar asset for {speaker}: {src}; fallback to initial.")
            make_initial_avatar(base, speaker, fp)
        make_ring(ring, speaker)
        result[speaker] = {"base": base, "ring": ring}
    return result


def build_buckets(sections: list[dict], images: list[Path]) -> list[list[dict]]:
    records = []
    for idx, sec in enumerate(sections):
        records.append({
            "section_id": section_id(sec, idx),
            "section_title": section_title(sec, idx),
            "speaker_turns": sec.get("speaker_turns") or [],
        })
    if len(records) <= len(images):
        buckets = [[r] for r in records]
        while len(buckets) < len(images):
            buckets.append([])
        return buckets
    return [[r] for r in records[:len(images)-1]] + [records[len(images)-1:]]


def build_timeline(dialogue_json: Path, images: list[Path], seg_dir: Path) -> dict:
    data = load_json(dialogue_json)
    sections = extract_sections(data)
    buckets = build_buckets(sections, images)
    turns = []
    for scene_idx, bucket in enumerate(buckets, start=1):
        for sec in bucket:
            for turn in sec["speaker_turns"]:
                turns.append({
                    "scene_index": scene_idx,
                    "scene_image": str(images[scene_idx-1]),
                    "section_id": sec["section_id"],
                    "section_title": sec["section_title"],
                    "speaker": normalize_speaker(turn.get("speaker", "Speaker")),
                    "spoken_text": (turn.get("spoken_text") or "").strip(),
                    "subtitle_text": (turn.get("subtitle_text") or "").strip(),
                    "estimated_seconds": float(turn.get("estimated_seconds") or 0),
                })
    segs = sorted_segment_files(seg_dir)
    if len(segs) != len(turns):
        print(f"[WARN] Segment count ({len(segs)}) != turn count ({len(turns)}).")
        n = min(len(segs), len(turns))
        segs, turns = segs[:n], turns[:n]
    t = 0.0
    for i, (turn, seg) in enumerate(zip(turns, segs), start=1):
        dur = ffprobe_duration(seg)
        turn.update({
            "segment_index": i,
            "segment_audio": str(seg),
            "start_sec": round(t, 3),
            "duration_sec": round(dur, 3),
            "end_sec": round(t + dur, 3),
        })
        t += dur
    return {
        "dialogue_json": str(dialogue_json),
        "segment_dir": str(seg_dir),
        "turn_count": len(turns),
        "scene_count": len(images),
        "total_duration": round(t, 3),
        "turns": turns,
    }


def drawtext_filter(input_label: str, output_label: str, textfile: Path, fp: str | None, fontsize: int,
                    x: str, y: str, enable: str | None = None) -> str:
    parts = [f"[{input_label}]drawtext="]
    if fp:
        parts.append(f"fontfile='{fp}':")
    parts += [
        "expansion=none:",
        f"textfile='{textfile.as_posix()}':fontsize={fontsize}:fontcolor=white:",
        f"x={x}:y={y}:line_spacing=4:",
        "box=0:boxborderw=0:boxcolor=black@0.0:",
        "borderw=1:bordercolor=black@0.42:shadowx=1:shadowy=1",
    ]
    if enable:
        parts.append(f":enable='{enable}'")
    parts.append(f"[{output_label}]")
    return "".join(parts)


def render_clip(turn: dict, out: Path, avatar_map: dict, fp: str | None, fade_in: bool, fade_out: bool, text_dir: Path, subtitle_panel: Path) -> None:
    duration = max(0.35, float(turn["duration_sec"]))
    speaker = normalize_speaker(turn["speaker"])
    chunks = split_subtitles(turn["spoken_text"])
    windows = subtitle_windows(chunks, duration)

    chunk_files = []
    for i, chunk in enumerate(chunks):
        p = text_dir / f"subtitle_{turn['segment_index']:03d}_{i:02d}.txt"
        write_text(p, chunk)
        chunk_files.append(p)

    wave_color = speaker_wave_hex(speaker)
    filters = [
        "[1:a]asplit=2[aout][wavein]",
        f"[wavein]showwaves=s={WAVE_W}x{WAVE_H}:mode=cline:colors=0x{wave_color}:rate={FPS},format=rgba,colorkey=0x000000:0.18:0.04[wave]",
        f"[0:v]scale={SCENE_TARGET_W}:{SCENE_TARGET_H}:force_original_aspect_ratio=decrease,pad={VIDEO_W}:{VIDEO_H}:(ow-iw)/2:{SCENE_PAD_TOP}:white,format=rgba[bg]",
        f"[2:v]scale={AVATAR_SIZE}:{AVATAR_SIZE}[av]",
        f"[3:v]scale={RING_SIZE}:{RING_SIZE}[ring]",
        f"[4:v]scale={SUBTITLE_BOX_W}:{SUBTITLE_BOX_H}[panel]",
        f"[bg][panel]overlay={SUBTITLE_BOX_X}:{SUBTITLE_BOX_Y}[vpanel]",
        f"[vpanel][ring]overlay={RING_X}:{RING_Y}[vring]",
        f"[vring][av]overlay={AVATAR_X}:{AVATAR_Y}[vavatar]",
    ]
    current = "vavatar"

    for i, cf in enumerate(chunk_files):
        start, end = windows[i]
        out_label = f"vsub{i:02d}"
        filters.append(drawtext_filter(current, out_label, cf, fp, SUBTITLE_FONT_SIZE,
                                       x=SUBTITLE_TEXT_X_EXPR, y=SUBTITLE_TEXT_Y_EXPR,
                                       enable=f"between(t,{start:.3f},{end:.3f})"))
        current = out_label

    filters.append(f"[{current}][wave]overlay={WAVE_X}:{WAVE_Y}[vwave]")
    current = "vwave"

    fades = []
    if fade_in:
        fades.append(f"fade=t=in:st=0:d={FADE_SEC}")
    if fade_out and duration > FADE_SEC:
        fades.append(f"fade=t=out:st={max(0, duration-FADE_SEC):.3f}:d={FADE_SEC}")
    if fades:
        filters.append(f"[{current}]{','.join(fades)}[vout]")
        vout = "vout"
    else:
        vout = current

    run([
        "ffmpeg", "-y",
        "-loop", "1", "-t", f"{duration:.3f}", "-i", turn["scene_image"],
        "-i", turn["segment_audio"],
        "-i", str(avatar_map[speaker]["base"]),
        "-i", str(avatar_map[speaker]["ring"]),
        "-i", str(subtitle_panel),
        "-filter_complex", ";".join(filters),
        "-map", f"[{vout}]",
        "-map", "[aout]",
        "-r", str(FPS),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "27",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        str(out),
    ])


def concat_and_optimize(clips: list[Path], concat_file: Path, tmp_video: Path, final: Path) -> None:
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(tmp_video)])
    run([
        "ffmpeg", "-y", "-i", str(tmp_video),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "28",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(final),
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--week-dir", default="", help="Week folder or full path. Leave blank to use latest.")
    parser.add_argument("--dialogue-json", default="", help="Optional explicit dialogue json path.")
    parser.add_argument("--force-rebuild", action="store_true")
    args = parser.parse_args()

    week_dir = latest_week_dir(args.week_dir or None)
    dialogue_json = resolve_dialogue_json(week_dir, args.dialogue_json or None)
    images = resolve_scene_images(week_dir)
    seg_dir = resolve_segment_dir(week_dir)

    out_dir = week_dir / "story_video"
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / "story_visual_video_test.mp4"
    timeline_json = out_dir / "story_turn_timeline.json"

    print(f"[INFO] Week dir: {week_dir}")
    print(f"[INFO] Dialogue JSON: {dialogue_json}")
    print(f"[INFO] Scene image count: {len(images)}")
    print(f"[INFO] Segment dir: {seg_dir}")

    if final.exists() and not args.force_rebuild:
        print(f"[SKIP] Output already exists: {final}")
        print("[TIP] Use --force-rebuild to regenerate")
        return

    for old in ("clips", "avatars"):
        p = out_dir / old
        if p.exists():
            shutil.rmtree(p)

    fp = font_path()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clip_dir = tmp_dir / "clips"
        avatar_dir = tmp_dir / "avatars"
        text_dir = tmp_dir / "text"
        clip_dir.mkdir()
        avatar_dir.mkdir()
        text_dir.mkdir()

        avatar_map = prepare_avatars(avatar_dir, fp)
        subtitle_panel = tmp_dir / "subtitle_panel.png"
        make_subtitle_panel(subtitle_panel)
        timeline = build_timeline(dialogue_json, images, seg_dir)
        timeline_json.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Wrote {timeline_json}")

        clips = []
        turns = timeline["turns"]
        for idx, turn in enumerate(turns):
            prev_scene = turns[idx - 1]["scene_index"] if idx > 0 else None
            next_scene = turns[idx + 1]["scene_index"] if idx < len(turns) - 1 else None
            scene = turn["scene_index"]
            clip = clip_dir / f"turn_{turn['segment_index']:03d}.mp4"
            render_clip(
                turn, clip, avatar_map, fp,
                fade_in=(idx == 0 or scene != prev_scene),
                fade_out=(idx == len(turns) - 1 or scene != next_scene),
                text_dir=text_dir,
                subtitle_panel=subtitle_panel,
            )
            clips.append(clip)

        concat_and_optimize(clips, tmp_dir / "concat.txt", tmp_dir / "concat.mp4", final)

    print(f"[OK] Created {final}")
    print("[OK] Only final mp4 + story_turn_timeline.json are kept under story_video.")


if __name__ == "__main__":
    main()
