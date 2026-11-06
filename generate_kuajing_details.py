#!/usr/bin/env python3
"""Generate 14 small detail stickers for the kuajing film (one per sentence,
second content element inside the sentence). Seedream 5.0 Pro, curl download
with retry. Cutting (rembg U2Net) is a separate step."""
import json, os, subprocess, sys
from pathlib import Path
import urllib.request

BASE = Path(__file__).resolve().parent
RAW = BASE / "cutouts" / "seedream_raw_kuajing_detail"
RAW.mkdir(parents=True, exist_ok=True)

import argparse
_ap = argparse.ArgumentParser()
_ap.add_argument("--template", default="coral-bay", help="style template under templates/ (default coral-bay)")
_template = _ap.parse_args().template
from template import load_template
STYLE = load_template(_template)["detail_style"]
PROMPTS = [
    "A small bottle of Japanese eye drops with a white cap",
    "A small cute alarm clock",
    "A small airplane flying",
    "A small cardboard box",
    "A round customs stamp seal",
    "A small cute snail",
    "A small clothing size tag",
    "A small paper tax bill with a large percent sign, no other text",
    "A small stack of gold coins",
    "A single light blue feather",
    "A small factory building with a chimney",
    "A small checklist clipboard with check marks",
    "A small warehouse building",
    "A small wooden abacus",
]

for i, subj in enumerate(PROMPTS):
    prompt = f"{subj}, {STYLE}"
    body = json.dumps({"model": "doubao-seedream-5-0-pro-260628", "prompt": prompt, "size": "1024x1024", "response_format": "url", "watermark": False}).encode()
    req = urllib.request.Request("https://ark.cn-beijing.volces.com/api/v3/images/generations", data=body, headers={"Content-Type": "application/json"}, method="POST")
    _key = os.environ.get("ARK_API_KEY", "")
    if not _key:
        print("ARK_API_KEY is not set. Get a key at the Volcano Ark console, then: export ARK_API_KEY=<key>", file=sys.stderr)
        sys.exit(2)
    req.add_header("Authorization", "Bearer " + _key)
    try:
        with urllib.request.build_opener().open(req, timeout=180) as r:
            data = json.load(r)
    except Exception as e:
        print(f"{i:02d} API FAILED: {e}", flush=True)
        continue
    url = data["data"][0]["url"]
    raw = RAW / f"raw_{i:02d}.jpg"
    subprocess.run(["curl", "-L", "--retry", "3", "--retry-delay", "2", "-o", str(raw), url], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"{i:02d} OK -> {raw} ({raw.stat().st_size} bytes)", flush=True)
print("done")
