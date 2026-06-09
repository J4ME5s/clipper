from faster_whisper import WhisperModel
import subprocess
import ollama
import json
import os
import librosa
import numpy as np


# ── 1. Transcription ──────────────────────────────────────────────────────────

def transcribe(video_path: str) -> list[dict]:
    model = WhisperModel("base", device="auto", compute_type="int8")
    segments, _ = model.transcribe(video_path, vad_filter=True)
    return [{"start": s.start, "end": s.end, "text": s.text.strip()} for s in segments]


# ── 2. Audio energy analysis ──────────────────────────────────────────────────

def get_energy_scores(video_path: str, segments: list[dict]) -> list[dict]:
    """
    Extract audio from video and compute RMS energy for each transcript segment.
    High energy = loud reactions, hype moments, laughter.
    """
    audio_path = video_path.replace(".mp4", "_audio.wav")

    # Extract mono audio at 16kHz
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
        raise ValueError(f"No JSON array found in LLM response: {raw}")

    clips = json.loads(raw[start:end])

    # Clamp clip times to actual candidate bounds as a safety net
    valid = []
    for clip in clips:
        if clip["end"] - clip["start"] >= 10:
            valid.append(clip)
    return valid if valid else clips


# ── 5. ffmpeg cutting ─────────────────────────────────────────────────────────

def cut_clips(video_path: str, clips: list[dict], output_dir: str) -> list[str]:
    os.makedirs(output_dir, exist_ok=True)
    output_files = []

    for i, clip in enumerate(clips):
        out_path = os.path.join(output_dir, f"clip_{i + 1}.mp4")
        subprocess.run([
            "ffmpeg", "-y",
            "-ss", str(clip["start"]),
            "-to", str(clip["end"]),
            "-i", video_path,
            "-c:v", "libx264",   # re-encode for clean cuts
            "-c:a", "aac",
            "-movflags", "+faststart",
            out_path
        ], check=True)
        output_files.append(out_path)

    return output_files