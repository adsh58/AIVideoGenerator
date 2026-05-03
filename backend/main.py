import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import upload, generate, videos

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app = FastAPI(title="AI Video Generator", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)
app.include_router(generate.router)
app.include_router(videos.router)

# Serve uploaded files
uploads_dir = os.path.join(BASE_DIR, "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

# Serve frontend
frontend_dir = os.path.join(BASE_DIR, "frontend")
app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dir, "assets")), name="assets")


@app.get("/")
def read_root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))


@app.on_event("startup")
def startup_event():
    init_db()
    print("✅ Database initialized")
    print("🚀 AI Video Generator running at http://localhost:8000")
