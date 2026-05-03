# AI Video Generator

A local, free AI video generator. Upload your photo + voice sample, write a prompt, and get a short video with your cloned voice and animated face.

## What it does

1. Upload your photo
2. Write a script prompt (AI generates the script)
3. Upload a voice recording (10–30 sec) — your voice gets cloned
4. Select video type (Short / Reel / Long) and duration
5. Describe the background scene
6. Click Generate — get a video with your face, voice, and background

## Setup (one time)

### Requirements
- Python 3.9+
- [FFmpeg](https://ffmpeg.org/download.html) — `winget install ffmpeg`
- [Ollama](https://ollama.com) (optional, for better scripts) — then `ollama pull llama3.2`
- Git

### Install

```bash
# Clone the repo
git clone https://github.com/YOUR_USERNAME/AIVideoGenerator.git
cd AIVideoGenerator

# Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# Run setup (installs packages + downloads SadTalker models ~300MB)
python setup.py
```

## Run

```bash
# Activate venv if not already
venv\Scripts\activate

# Start the server
python run.py
```

Open [http://localhost:8000](http://localhost:8000)

## Video pipeline

```
Script Prompt → Ollama (local LLM) → Script text
Voice Sample  → Coqui XTTS-v2     → Cloned speech audio
Photo         → SadTalker          → Animated face video
Background    → Generated gradient → Bokeh background
                ↓
            MoviePy + FFmpeg → Final video
```

## Video formats

| Type  | Resolution | Aspect | Max Duration |
|-------|-----------|--------|--------------|
| Short | 1080×1920 | 9:16   | 60s          |
| Reel  | 1080×1920 | 9:16   | 90s          |
| Long  | 1920×1080 | 16:9   | 10 min       |

## Tech stack (all free, all local)

- **Backend**: FastAPI + SQLite
- **Script AI**: Ollama (llama3.2)
- **Voice cloning**: Coqui XTTS-v2
- **Face animation**: SadTalker
- **Video**: MoviePy + FFmpeg
- **Frontend**: HTML + Tailwind CSS

## Notes

- First video takes longer (models load into RAM)
- XTTS-v2 needs ~4GB RAM; SadTalker needs ~6GB RAM
- GPU (CUDA) speeds up both significantly
- Without SadTalker, falls back to Ken Burns (photo zoom) effect
