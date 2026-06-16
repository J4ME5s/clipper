from faster_whisper import WhisperModel
import subprocess
import ollama
import json
import os
import librosa
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# 1. Transcription

def transcribe(video_path: str) -> list[dict]:
    model = WhisperModel("base", device="auto", compute_type="int8")
    # word_timestamps=True makes whisper return timing for each individual word
    segments, _ = model.transcribe(video_path, vad_filter=True, word_timestamps=True)

    result = []
    for s in segments:
        # Pull word-level data out alongside the segment-level data
        words = [{"word": w.word, "start": w.start, "end": w.end} for w in (s.words or [])]
        result.append({
            "start": s.start,
            "end": s.end,
            "text": s.text.strip(),
            "words": words,
        })
    return result


# 2. Audio energy analysis
def get_energy_scores(video_path: str, segments: list[dict]) -> list[dict]:
    audio_path = video_path.replace(".mp4", "_audio.wav")

    # Rip mono audio at 16kHz for analysis
    subprocess.run([
        "ffmpeg", "-y", "-i", video_path,
        "-ac", "1", "-ar", "16000",
        audio_path
    ], check=True, capture_output=True)

    y, sr = librosa.load(audio_path, sr=16000)
    os.remove(audio_path)

    scored = []
    for seg in segments:
        start_sample = int(seg["start"] * sr)
        end_sample = int(seg["end"] * sr)
        chunk = y[start_sample:end_sample]

        if len(chunk) == 0:
            energy = 0.0
        else:
            energy = float(np.sqrt(np.mean(chunk ** 2)))  # RMS energy

        scored.append({**seg, "energy": energy})

    # Normalize energy to 0–1 scale
    energies = [s["energy"] for s in scored]
    max_e = max(energies) if max(energies) > 0 else 1
    for s in scored:
        s["energy"] = round(s["energy"] / max_e, 3)

    return scored


# ── 3. Group segments into candidate windows ──────────────────────────────────

def build_candidate_windows(scored_segments: list[dict],
                             window_sec: float = 60.0,
                             min_clip: float = 20.0,
                             max_clip: float = 90.0) -> list[dict]:
    """
    Slide a window over segments and score each window by:
      - average audio energy
      - word density (how much is being said)
    Returns top candidate windows for the LLM to evaluate.
    """
    if not scored_segments:
        return []

    candidates = []
    i = 0
    while i < len(scored_segments):
        seg = scored_segments[i]
        window_start = seg["start"]
        window_end = window_start + window_sec

        # Collect all segments that fall in this window
        window_segs = [s for s in scored_segments
                       if s["start"] >= window_start and s["end"] <= window_end]

        if not window_segs:
            i += 1
            continue

        actual_end = window_segs[-1]["end"]
        duration = actual_end - window_start

        if duration < min_clip:
            i += 1
            continue

        text = " ".join(s["text"] for s in window_segs)
        avg_energy = np.mean([s["energy"] for s in window_segs])
        word_count = len(text.split())
        word_density = word_count / max(duration, 1)

        # Combined score: weight energy more heavily
        score = (avg_energy * 0.7) + (min(word_density / 3, 1.0) * 0.3)

        candidates.append({
            "start": round(window_start, 1),
            "end": round(min(actual_end, window_start + max_clip), 1),
            "text": text,
            "score": round(float(score), 3),
            "avg_energy": round(float(avg_energy), 3),
            "word_count": word_count,
        })

        # Advance by half a window for overlap
        i += max(1, len(window_segs) // 2)

    # Return top 12 candidates by score for the LLM to pick from
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:12]


# ── 4. LLM clip selection ─────────────────────────────────────────────────────

def pick_clips(scored_segments: list[dict]) -> list[dict]:
    candidates = build_candidate_windows(scored_segments)

    if not candidates:
        raise ValueError("No candidate windows found — video may be too short or silent.")

    candidate_text = ""
    for idx, c in enumerate(candidates):
        candidate_text += (
            f"\nCandidate {idx + 1} [{c['start']}s – {c['end']}s] "
            f"(energy={c['avg_energy']}, words={c['word_count']})\n"
            f"  \"{c['text'][:300]}{'...' if len(c['text']) > 300 else ''}\"\n"
        )

    prompt = f"""You are an expert clip editor for gaming and vtuber content on TikTok, YouTube Shorts, and Twitch clips.

You will be given a list of candidate moments from a stream, each with:
- Timestamps
- An energy score (0–1, higher = louder/more hype audio)
- Word count
- A transcript snippet

Your job: pick the 3–5 BEST clips that would perform well as short-form content.

Prioritize moments that have:
- Genuine reactions (surprise, hype, laughter, disbelief)
- A clear beginning and payoff within the clip
- High energy OR emotionally interesting dialogue
- Something a viewer would want to share

Avoid:
- Slow or quiet moments with no payoff
- Clips that start or end mid-sentence awkwardly
- Repetitive or filler content

Candidates:
{candidate_text}

Respond ONLY with a raw JSON array. No explanation, no markdown, no code fences.
[{{"start": 0.0, "end": 0.0, "reason": "one sentence explanation"}}]
"""

    response = ollama.chat(
        model="llama3:8b",
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response["message"]["content"].strip()
    start = raw.find("[")
    end = raw.rfind("]") + 1
    if start == -1 or end == 0:
        raise ValueError(f"No JSON array in LLM response: {raw}")

    clips = json.loads(raw[start:end])
    valid = [c for c in clips if c["end"] - c["start"] >= 10]
    return valid if valid else clips


# 5. Caption generation (Pillow-based, no libass needed)

# Font priority list for macOS — falls back to Pillow's built-in if none found
_FONT_PATHS = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]

def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_PATHS:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    # Pillow 10+ supports size param on load_default — looks fine at larger sizes
    return ImageFont.load_default(size=size)


def _build_caption_events(segments: list[dict], clip_start: float, clip_end: float) -> list[dict]:
    """
    Convert transcript segments into a flat list of caption events:
    [{text, start, end}, ...] with times relative to clip start (seconds).
    4-word chunks, TikTok-style.
    """
    events = []
    chunk_size = 4

    for seg in segments:
        if seg["end"] < clip_start or seg["start"] > clip_end:
            continue

        words = seg.get("words", [])

        if not words:
            events.append({
                "text": seg["text"].strip(),
                "start": max(seg["start"], clip_start) - clip_start,
                "end": min(seg["end"], clip_end) - clip_start,
            })
        else:
            for j in range(0, len(words), chunk_size):
                chunk = words[j:j + chunk_size]
                events.append({
                    "text": " ".join(w["word"].strip() for w in chunk),
                    "start": max(chunk[0]["start"], clip_start) - clip_start,
                    "end": min(chunk[-1]["end"], clip_end) - clip_start,
                })

    return events


def _draw_caption(img: Image.Image, text: str, font: ImageFont.FreeTypeFont) -> Image.Image:
    """
    Draw TikTok-style caption onto a copy of img:
    - White bold text, black outline, semi-transparent pill background
    - Centered horizontally, near the bottom
    """
    img = img.copy()
    draw = ImageDraw.Draw(img)
    W, H = img.size

    # Wrap text if too wide (>70% of frame width)
    words = text.split()
    lines = []
    current = []
    for word in words:
        test = " ".join(current + [word])
        bbox = font.getbbox(test)
        if bbox[2] - bbox[0] > W * 0.80 and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    # Measure total text block
    line_height = font.size + 6
    block_h = line_height * len(lines)
    pad_x, pad_y = 20, 12
    margin_bottom = int(H * 0.08)  # 8% from bottom

    # Draw each line centered
    y_top = H - margin_bottom - block_h

    # Draw pill background across all lines
    max_w = max(
        font.getbbox(line)[2] - font.getbbox(line)[0] for line in lines
    )
    rx = (W - max_w) // 2 - pad_x
    ry = y_top - pad_y
    rw = W - rx
    rh = y_top + block_h + pad_y

    # Semi-transparent dark background
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)
    ov_draw.rounded_rectangle([rx, ry, rw, rh], radius=12, fill=(0, 0, 0, 160))
    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(img)

    for k, line in enumerate(lines):
        bbox = font.getbbox(line)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        y = y_top + k * line_height

        # Black outline (draw text offset in 4 directions)
        for dx, dy in [(-2,0),(2,0),(0,-2),(0,2),(-2,-2),(2,-2),(-2,2),(2,2)]:
            draw.text((x + dx, y + dy), line, font=font, fill=(0, 0, 0))

        # White text on top
        draw.text((x, y), line, font=font, fill=(255, 255, 255))

    return img


# 6. ffmpeg cutting with Pillow caption burn-in

def cut_clips(video_path: str, clips: list[dict], output_dir: str,
              all_segments: list[dict] = None, captions: bool = False) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    output_files = []

    for i, clip in enumerate(clips):
        out_path = os.path.join(output_dir, f"clip_{i + 1}.mp4")

        if captions and all_segments:
            _cut_with_captions(video_path, clip, out_path, all_segments)
        else:
            # Plain cut — no captions
            subprocess.run([
                "ffmpeg", "-y",
                "-ss", str(clip["start"]),
                "-to", str(clip["end"]),
                "-i", video_path,
                "-c:v", "libx264",
                "-c:a", "aac",
                "-movflags", "+faststart",
                out_path
            ], check=True)

        output_files.append(out_path)

    return output_files


def _cut_with_captions(video_path: str, clip: dict, out_path: str,
                       all_segments: list[dict]) -> None:
    """
    Burn captions into a clip using Pillow — no libass required.

    Pipeline:
      1. ffmpeg pipes raw RGB frames from the clip window
      2. Python draws caption text onto each frame with Pillow
      3. ffmpeg re-encodes the modified frames + original audio into the output
    """
    clip_start = clip["start"]
    clip_end = clip["end"]
    duration = clip_end - clip_start

    # Build caption event list (times relative to clip start)
    events = _build_caption_events(all_segments, clip_start, clip_end)

    # --- Step 1: probe video dimensions and framerate ---
    probe = subprocess.run([
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate",
        "-of", "csv=p=0",
        video_path
    ], capture_output=True, text=True, check=True)

    parts = probe.stdout.strip().split(",")
    W, H = int(parts[0]), int(parts[1])
    fps_num, fps_den = map(int, parts[2].split("/"))
    fps = fps_num / fps_den

    font_size = max(24, int(H * 0.07))  # ~7% of frame height
    font = _load_font(font_size)

    # --- Step 2: pipe raw frames out of ffmpeg ---
    extractor = subprocess.Popen([
        "ffmpeg",
        "-ss", str(clip_start),
        "-to", str(clip_end),
        "-i", video_path,
        "-f", "rawvideo",
        "-pix_fmt", "rgb24",
        "-an",          # no audio in this pipe
        "-"
    ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # --- Step 3: pipe modified frames into ffmpeg for re-encoding ---
    encoder = subprocess.Popen([
        "ffmpeg", "-y",
        # Video from stdin
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{W}x{H}",
        "-r", str(fps),
        "-i", "-",
        # Audio from original file at the right offset
        "-ss", str(clip_start),
        "-to", str(clip_end),
        "-i", video_path,
        "-map", "0:v",
        "-map", "1:a?",     # ? = ok if no audio stream
        "-c:v", "libx264",
        "-c:a", "aac",
        "-movflags", "+faststart",
        out_path
    ], stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)

    # --- Step 4: process frames ---
    frame_size = W * H * 3
    frame_index = 0

    try:
        while True:
            raw = extractor.stdout.read(frame_size)
            if len(raw) < frame_size:
                break  # EOF

            img = Image.frombytes("RGB", (W, H), raw)

            # Find which caption event is active at this frame's timestamp
            frame_time = frame_index / fps
            active = next(
                (e for e in events if e["start"] <= frame_time < e["end"]),
                None
            )

            if active:
                img = _draw_caption(img, active["text"], font)

            encoder.stdin.write(img.tobytes())
            frame_index += 1

    finally:
        extractor.stdout.close()
        extractor.wait()
        encoder.stdin.close()
        encoder.wait()