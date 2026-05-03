#!/usr/bin/env python3
"""Start the AI Video Generator server."""
import os
import sys
import subprocess

def check_ffmpeg():
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def main():
    if not check_ffmpeg():
        print("❌ FFmpeg not found. Please install FFmpeg:")
        print("   Windows: winget install ffmpeg  OR  choco install ffmpeg")
        print("   Then restart your terminal.")
        sys.exit(1)

    os.makedirs("uploads/photos", exist_ok=True)
    os.makedirs("uploads/voices", exist_ok=True)
    os.makedirs("uploads/videos", exist_ok=True)

    print("=" * 50)
    print("  AI Video Generator")
    print("=" * 50)
    print("  Opening at: http://localhost:8000")
    print("  Press Ctrl+C to stop")
    print("=" * 50)

    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":
    main()
