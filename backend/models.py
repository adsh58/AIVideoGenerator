from sqlalchemy import Column, Integer, String, Text, DateTime, Float, Enum
from sqlalchemy.sql import func
import enum
from backend.database import Base


class VideoType(str, enum.Enum):
    short = "short"
    reel = "reel"
    long = "long"


class JobStatus(str, enum.Enum):
    pending = "pending"
    generating_script = "generating_script"
    generating_audio = "generating_audio"
    animating_face = "animating_face"
    composing_video = "composing_video"
    completed = "completed"
    failed = "failed"


class Project(Base):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    photo_path = Column(String(500))
    voice_path = Column(String(500))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, nullable=True)
    title = Column(String(255), default="Untitled Video")

    # Inputs
    photo_path = Column(String(500))
    voice_path = Column(String(500))
    script_prompt = Column(Text)
    background_prompt = Column(Text)
    video_type = Column(String(50), default="reel")
    video_length = Column(Integer, default=60)  # seconds

    # Generated content
    generated_script = Column(Text)
    audio_path = Column(String(500))
    animated_face_path = Column(String(500))
    background_path = Column(String(500))
    final_video_path = Column(String(500))

    # Status
    status = Column(String(50), default="pending")
    progress = Column(Integer, default=0)  # 0-100
    error_message = Column(Text)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
