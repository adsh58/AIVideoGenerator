import os
import asyncio
import traceback
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import VideoJob
from backend.services import script_service, tts_service, face_animator, video_composer

router = APIRouter(prefix="/api/generate", tags=["generate"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ALLOWED_VIDEO_TYPES = {"short", "reel", "long"}


class GenerateRequest(BaseModel):
    title: str = "My Video"
    photo_path: str
    voice_path: str
    script_prompt: str
    background_prompt: str
    video_type: str = "short"
    video_length: int = 60

    @field_validator("video_type")
    @classmethod
    def check_type(cls, v):
        if v not in ALLOWED_VIDEO_TYPES:
            raise ValueError(f"video_type must be one of {ALLOWED_VIDEO_TYPES}")
        return v

    @field_validator("video_length")
    @classmethod
    def check_length(cls, v):
        return max(10, min(v, 600))


class ScriptPreviewRequest(BaseModel):
    script_prompt: str
    video_type: str = "short"
    video_length: int = 60


def _update_job(db: Session, job_id: int, **kwargs):
    db.query(VideoJob).filter(VideoJob.id == job_id).update(kwargs)
    db.commit()


async def run_pipeline(job_id: int):
    """Full video generation pipeline running as a background task."""
    db = None
    try:
        from backend.database import SessionLocal
        db = SessionLocal()

        job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
        if not job:
            return

        out_dir = os.path.join(BASE_DIR, "uploads", "videos", f"job_{job_id}")
        os.makedirs(out_dir, exist_ok=True)
        loop = asyncio.get_running_loop()

        # ── Step 1: Generate script ──────────────────────────────────────
        _update_job(db, job_id, status="generating_script", progress=10)
        script = await script_service.generate_script(
            job.script_prompt, job.video_type, job.video_length
        )
        if not script or len(script.strip()) < 10:
            raise ValueError("Script generation returned empty result")
        _update_job(db, job_id, generated_script=script, progress=25)

        # ── Step 2: Voice synthesis ──────────────────────────────────────
        _update_job(db, job_id, status="generating_audio", progress=30)
        audio_path = os.path.join(out_dir, "speech.wav")
        await loop.run_in_executor(
            None, tts_service.generate_speech, script, job.voice_path, audio_path, job.script_prompt
        )
        if not os.path.exists(audio_path) or os.path.getsize(audio_path) < 1000:
            raise ValueError("Audio generation failed or produced empty file")
        _update_job(db, job_id, audio_path=audio_path, progress=55)

        # ── Step 3: Face animation ───────────────────────────────────────
        _update_job(db, job_id, status="animating_face", progress=60)
        face_dir = os.path.join(out_dir, "face")
        face_video = await loop.run_in_executor(
            None, face_animator.animate_face, job.photo_path, audio_path, face_dir, job.video_type
        )
        if not os.path.exists(face_video) or os.path.getsize(face_video) < 1000:
            raise ValueError("Face animation failed or produced empty file")
        _update_job(db, job_id, animated_face_path=face_video, progress=80)

        # ── Step 4: Compose final video ──────────────────────────────────
        _update_job(db, job_id, status="composing_video", progress=85)
        final_path = os.path.join(out_dir, "final.mp4")
        await loop.run_in_executor(
            None, video_composer.compose_video,
            face_video, job.background_prompt, job.video_type, final_path, script
        )
        if not os.path.exists(final_path) or os.path.getsize(final_path) < 1000:
            raise ValueError("Video composition failed or produced empty file")

        _update_job(
            db, job_id,
            status="completed",
            progress=100,
            final_video_path=final_path,
            completed_at=datetime.utcnow(),
        )

    except Exception as e:
        err = f"{type(e).__name__}: {e}"
        print(f"[Pipeline] Job {job_id} failed:\n{traceback.format_exc()}")
        if db:
            _update_job(db, job_id, status="failed", error_message=err, progress=0)
    finally:
        if db:
            db.close()


@router.post("/video")
async def create_video_job(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if not os.path.exists(req.photo_path):
        raise HTTPException(400, "Photo file not found. Please re-upload your photo.")
    if not os.path.exists(req.voice_path):
        raise HTTPException(400, "Voice file not found. Please re-upload your voice sample.")
    if not req.script_prompt.strip():
        raise HTTPException(400, "Script prompt cannot be empty.")
    if not req.background_prompt.strip():
        raise HTTPException(400, "Background prompt cannot be empty.")

    job = VideoJob(
        title=req.title.strip() or "My Video",
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
async def preview_script(req: ScriptPreviewRequest):
    """Generate a script preview — does NOT require photo or voice."""
    script = await script_service.generate_script(
        req.script_prompt, req.video_type, req.video_length
    )
    return JSONResponse({"script": script})
