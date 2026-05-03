#!/usr/bin/env python3
"""
Setup script: installs dependencies and downloads SadTalker models.
Run once before first use: python setup.py
"""
import os
import sys
import subprocess
import urllib.request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd, **kwargs):
    print(f"  > {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    result = subprocess.run(cmd, shell=isinstance(cmd, str), **kwargs)
    return result.returncode == 0


def step(msg):
    print(f"\n{'='*50}")
    print(f"  {msg}")
    print(f"{'='*50}")


def install_packages():
    step("Installing Python packages")
    return run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def install_sadtalker():
    step("Setting up SadTalker (face animation)")
    sadtalker_dir = os.path.join(BASE_DIR, "SadTalker")

    if os.path.isdir(sadtalker_dir):
        print("  SadTalker directory already exists, skipping clone.")
    else:
        print("  Cloning SadTalker from GitHub...")
        ok = run(["git", "clone", "https://github.com/OpenTalker/SadTalker.git", sadtalker_dir])
        if not ok:
            print("  ⚠️  Could not clone SadTalker. Face animation will use static photo fallback.")
            return

    # Install SadTalker requirements
    st_req = os.path.join(sadtalker_dir, "requirements.txt")
    if os.path.isfile(st_req):
        print("  Installing SadTalker dependencies...")
        run([sys.executable, "-m", "pip", "install", "-r", st_req])

    # Download models
    checkpoints_dir = os.path.join(sadtalker_dir, "checkpoints")
    gfpgan_dir = os.path.join(sadtalker_dir, "gfpgan", "weights")

    if not os.path.isdir(checkpoints_dir) or not os.listdir(checkpoints_dir):
        print("  Downloading SadTalker model checkpoints (~300MB)...")
        os.makedirs(checkpoints_dir, exist_ok=True)
        # Use the provided download script if available
        dl_script = os.path.join(sadtalker_dir, "scripts", "download_models.sh")
        if os.path.isfile(dl_script):
            run(["bash", dl_script], cwd=sadtalker_dir)
        else:
            # Manual model download
            _download_sadtalker_models(checkpoints_dir, gfpgan_dir)
    else:
        print("  SadTalker checkpoints already present.")

    print("  ✅ SadTalker setup complete.")


def _download_sadtalker_models(checkpoints_dir, gfpgan_dir):
    """Download SadTalker model files."""
    os.makedirs(gfpgan_dir, exist_ok=True)

    models = [
        (
            "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00109-model.pth.tar",
            os.path.join(checkpoints_dir, "mapping_00109-model.pth.tar"),
        ),
        (
            "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/mapping_00229-model.pth.tar",
            os.path.join(checkpoints_dir, "mapping_00229-model.pth.tar"),
        ),
        (
            "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_256.safetensors",
            os.path.join(checkpoints_dir, "SadTalker_V0.0.2_256.safetensors"),
        ),
        (
            "https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc/SadTalker_V0.0.2_512.safetensors",
            os.path.join(checkpoints_dir, "SadTalker_V0.0.2_512.safetensors"),
        ),
        (
            "https://github.com/xinntao/facexlib/releases/download/v0.1.0/alignment_WFLW_4HG.pth",
            os.path.join(checkpoints_dir, "alignment_WFLW_4HG.pth"),
        ),
        (
            "https://github.com/xinntao/facexlib/releases/download/v0.1.0/detection_Resnet50_Final.pth",
            os.path.join(checkpoints_dir, "detection_Resnet50_Final.pth"),
        ),
        (
            "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth",
            os.path.join(gfpgan_dir, "GFPGANv1.4.pth"),
        ),
    ]

    for url, dest in models:
        if os.path.isfile(dest):
            print(f"  Already exists: {os.path.basename(dest)}")
            continue
        print(f"  Downloading {os.path.basename(dest)}...")
        try:
            urllib.request.urlretrieve(url, dest)
            print(f"  ✅ {os.path.basename(dest)}")
        except Exception as e:
            print(f"  ⚠️  Failed to download {os.path.basename(dest)}: {e}")


def check_ollama():
    step("Checking Ollama (local LLM)")
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            print("  ✅ Ollama is running.")
            if "llama3" not in result.stdout.lower():
                print("  Pulling llama3.2 model (first time, ~2GB)...")
                run(["ollama", "pull", "llama3.2"])
            return True
    except Exception:
        pass
    print("  ⚠️  Ollama not found or not running.")
    print("     Download from: https://ollama.com")
    print("     After install: ollama pull llama3.2")
    print("     App will still work with a built-in fallback script generator.")
    return False


def check_ffmpeg():
    step("Checking FFmpeg")
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        print("  ✅ FFmpeg found.")
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("  ❌ FFmpeg not found!")
        print("     Install with: winget install ffmpeg")
        print("     Or download from: https://ffmpeg.org/download.html")
        return False


def main():
    print("\n" + "=" * 50)
    print("  AI Video Generator — Setup")
    print("=" * 50)

    ok_pkg = install_packages()
    ok_ffmpeg = check_ffmpeg()
    install_sadtalker()
    check_ollama()

    print("\n" + "=" * 50)
    print("  Setup Summary")
    print("=" * 50)
    print(f"  Python packages: {'✅' if ok_pkg else '❌'}")
    print(f"  FFmpeg:          {'✅' if ok_ffmpeg else '❌ (required!)'}")
    print(f"  SadTalker:       see above")
    print(f"  Ollama:          optional (improves scripts)")
    print()
    print("  To start the app:")
    print("    python run.py")
    print()
    print("  Then open: http://localhost:8000")
    print("=" * 50)


if __name__ == "__main__":
    main()
