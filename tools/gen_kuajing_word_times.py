#!/usr/bin/env python3
"""Generate word-level timestamps for the kuajing v10 Bear track.

Runs faster-whisper (local, free) on output/kuajing-seedream-v10/audio.mp3
with word_timestamps=True, then splits the words into the 14 beats using
the known sentence boundaries (from the v13 BEAT_DURS measurement).
Writes:
  scripts/<stem>_word_times.json : {beat_index: [{word, start, end}]}
      with start/end in seconds RELATIVE to the beat's start.
  scripts/<stem>_beat_durs.json : [durations] (the 14 measured durations).
These are consumed by sticker_motion.resolve_trigger (trigger_word) and
resolve_beat_durs, so the renderer no longer hardcodes one film's timing.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
AUDIO = BASE / "output" / "kuajing-seedream-v10" / "audio.mp3"
SCRIPT = BASE / "scripts" / "跨境电商.json"
# Measured sentence boundaries (v13, faster-whisper on the same audio).
BEAT_DURS = [3.76, 3.40, 4.22, 3.42, 3.16, 3.86, 3.06, 3.48,
             3.80, 3.82, 3.58, 3.52, 3.62, 3.78]
BOUNDS = [0.0]
for d in BEAT_DURS:
    BOUNDS.append(BOUNDS[-1] + d)


def decode_audio(path):
    raw = subprocess.check_output(
        ["ffmpeg", "-v", "error", "-i", str(path),
         "-ar", "16000", "-ac", "1", "-f", "s16le", "-"])
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def main():
    from faster_whisper import WhisperModel
    model = WhisperModel("base", device="cpu", compute_type="int8")
    x = decode_audio(AUDIO)
    segments, _ = model.transcribe(x, language="zh", word_timestamps=True)
    words = []
    for seg in segments:
        for w in (seg.words or []):
            words.append({"word": w.word.strip(), "start": w.start, "end": w.end})
    print("words total:", len(words))
    # split into beats by start time
    beats = {str(i): [] for i in range(len(BEAT_DURS))}
    for w in words:
        for i in range(len(BEAT_DURS)):
            if BOUNDS[i] <= w["start"] < BOUNDS[i + 1]:
                beats[str(i)].append({
                    "word": w["word"],
                    "start": round(w["start"] - BOUNDS[i], 3),
                    "end": round(w["end"] - BOUNDS[i], 3),
                })
                break
    for i in range(len(BEAT_DURS)):
        ws = beats[str(i)]
        print("beat %d: %d words %s" % (
            i, len(ws),
            " ".join(w["word"] for w in ws[:8])))
    stem = SCRIPT.stem
    (BASE / "scripts" / (stem + "_word_times.json")).write_text(
        json.dumps(beats, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE / "scripts" / (stem + "_beat_durs.json")).write_text(
        json.dumps(BEAT_DURS, ensure_ascii=False), encoding="utf-8")
    print("wrote scripts/%s_word_times.json and scripts/%s_beat_durs.json"
          % (stem, stem))


if __name__ == "__main__":
    main()
