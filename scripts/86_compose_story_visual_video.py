#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
except Exception as exc:
    raise RuntimeError("Pillow is required. Please install pillow before running Step 86.") from exc


VIDEO_W = 1280
VIDEO_H = 720
FPS = 30

SCENE_W = 1110
SCENE_H = 610
SCENE_X = (VIDEO_W - SCENE_W) // 2
SCENE_Y = 8

BAND_Y = 612
BAND_H = VIDEO_H - BAND_Y

AVATAR_SIZE = 104
AVATAR_X = 56
AVATAR_Y = 606

PANEL_X = 188
PANEL_Y = 618
PANEL_W = 720
PANEL_H = 82
PANEL_RADIUS = 22

LABEL_W = 92
LABEL_H = 30
LABEL_X = AVATAR_X + (AVATAR_SIZE - LABEL_W) // 2
LABEL_Y = AVATAR_Y + AVATAR_SIZE - 18

SUBTITLE_FONT_SIZE = 30
SUBTITLE_CHARS_PER_LINE = 26
SUBTITLE_MAX_CHARS_PER_PAGE = 26
SUBTITLE_MIN_PAGE_SEC = 0.75

WAVE_W = 440
WAVE_H = 14
WAVE_X = PANEL_X + (PANEL_W - WAVE_W) // 2
WAVE_Y = PANEL_Y + PANEL_H - 20

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

    for p in [
        week_dir / "weekly_dialogue_story_only_v8.json",
        week_dir / "weekly_dialogue_story_only_v8_11.json",
        week_dir / "weekly_dialogue_story_only.json",
    ]:
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
    images = sorted(
        [p for p in d.glob("scene_*.*") if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}],
        key=lambda p: p.stem,
    )
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
    return (196, 120, 255, 255) if normalize_speaker(speaker) == "Miranda" else (255, 210, 64, 255)


def speaker_label_rgba(speaker: str) -> tuple[int, int, int, int]:
    return (70, 64, 104, 230) if normalize_speaker(speaker) == "Miranda" else (112, 87, 28, 230)


def speaker_wave_hex(speaker: str) -> str:
    return "c478ff" if normalize_speaker(speaker) == "Miranda" else "ffd240"


def visible_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text or ""))


def break_long_piece(piece: str, max_chars: int) -> list[str]:
    piece = piece.strip()
    if not piece:
        return []
    return [piece[i:i + max_chars] for i in range(0, len(piece), max_chars)]


def split_subtitles(text: str) -> list[str]:
    text = re.sub(r"\s+", "", (text or "").strip())
    if not text:
        return [""]
    pieces = [m.group(0).strip() for m in PUNCTUATION_PATTERN.finditer(text) if m.group(0).strip()]
    if not pieces:
        pieces = break_long_piece(text, SUBTITLE_MAX_CHARS_PER_PAGE)

    pages = []
    current = ""
    for raw_piece in pieces:
        for piece in break_long_piece(raw_piece, SUBTITLE_MAX_CHARS_PER_PAGE):
            if not current:
                current = piece
            elif visible_len(current + piece) <= SUBTITLE_MAX_CHARS_PER_PAGE:
                current += piece
            else:
                pages.append(current)
                current = piece
    if current:
        pages.append(current)
    return pages or [""]


def subtitle_windows(chunks: list[str], duration: float) -> list[tuple[float, float]]:
    n = max(len(chunks), 1)
    if n == 1:
        return [(0.0, duration)]
    if duration <= SUBTITLE_MIN_PAGE_SEC * n:
        each = duration / n
        return [(i * each, duration if i == n - 1 else (i + 1) * each) for i in range(n)]

    weights = [max(visible_len(c), 6) for c in chunks]
    base = SUBTITLE_MIN_PAGE_SEC
    remaining = max(0.0, duration - base * n)
    total = float(sum(weights)) or 1.0
    windows = []
    t = 0.0
    for i, w in enumerate(weights):
        length = base + remaining * (w / total)
        end = duration if i == n - 1 else min(duration, t + length)
        windows.append((t, end))
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


def load_font(size: int) -> ImageFont.ImageFont:
    fp = font_path()
    if fp:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            pass
    return ImageFont.load_default()


def circle_mask(size: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(m)
    d.ellipse((0, 0, size - 1, size - 1), fill=255)
    return m


def center_crop(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(img, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))


def make_circle_avatar(img_path: Path, speaker: str) -> Image.Image:
    accent = speaker_rgba(speaker)
    canvas_size = AVATAR_SIZE + 18
    avatar_layer = Image.new("RGBA", (canvas_size, canvas_size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(avatar_layer)

    draw.ellipse((0, 0, canvas_size - 1, canvas_size - 1), fill=(accent[0], accent[1], accent[2], 30))
    draw.ellipse((4, 4, canvas_size - 5, canvas_size - 5), fill=(accent[0], accent[1], accent[2], 70))
    draw.ellipse((8, 8, canvas_size - 9, canvas_size - 9), fill=(accent[0], accent[1], accent[2], 130))

    inner = Image.new("RGBA", (AVATAR_SIZE, AVATAR_SIZE), (255, 255, 255, 0))
    if img_path.exists():
        src = Image.open(img_path).convert("RGBA")
        src = center_crop(src, (AVATAR_SIZE, AVATAR_SIZE))
        src = src.filter(ImageFilter.UnsharpMask(radius=0.6, percent=120, threshold=2))
        inner.paste(src, (0, 0), circle_mask(AVATAR_SIZE))
    else:
        d = ImageDraw.Draw(inner)
        bg = (220, 170, 28, 255) if normalize_speaker(speaker) == "Tom" else (128, 84, 196, 255)
        d.ellipse((0, 0, AVATAR_SIZE - 1, AVATAR_SIZE - 1), fill=bg)
        f = load_font(54)
        initial = "T" if normalize_speaker(speaker) == "Tom" else "M"
        bbox = d.textbbox((0, 0), initial, font=f)
        d.text(((AVATAR_SIZE - (bbox[2] - bbox[0])) / 2, (AVATAR_SIZE - (bbox[3] - bbox[1])) / 2 - 4),
               initial, font=f, fill=(255, 255, 255, 255))

    edge = ImageDraw.Draw(inner)
    edge.ellipse((1, 1, AVATAR_SIZE - 2, AVATAR_SIZE - 2), outline=(255, 255, 255, 245), width=3)
    edge.ellipse((5, 5, AVATAR_SIZE - 6, AVATAR_SIZE - 6), outline=accent, width=4)

    avatar_layer.alpha_composite(inner, (9, 9))
    return avatar_layer


def draw_centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str,
                       font: ImageFont.ImageFont, fill: tuple[int, int, int, int],
                       shadow: bool = True) -> None:
    x0, y0, x1, y1 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    x = x0 + (x1 - x0 - tw) / 2
    y = y0 + (y1 - y0 - th) / 2 - 2
    if shadow:
        draw.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 110))
    draw.text((x, y), text, font=font, fill=fill)


def create_subtitle_panel(size: tuple[int, int]) -> Image.Image:
    w, h = size
    panel = Image.new("RGBA", (w, h), (255, 255, 255, 0))
    d = ImageDraw.Draw(panel)
    d.rounded_rectangle((4, 5, w - 4, h - 2), radius=PANEL_RADIUS, fill=(0, 0, 0, 55))
    d.rounded_rectangle((0, 0, w - 8, h - 8), radius=PANEL_RADIUS,
                        fill=(12, 22, 38, 158), outline=(255, 255, 255, 72), width=1)
    d.rounded_rectangle((1, 1, w - 9, int(h * 0.45)), radius=PANEL_RADIUS - 2,
                        fill=(255, 255, 255, 14))
    return panel


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
                    "scene_image": str(images[scene_idx - 1]),
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


def compose_frame(turn: dict, subtitle_text: str, avatar_cache: dict[str, Image.Image], out_path: Path) -> None:
    frame = Image.new("RGB", (VIDEO_W, VIDEO_H), "white").convert("RGBA")

    scene = Image.open(turn["scene_image"]).convert("RGBA")
    scene = ImageOps.contain(scene, (SCENE_W, SCENE_H), method=Image.Resampling.LANCZOS)
    sx = SCENE_X + (SCENE_W - scene.width) // 2
    sy = SCENE_Y + (SCENE_H - scene.height) // 2
    frame.alpha_composite(scene, (sx, sy))

    band = Image.new("RGBA", (VIDEO_W, BAND_H), (255, 255, 255, 0))
    bd = ImageDraw.Draw(band)
    for s in range(BAND_H):
        alpha = int(8 + 34 * (s / max(BAND_H - 1, 1)))
        bd.line((0, s, VIDEO_W, s), fill=(10, 18, 34, alpha))
    frame.alpha_composite(band, (0, BAND_Y))

    speaker = normalize_speaker(turn["speaker"])
    avatar = avatar_cache[speaker]
    frame.alpha_composite(avatar, (AVATAR_X - 9, AVATAR_Y - 9))

    d = ImageDraw.Draw(frame)
    label_color = speaker_label_rgba(speaker)
    d.rounded_rectangle((LABEL_X, LABEL_Y, LABEL_X + LABEL_W, LABEL_Y + LABEL_H), radius=9, fill=label_color)
    name_font = load_font(22)
    draw_centered_text(d, (LABEL_X, LABEL_Y - 1, LABEL_X + LABEL_W, LABEL_Y + LABEL_H - 1),
                       speaker, name_font, (255, 255, 255, 245), shadow=False)

    panel = create_subtitle_panel((PANEL_W, PANEL_H))
    frame.alpha_composite(panel, (PANEL_X, PANEL_Y))

    sub_font = load_font(SUBTITLE_FONT_SIZE)
    text_box = (PANEL_X + 22, PANEL_Y + 5, PANEL_X + PANEL_W - 22, PANEL_Y + 50)
    draw_centered_text(d, text_box, subtitle_text, sub_font, (244, 247, 251, 255), shadow=True)

    frame.convert("RGB").save(out_path, quality=95)


def render_clip(turn: dict, out: Path, frame_dir: Path, avatar_cache: dict[str, Image.Image]) -> None:
    duration = max(0.35, float(turn["duration_sec"]))
    speaker = normalize_speaker(turn["speaker"])
    chunks = split_subtitles(turn["spoken_text"])
    windows = subtitle_windows(chunks, duration)

    chunk_video_files = []
    for i, chunk in enumerate(chunks):
        start, end = windows[i]
        chunk_duration = max(0.20, end - start)
        frame_path = frame_dir / f"frame_{turn['segment_index']:03d}_{i:02d}.png"
        chunk_video = frame_dir / f"chunk_{turn['segment_index']:03d}_{i:02d}.mp4"
        compose_frame(turn, chunk, avatar_cache, frame_path)

        run([
            "ffmpeg", "-y",
            "-loop", "1", "-t", f"{chunk_duration:.3f}", "-i", str(frame_path),
            "-r", str(FPS),
            "-c:v", "libx264", "-preset", "fast", "-crf", "18",
            "-pix_fmt", "yuv420p",
            str(chunk_video),
        ])
        chunk_video_files.append(chunk_video)

    concat_list = frame_dir / f"chunks_{turn['segment_index']:03d}.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in chunk_video_files), encoding="utf-8")
    silent_video = frame_dir / f"silent_{turn['segment_index']:03d}.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(silent_video)])

    wave_color = speaker_wave_hex(speaker)
    filter_complex = (
        f"[1:a]asplit=2[aout][wavein];"
        f"[wavein]showwaves=s={WAVE_W}x{WAVE_H}:mode=cline:colors=0x{wave_color}:rate={FPS}[wave];"
        f"[0:v][wave]overlay={WAVE_X}:{WAVE_Y}[vout]"
    )

    run([
        "ffmpeg", "-y",
        "-i", str(silent_video),
        "-i", turn["segment_audio"],
        "-filter_complex", filter_complex,
        "-map", "[vout]",
        "-map", "[aout]",
        "-c:v", "libx264", "-preset", "fast", "-crf", "20",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-shortest",
        str(out),
    ])


def concat_and_optimize(clips: list[Path], concat_file: Path, tmp_video: Path, final: Path) -> None:
    concat_file.write_text("".join(f"file '{p.resolve()}'\n" for p in clips), encoding="utf-8")
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(tmp_video)])
    run([
        "ffmpeg", "-y", "-i", str(tmp_video),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        str(final),
    ])


def prepare_avatar_cache() -> dict[str, Image.Image]:
    return {
        "Tom": make_circle_avatar(Path("assets/tom.png"), "Tom"),
        "Miranda": make_circle_avatar(Path("assets/miranda.png"), "Miranda"),
    }


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

    timeline = build_timeline(dialogue_json, images, seg_dir)
    timeline_json.write_text(json.dumps(timeline, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] Wrote {timeline_json}")

    avatar_cache = prepare_avatar_cache()

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        clip_dir = tmp_dir / "clips"
        frame_dir = tmp_dir / "frames"
        clip_dir.mkdir()
        frame_dir.mkdir()

        clips = []
        for turn in timeline["turns"]:
            clip = clip_dir / f"turn_{turn['segment_index']:03d}.mp4"
            render_clip(turn, clip, frame_dir, avatar_cache)
            clips.append(clip)

        concat_and_optimize(clips, tmp_dir / "concat.txt", tmp_dir / "concat.mp4", final)

    print(f"[OK] Created {final}")
    print("[OK] Only final mp4 + story_turn_timeline.json are kept under story_video.")


if __name__ == "__main__":
    main()
