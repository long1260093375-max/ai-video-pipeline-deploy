#!/usr/bin/env python3
"""Offline TTS for the video pipeline, using Piper (no network, no Edge/Bing).

Why Piper exists here: in this VM, edge-tts cannot reach Microsoft's speech
endpoint. The egress proxy MITMs TLS with its own CA, and edge-tts hardcodes
its SSL context from certifi (which does not include that CA); even after
patching the CA in, the websocket read times out through the proxy.
Piper runs locally and works regardless of network.

Usage:
    python3 tools/tts_piper.py --text "你好" --out voice.mp3 [--pad-to 4.5]

--pad-to: if the spoken audio is shorter than the segment duration, pad the
tail with silence so the audio lines up with the subtitle timing (Piper
speaks at ~5.6 chars/s, faster than the pipeline's 4.5 chars/s estimate, so
padding is the normal case). If it is longer, it is sped up just enough to
fit, so no words are cut off at the end of a segment.
"""
import argparse, subprocess, sys, tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent
PIPER = BASE / "piper" / "piper"
MODEL = BASE / "piper" / "models" / "zh_huayan.onnx"


def duration(path):
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1", str(path),
    ]).decode().strip()
    return float(out.split("=")[1])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--pad-to", type=float, default=0.0)
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "voice.wav"
        r = subprocess.run(
            [str(PIPER), "--model", str(MODEL), "--output_file", str(wav)],
            input=args.text.encode("utf-8"), capture_output=True,
        )
        if r.returncode != 0 or not wav.exists():
            print(r.stderr.decode(errors="ignore")[-500:], file=sys.stderr)
            return 1
        dur = duration(wav)
        target = args.pad_to
        if target and dur > target:
            # speed up just enough to fit, then pad any rounding gap
            filt = f"atempo={dur / target:.3f},apad=whole_dur={target}"
        elif target:
            filt = f"apad=whole_dur={target}"
        else:
            filt = "anull"
        subprocess.run([
            "ffmpeg", "-y", "-v", "error", "-i", str(wav),
            "-af", filt, "-t", str(target) if target else "9999",
            "-q:a", "9", "-acodec", "libmp3lame", str(out),
        ], check=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
