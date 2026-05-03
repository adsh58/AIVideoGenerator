import os
import torch

_tts = None


def _get_tts():
    global _tts
    if _tts is None:
        from TTS.api import TTS
        device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"[TTS] Loading XTTS-v2 on {device}...")
        _tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
        print("[TTS] Model loaded.")
    return _tts


def generate_speech(script: str, voice_sample_path: str, output_path: str) -> str:
    """Clone voice from sample and synthesize speech from script."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    tts = _get_tts()
    tts.tts_to_file(
        text=script,
        speaker_wav=voice_sample_path,
        language="en",
        file_path=output_path,
    )
    return output_path


def get_audio_duration(audio_path: str) -> float:
    """Return duration of audio file in seconds."""
    try:
        import librosa
        duration = librosa.get_duration(path=audio_path)
        return duration
    except Exception:
        try:
            from pydub import AudioSegment
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception:
            return 60.0
