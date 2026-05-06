"""
Face animator — FFmpeg zoompan filter.
Renders a Ken Burns (gentle zoom) effect over the audio duration.
Completes in ~2-6s regardless of video length.
"""
import os
import subprocess
import sys

import imageio_ffmpeg

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SADTALKER_DIR = os.path.join(BASE_DIR, "SadTalker")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# Output resolution per video type
RESOLUTIONS = {
    "short": (720, 1280),
    "reel":  (720, 1280),
    "long":  (1280, 720),
}


def is_sadtalker_installed() -> bool:
    if not os.path.isdir(SADTALKER_DIR):
        return False
    if not os.path.isfile(os.path.join(SADTALKER_DIR, "inference.py")):
        return False
    ckpt_dir = os.path.join(SADTALKER_DIR, "checkpoints")
    if not os.path.isdir(ckpt_dir):
        return False
    # Need at least the main safetensors model
    safetensors = [f for f in os.listdir(ckpt_dir) if f.endswith(".safetensors") and os.path.getsize(os.path.join(ckpt_dir, f)) > 1_000_000]
    return len(safetensors) > 0


def animate_face(photo_path: str, audio_path: str, output_dir: str,
                 video_type: str = "short") -> str:
    """Animate photo with audio. Returns path to output video."""
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(photo_path):
        raise FileNotFoundError(f"Photo not found: {photo_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio not found: {audio_path}")

    if is_sadtalker_installed():
        print("[FaceAnimator] SadTalker detected — generating lip-sync animation (may take 5-15 min on CPU)")
        return _run_sadtalker(photo_path, audio_path, output_dir, video_type)

    print("[FaceAnimator] SadTalker not ready — using Ken Burns zoom effect")
    return _ken_burns_ffmpeg(photo_path, audio_path, output_dir, video_type)


def _ken_burns_ffmpeg(photo_path: str, audio_path: str, output_dir: str,
                      video_type: str = "short") -> str:
    """
    Gentle zoom effect using FFmpeg zoompan filter.
    ~2-6s for any video length because FFmpeg does it natively.
    """
    W, H = RESOLUTIONS.get(video_type, (720, 1280))
    output_path = os.path.join(output_dir, "face_animated.mp4")

    duration = _get_audio_duration(audio_path)
    fps = 24
    total_frames = max(1, int(duration * fps))
    zoom_step = round(0.05 / total_frames, 8)

    # zoompan: zoom from 1.0 → 1.05 smoothly, centered
    zoom_expr = f"min(zoom+{zoom_step},1.05)"
    vf = (
        f"zoompan=z='{zoom_expr}'"
        f":x='iw/2-(iw/zoom/2)'"
        f":y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={W}x{H}:fps={fps}"
    )

    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", photo_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"[FaceAnimator] zoompan failed: {result.stderr[-300:]}")
        return _static_ffmpeg(photo_path, audio_path, output_dir, W, H)

    return output_path


def _static_ffmpeg(photo_path: str, audio_path: str, output_dir: str,
                   W: int = 720, H: int = 1280) -> str:
    """Fallback: photo + audio, no zoom, scale to fit."""
    output_path = os.path.join(output_dir, "face_static.mp4")
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2"
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", photo_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Static video fallback also failed: {result.stderr[-300:]}")
    return output_path


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using FFmpeg."""
    result = subprocess.run(
        [FFMPEG, "-i", audio_path, "-f", "null", "-"],
        capture_output=True, text=True, timeout=15
    )
    for line in result.stderr.splitlines():
        if "Duration:" in line:
            try:
                d = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = d.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                pass
    return 60.0


def _run_sadtalker(photo_path: str, audio_path: str, output_dir: str,
                   video_type: str = "short") -> str:
    """Use SadTalker for realistic lip-sync."""
    import torch
    use_gpu = torch.cuda.is_available()

    # CPU mode: 256px + crop is 3-4x faster than 512 + full
    size = "512" if use_gpu else "256"
    preprocess = "full" if use_gpu else "crop"

    cmd = [
        sys.executable,
        os.path.join(SADTALKER_DIR, "inference.py"),
        "--driven_audio", audio_path,
        "--source_image", photo_path,
        "--result_dir", output_dir,
        "--still",
        "--preprocess", preprocess,
        "--size", size,
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = SADTALKER_DIR
    print(f"[SadTalker] Running on {'GPU' if use_gpu else 'CPU'} (size={size}, preprocess={preprocess})")

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        cwd=SADTALKER_DIR, env=env, timeout=1800
    )

    if result.returncode == 0:
        # SadTalker may output to a subdirectory — search recursively
        for root, _, files in os.walk(output_dir):
            for fname in files:
                if fname.endswith(".mp4"):
                    return os.path.join(root, fname)

    print(f"[SadTalker] returncode={result.returncode}")
    print(f"[SadTalker] stderr: {result.stderr[-500:]}")
    print("[SadTalker] Falling back to Ken Burns")
    return _ken_burns_ffmpeg(photo_path, audio_path, output_dir, video_type)
