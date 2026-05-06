"""
Fast talking-head animator using face_alignment (68-pt landmarks) + audio energy.
No GPU required. Produces mouth-moving animation in ~10-30s for 60s video.
Falls back gracefully if no face is detected.
"""
import os
import subprocess
import tempfile
import numpy as np
import cv2

import imageio_ffmpeg
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

# 68-point landmark mouth indices
_MOUTH_OUTER = list(range(48, 60))   # outer lip
_MOUTH_INNER = list(range(60, 68))   # inner lip
_LIP_TOP     = 62  # upper inner center
_LIP_BOTTOM  = 66  # lower inner center
_LIP_LEFT    = 60  # left inner corner
_LIP_RIGHT   = 64  # right inner corner


def create_talking_video(photo_path: str, audio_path: str, output_path: str,
                         width: int = 720, height: int = 1280) -> bool:
    """
    Generate a talking-head video from a photo and audio.
    Returns True if face was found, False if no face detected.
    """
    try:
        # Disable torch.compile — needs MSVC cl.exe which is not always installed
        import torch
        torch._dynamo.disable()
        os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")

        import face_alignment

        img_bgr = cv2.imread(photo_path)
        if img_bgr is None:
            return False

        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        h_img, w_img = img_bgr.shape[:2]

        # Detect landmarks (downloads ~100MB model on first run)
        fa = face_alignment.FaceAlignment(
            face_alignment.LandmarksType.TWO_D,
            device='cpu',
            flip_input=False,
            face_detector='sfd',
        )
        preds = fa.get_landmarks(img_rgb)
        if not preds:
            print("[TalkingHead] No face detected in photo")
            return False

        lm = preds[0]  # (68, 2) array

        # Mouth positions
        top_pt    = lm[_LIP_TOP].astype(int)
        bottom_pt = lm[_LIP_BOTTOM].astype(int)
        left_pt   = lm[_LIP_LEFT].astype(int)
        right_pt  = lm[_LIP_RIGHT].astype(int)

        mouth_cx  = int((left_pt[0] + right_pt[0]) / 2)
        mouth_cy  = int((top_pt[1] + bottom_pt[1]) / 2)
        mouth_w   = int(abs(right_pt[0] - left_pt[0]))
        closed_gap = max(2, int(abs(bottom_pt[1] - top_pt[1])))

        print(f"[TalkingHead] Mouth at ({mouth_cx},{mouth_cy}), width={mouth_w}px")

        # Extract audio energy envelope
        energy = _get_audio_energy(audio_path)
        audio_dur = _get_audio_duration(audio_path)

        fps = 24
        n_frames = max(1, int(audio_dur * fps))
        print(f"[TalkingHead] Rendering {n_frames} frames at {fps}fps...")

        with tempfile.TemporaryDirectory(prefix="talkhead_") as tmpdir:
            for i in range(n_frames):
                t = i / fps
                energy_val = _sample_energy(energy, t, audio_dur)

                # Map energy to mouth opening (smoothed)
                open_ratio = min(1.0, max(0.0, energy_val * 3.0))
                max_open_px = max(4, int(mouth_w * 0.38))
                mouth_open_px = int(open_ratio * max_open_px)

                frame = img_bgr.copy()
                if mouth_open_px > closed_gap + 1:
                    _paint_mouth(frame, mouth_cx, mouth_cy, mouth_w, mouth_open_px,
                                 img_bgr, lm)

                frame_path = os.path.join(tmpdir, f"{i:06d}.jpg")
                cv2.imwrite(frame_path, frame, [cv2.IMWRITE_JPEG_QUALITY, 88])

            # Compile frames into video
            pattern = os.path.join(tmpdir, "%06d.jpg")
            _compile(pattern, audio_path, output_path, fps, width, height)

        ok = os.path.exists(output_path) and os.path.getsize(output_path) > 10_000
        if ok:
            print(f"[TalkingHead] Done — {os.path.getsize(output_path)//1024}KB")
        return ok

    except Exception as e:
        import traceback
        print(f"[TalkingHead] Error: {e}")
        traceback.print_exc()
        return False


def _paint_mouth(frame: np.ndarray, cx: int, cy: int, mouth_w: int,
                 open_px: int, orig: np.ndarray, lm: np.ndarray):
    """
    Draw a realistic open-mouth effect:
    1. Dark mouth cavity
    2. Upper teeth strip
    3. Soft lip border
    """
    ew = max(6, int(mouth_w * 0.52))
    eh = max(3, open_px)

    # Soft gum/cavity color sampled from original mouth region
    mouth_region = orig[max(0, cy - 5):cy + 5, max(0, cx - ew):cx + ew]
    if mouth_region.size > 0:
        avg_lip = np.median(mouth_region, axis=(0, 1)).astype(np.uint8)
        cavity_color = (
            max(0, int(avg_lip[0]) - 80),
            max(0, int(avg_lip[1]) - 90),
            max(0, int(avg_lip[2]) - 70),
        )
    else:
        cavity_color = (25, 18, 28)

    # Main cavity
    cv2.ellipse(frame, (cx, cy), (ew, eh), 0, 0, 360, cavity_color, -1)

    # Upper teeth (visible only when sufficiently open)
    if eh > 7:
        teeth_h = max(2, eh // 3)
        teeth_y = cy - eh // 4
        cv2.ellipse(frame, (cx, teeth_y), (int(ew * 0.72), teeth_h),
                    0, 0, 180, (218, 213, 208), -1)

    # Soft border to blend with lip
    cv2.ellipse(frame, (cx, cy), (ew + 3, eh + 2), 0, 0, 360,
                tuple(min(255, c + 40) for c in cavity_color), 2)


def _get_audio_energy(audio_path: str) -> np.ndarray:
    """Extract per-frame (24fps) RMS energy from audio."""
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=16000, mono=True)
        hop = max(1, sr // 24)
        rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
        if rms.max() > 0:
            rms = rms / rms.max()
        # Smooth with small window
        kernel = np.ones(3) / 3
        rms = np.convolve(rms, kernel, mode='same')
        return rms
    except Exception as e:
        print(f"[TalkingHead] Audio energy error: {e}")
        return np.ones(3600) * 0.6


def _sample_energy(energy: np.ndarray, t: float, dur: float) -> float:
    if len(energy) == 0 or dur <= 0:
        return 0.5
    idx = int((t / dur) * len(energy))
    idx = max(0, min(idx, len(energy) - 1))
    return float(energy[idx])


def _get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        [FFMPEG, "-i", audio_path, "-f", "null", "-"],
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


def _compile(frame_pattern: str, audio_path: str, output_path: str,
             fps: int, W: int, H: int):
    """Compile JPEG frames + audio into mp4 at target resolution."""
    vf = f"scale={W}:{H}:force_original_aspect_ratio=decrease,pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"
    cmd = [
        FFMPEG, "-y",
        "-framerate", str(fps),
        "-i", frame_pattern,
        "-i", audio_path,
        "-vf", vf,
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Frame compile failed: {result.stderr[-300:]}")
