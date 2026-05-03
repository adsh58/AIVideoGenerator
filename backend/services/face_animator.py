"""
Face animator — uses FFmpeg directly (fast) instead of moviepy frame-by-frame (slow).
Ken Burns zoom effect: FFmpeg zoompan filter renders in seconds, not minutes.
"""
import os
import subprocess
import sys

import imageio_ffmpeg

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SADTALKER_DIR = os.path.join(BASE_DIR, "SadTalker")
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


def is_sadtalker_installed() -> bool:
    return (
        os.path.isdir(SADTALKER_DIR)
        and os.path.isfile(os.path.join(SADTALKER_DIR, "inference.py"))
        and os.path.isdir(os.path.join(SADTALKER_DIR, "checkpoints"))
    )


def animate_face(photo_path: str, audio_path: str, output_dir: str) -> str:
    os.makedirs(output_dir, exist_ok=True)
    if is_sadtalker_installed():
        return _run_sadtalker(photo_path, audio_path, output_dir)
    return _ken_burns_ffmpeg(photo_path, audio_path, output_dir)


def _ken_burns_ffmpeg(photo_path: str, audio_path: str, output_dir: str) -> str:
    """
    FFmpeg zoompan filter — renders in ~5 seconds regardless of video length.
    Zoom from 1.0x to 1.05x smoothly over the audio duration.
    """
    output_path = os.path.join(output_dir, "face_animated.mp4")

    # Get audio duration
    duration = _get_duration(audio_path)
    fps = 24
    total_frames = int(duration * fps)

    # zoompan: smooth zoom from 1.0 to 1.05, centered
    # z expression: starts at 1.0, increases by 0.05/total_frames each frame
    zoom_expr = f"'min(zoom+{0.05/max(total_frames,1):.8f},1.05)'"
    vf = (
        f"zoompan=z={zoom_expr}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s=720x1280:fps={fps}"
    )

    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", photo_path,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"[FaceAnimator] zoompan failed, trying simple static: {result.stderr[-300:]}")
        return _static_ffmpeg(photo_path, audio_path, output_dir)

    return output_path


def _static_ffmpeg(photo_path: str, audio_path: str, output_dir: str) -> str:
    """Fallback: static photo + audio, no zoom."""
    output_path = os.path.join(output_dir, "face_static.mp4")
    cmd = [
        FFMPEG, "-y",
        "-loop", "1",
        "-i", photo_path,
        "-i", audio_path,
        "-vf", "scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=120)
    return output_path


def _get_duration(audio_path: str) -> float:
    cmd = [
        FFMPEG.replace("ffmpeg", "ffprobe").replace("ffmpeg-win", "ffprobe-win"),
        "-v", "quiet", "-print_format", "json", "-show_format", audio_path,
    ]
    # Try ffprobe from same dir as ffmpeg
    ffprobe = os.path.join(os.path.dirname(FFMPEG), "ffprobe.exe")
    if not os.path.exists(ffprobe):
        ffprobe = FFMPEG  # fallback: use ffmpeg with stderr
    try:
        import json
        probe_cmd = [
            FFMPEG, "-i", audio_path,
            "-f", "null", "-",
        ]
        r = subprocess.run(probe_cmd, capture_output=True, text=True, timeout=10)
        # parse "Duration: HH:MM:SS.ss" from stderr
        for line in r.stderr.splitlines():
            if "Duration:" in line:
                dur_str = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = dur_str.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        pass
    return 60.0


def _run_sadtalker(photo_path: str, audio_path: str, output_dir: str) -> str:
    cmd = [
        sys.executable,
        os.path.join(SADTALKER_DIR, "inference.py"),
        "--driven_audio", audio_path,
        "--source_image", photo_path,
        "--result_dir", output_dir,
        "--still", "--preprocess", "full",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = SADTALKER_DIR
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=SADTALKER_DIR, env=env, timeout=600)
    if result.returncode != 0:
        return _ken_burns_ffmpeg(photo_path, audio_path, output_dir)
    for fname in os.listdir(output_dir):
        if fname.endswith(".mp4"):
            return os.path.join(output_dir, fname)
    return _ken_burns_ffmpeg(photo_path, audio_path, output_dir)
