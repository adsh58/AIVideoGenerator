import os
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import VideoJob

router = APIRouter(prefix="/api/generate", tags=["generate"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class GenerateRequest(BaseModel):
    title: str = "My Video"
    photo_path: str
    voice_path: str
    script_prompt: str
    background_prompt: str
    video_type: str = "reel"   # short | reel | long
    video_length: int = 60     # seconds


def _update_job(db: Session, job_id: int, **kwargs):
    db.query(VideoJob).filter(VideoJob.id == job_id).update(kwargs)
    db.commit()


async def run_pipeline(job_id: int):
    """Full async video generation pipeline."""
    from backend.database import SessionLocal
    from backend.services.script_service import generate_script
    from backend.services.tts_service import generate_speech
    from backend.services.face_animator import animate_face
    from backend.services.video_composer import compose_video

    db = SessionLocal()
    try:
        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if not job:
            return

        out_dir = os.path.join(BASE_DIR, "uploads", "videos", f"job_{job_id}")
        os.makedirs(out_dir, exist_ok=True)

        # Step 1: Generate script
        _update_job(db, job_id, status="generating_script", progress=10)
        script = await generate_script(job.script_prompt, job.video_type, job.video_length)
        _update_job(db, job_id, generated_script=script, progress=25)

        # Step 2: Generate audio (voice cloning)
        _update_job(db, job_id, status="generating_audio", progress=30)
        audio_path = os.path.join(out_dir, "speech.wav")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: __import__("backend.services.tts_service", fromlist=["generate_speech"]).generate_speech(
                script, job.voice_path, audio_path
            ),
        )
        _update_job(db, job_id, audio_path=audio_path, progress=55)

        # Step 3: Face animation
        _update_job(db, job_id, status="animating_face", progress=60)
        face_dir = os.path.join(out_dir, "face")
        face_video = await loop.run_in_executor(
            None,
            lambda: __import__("backend.services.face_animator", fromlist=["animate_face"]).animate_face(
                job.photo_path, audio_path, face_dir
            ),
        )
        _update_job(db, job_id, animated_face_path=face_video, progress=80)

        # Step 4: Compose final video
        _update_job(db, job_id, status="composing_video", progress=85)
        final_path = os.path.join(out_dir, "final.mp4")
        await loop.run_in_executor(
            None,
            lambda: __import__("backend.services.video_composer", fromlist=["compose_video"]).compose_video(
                face_video,
                job.background_prompt,
                job.video_type,
                final_path,
                script,
            ),
        )

        _update_job(
            db, job_id,
            status="completed",
            progress=100,
            final_video_path=final_path,
            completed_at=datetime.utcnow(),
        )

    except Exception as e:
        _update_job(db, job_id, status="failed", error_message=str(e), progress=0)
        print(f"[Pipeline] Job {job_id} failed: {e}")
    finally:
        db.close()


@router.post("/video")
async def create_video_job(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not os.path.exists(req.photo_path):
        raise HTTPException(400, "Photo file not found")
    if not os.path.exists(req.voice_path):
        raise HTTPException(400, "Voice file not found")

    job = VideoJob(
        title=req.title,
        photo_path=req.photo_path,
        voice_path=req.voice_path,
        script_prompt=req.script_prompt,
        background_prompt=req.background_prompt,
        video_type=req.video_type,
        video_length=req.video_length,
        status="pending",
        progress=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    background_tasks.add_task(run_pipeline, job.id)

    return JSONResponse({"success": True, "job_id": job.id, "status": "pending"})


@router.post("/script-preview")
async def preview_script(req: GenerateRequest):
    """Quick script preview without starting full pipeline."""
    from backend.services.script_service import generate_script
    script = await generate_script(req.script_prompt, req.video_type, req.video_length)
    return JSONResponse({"script": script})
