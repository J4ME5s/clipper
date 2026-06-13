from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import shutil, os, uuid
import yt_dlp
from pipeline import transcribe, get_energy_scores, pick_clips, cut_clips

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Parse a "mm:ss" or "hh:mm:ss" string into total seconds
def parse_timestamp(ts: str) -> float:
    parts = ts.strip().split(":")
    parts = [float(p) for p in parts]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"Invalid timestamp: {ts}")

# Download a YouTube/Twitch URL using yt-dlp, optionally trimming to a time range
def download_url(url: str, output_path: str, start_time: Optional[str], end_time: Optional[str]):
    ydl_opts = {
        "format": "best[ext=mp4]/best",
        "outtmpl": output_path,
        "quiet": True,
    }

    # If timestamps are provided, only download that section
    if start_time and end_time:
        start_sec = parse_timestamp(start_time)
        end_sec = parse_timestamp(end_time)
        ydl_opts["download_ranges"] = yt_dlp.utils.download_range_func(
            None, [(start_sec, end_sec)]
        )
        ydl_opts["force_keyframes_at_cuts"] = True

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])


@app.post("/process")
async def process_video(
    # File upload (optional — either file or url must be provided)
    file: Optional[UploadFile] = File(None),
    # URL fields
    url: Optional[str] = Form(None),
    start_time: Optional[str] = Form(None),
    end_time: Optional[str] = Form(None),
):
    job_id = str(uuid.uuid4())
    output_dir = f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs/{job_id}_clips"
    video_path = f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs/{job_id}_input.mp4"

    os.makedirs(f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs", exist_ok=True)

    if url:
        # Download from URL, with optional timestamp trimming
        download_url(url, video_path, start_time, end_time)
    elif file:
        # Save uploaded file to disk
        with open(video_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
    else:
        return {"error": "Provide either a file or a URL"}

    segments = transcribe(video_path)
    scored_segments = get_energy_scores(video_path, segments)
    clips = pick_clips(scored_segments)
    clip_files = cut_clips(video_path, clips, output_dir)

    # Clean up the input file after processing
    os.remove(video_path)

    return {
        "job_id": job_id,
        "clips": [
            {"file": os.path.basename(f), "reason": clips[i].get("reason", "highlight moment")}
            for i, f in enumerate(clip_files)
        ]
    }


@app.get("/clips/{job_id}/{filename}")
def download_clip(job_id: str, filename: str):
    path = f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs/{job_id}_clips/{filename}"
    return FileResponse(path, media_type="video/mp4", filename=filename)