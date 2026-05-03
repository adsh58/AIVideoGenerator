import os
import re
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    from moviepy.editor import (
        VideoFileClip, ImageClip, AudioFileClip,
        CompositeVideoClip, TextClip, ColorClip,
    )
except ImportError:
    from moviepy import (
        VideoFileClip, ImageClip, AudioFileClip,
        CompositeVideoClip, TextClip, ColorClip,
    )

# Video format specs
FORMAT_SPECS = {
    "short": {"width": 1080, "height": 1920, "fps": 30},  # 9:16 vertical
    "reel":  {"width": 1080, "height": 1920, "fps": 30},  # 9:16 vertical
    "long":  {"width": 1920, "height": 1080, "fps": 30},  # 16:9 horizontal
}


def compose_video(
    face_video_path: str,
    background_prompt: str,
    video_type: str,
    output_path: str,
    script_text: str = "",
) -> str:
    """Compose the final video: background + face overlay + captions."""
    spec = FORMAT_SPECS.get(video_type, FORMAT_SPECS["reel"])
    W, H, FPS = spec["width"], spec["height"], spec["fps"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    face_clip = VideoFileClip(face_video_path)
    duration = face_clip.duration

    # 1. Generate background
    bg_image = _generate_background(background_prompt, W, H)
    bg_path = output_path.replace(".mp4", "_bg.jpg")
    bg_image.save(bg_path, quality=95)
    _bg = ImageClip(bg_path)
    bg_clip = _bg.with_duration(duration) if hasattr(_bg, 'with_duration') else _bg.set_duration(duration)

    # 2. Position face video
    if video_type in ("short", "reel"):
        face_clip = _fit_face_vertical(face_clip, W, H)
    else:
        face_clip = _fit_face_horizontal(face_clip, W, H)

    # 3. Add captions if script provided
    clips = [bg_clip, face_clip]
    if script_text:
        caption_clips = _make_caption_clips(script_text, duration, W, H, video_type)
        clips.extend(caption_clips)

    # 4. Compose and export
    final = CompositeVideoClip(clips, size=(W, H))
    if face_clip.audio:
        final = final.with_audio(face_clip.audio) if hasattr(final, 'with_audio') else final.set_audio(face_clip.audio)

    write_kwargs = dict(fps=FPS, codec="libx264", audio_codec="aac", threads=4, logger=None)
    import inspect
    if "preset" in inspect.signature(final.write_videofile).parameters:
        write_kwargs["preset"] = "fast"
    final.write_videofile(output_path, **write_kwargs)

    # Cleanup temp bg
    if os.path.exists(bg_path):
        os.remove(bg_path)

    return output_path


def _generate_background(prompt: str, width: int, height: int) -> Image.Image:
    """
    Generate a background image based on the prompt.
    Creates atmospheric gradient + text description overlay.
    """
    prompt_lower = prompt.lower()

    # Color palette based on keywords
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

    # Multi-stop gradient
    for y in range(height):
        ratio = y / height
        if ratio < 0.5:
            t = ratio * 2
            r = int(colors[0][0] + (colors[1][0] - colors[0][0]) * t)
            g = int(colors[0][1] + (colors[1][1] - colors[0][1]) * t)
            b = int(colors[0][2] + (colors[1][2] - colors[0][2]) * t)
        else:
            t = (ratio - 0.5) * 2
            r = int(colors[1][0] + (colors[2][0] - colors[1][0]) * t)
            g = int(colors[1][1] + (colors[2][1] - colors[1][1]) * t)
            b = int(colors[1][2] + (colors[2][2] - colors[1][2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Add bokeh light effects
    img = _add_bokeh(img, colors)

    # Slight blur for depth
    img = img.filter(ImageFilter.GaussianBlur(radius=3))

    return img


def _add_bokeh(img: Image.Image, colors: list) -> Image.Image:
    """Add soft circular light spots for bokeh effect."""
    import random
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    random.seed(42)

    base_color = colors[-1]
    for _ in range(30):
        x = random.randint(0, img.width)
        y = random.randint(0, img.height)
        r = random.randint(40, 200)
        alpha = random.randint(10, 40)
        light_r = min(255, base_color[0] + 80)
        light_g = min(255, base_color[1] + 60)
        light_b = min(255, base_color[2] + 40)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(light_r, light_g, light_b, alpha))

    img = img.convert("RGBA")
    img = Image.alpha_composite(img, overlay)
    return img.convert("RGB")


def _compat(clip, **kwargs):
    """Works with both moviepy 1.x (set_X) and 2.x (with_X)."""
    for k, v in kwargs.items():
        fn = f"with_{k}" if hasattr(clip, f"with_{k}") else f"set_{k}"
        clip = getattr(clip, fn)(v)
    return clip


def _resize(clip, new_size):
    """moviepy 1.x: .resize(), moviepy 2.x: .resized()."""
    if hasattr(clip, 'resized'):
        return clip.resized(new_size)
    return clip.resize(new_size)


def _fit_face_vertical(clip: VideoFileClip, W: int, H: int) -> VideoFileClip:
    """Position face for vertical (9:16) video — centered, upper 70%."""
    face_h = int(H * 0.72)
    scale = face_h / clip.h
    new_w = int(clip.w * scale)
    clip = _resize(clip, (new_w, face_h))
    x = (W - new_w) // 2
    y = int(H * 0.02)
    return _compat(clip, position=(x, y))


def _fit_face_horizontal(clip: VideoFileClip, W: int, H: int) -> VideoFileClip:
    """Position face for horizontal (16:9) — left side."""
    face_h = int(H * 0.85)
    scale = face_h / clip.h
    new_w = int(clip.w * scale)
    clip = _resize(clip, (new_w, face_h))
    x = int(W * 0.05)
    y = (H - face_h) // 2
    return _compat(clip, position=(x, y))


def _make_caption_clips(script: str, duration: float, W: int, H: int, video_type: str) -> list:
    """Split script into timed caption segments."""
    words = script.split()
    if not words:
        return []

    words_per_second = len(words) / duration
    chunk_size = max(5, int(words_per_second * 3))  # ~3 sec per caption
    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]

    clips = []
    time_per_chunk = duration / len(chunks)
    font_size = 52 if video_type in ("short", "reel") else 40
    y_pos = int(H * 0.80) if video_type in ("short", "reel") else int(H * 0.85)

    for i, chunk in enumerate(chunks):
        text = " ".join(chunk)
        start = i * time_per_chunk
        end = min(start + time_per_chunk, duration)
        chunk_dur = end - start

        try:
            txt_clip = TextClip(
                text,
                fontsize=font_size,
                color="white",
                stroke_color="black",
                stroke_width=2,
                method="caption",
                size=(int(W * 0.9), None),
                font="Arial-Bold",
            )
            txt_clip = _compat(txt_clip, start=start, duration=chunk_dur, position=("center", y_pos))
            clips.append(txt_clip)
        except Exception as e:
            print(f"[Caption] Skipping caption chunk {i}: {e}")

    return clips
