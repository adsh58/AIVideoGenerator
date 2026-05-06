"""
TTS Service
- Default: edge-tts (Microsoft, free, high-quality voices, needs internet)
- Auto-detects Hinglish prompts → uses Indian English/Hindi voice
- Voice clone: set USE_VOICE_CLONE=true + install Coqui TTS
"""
import os
import asyncio
import subprocess

import imageio_ffmpeg

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
USE_VOICE_CLONE = os.getenv("USE_VOICE_CLONE", "false").lower() == "true"

# Voice map by language
_VOICES = {
    "en": os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural"),
    "hi": "hi-IN-MadhurNeural",        # Indian Hindi male, natural
    "hi_f": "hi-IN-SwaraNeural",       # Indian Hindi female
    "en_in": "en-IN-PrabhatNeural",    # Indian English male
}

_HINGLISH_KEYWORDS = {
    "hinglish", "hindi", "indian", "hindi english",
    "hindi mein", "hindi me", "hindi mai", "bolna", "bolo",
}

_coqui_model = None


def _detect_language(script_prompt: str) -> str:
    """Return voice key based on language hint in prompt."""
    p = (script_prompt or "").lower()
    if any(k in p for k in _HINGLISH_KEYWORDS):
        return "en_in"  # Indian English voice reads Hinglish well
    return "en"


def generate_speech(script: str, voice_sample_path: str, output_path: str,
                    script_prompt: str = "") -> str:
    """Synchronous entry point — safe to call from thread pool executor."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    if not script or not script.strip():
        raise ValueError("Script is empty — cannot generate audio")

    if USE_VOICE_CLONE and voice_sample_path and os.path.exists(voice_sample_path):
        try:
            return _coqui_generate(script, voice_sample_path, output_path)
        except Exception as e:
            print(f"[TTS] Voice clone failed ({e}), falling back to edge-tts")

    return _edge_tts_generate(script, output_path, script_prompt)


# ── edge-tts ─────────────────────────────────────────────────────────────────

def _edge_tts_generate(script: str, output_path: str, script_prompt: str = "") -> str:
    lang = _detect_language(script_prompt)
    voice = _VOICES.get(lang, _VOICES["en"])

    mp3_path = os.path.splitext(output_path)[0] + ".mp3"

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_edge_tts_async(script, voice, mp3_path))
    finally:
        loop.close()

    if not os.path.exists(mp3_path) or os.path.getsize(mp3_path) < 100:
        raise RuntimeError(f"edge-tts produced no output (voice={voice})")

    # Always convert to wav for consistent downstream handling
    _ffmpeg_convert(mp3_path, output_path)
    try:
        os.remove(mp3_path)
    except Exception:
        pass

    if not os.path.exists(output_path) or os.path.getsize(output_path) < 100:
        raise RuntimeError("Audio conversion produced empty file")

    return output_path


async def _edge_tts_async(script: str, voice: str, mp3_path: str):
    import edge_tts
    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(mp3_path)


def _ffmpeg_convert(src: str, dst: str):
    result = subprocess.run(
        [FFMPEG, "-y", "-i", src, "-ar", "22050", "-ac", "1", dst],
        capture_output=True, timeout=60
    )
    if result.returncode != 0:
        # Last resort: raw copy (ffmpeg may still handle it)
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
