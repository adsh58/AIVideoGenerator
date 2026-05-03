"""
Video composer — uses FFmpeg filter_complex directly.
This is 20-50x faster than moviepy's frame-by-frame Python rendering.
"""
import os
import subprocess
import json
from PIL import Image, ImageDraw, ImageFilter

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

FORMAT_SPECS = {
    "short": {"width": 720,  "height": 1280, "fps": 24},  # 9:16 vertical
    "reel":  {"width": 720,  "height": 1280, "fps": 24},  # 9:16 vertical
    "long":  {"width": 1280, "height": 720,  "fps": 24},  # 16:9 horizontal
}


def compose_video(
    face_video_path: str,
    background_prompt: str,
    video_type: str,
    output_path: str,
    script_text: str = "",
) -> str:
    spec = FORMAT_SPECS.get(video_type, FORMAT_SPECS["reel"])
    W, H = spec["width"], spec["height"]
    FPS = spec["fps"]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. Generate background image
    bg_image = _generate_background(background_prompt, W, H)
    bg_path = output_path.replace(".mp4", "_bg.jpg")
    bg_image.save(bg_path, quality=92)

    # 2. Get face video duration
    duration = _get_video_duration(face_video_path)

    # 3. Build subtitle file if script provided
    srt_path = None
    if script_text.strip():
        srt_path = output_path.replace(".mp4", ".srt")
        _write_srt(script_text, duration, srt_path)

    # 4. Compose with FFmpeg
    _compose_ffmpeg(face_video_path, bg_path, srt_path, output_path, W, H, FPS, video_type)

    # Cleanup
    for p in [bg_path, srt_path]:
        if p and os.path.exists(p):
            os.remove(p)

    return output_path


def _compose_ffmpeg(face_path, bg_path, srt_path, output_path, W, H, FPS, video_type):
    """
    FFmpeg filter_complex:
      [0] background image (looped for duration)
      [1] face video (scaled + positioned)
      overlay them, optionally burn subtitles
    """
    # Face position: centered top for vertical, left for horizontal
    if video_type in ("short", "reel"):
        face_h = int(H * 0.72)
        face_w = -2  # auto width keeping aspect ratio (must be divisible by 2)
        x_expr = f"(main_w-overlay_w)/2"
        y_expr = f"{int(H * 0.02)}"
    else:
        face_h = int(H * 0.85)
        face_w = -2
        x_expr = f"{int(W * 0.05)}"
        y_expr = f"(main_h-overlay_h)/2"

    # Subtitle filter — Windows path needs special escaping for FFmpeg filter syntax
    sub_filter = ""
    if srt_path and os.path.exists(srt_path):
        # Copy SRT to a short path with no spaces/colons to avoid FFmpeg filter escaping issues
        import shutil, tempfile
        safe_srt_dir = tempfile.mkdtemp(prefix="srt")
        safe_srt = os.path.join(safe_srt_dir, "s.srt").replace("\\", "/")
        shutil.copy2(srt_path, safe_srt)
        # On Windows, also escape the drive letter colon
        safe_srt_escaped = safe_srt.replace(":", "\\:")
        sub_filter = f",subtitles='{safe_srt_escaped}':force_style='FontName=Arial,FontSize=20,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1,Alignment=2'"

    filter_complex = (
        f"[0:v]scale={W}:{H},loop=loop=-1:size=1:start=0[bg];"
        f"[1:v]scale={face_w}:{face_h}[face];"
        f"[bg][face]overlay={x_expr}:{y_expr}{sub_filter}[out]"
    )

    cmd = [
        FFMPEG, "-y",
        "-i", bg_path,
        "-i", face_path,
        "-filter_complex", filter_complex,
        "-map", "[out]",
        "-map", "1:a",
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
        # Fallback: simpler overlay without subtitles
        print(f"[Composer] filter_complex failed, trying simple overlay: {result.stderr[-400:]}")
        _compose_simple(face_path, bg_path, output_path, W, H, FPS)


def _compose_simple(face_path, bg_path, output_path, W, H, FPS):
    """Simplest possible: just put face video over background, no subtitles."""
    cmd = [
        FFMPEG, "-y",
        "-loop", "1", "-i", bg_path,
        "-i", face_path,
        "-filter_complex",
        f"[0:v]scale={W}:{H}[bg];[1:v]scale=-2:{int(H*0.72)}[face];[bg][face]overlay=(main_w-overlay_w)/2:{int(H*0.02)}[out]",
        "-map", "[out]", "-map", "1:a",
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-shortest", "-movflags", "+faststart",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, timeout=300)


def _write_srt(script: str, duration: float, srt_path: str):
    """Write an SRT subtitle file, splitting script into timed chunks."""
    words = script.split()
    if not words:
        return
    chunk_size = max(6, int(len(words) / max(duration / 3, 1)))
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    time_each = duration / len(chunks)

    def fmt_time(secs):
        h = int(secs // 3600)
        m = int((secs % 3600) // 60)
        s = secs % 60
        return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

    with open(srt_path, "w", encoding="utf-8") as f:
        for i, chunk in enumerate(chunks):
            start = i * time_each
            end = min(start + time_each, duration)
            f.write(f"{i+1}\n{fmt_time(start)} --> {fmt_time(end)}\n{chunk}\n\n")


def _get_video_duration(video_path: str) -> float:
    cmd = [FFMPEG, "-i", video_path, "-f", "null", "-"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    for line in r.stderr.splitlines():
        if "Duration:" in line:
            try:
                dur_str = line.split("Duration:")[1].split(",")[0].strip()
                h, m, s = dur_str.split(":")
                return int(h) * 3600 + int(m) * 60 + float(s)
            except Exception:
                pass
    return 60.0


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
        c0, c1 = (colors[0], colors[1]) if ratio < 0.5 else (colors[1], colors[2])
        t = (ratio * 2) if ratio < 0.5 else ((ratio - 0.5) * 2)
        r = int(c0[0] + (c1[0] - c0[0]) * t)
        g = int(c0[1] + (c1[1] - c0[1]) * t)
        b = int(c0[2] + (c1[2] - c0[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

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
        draw.ellipse([x-r, y-r, x+r, y+r], fill=(min(255,base[0]+80), min(255,base[1]+60), min(255,base[2]+40), a))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
