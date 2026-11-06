#!/usr/bin/env python3
"""Generate a 1-minute science-video script with Zhipu's chat API, so the
standalone pipeline can write its own copy without Muse.

Why this exists: the cutout render scripts (make_sentence_cutout7.py,
make_kuajing_cutout.py, ...) hardcode BEATS in the file. Without a script
generator, the team can only re-render old episodes on their own computer,
not make a new one. This script closes that gap: topic in, script JSON out.

Output JSON (saved to --out, default scripts/<topic-slug>.json):
    {
      "topic": "跨境电商出海",
      "title": "什么是跨境电商出海？",
      "beats": [{"text": "...", "key": "出海", "char": "出", "color": [59, 130, 246]}],
      "groups": [[0, 1], [2], ...],
      "end_cards": ["出海第一步：先小批量测试", "下期想听哪个概念，评论区告诉我"],
      "sticker_prompts": [{"key": "出海", "prompt": "a globe with an open parcel ..."}]
    }
    beats[].color cycles the pipeline palette; groups cover every beat
    exactly once, in order, grouped purely by meaning (no fixed group size).

Auth (key is never written to a file or printed):
  - Set ZHIPU_API_KEY in the environment. If it is missing the script
    stops with a clear message instead of guessing.
  - (The Muse copy of this script also falls back to the registered
    custom.zhipu connection; the local deploy copy does not.)

Usage:
    python3 generate_script_zhipu.py --topic "锚定效应"
    python3 generate_script_zhipu.py --topic "锚定效应" --model glm-4-plus --out scripts/maoding.json

The returned script is a draft: the team still reviews the finished film
(concept correctness, examples, no hard errors) before publishing, exactly
as with any Muse-written script.
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent
PALETTE = [(59, 130, 246), (245, 158, 11), (168, 85, 247),
           (34, 197, 94), (239, 68, 68)]

SYSTEM = (
    "You write 1-minute Chinese science-video scripts for a general audience. "
    "Style: spoken, plain, one idea per sentence, no jargon without an example. "
    "Structure: open with a concrete question or scene, explain the concept with "
    "one everyday example, name one common pitfall or cost, give one actionable "
    "first step, close with a one-line summary. "
    "Rules: 12-14 sentences total, 240-280 Chinese characters in total, each "
    "sentence is a single short clause (no comma chains). Every sentence gets a "
    "2-5 character key phrase that names what the picture should show. Group "
    "the sentences purely by meaning: sentences that belong together share a "
    "group, a meaning break starts a new group, no fixed group size. "
    "Also give one English sticker prompt per sentence: object-first, a single "
    "large subject filling most of the frame, cute flat cartoon, no text, "
    "no words, transparent background, no white border. "
    "Output ONLY a JSON object, no markdown, no explanation, with keys: "
    "title, beats (list of {text, key}), groups (list of lists of indices), "
    "end_cards (list of 2 strings), sticker_prompts (list of {key, prompt} "
    "in the same order as beats)."
)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise RuntimeError("redirect refused, verify the endpoint")


def call_zhipu(topic, model):
    body = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": "Topic: %s" % topic},
        ],
        "temperature": 0.7,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        data=body, headers={"Content-Type": "application/json"}, method="POST")
    key = os.environ.get("ZHIPU_API_KEY", "")
    if key:
        request.add_header("Authorization", "Bearer " + key)
    else:
        # No key in the environment and no Muse vault here (local deploy):
        # fail with a clear message instead of an ImportError.
        raise SystemExit("ZHIPU_API_KEY is not set. Get a key at bigmodel.cn "
                         "console -> API Keys, then: export ZHIPU_API_KEY=<key>")
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=180) as resp:
        data = json.load(resp)
    content = data["choices"][0]["message"]["content"]
    # Tolerate a fenced code block even though the prompt forbids it.
    m = re.search(r"\{.*\}", content, re.S)
    if not m:
        raise RuntimeError("model did not return JSON: %s" % content[:300])
    return json.loads(m.group(0))


def validate_and_finish(topic, raw):
    beats = raw["beats"]
    groups = raw["groups"]
    if not (12 <= len(beats) <= 14):
        raise RuntimeError("beats must be 12-14, got %d" % len(beats))
    flat = [i for g in groups for i in g]
    if flat != list(range(len(beats))):
        raise RuntimeError("groups must cover every beat exactly once, in order")
    if len(raw.get("sticker_prompts", [])) != len(beats):
        raise RuntimeError("sticker_prompts must match beats one-to-one")
    total = sum(len(b["text"]) for b in beats)
    if not (200 <= total <= 320):
        raise RuntimeError("total characters %d outside 200-320" % total)
    out_beats = []
    for i, b in enumerate(beats):
        key = b["key"]
        out_beats.append({
            "text": b["text"], "key": key, "char": key[0],
            "color": list(PALETTE[i % len(PALETTE)]),
        })
    return {
        "topic": topic,
        "title": raw.get("title") or ("什么是%s？" % topic),
        "beats": out_beats,
        "groups": groups,
        "end_cards": raw.get("end_cards", [])[:2],
        "sticker_prompts": raw["sticker_prompts"],
        "total_chars": total,
        "estimated_seconds": round(total / 4.5 + 9, 1),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--topic", required=True)
    ap.add_argument("--model", default="glm-4-flash")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    raw = call_zhipu(args.topic, args.model)
    script = validate_and_finish(args.topic, raw)

    out = Path(args.out) if args.out else BASE / "scripts" / (
        re.sub(r"[^\w\-]+", "-", args.topic).strip("-") + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print("saved: %s" % out)
    print("beats: %d, chars: %d, estimated: %.1fs (incl. title + end cards)"
          % (len(script["beats"]), script["total_chars"],
             script["estimated_seconds"]))
    print("title: %s" % script["title"])
    for i, b in enumerate(script["beats"]):
        print("  %02d %s  [%s]" % (i, b["text"], b["key"]))


if __name__ == "__main__":
    main()
