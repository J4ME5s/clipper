from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import shutil, os, uuid
from pipeline import transcribe, get_energy_scores, pick_clips, cut_clips
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/process")
async def process_video(file: UploadFile = File(...)):
    job_id = str(uuid.uuid4())
    upload_path = f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs/{job_id}_{file.filename}"
    output_dir = f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs/{job_id}_clips"

    os.makedirs(f"/Users/jamesshin/Desktop/dump/Projects/clipper/outputs", exist_ok=True)

    with open(upload_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    segments = transcribe(upload_path)
    scored_segments = get_energy_scores(upload_path, segments)
    clips = pick_clips(scored_segments)
    clip_files = cut_clips(upload_path, clips, output_dir)

    return {
        "job_id": job_id,
        "clips": [
            {"file": os.path.basename(f), "reason": clips[i].get("reason", "highlight moment")}
            for i, f in enumerate(clip_files)
        ]
    }

@app.get("/clips/{job_id}/{filename}")
def download_clip(job_id: str, filename: str):
    path = f"/tmp/{job_id}_clips/{filename}"
    return FileResponse(path, media_type="video/mp4", filename=filename)