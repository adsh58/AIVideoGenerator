import os
import subprocess
import sys
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SADTALKER_DIR = os.path.join(BASE_DIR, "SadTalker")


def is_sadtalker_installed() -> bool:
    return (
        os.path.isdir(SADTALKER_DIR)
        and os.path.isfile(os.path.join(SADTALKER_DIR, "inference.py"))
        and os.path.isdir(os.path.join(SADTALKER_DIR, "checkpoints"))
    )


def animate_face(photo_path: str, audio_path: str, output_dir: str) -> str:
    """
    Animate a face photo with audio using SadTalker.
    Returns path to the generated video.
    """
    os.makedirs(output_dir, exist_ok=True)

    if is_sadtalker_installed():
        return _run_sadtalker(photo_path, audio_path, output_dir)
    else:
        print("[FaceAnimator] SadTalker not found. Using static photo fallback.")
        return _static_photo_video(photo_path, audio_path, output_dir)


def _run_sadtalker(photo_path: str, audio_path: str, output_dir: str) -> str:
    python_exec = sys.executable
    cmd = [
        python_exec,
        os.path.join(SADTALKER_DIR, "inference.py"),
        "--driven_audio", audio_path,
        "--source_image", photo_path,
        "--result_dir", output_dir,
        "--still",
        "--preprocess", "full",
        "--enhancer", "gfpgan",
    ]

    env = os.environ.copy()
    env["PYTHONPATH"] = SADTALKER_DIR

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=SADTALKER_DIR,
        env=env,
        timeout=600,
    )

    if result.returncode != 0:
        print(f"[SadTalker] Error: {result.stderr}")
        return _static_photo_video(photo_path, audio_path, output_dir)

    # Find the output video (SadTalker saves to output_dir/*.mp4)
    for fname in os.listdir(output_dir):
        if fname.endswith(".mp4"):
            return os.path.join(output_dir, fname)

    return _static_photo_video(photo_path, audio_path, output_dir)


def _static_photo_video(photo_path: str, audio_path: str, output_dir: str) -> str:
    """
    Fallback: create a video from the static photo + audio.
    Adds a subtle zoom/pan (Ken Burns effect) to make it look dynamic.
    """
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips
    from moviepy.video.fx.all import resize
    import numpy as np
    from PIL import Image

    audio = AudioFileClip(audio_path)
    duration = audio.duration

    img = Image.open(photo_path).convert("RGB")
    w, h = img.size
    aspect = w / h
    target_h = 1080
    target_w = int(target_h * aspect)
    img = img.resize((target_w, target_h), Image.LANCZOS)
    img_array = np.array(img)

    # Ken Burns: slight zoom in over duration
    def make_frame(t):
        progress = t / duration
        scale = 1.0 + 0.05 * progress  # zoom from 100% to 105%
        new_w = int(target_w * scale)
        new_h = int(target_h * scale)
        pil = Image.fromarray(img_array).resize((new_w, new_h), Image.LANCZOS)
        left = (new_w - target_w) // 2
        top = (new_h - target_h) // 2
        cropped = pil.crop((left, top, left + target_w, top + target_h))
        return np.array(cropped)

    from moviepy.editor import VideoClip
    clip = VideoClip(make_frame, duration=duration)
    clip = clip.set_audio(audio)

    output_path = os.path.join(output_dir, "face_animated.mp4")
    clip.write_videofile(
        output_path,
        fps=24,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
    return output_path
