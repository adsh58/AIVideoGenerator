"""
Video composer — FFmpeg filter_complex with -loop 1 on background image.
Using -loop 1 on the input (not the loop filter) is ~10x faster.
"""
import os
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFilter

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

FORMAT_SPECS = {
    "short": {"width": 720,  "height": 1280, "fps": 24},
    "reel":  {"width": 720,  "height": 1280, "fps": 24},
    "long":  {"width": 1280, "height": 720,  "fps": 24},
}


def compose_video(
    face_video_path: str,
    background_prompt: str,
    video_type: str,
    output_path: str,
    script_text: str = "",
) -> str:
    spec = FORMAT_SPECS.get(video_type, FORMAT_SPECS["short"])
    W, H = spec["width"], spec["height"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. Generate background image
    bg_image = _generate_background(background_prompt, W, H)
    bg_path = output_path.replace(".mp4", "_bg.jpg")
    bg_image.save(bg_path, quality=92)

    # 2. Get face video duration
    duration = _get_video_duration(face_video_path)

    # 3. Write subtitle file
    srt_path = None
    if script_text.strip():
        srt_path = output_path.replace(".mp4", ".srt")
        _write_srt(script_text, duration, srt_path)

    # 4. Compose
    try:
        _compose_ffmpeg(face_video_path, bg_path, srt_path, output_path, W, H, video_type)
    except Exception as e:
        print(f"[Composer] Primary compose failed ({e}), trying fallback...")
        _compose_fallback(face_video_path, bg_path, output_path, W, H, video_type)

    # 5. Cleanup temp files
    for p in [bg_path, srt_path]:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
        raise RuntimeError("FFmpeg produced no valid output file")

    return output_path


def _compose_ffmpeg(face_path, bg_path, srt_path, output_path, W, H, video_type):
    """
    Key: -loop 1 on background image = FFmpeg loops it natively (fast).
    No 'loop' video filter needed — that was the 21s bottleneck.
    """
    if video_type in ("short", "reel"):
        face_h = int(H * 0.72)
        x_pos = "(main_w-overlay_w)/2"
        y_pos = str(int(H * 0.02))
    else:
        face_h = int(H * 0.85)
        x_pos = str(int(W * 0.05))
        y_pos = "(main_h-overlay_h)/2"

    # Build subtitle filter safely
    sub_filter = _build_subtitle_filter(srt_path)

    filter_complex = (
        f"[0:v]scale={W}:{H}[bg];"
        f"[1:v]scale=-2:{face_h}[face];"
        f"[bg][face]overlay={x_pos}:{y_pos}{sub_filter}[out]"
    )

    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-framerate", "24", "-i", bg_path,   # bg image, looped natively
        "-i", face_path,                                     # face video
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-500:])


def _compose_fallback(face_path, bg_path, output_path, W, H, video_type):
    """Simplest possible compose — no subtitles, just overlay."""
    if video_type in ("short", "reel"):
        face_h = int(H * 0.72)
        pos = f"(main_w-overlay_w)/2:{int(H * 0.02)}"
    else:
        face_h = int(H * 0.85)
        pos = f"{int(W * 0.05)}:(main_h-overlay_h)/2"

    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-framerate", "24", "-i", bg_path,
        "-i", face_path,
        "-filter_complex",
        f"[0:v]scale={W}:{H}[bg];[1:v]scale=-2:{face_h}[face];[bg][face]overlay={pos}[out]",
        "-map", "[out]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Fallback compose failed: {result.stderr[-300:]}")


def _build_subtitle_filter(srt_path: str) -> str:
    """Return FFmpeg subtitle filter string, or empty string if unavailable."""
    if not srt_path or not os.path.exists(srt_path):
        return ""
    try:
        # Copy SRT to a temp dir with a simple path (no spaces, no colon in body)
        tmp_dir = tempfile.mkdtemp(prefix="vsrt_")
        tmp_srt = os.path.join(tmp_dir, "sub.srt")
        shutil.copy2(srt_path, tmp_srt)
        # FFmpeg filter needs forward slashes + escaped colon for Windows drive letter
        safe = tmp_srt.replace("\\", "/")
        # Escape colon after drive letter (e.g. C: -> C\:)
        if len(safe) > 1 and safe[1] == ":":
            safe = safe[0] + "\\:" + safe[2:]
        style = "FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1,Alignment=2"
        return f",subtitles='{safe}':force_style='{style}'"
    except Exception as e:
        print(f"[Composer] Subtitle filter skipped: {e}")
        return ""


def _write_srt(script: str, duration: float, srt_path: str):
    words = script.split()
    if not words:
        return
    chunk_size = max(6, int(len(words) / max(duration / 3, 1)))
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    time_each = duration / len(chunks)

    def fmt(secs):
        h, m = int(secs // 3600), int((secs % 3600) // 60)
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            start = i * time_each
            end = min(start + time_each, duration)
            f.write(f"{i+1}\n{fmt(start)} --> {fmt(end)}\n{chunk}\n\n")


def _get_video_duration(video_path: str) -> float:
    result = subprocess.run(
        [FFMPEG, "-i", video_path, "-f", "null", "-"],
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


def _generate_background(prompt: str, width: int, height: int) -> Image.Image:
    p = prompt.lower()
    if any(w in p for w in ["cozy", "warm", "chair", "light", "candle", "studio"]):
        colors = [(40, 20, 10), (90, 55, 30), (140, 90, 50)]
    elif any(w in p for w in ["night", "dark", "moody", "dramatic"]):
        colors = [(5, 5, 20), (20, 15, 45), (40, 30, 80)]
    elif any(w in p for w in ["nature", "outdoor", "forest", "green"]):
        colors = [(10, 40, 20), (30, 80, 50), (60, 120, 80)]
    elif any(w in p for w in ["tech", "digital", "modern", "blue"]):
        colors = [(5, 10, 30), (15, 30, 70), (30, 60, 130)]
    elif any(w in p for w in ["bright", "light", "clean", "white"]):
        colors = [(200, 200, 210), (230, 230, 240), (245, 245, 255)]
    else:
        colors = [(15, 20, 35), (30, 40, 70), (50, 65, 110)]

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        c0, c1 = (colors[0], colors[1]) if ratio < 0.5 else (colors[1], colors[2])
        t = (ratio * 2) if ratio < 0.5 else ((ratio - 0.5) * 2)
        draw.line([(0, y), (width, y)], fill=(
            int(c0[0] + (c1[0] - c0[0]) * t),
            int(c0[1] + (c1[1] - c0[1]) * t),
            int(c0[2] + (c1[2] - c0[2]) * t),
        ))

    img = _add_bokeh(img, colors)
    return img.filter(ImageFilter.GaussianBlur(radius=4))


def _add_bokeh(img: Image.Image, colors: list) -> Image.Image:
    import random
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    random.seed(42)
    base = colors[-1]
    for _ in range(25):
        x = random.randint(0, img.width)
        y = random.randint(0, img.height)
        r = random.randint(40, 180)
        a = random.randint(10, 35)
        draw.ellipse(
            [x - r, y - r, x + r, y + r],
            fill=(min(255, base[0] + 80), min(255, base[1] + 60), min(255, base[2] + 40), a)
        )
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
