#!/usr/bin/env python3
"""Doubao TTS 2.0 (seed-tts-2.0) synthesis, standalone version for local deployment.

Reads the API key from the DOUBAO_TTS_API_KEY environment variable
(no Muse secure vault). Same interface as the Muse connector helper:

    python3 tools/tts_doubao.py --text "你好" --speaker zh_male_xionger_uranus_bigtts \
        --out voice.mp3 [--speech-rate 10] [--pad-to 3.5]

speech-rate: -50 = 0.5x, 0 = 1.0x, 10 = 1.1x, 100 = 2.0x.
Response is chunked JSON; each chunk carries base64 audio in `data`.

Get a key: Volcano Engine console -> Voice service (语音合成) -> API key.
Note: the TTS key/resource is separate from the Ark image key; an Ark
arrears settlement does not automatically grant the voice resource.
"""
import argparse
import base64
import json
import os
import sys
import uuid
import urllib.error
import urllib.request

URL = "https://openspeech.bytedance.com/api/v3/tts/unidirectional"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--text", required=True)
    ap.add_argument("--speaker", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--speech-rate", type=int, default=0)
    ap.add_argument("--format", default="mp3")
    ap.add_argument("--pad-to", type=float, default=0.0)
    args = ap.parse_args()
    key = os.environ.get("DOUBAO_TTS_API_KEY", "")
    if not key:
        print("DOUBAO_TTS_API_KEY is not set. Get a key at the Volcano Engine "
              "console (voice service), then: export DOUBAO_TTS_API_KEY=<key>",
              file=sys.stderr)
        return 2
    body = json.dumps({
        "req_params": {
            "text": args.text,
            "speaker": args.speaker,
            "audio_params": {"format": args.format, "sample_rate": 24000},
            "speech_rate": args.speech_rate,
        },
    }).encode()
    req = urllib.request.Request(URL, data=body, method="POST", headers={
        "Content-Type": "application/json",
        "X-Api-Resource-Id": "seed-tts-2.0",
        "X-Api-Request-Id": str(uuid.uuid4()),
        "X-Api-Key": key,
    })
    try:
        with urllib.request.build_opener().open(req, timeout=120) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        print("HTTP", e.code, e.read().decode(errors="ignore")[:500], file=sys.stderr)
        return 1
    audio = bytearray()
    used_chars = None
    for line in raw.decode(errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("code") not in (None, 0, 20000000):
            print("TTS error", obj.get("code"), obj.get("message"), file=sys.stderr)
            return 1
        if obj.get("data"):
            audio += base64.b64decode(obj["data"])
        if isinstance(obj.get("usage"), dict):
            used_chars = obj["usage"].get("text_words")
    if not audio:
        print("no audio returned", file=sys.stderr)
        return 1
    import subprocess
    from pathlib import Path
    raw_path = Path(args.out + ".raw")
    with open(raw_path, "wb") as f:
        f.write(audio)
    target = args.pad_to
    if target:
        import subprocess as sp
        dur_out = sp.check_output(["ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of", "default=noprint_wrappers=1",
            str(raw_path)]).decode().strip()
        dur = float(dur_out.split("=")[1])
        if dur > target:
            filt = f"atempo={dur / target:.3f},apad=whole_dur={target}"
        else:
            filt = f"apad=whole_dur={target}"
        sp.run(["ffmpeg", "-y", "-v", "error", "-i", str(raw_path), "-af", filt,
                "-t", str(target), "-q:a", "9", "-acodec", "libmp3lame", args.out],
               check=True)
        raw_path.unlink()
    else:
        raw_path.rename(args.out)
    print(f"saved {args.out} ({len(audio)} bytes, chars={used_chars})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
