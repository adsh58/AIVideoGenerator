import os
import uuid
import shutil
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")

router = APIRouter(prefix="/api/upload", tags=["upload"])

ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_AUDIO = {".mp3", ".wav", ".m4a", ".ogg", ".webm"}


def _save_file(file: UploadFile, subfolder: str, allowed_exts: set) -> dict:
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed_exts:
        raise HTTPException(400, f"File type {ext} not allowed. Use: {allowed_exts}")

    dest_dir = os.path.join(UPLOAD_DIR, subfolder)
    os.makedirs(dest_dir, exist_ok=True)
    filename = f"{uuid.uuid4()}{ext}"
    dest_path = os.path.join(dest_dir, filename)

    with open(dest_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    return {"path": dest_path, "filename": filename, "url": f"/uploads/{subfolder}/{filename}"}


@router.post("/photo")
async def upload_photo(file: UploadFile = File(...)):
    result = _save_file(file, "photos", ALLOWED_IMAGE)
    return JSONResponse({"success": True, **result})


@router.post("/voice")
async def upload_voice(file: UploadFile = File(...)):
    result = _save_file(file, "voices", ALLOWED_AUDIO)
    return JSONResponse({"success": True, **result})
