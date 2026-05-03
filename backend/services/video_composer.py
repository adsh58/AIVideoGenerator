import os
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from moviepy import (
    VideoFileClip, ImageClip, AudioFileClip,
    CompositeVideoClip, TextClip,
)

FORMAT_SPECS = {
    "short": {"width": 1080, "height": 1920, "fps": 30},
    "reel":  {"width": 1080, "height": 1920, "fps": 30},
    "long":  {"width": 1920, "height": 1080, "fps": 30},
}


def compose_video(
    face_video_path: str,
    background_prompt: str,
    video_type: str,
    output_path: str,
    script_text: str = "",
) -> str:
    spec = FORMAT_SPECS.get(video_type, FORMAT_SPECS["reel"])
    W, H, FPS = spec["width"], spec["height"], spec["fps"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    face_clip = VideoFileClip(face_video_path)
    duration = face_clip.duration

    # 1. Background
    bg_image = _generate_background(background_prompt, W, H)
    bg_path = output_path.replace(".mp4", "_bg.jpg")
    bg_image.save(bg_path, quality=95)
    bg_clip = ImageClip(bg_path).with_duration(duration)

    # 2. Resize and position face
    if video_type in ("short", "reel"):
        face_clip = _fit_face_vertical(face_clip, W, H)
    else:
        face_clip = _fit_face_horizontal(face_clip, W, H)

    # 3. Captions
    clips = [bg_clip, face_clip]
    if script_text:
        caption_clips = _make_caption_clips(script_text, duration, W, H, video_type)
        clips.extend(caption_clips)

    # 4. Compose and export
    final = CompositeVideoClip(clips, size=(W, H))
    if face_clip.audio:
        final = final.with_audio(face_clip.audio)

    final.write_videofile(
        output_path,
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="fast",
        threads=4,
        logger=None,
    )

    if os.path.exists(bg_path):
        os.remove(bg_path)

    return output_path


def _generate_background(prompt: str, width: int, height: int) -> Image.Image:
    prompt_lower = prompt.lower()

    if any(w in prompt_lower for w in ["cozy", "warm", "chair", "light", "candle", "studio"]):
        colors = [(40, 20, 10), (90, 55, 30), (140, 90, 50)]
    elif any(w in prompt_lower for w in ["night", "dark", "moody", "dramatic"]):
        colors = [(5, 5, 20), (20, 15, 45), (40, 30, 80)]
    elif any(w in prompt_lower for w in ["nature", "outdoor", "forest", "green"]):
        colors = [(10, 40, 20), (30, 80, 50), (60, 120, 80)]
    elif any(w in prompt_lower for w in ["tech", "digital", "modern", "blue"]):
        colors = [(5, 10, 30), (15, 30, 70), (30, 60, 130)]
    elif any(w in prompt_lower for w in ["bright", "light", "clean", "white"]):
        colors = [(200, 200, 210), (230, 230, 240), (245, 245, 255)]
    else:
        colors = [(15, 20, 35), (30, 40, 70), (50, 65, 110)]

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    for y in range(height):
        ratio = y / height
        if ratio < 0.5:
            t = ratio * 2
            c0, c1 = colors[0], colors[1]
        else:
            t = (ratio - 0.5) * 2
            c0, c1 = colors[1], colors[2]
        r = int(c0[0] + (c1[0] - c0[0]) * t)
        g = int(c0[1] + (c1[1] - c0[1]) * t)
        b = int(c0[2] + (c1[2] - c0[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    img = _add_bokeh(img, colors)
    img = img.filter(ImageFilter.GaussianBlur(radius=3))
    return img


def _add_bokeh(img: Image.Image, colors: list) -> Image.Image:
    import random
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    random.seed(42)
    base = colors[-1]
    for _ in range(30):
        x = random.randint(0, img.width)
        y = random.randint(0, img.height)
        r = random.randint(40, 200)
        a = random.randint(10, 40)
        lr = min(255, base[0] + 80)
        lg = min(255, base[1] + 60)
        lb = min(255, base[2] + 40)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(lr, lg, lb, a))
    img = Image.alpha_composite(img.convert("RGBA"), overlay)
    return img.convert("RGB")


def _fit_face_vertical(clip: VideoFileClip, W: int, H: int) -> VideoFileClip:
    face_h = int(H * 0.72)
    scale = face_h / clip.h
    new_w = int(clip.w * scale)
    clip = clip.resized((new_w, face_h))
    x = (W - new_w) // 2
    y = int(H * 0.02)
    return clip.with_position((x, y))


def _fit_face_horizontal(clip: VideoFileClip, W: int, H: int) -> VideoFileClip:
    face_h = int(H * 0.85)
    scale = face_h / clip.h
    new_w = int(clip.w * scale)
    clip = clip.resized((new_w, face_h))
    x = int(W * 0.05)
    y = (H - face_h) // 2
    return clip.with_position((x, y))


def _find_font() -> str:
    """Return a font path that definitely exists on this system."""
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
        "C:/Windows/Fonts/calibri.ttf",
        "C:/Windows/Fonts/segoeui.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return "Arial"  # last resort


def _make_caption_clips(script: str, duration: float, W: int, H: int, video_type: str) -> list:
    words = script.split()
    if not words:
        return []

    words_per_second = len(words) / duration
    chunk_size = max(5, int(words_per_second * 3))
    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

    clips = []
    time_per_chunk = duration / len(chunks)
    font_size = 52 if video_type in ("short", "reel") else 40
    y_pos = int(H * 0.80) if video_type in ("short", "reel") else int(H * 0.85)

    for i, chunk in enumerate(chunks):
        text = " ".join(chunk)
        start = i * time_per_chunk
        chunk_dur = min(time_per_chunk, duration - start)

        try:
            font_path = _find_font()
            txt_clip = (
                TextClip(
                    font=font_path,
                    text=text,
                    font_size=font_size,
                    color="white",
                    stroke_color="black",
                    stroke_width=2,
                    method="caption",
                    size=(int(W * 0.9), None),
                )
                .with_start(start)
                .with_duration(chunk_dur)
                .with_position(("center", y_pos))
            )
            clips.append(txt_clip)
        except Exception as e:
            print(f"[Caption] Skipping chunk {i}: {e}")

    return clips
