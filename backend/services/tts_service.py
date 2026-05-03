"""
TTS Service
- Default: edge-tts (Microsoft, free, high quality, no cloning, needs internet)
- Upgrade: Coqui XTTS-v2 (voice cloning, set USE_VOICE_CLONE=true in .env)
"""
import os
import asyncio
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
USE_VOICE_CLONE = os.getenv("USE_VOICE_CLONE", "false").lower() == "true"

_coqui_model = None


def generate_speech(script: str, voice_sample_path: str, output_path: str) -> str:
    """Synchronous entry point — safe to call from thread pool executor."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    if not script or not script.strip():
        raise ValueError("Script is empty — cannot generate audio")

    if USE_VOICE_CLONE:
        return _coqui_generate(script, voice_sample_path, output_path)
    else:
        return _edge_tts_generate(script, output_path)


# ── edge-tts ─────────────────────────────────────────────────────────────────

def _edge_tts_generate(script: str, output_path: str) -> str:
    """Run edge-tts in its own event loop (safe from thread pool)."""
    voice = os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural")

    # Create a fresh event loop — safe because this runs in a thread, not the main loop
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_edge_tts_async(script, voice, output_path))
    finally:
        loop.close()

    # edge-tts outputs mp3 directly; convert to wav so ffmpeg downstream is consistent
    if output_path.endswith(".mp3"):
        return output_path  # already correct format

    mp3_path = os.path.splitext(output_path)[0] + ".mp3"
    if os.path.exists(mp3_path):
        _ffmpeg_convert(mp3_path, output_path)
        os.remove(mp3_path)
    elif not os.path.exists(output_path):
        raise RuntimeError("edge-tts produced no output file")

    return output_path


async def _edge_tts_async(script: str, voice: str, output_path: str):
    import edge_tts
    mp3_path = os.path.splitext(output_path)[0] + ".mp3"
    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(mp3_path)


def _ffmpeg_convert(src: str, dst: str):
    """Convert audio format using bundled ffmpeg."""
    result = subprocess.run(
        [FFMPEG, "-y", "-i", src, dst],
        capture_output=True, timeout=60
    )
    if result.returncode != 0:
        # Fallback: just copy — ffmpeg downstream can handle mp3 as wav input
        import shutil
        shutil.copy2(src, dst)


# ── Coqui XTTS (voice cloning) ───────────────────────────────────────────────

def _coqui_generate(script: str, voice_sample_path: str, output_path: str) -> str:
    global _coqui_model
    if _coqui_model is None:
        import torch
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[TTS] Loading XTTS-v2 on {device}...")
        _coqui_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

    _coqui_model.tts_to_file(
        text=script,
        speaker_wav=voice_sample_path,
        language="en",
        file_path=output_path,
    )
    return output_path
