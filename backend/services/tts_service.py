"""
TTS Service — two modes:
1. edge-tts  : works immediately, high-quality Microsoft voices, no voice cloning
2. Coqui XTTS: voice cloning from your sample, requires: pip install TTS (needs C++ build tools)

Set USE_VOICE_CLONE=true in .env to enable Coqui (after installing build tools + TTS).
"""
import os
import asyncio

USE_VOICE_CLONE = os.getenv("USE_VOICE_CLONE", "false").lower() == "true"

# Coqui XTTS (only loaded if voice cloning is enabled)
_tts_model = None


def _get_coqui_tts():
    global _tts_model
    if _tts_model is None:
        import torch
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[TTS] Loading XTTS-v2 on {device}...")
        _tts_model = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    return _tts_model


async def _edge_tts_generate(script: str, output_path: str):
    """Generate speech using Microsoft Edge TTS (free, high quality, no cloning)."""
    import edge_tts
    # Use a clear, natural English voice
    voice = os.getenv("EDGE_TTS_VOICE", "en-US-AndrewMultilingualNeural")
    communicate = edge_tts.Communicate(script, voice)
    await communicate.save(output_path)


def generate_speech(script: str, voice_sample_path: str, output_path: str) -> str:
    """Generate speech. Uses voice cloning if USE_VOICE_CLONE=true, else edge-tts."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Convert output path to .mp3 for edge-tts (it outputs mp3)
    if not USE_VOICE_CLONE:
        mp3_path = output_path.replace(".wav", ".mp3")
        asyncio.run(_edge_tts_generate(script, mp3_path))
        # Convert mp3 -> wav for consistency
        _convert_to_wav(mp3_path, output_path)
        if os.path.exists(mp3_path) and mp3_path != output_path:
            os.remove(mp3_path)
        return output_path

    # Coqui XTTS voice cloning
    tts = _get_coqui_tts()
    tts.tts_to_file(
        text=script,
        speaker_wav=voice_sample_path,
        language="en",
        file_path=output_path,
    )
    return output_path


def _convert_to_wav(mp3_path: str, wav_path: str):
    """Convert audio to wav using bundled ffmpeg from imageio_ffmpeg."""
    try:
        import imageio_ffmpeg
        import subprocess
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        result = subprocess.run(
            [ffmpeg_exe, "-y", "-i", mp3_path, wav_path],
            capture_output=True, timeout=60
        )
        if result.returncode == 0 and os.path.exists(wav_path):
            return
        # fallback to pydub with explicit ffmpeg
        from pydub import AudioSegment
        AudioSegment.converter = ffmpeg_exe
        audio = AudioSegment.from_file(mp3_path)
        audio.export(wav_path, format="wav")
    except Exception as e:
        print(f"[TTS] Audio conversion warning: {e} — using mp3 as-is")
        import shutil
        shutil.copy2(mp3_path, wav_path)


def get_audio_duration(audio_path: str) -> float:
    """Return duration of audio file in seconds."""
    try:
        import librosa
        return librosa.get_duration(path=audio_path)
    except Exception:
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception:
            return 60.0
