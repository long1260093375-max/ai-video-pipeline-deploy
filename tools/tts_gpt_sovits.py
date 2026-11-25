#!/usr/bin/env python3
"""Local TTS for the video pipeline, using a GPT-SoVITS server (api_v2).

Why this exists: Doubao TTS (the pipeline's 熊二 voice) is blocked
(403 `45000030 resource not granted` since 2026-11-06), so new voiceover
can only reuse cached audio. GPT-SoVITS runs locally on the team's
Windows PC and clones a voice from a short reference clip, so it removes
the dependency on Doubao's voice service entirely.

The GPT-SoVITS server must be running on this machine first:

    cd <GPT-SoVITS install dir>
    python api_v2.py -a 127.0.0.1 -p 9880

Usage:
    python3 tools/tts_gpt_sovits.py --text "你好" --out voice.mp3 [--pad-to 4.5]

    --ref-audio: 3-10s clean clip of the target voice (default: the cached
        熊二 clip, tools/gpt_sovits_ref_audio/xionger_ref.mp3).
    --prompt-text: transcript of the reference clip (default: the clip's
        own line, "你有没有在手机上买过一瓶日本来的眼药水").
    --server: GPT-SoVITS api_v2 base URL (default http://127.0.0.1:9880).
    --speed: speed_factor, 1.1 matches the old 熊二 1.1x pace.
    --pad-to: same as tts_piper.py / tts_doubao.py: pad the tail with
        silence, or speed up just enough to fit, so audio lines up with
        the subtitle timing.

The reference audio path is read by the server, so it must be a path on
the machine running GPT-SoVITS (same machine as this script).
"""
import argparse
import json
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
DEFAULT_REF = BASE / "gpt_sovits_ref_audio" / "xionger_ref.mp3"
DEFAULT_PROMPT = "你有没有在手机上买过一瓶日本来的眼药水"


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
    ap.add_argument("--ref-audio", default=str(DEFAULT_REF))
    ap.add_argument("--prompt-text", default=DEFAULT_PROMPT)
    ap.add_argument("--server", default="http://127.0.0.1:9880")
    ap.add_argument("--speed", type=float, default=1.1)
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    ref = Path(args.ref_audio)
    if not ref.exists():
        print(f"reference audio not found: {ref}", file=sys.stderr)
        return 2
    body = json.dumps({
        "text": args.text,
        "text_lang": "zh",
        "ref_audio_path": str(ref.resolve()),
        "prompt_text": args.prompt_text,
        "prompt_lang": "zh",
        "text_split_method": "cut5",
        "batch_size": 1,
        "speed_factor": args.speed,
        "media_type": "wav",
        "streaming_mode": False,
    }).encode()
    req = urllib.request.Request(args.server.rstrip("/") + "/tts", data=body,
                                 method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.build_opener().open(req, timeout=300) as r:
            raw = r.read()
            ctype = r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        print("GPT-SoVITS error HTTP", e.code,
              e.read().decode(errors="ignore")[:500], file=sys.stderr)
        return 1
    except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
        print(f"cannot reach GPT-SoVITS server at {args.server}: {e}\n"
              "start it first: cd <GPT-SoVITS dir> && "
              "python api_v2.py -a 127.0.0.1 -p 9880", file=sys.stderr)
        return 1
    if "application/json" in ctype:
        print("GPT-SoVITS error:", raw.decode(errors="ignore")[:500],
              file=sys.stderr)
        return 1
    if not raw:
        print("no audio returned", file=sys.stderr)
        return 1
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "voice.wav"
        wav.write_bytes(raw)
        dur = duration(wav)
        target = args.pad_to
        if target and dur > target:
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
    print(f"saved {out} ({len(raw)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
