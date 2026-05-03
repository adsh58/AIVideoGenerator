import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import VideoJob

router = APIRouter(prefix="/api/videos", tags=["videos"])


def _job_to_dict(job: VideoJob) -> dict:
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "progress": job.progress,
        "video_type": job.video_type,
        "video_length": job.video_length,
        "generated_script": job.generated_script,
        "final_video_url": f"/api/videos/{job.id}/download" if job.final_video_path else None,
        "error_message": job.error_message,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


@router.get("")
def list_videos(db: Session = Depends(get_db)):
    jobs = db.query(VideoJob).order_by(VideoJob.id.desc()).all()
    return JSONResponse({"videos": [_job_to_dict(j) for j in jobs]})


@router.get("/{job_id}")
def get_video(job_id: int, db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Video not found")
    return JSONResponse(_job_to_dict(job))


@router.get("/{job_id}/download")
def download_video(job_id: int, db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job or not job.final_video_path:
        raise HTTPException(404, "Video not ready")
    if not os.path.exists(job.final_video_path):
        raise HTTPException(404, "Video file not found on disk")
    return FileResponse(
        job.final_video_path,
        media_type="video/mp4",
        filename=f"{job.title.replace(' ', '_')}.mp4",
    )


@router.delete("/{job_id}")
def delete_video(job_id: int, db: Session = Depends(get_db)):
    job = db.query(VideoJob).filter(VideoJob.id == job_id).first()
    if not job:
        raise HTTPException(404, "Video not found")
    if job.final_video_path and os.path.exists(job.final_video_path):
        import shutil
        parent = os.path.dirname(job.final_video_path)
        shutil.rmtree(parent, ignore_errors=True)
    db.delete(job)
    db.commit()
    return JSONResponse({"success": True})
